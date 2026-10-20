"""
流程3 Celery 任务与状态机（与 content_gen 隔离）。

两阶段：
  process_flow3_run  : Step1 校验 → Step2 Hook Agent 出 prompt → 进入 awaiting_hook 暂停。
  continue_flow3_run : 人工上传 Hook mp4 并点「继续」后触发，执行 Step4~7。

全程把每步输入/输出/耗时/状态写入 run.run_log（供前端日志抽屉）。
"""
import math
import os
import random
import time

from celery import shared_task
from celery.exceptions import SoftTimeLimitExceeded
from django.conf import settings
from django.utils import timezone

from .models import Flow3Material, Flow3Run
from .services import (
    concat_segments,
    generate_hook_prompt,
    generate_image,
    generate_metadata,
    generate_narration_audio,
    generate_narration_script,
    mix_bgm_and_dedup,
    probe_duration,
    render_segment_b,
    render_segment_c,
    _generate_image_prompt,
)

SEG_A_SECONDS = 7  # SegA Hook 固定 7 秒
# SegB 旁白分段：固定 1 段，时长按 TTS 实际音频决定（这里仅给 AI 生成文案的目标段长）。
SEGB_TARGET_SHOT_COUNT = 3
SEGB_TARGET_SHOT_DURATION = 7


def _can_continue(run_id, token):
    """任务是否还该继续（未被暂停/停止、token 未失效）。"""
    run = Flow3Run.objects.only("status", "task_token").get(pk=run_id)
    return str(run.task_token) == str(token) and run.status not in (
        Flow3Run.STATUS_PAUSED, Flow3Run.STATUS_STOPPED,
    )


def _log_step(run, step, status, detail=None, error="", elapsed=None):
    """往 run_log.steps 追加一步并落库，供前端实时查看。"""
    log = run.run_log or {}
    steps = log.get("steps") or []
    entry = {"step": step, "status": status, "at": timezone.now().isoformat()}
    if elapsed is not None:
        entry["elapsed_seconds"] = round(elapsed, 2)
    if error:
        entry["error"] = error
    if detail:
        entry.update(detail)
    steps.append(entry)
    log["steps"] = steps
    run.run_log = log
    run.save(update_fields=["run_log", "updated_at"])


def _resolve_hook_material(run):
    """
    解析本任务要用的 Hook 素材：
      - 用户在创建时已指定 run.hook_material → 用它（允许复用已使用的）。
      - 否则从 hook 库随机取一个「未使用 + 启用」的素材。
      - 都没有 → 返回 None（走原「出 prompt + 等待人工上传」流程）。
    """
    if run.hook_material_id:
        return run.hook_material
    candidates = list(Flow3Material.objects.filter(
        material_type=Flow3Material.TYPE_HOOK,
        tag=Flow3Material.TAG_UNUSED,
        enabled=True,
    ))
    if not candidates:
        return None
    import random as _r
    return _r.Random(run.layout_seed).choice(candidates)


@shared_task(bind=True, soft_time_limit=600, time_limit=900)
def process_flow3_run(self, run_id, task_token):
    """
    Step1~3：校验 → 解析 Hook 素材。
      - 若选用/随机到 hook 库素材：直接用其文件作为 Hook 视频，标记素材「已使用」，
        跳过「出 prompt + 等待上传」，直接进入 Step4~7 出片。
      - 否则：Hook Agent 出 prompt → 进入 awaiting_hook 暂停等人工上传。
    """
    run = Flow3Run.objects.get(pk=run_id)
    if not _can_continue(run_id, task_token):
        return
    run.error_message = ""
    run.run_log = {"keyword": run.keyword, "started_at": timezone.now().isoformat(), "steps": []}
    run.status = Flow3Run.STATUS_RUNNING
    run.save(update_fields=["error_message", "run_log", "status", "updated_at"])

    # Step2a：优先走「从 hook 素材库取素材」路径。
    material = _resolve_hook_material(run)
    if material:
        # 直接引用素材文件作为 Hook 视频（不复制，省空间）；标记素材为已使用。
        run.hook_material = material
        run.hook_video.name = material.file.name
        run.save(update_fields=["hook_material", "hook_video", "updated_at"])
        if material.tag != Flow3Material.TAG_USED:
            material.tag = Flow3Material.TAG_USED
            material.save(update_fields=["tag", "updated_at"])
        _log_step(run, "hook_material", "success", detail={
            "message": "已从 Hook 素材库选用素材，跳过人工上传。",
            "material_id": material.id, "material_name": material.name or material.file.name,
        })
        # 直接进入 Step4~7（复用 continue 的组装逻辑）。
        continue_flow3_run.delay(run_id, task_token)
        return

    # Step2b：素材库无可用 hook → 走原 Hook Agent 出 prompt 流程。
    _log_step(run, "hook_prompt", "running")
    started = time.monotonic()
    try:
        video_prompt, log = generate_hook_prompt(run)
        run.hook_prompt = video_prompt
        run.save(update_fields=["hook_prompt", "updated_at"])
        _log_step(run, "hook_prompt", "success", detail={
            "model": log.get("model"), "prompt": log.get("prompt"),
            "raw_output": log.get("raw_output"), "video_prompt": video_prompt,
        }, elapsed=time.monotonic() - started)
    except Exception as exc:
        run.status = Flow3Run.STATUS_FAILED
        run.error_message = f"Hook Prompt 生成失败：{exc}"
        run.save(update_fields=["status", "error_message", "updated_at"])
        _log_step(run, "hook_prompt", "failed", error=str(exc), elapsed=time.monotonic() - started)
        return

    if not _can_continue(run_id, task_token):
        return
    # Step3：进入等待 Hook 上传的暂停态。
    run.status = Flow3Run.STATUS_AWAITING_HOOK
    run.save(update_fields=["status", "updated_at"])
    _log_step(run, "await_hook", "waiting", detail={"message": "已生成 Hook Prompt，等待人工上传 Hook 视频后继续。"})


@shared_task(bind=True, soft_time_limit=3600, time_limit=3900)
def continue_flow3_run(self, run_id, task_token):
    """Step4~7：Hook mp4 已上传后执行 并行Agent → 组装 → 混音防封 → 完成。"""
    run = Flow3Run.objects.get(pk=run_id)
    if not _can_continue(run_id, task_token):
        return
    if not run.hook_video:
        run.status = Flow3Run.STATUS_FAILED
        run.error_message = "未上传 Hook 视频，无法继续。"
        run.save(update_fields=["status", "error_message", "updated_at"])
        return

    run.status = Flow3Run.STATUS_RUNNING
    run.error_message = ""
    run.save(update_fields=["status", "error_message", "updated_at"])

    try:
        _run_assembly(run, run_id, task_token)
    except SoftTimeLimitExceeded:
        if _can_continue(run_id, task_token):
            run.status = Flow3Run.STATUS_FAILED
            run.error_message = "达到时间上限，任务未完成。"
            run.save(update_fields=["status", "error_message", "updated_at"])
    except Exception as exc:
        if _can_continue(run_id, task_token):
            run.status = Flow3Run.STATUS_FAILED
            run.error_message = str(exc)
            run.save(update_fields=["status", "error_message", "updated_at"])
        _log_step(run, "assembly", "failed", error=str(exc))
        raise


def _media_abs(rel_or_name):
    """把 FileField.name / 相对路径转成 MEDIA_ROOT 下绝对路径。"""
    return os.path.join(settings.MEDIA_ROOT, str(rel_or_name))


def _run_assembly(run, run_id, token):
    """Step4~7 主体。"""
    # ---- Step4：Agent 生成。每步带幂等跳过：对应产出已存在则跳过，避免重启/续跑重复消耗 AI 额度。----
    # 4a 旁白脚本
    if (run.narration or {}).get("shots"):
        narration = run.narration
        _log_step(run, "narration_script", "skipped", detail={"reason": "已存在，跳过"})
    else:
        _log_step(run, "narration_script", "running")
        started = time.monotonic()
        narration, nlog = generate_narration_script(run, SEGB_TARGET_SHOT_COUNT, SEGB_TARGET_SHOT_DURATION)
        run.narration = narration
        run.save(update_fields=["narration", "updated_at"])
        _log_step(run, "narration_script", "success", detail={
            "model": nlog.get("model"), "prompt": nlog.get("prompt"),
            "raw_output": nlog.get("raw_output"), "shots": narration.get("shots"),
        }, elapsed=time.monotonic() - started)
    if not _can_continue(run_id, token):
        return

    # 4b TTS 合成（印式英语）
    if run.narration_audio:
        _log_step(run, "tts", "skipped", detail={"reason": "已存在，跳过"})
    else:
        _log_step(run, "tts", "running")
        started = time.monotonic()
        out_dir = os.path.join(settings.MEDIA_ROOT, "flow3", "narration")
        audio_list, tts_log = generate_narration_audio(
            narration.get("shots") or [], run.language, out_dir, f"{run.id}"
        )
        run.narration_audio = [
            {"index": a["index"], "file": os.path.relpath(a["file"], settings.MEDIA_ROOT).replace("\\", "/"),
             "provider": a["provider"]}
            for a in audio_list
        ]
        run.save(update_fields=["narration_audio", "updated_at"])
        _log_step(run, "tts", "success", detail={"segments": tts_log.get("segments"), "audio_count": len(audio_list)},
                  elapsed=time.monotonic() - started)
    if not _can_continue(run_id, token):
        return

    # 4c 模糊底图
    if run.blur_bg_file:
        _log_step(run, "blur_bg", "skipped", detail={"reason": "已存在，跳过"})
    else:
        _log_step(run, "blur_bg", "running")
        started = time.monotonic()
        bg_prompt, bg_log = _generate_image_prompt(run, "blur_bg")
        bg_file, bg_ext = generate_image(bg_prompt)
        run.blur_bg_file.save(f"{run.id}_blur.{bg_ext}", bg_file, save=True)
        _log_step(run, "blur_bg", "success", detail={"image_prompt": bg_prompt}, elapsed=time.monotonic() - started)
    if not _can_continue(run_id, token):
        return

    # 4d 尾图
    if run.tail_image_file:
        _log_step(run, "tail_image", "skipped", detail={"reason": "已存在，跳过"})
    else:
        _log_step(run, "tail_image", "running")
        started = time.monotonic()
        tail_prompt, tail_log = _generate_image_prompt(run, "tail_image")
        tail_file, tail_ext = generate_image(tail_prompt)
        run.tail_image_file.save(f"{run.id}_tail.{tail_ext}", tail_file, save=True)
        _log_step(run, "tail_image", "success", detail={"image_prompt": tail_prompt}, elapsed=time.monotonic() - started)
    if not _can_continue(run_id, token):
        return

    # 4e 元数据
    if run.title:
        _log_step(run, "metadata", "skipped", detail={"reason": "已存在，跳过"})
    else:
        _log_step(run, "metadata", "running")
        started = time.monotonic()
        meta, mlog = generate_metadata(run)
        run.title = meta["title"]
        run.description = meta["description"]
        run.thumbnail_prompt = meta["thumbnail_prompt"]
        run.save(update_fields=["title", "description", "thumbnail_prompt", "updated_at"])
        _log_step(run, "metadata", "success", detail={"title": meta["title"]}, elapsed=time.monotonic() - started)
    if not _can_continue(run_id, token):
        return

    # 4f 封面图（按元数据的 thumbnail_prompt 生图，供打包交付）
    if run.thumbnail_file:
        _log_step(run, "thumbnail", "skipped", detail={"reason": "已存在，跳过"})
    elif run.thumbnail_prompt:
        _log_step(run, "thumbnail", "running", detail={"thumbnail_prompt": run.thumbnail_prompt})
        started = time.monotonic()
        try:
            tn_file, tn_ext = generate_image(run.thumbnail_prompt)
            run.thumbnail_file.save(f"{run.id}_thumb.{tn_ext}", tn_file, save=True)
            _log_step(run, "thumbnail", "success", elapsed=time.monotonic() - started)
        except Exception as exc:
            # 封面失败不阻断出片（视频仍可交付，封面可后续重生成）。
            _log_step(run, "thumbnail", "failed", error=str(exc), elapsed=time.monotonic() - started)
    else:
        _log_step(run, "thumbnail", "skipped", detail={"reason": "无封面提示词"})
    if not _can_continue(run_id, token):
        return

    # ---- Step5：图层与媒体组装 ----
    # 时长计算：SegA=7s；SegB=TTS 实际总时长；SegC=总时长-7-SegB。
    segb_duration = 0.0
    for a in run.narration_audio or []:
        d = probe_duration(_media_abs(a["file"]))
        if d:
            segb_duration += d
    if segb_duration <= 0:
        segb_duration = SEGB_TARGET_SHOT_COUNT * SEGB_TARGET_SHOT_DURATION  # 兜底
    segc_duration = run.total_duration - SEG_A_SECONDS - segb_duration
    if segc_duration <= 0:
        raise RuntimeError(
            f"总时长（{run.total_duration}s）不足以容纳 Hook 7s + 旁白 {segb_duration:.1f}s，"
            f"请调大总时长或缩短旁白。"
        )
    _log_step(run, "duration_plan", "success", detail={
        "total": run.total_duration, "seg_a": SEG_A_SECONDS,
        "seg_b": round(segb_duration, 2), "seg_c": round(segc_duration, 2),
    })

    # 取素材：9:16 录屏（库内 enabled 的第一个）。
    screen = Flow3Material.objects.filter(
        material_type=Flow3Material.TYPE_SCREEN, enabled=True
    ).order_by("-created_at").first()
    if not screen:
        raise RuntimeError("素材库未配置 9:16 录屏素材，无法合成 SegB。")
    screen_abs = _media_abs(screen.file.name)
    screen_dur = screen.duration or probe_duration(screen_abs) or 0

    # SegB：Remotion 画中画（左右由 layout_seed 决定）。渲染最慢，已有则跳过。
    segb_abs = _media_abs(f"flow3/segb/{run.id}_segb.mp4")
    if run.segb_file and os.path.exists(segb_abs):
        _log_step(run, "render_segb", "skipped", detail={"reason": "已存在，跳过"})
    else:
        _log_step(run, "render_segb", "running")
        started = time.monotonic()
        os.makedirs(os.path.dirname(segb_abs), exist_ok=True)
        # 音频用 render 容器可见的绝对路径
        audio_abs = [{"index": a["index"], "file": _media_abs(a["file"]), "provider": a["provider"]}
                     for a in run.narration_audio or []]
        render_segment_b(
            promo_code=run.promo_code, blur_bg_abs=_media_abs(run.blur_bg_file.name),
            screen_abs=screen_abs, screen_duration=screen_dur,
            shots=narration.get("shots") or [], narration_audio=audio_abs,
            segb_duration=segb_duration, layout_seed=run.layout_seed,
            output_abs_path=segb_abs,
        )
        run.segb_file.name = f"flow3/segb/{run.id}_segb.mp4"
        run.save(update_fields=["segb_file", "updated_at"])
        _log_step(run, "render_segb", "success", detail={"duration": round(segb_duration, 2),
                  "screen_on_right": run.layout_seed % 2 == 0}, elapsed=time.monotonic() - started)
    if not _can_continue(run_id, token):
        return

    # SegC：ffmpeg zoompan 尾图微动。已有则跳过。
    segc_abs = _media_abs(f"flow3/segc/{run.id}_segc.mp4")
    if run.segc_file and os.path.exists(segc_abs):
        _log_step(run, "render_segc", "skipped", detail={"reason": "已存在，跳过"})
    else:
        _log_step(run, "render_segc", "running")
        started = time.monotonic()
        render_segment_c(_media_abs(run.tail_image_file.name), segc_duration, segc_abs)
        run.segc_file.name = f"flow3/segc/{run.id}_segc.mp4"
        run.save(update_fields=["segc_file", "updated_at"])
        _log_step(run, "render_segc", "success", detail={"duration": round(segc_duration, 2)},
                  elapsed=time.monotonic() - started)
    if not _can_continue(run_id, token):
        return

    # 三段 concat：SegA(Hook mp4) + SegB + SegC。
    _log_step(run, "concat", "running")
    started = time.monotonic()
    concat_abs = _media_abs(f"flow3/rendered/{run.id}_concat.mp4")
    concat_segments(
        [_media_abs(run.hook_video.name), segb_abs, segc_abs],
        concat_abs,
    )
    _log_step(run, "concat", "success", elapsed=time.monotonic() - started)
    if not _can_continue(run_id, token):
        return

    # ---- Step6：BGM 混音 + 防封去重 ----
    _log_step(run, "mix_dedup", "running")
    started = time.monotonic()
    bgm_abs = ""
    bgms = list(Flow3Material.objects.filter(material_type=Flow3Material.TYPE_BGM, enabled=True))
    if bgms:
        rnd = random.Random(run.bgm_seed)
        chosen = rnd.choice(bgms)
        bgm_abs = _media_abs(chosen.file.name)
        run.bgm_file = chosen.file.name
        run.save(update_fields=["bgm_file", "updated_at"])
    final_abs = _media_abs(f"flow3/rendered/{run.id}_final.mp4")
    mix_bgm_and_dedup(concat_abs, bgm_abs, final_abs)
    run.rendered_file.name = f"flow3/rendered/{run.id}_final.mp4"
    run.status = Flow3Run.STATUS_COMPLETED
    run.save(update_fields=["rendered_file", "status", "updated_at"])
    _log_step(run, "mix_dedup", "success", detail={"bgm": run.bgm_file or "(无)"},
              elapsed=time.monotonic() - started)
    run_log = run.run_log or {}
    run_log["finished_at"] = timezone.now().isoformat()
    run.run_log = run_log
    run.save(update_fields=["run_log", "updated_at"])
