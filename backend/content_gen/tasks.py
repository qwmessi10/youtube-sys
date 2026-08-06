import os
import time

from celery import shared_task
from celery.exceptions import SoftTimeLimitExceeded
from django.conf import settings
from django.utils import timezone

from keywords.services import get_setting

from .models import ContentItem, ContentRun
from .services import (
    generate_metadata,
    generate_narration_audio,
    generate_storyboard,
    generate_thumbnail,
    merge_clips,
    render_video,
)


def _can_continue(run_id, token):
    """任务是否还该继续（未被暂停/停止、token 未失效）。"""
    run = ContentRun.objects.only("status", "task_token").get(pk=run_id)
    return run.status == ContentRun.STATUS_RUNNING and str(run.task_token) == str(token)


def _generate_one_item(item, run):
    """
    单个关键词的 AI 生成：元数据 → 封面出图 → 分镜脚本。
    任一子步骤失败都记录到 item，但不同子步骤相互独立（封面失败不影响分镜）。
    每一步的输入提示词、原始输出、解析结果、耗时都写进 gen_log，供前端日志抽屉展示。
    """
    item.status = ContentItem.STATUS_GENERATING
    item.error_message = ""
    # 重新生成时清空旧日志，steps 按执行顺序记录每一步的状态与详情。
    log = {"keyword": item.keyword, "started_at": timezone.now().isoformat(), "steps": []}
    item.gen_log = log
    item.save(update_fields=["status", "error_message", "gen_log", "updated_at"])

    errors = []

    def record(step, status, detail=None, error="", elapsed=None):
        """往 gen_log.steps 追加一条步骤记录并立即落库，让前端能实时看到进度。"""
        entry = {"step": step, "status": status, "at": timezone.now().isoformat()}
        if elapsed is not None:
            entry["elapsed_seconds"] = round(elapsed, 2)
        if error:
            entry["error"] = error
        if detail:
            entry.update(detail)
        log["steps"].append(entry)
        item.gen_log = log
        item.save(update_fields=["gen_log", "updated_at"])

    # 1) 元数据（标题/描述/封面提示词）
    record("metadata", "running")
    started = time.monotonic()
    try:
        meta, meta_log = generate_metadata(item.keyword)
        item.title = meta["title"]
        item.description = meta["description"]
        item.thumbnail_prompt = meta["thumbnail_prompt"]
        record("metadata", "success", detail={
            "model": meta_log.get("model"),
            "prompt": meta_log.get("prompt"),
            "raw_output": meta_log.get("raw_output"),
            "parsed": meta_log.get("parsed"),
            "title": meta["title"],
            "description": meta["description"],
            "thumbnail_prompt": meta["thumbnail_prompt"],
        }, elapsed=time.monotonic() - started)
    except Exception as exc:
        errors.append(f"元数据生成失败：{exc}")
        record("metadata", "failed", error=str(exc), elapsed=time.monotonic() - started)

    # 2) 封面出图（依赖上一步的封面提示词）
    if item.thumbnail_prompt:
        record("thumbnail", "running", detail={"thumbnail_prompt": item.thumbnail_prompt})
        started = time.monotonic()
        try:
            content_file, ext = generate_thumbnail(item.thumbnail_prompt)
            item.thumbnail_file.save(f"{run.id}_{item.id}.{ext}", content_file, save=False)
            record("thumbnail", "success", detail={
                "thumbnail_prompt": item.thumbnail_prompt,
                "model": get_setting("GEMINI_IMAGE_MODEL", "gemini-3.1-flash-image"),
            }, elapsed=time.monotonic() - started)
        except Exception as exc:
            errors.append(f"封面出图失败：{exc}")
            record("thumbnail", "failed", detail={"thumbnail_prompt": item.thumbnail_prompt},
                   error=str(exc), elapsed=time.monotonic() - started)
    else:
        record("thumbnail", "skipped", error="没有封面提示词，跳过出图")

    # 3) 分镜脚本（段数可变，默认 8+8）。流程一额外产出每段旁白文案。
    is_flow1 = run.flow == ContentRun.FLOW_AUTO
    record("storyboard", "running")
    started = time.monotonic()
    try:
        storyboard, sb_log = generate_storyboard(
            item.keyword, run.shot_count, run.shot_duration, with_narration=is_flow1
        )
        item.storyboard = storyboard
        record("storyboard", "success", detail={
            "model": sb_log.get("model"),
            "prompt": sb_log.get("prompt"),
            "raw_output": sb_log.get("raw_output"),
            "parsed": sb_log.get("parsed"),
            "shots": storyboard.get("shots"),
        }, elapsed=time.monotonic() - started)
    except Exception as exc:
        errors.append(f"分镜脚本生成失败：{exc}")
        record("storyboard", "failed", error=str(exc), elapsed=time.monotonic() - started)

    # 流程一到此完成「内容生成」阶段（元数据/封面/分镜+旁白文案）。
    # 若三步全失败则直接失败；否则继续 TTS + Remotion 渲染。
    if is_flow1:
        _finalize_flow1_item(item, run, log, errors, record)
        return

    log["finished_at"] = timezone.now().isoformat()
    if errors:
        item.error_message = "；".join(errors)
        # 只要有任一产出就算「已生成」，全失败才标失败。
        item.status = ContentItem.STATUS_FAILED if len(errors) == 3 else ContentItem.STATUS_GENERATED
    else:
        item.status = ContentItem.STATUS_GENERATED
    item.gen_log = log
    item.save()


def _finalize_flow1_item(item, run, log, errors, record):
    """
    流程一后半段：TTS 旁白音频 → Remotion 渲染成品。
    在 _generate_one_item 内容生成三步之后调用。
    - 分镜有产出才做 TTS + 渲染；分镜失败则无法渲染，直接失败收尾。
    - TTS 单段失败会自动降级/跳过（该段无声），不阻断渲染。
    - 渲染成功 → STATUS_RENDERED；渲染失败 → STATUS_FAILED（但保留已生成内容）。
    """
    shots = (item.storyboard or {}).get("shots") or []
    if not shots:
        log["finished_at"] = timezone.now().isoformat()
        item.error_message = "；".join(errors) or "分镜脚本为空，无法渲染视频"
        item.status = ContentItem.STATUS_FAILED
        item.gen_log = log
        item.save()
        return

    # 4) TTS 旁白音频
    record("narration", "running", detail={"provider": run.tts_provider})
    started = time.monotonic()
    narration_audio = []
    try:
        out_dir = os.path.join(settings.MEDIA_ROOT, "content", "narration")
        prefix = f"{run.id}_{item.id}"
        narration_audio, tts_log = generate_narration_audio(
            shots, run.language, run.tts_provider, out_dir, prefix
        )
        # 存相对 media 的路径，前端可拼 /media 访问；渲染时再还原绝对路径。
        item.narration_audio = [
            {"index": a["index"],
             "file": os.path.relpath(a["file"], settings.MEDIA_ROOT).replace("\\", "/"),
             "provider": a["provider"]}
            for a in narration_audio
        ]
        item.save(update_fields=["narration_audio", "updated_at"])
        record("narration", "success", detail={
            "provider": run.tts_provider,
            "segments": tts_log.get("segments"),
            "audio_count": len(narration_audio),
        }, elapsed=time.monotonic() - started)
    except Exception as exc:
        errors.append(f"旁白合成失败：{exc}")
        record("narration", "failed", error=str(exc), elapsed=time.monotonic() - started)

    # 5) Remotion 渲染成品
    record("render", "running")
    started = time.monotonic()
    item.status = ContentItem.STATUS_RENDERING
    item.save(update_fields=["status", "updated_at"])
    try:
        rel_dir = os.path.join("content", "rendered")
        os.makedirs(os.path.join(settings.MEDIA_ROOT, rel_dir), exist_ok=True)
        rel_path = os.path.join(rel_dir, f"{run.id}_{item.id}.mp4")
        out_abs = os.path.join(settings.MEDIA_ROOT, rel_path)
        cover_abs = (
            os.path.join(settings.MEDIA_ROOT, item.thumbnail_file.name)
            if item.thumbnail_file else ""
        )
        # 音频用 render 容器可见的绝对路径（共享卷路径一致）
        audio_abs = [
            {"index": a["index"], "file": os.path.join(settings.MEDIA_ROOT, a["file"]),
             "provider": a["provider"]}
            for a in item.narration_audio
        ]
        render_result = render_video(
            title=item.title, keyword=item.keyword, promo_code=run.promo_code,
            cover_abs_path=cover_abs, shots=shots, narration_audio=audio_abs,
            output_abs_path=out_abs,
        )
        item.rendered_file.name = rel_path.replace("\\", "/")
        item.status = ContentItem.STATUS_RENDERED
        record("render", "success", detail={
            "output": rel_path.replace("\\", "/"),
            "duration_in_frames": render_result.get("durationInFrames"),
        }, elapsed=time.monotonic() - started)
    except Exception as exc:
        errors.append(f"视频渲染失败：{exc}")
        item.status = ContentItem.STATUS_FAILED
        record("render", "failed", error=str(exc), elapsed=time.monotonic() - started)

    log["finished_at"] = timezone.now().isoformat()
    if errors:
        item.error_message = "；".join(errors)
    item.gen_log = log
    item.save()


# 内容生成含多次 AI 调用 + 出图，可能较慢。放宽超时（软 1h、硬 1h5m）。
@shared_task(bind=True, soft_time_limit=3600, time_limit=3900)
def process_content_run(self, run_id, task_token):
    """
    批次内容生成：逐个关键词生成元数据 + 封面 + 分镜脚本。
    生成完成后 item 进入「待上传视频」状态，等待人工上传分镜视频再触发合并。
    """
    run = ContentRun.objects.get(pk=run_id)
    if not _can_continue(run_id, task_token):
        return
    run.error_message = ""
    run.save(update_fields=["error_message", "updated_at"])
    try:
        items = list(run.items.all())
        for item in items:
            if not _can_continue(run_id, task_token):
                return
            # 已完成的（重启场景）跳过，避免重复消耗 AI 额度 / 重复渲染。
            # 流程二：已生成/已合并；流程一：已渲染成品。
            if item.status in [
                ContentItem.STATUS_GENERATED, ContentItem.STATUS_MERGED,
                ContentItem.STATUS_RENDERED,
            ]:
                continue
            try:
                _generate_one_item(item, run)
            except Exception as exc:  # 单个词失败不中断整批
                item.status = ContentItem.STATUS_FAILED
                item.error_message = str(exc)
                item.save()
        if _can_continue(run_id, task_token):
            run.status = ContentRun.STATUS_COMPLETED
            run.save(update_fields=["status", "updated_at"])
    except SoftTimeLimitExceeded:
        if _can_continue(run_id, task_token):
            run.status = ContentRun.STATUS_COMPLETED
            run.error_message = "达到时间上限，已保存此前生成的内容后结束"
            run.save(update_fields=["status", "error_message", "updated_at"])
    except Exception as exc:
        if _can_continue(run_id, task_token):
            run.status = ContentRun.STATUS_FAILED
            run.error_message = str(exc)
            run.save(update_fields=["status", "error_message", "updated_at"])
        raise


@shared_task(bind=True, soft_time_limit=600, time_limit=900)
def regenerate_content_item(self, item_id):
    """重新生成单条记录的 AI 内容（元数据/封面/分镜），用于单条重试。"""
    item = ContentItem.objects.select_related("run").get(pk=item_id)
    try:
        _generate_one_item(item, item.run)
    except Exception as exc:
        item.status = ContentItem.STATUS_FAILED
        item.error_message = str(exc)
        item.save(update_fields=["status", "error_message", "updated_at"])
        raise


@shared_task(bind=True, soft_time_limit=1200, time_limit=1500)
def merge_content_item(self, item_id):
    """把某条记录已上传的分镜视频按顺序合并为成品。由上传完成后前端触发。"""
    item = ContentItem.objects.get(pk=item_id)
    clips = sorted(item.clip_files or [], key=lambda c: c.get("index", 0))
    if not clips:
        item.status = ContentItem.STATUS_FAILED
        item.error_message = "没有已上传的分镜视频，无法合并"
        item.save(update_fields=["status", "error_message", "updated_at"])
        return

    item.status = ContentItem.STATUS_MERGING
    item.error_message = ""
    item.save(update_fields=["status", "error_message", "updated_at"])
    try:
        clip_paths = [os.path.join(settings.MEDIA_ROOT, c["file"]) for c in clips]
        rel_dir = os.path.join("content", "merged")
        os.makedirs(os.path.join(settings.MEDIA_ROOT, rel_dir), exist_ok=True)
        rel_path = os.path.join(rel_dir, f"{item.run_id}_{item.id}.mp4")
        abs_path = os.path.join(settings.MEDIA_ROOT, rel_path)
        merge_clips(clip_paths, abs_path)
        # 用相对 media 的路径记录，前端拼 /media/ 即可访问
        item.merged_file.name = rel_path.replace("\\", "/")
        item.status = ContentItem.STATUS_MERGED
        item.save(update_fields=["merged_file", "status", "updated_at"])
    except Exception as exc:
        item.status = ContentItem.STATUS_FAILED
        item.error_message = f"合并失败：{exc}"
        item.save(update_fields=["status", "error_message", "updated_at"])
        raise
