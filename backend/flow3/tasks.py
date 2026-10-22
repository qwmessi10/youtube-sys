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
import threading
import time
from concurrent.futures import ThreadPoolExecutor

from celery import shared_task
from celery.exceptions import SoftTimeLimitExceeded
from django.conf import settings
from django.db import transaction
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


# 并行步骤会并发写 run_log（JSON）；加锁 + 每次从 DB 重读最新 run_log 再追加，避免互相覆盖。
_LOG_LOCK = threading.Lock()


def _log_step(run, step, status, detail=None, error="", elapsed=None):
    """往 run_log.steps 追加一步并落库，供前端实时查看。线程安全（并行装配下不丢步骤）。"""
    entry = {"step": step, "status": status, "at": timezone.now().isoformat()}
    if elapsed is not None:
        entry["elapsed_seconds"] = round(elapsed, 2)
    if error:
        entry["error"] = error
    if detail:
        entry.update(detail)
    with _LOG_LOCK:
        # 从 DB 重读最新 run_log（可能已被其他线程追加），再 append，只更新 run_log 列。
        fresh = Flow3Run.objects.only("run_log").get(pk=run.pk)
        log = fresh.run_log or {}
        steps = log.get("steps") or []
        steps.append(entry)
        log["steps"] = steps
        Flow3Run.objects.filter(pk=run.pk).update(run_log=log, updated_at=timezone.now())
        run.run_log = log  # 同步内存对象


def _resolve_hook_material(run):
    """
    解析本任务要用的 Hook 素材：
      - 用户在创建时已指定 run.hook_material → 用它（允许复用已使用的；批量模式由 views 预分配）。
      - 否则在 run.hook_group 分组内随机取一个「未使用 + 启用」素材，并原子标记为已使用（防并发撞车）。
      - 都没有 → 返回 None（走原「出 prompt + 等待人工上传」流程）。
    """
    if run.hook_material_id:
        return run.hook_material
    import random as _r
    with transaction.atomic():
        qs = Flow3Material.objects.select_for_update(skip_locked=True).filter(
            material_type=Flow3Material.TYPE_HOOK,
            tag=Flow3Material.TAG_UNUSED,
            enabled=True,
        )
        # 仅在任务指定的 hook 分组内取（兼容历史：未设分组则不限制）。
        if run.hook_group_id:
            qs = qs.filter(group_id=run.hook_group_id)
        candidates = list(qs)
        if not candidates:
            return None
        chosen = _r.Random(run.layout_seed).choice(candidates)
        chosen.tag = Flow3Material.TAG_USED
        chosen.save(update_fields=["tag", "updated_at"])
    return chosen


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
    if not run.started_at:
        run.started_at = timezone.now()
    run.save(update_fields=["error_message", "run_log", "status", "started_at", "updated_at"])

    # Step2a：优先走「从 hook 素材库取素材」路径。
    material = _resolve_hook_material(run)
    if material:
        # 直接引用素材文件作为 Hook 视频（不复制，省空间）。素材在 _resolve 内已标记已使用。
        run.hook_material = material
        run.hook_video.name = material.file.name
        run.save(update_fields=["hook_material", "hook_video", "updated_at"])
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
        run.finished_at = timezone.now()
        run.save(update_fields=["status", "error_message", "finished_at", "updated_at"])
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
        run.finished_at = timezone.now()
        run.save(update_fields=["status", "error_message", "finished_at", "updated_at"])
        return

    run.status = Flow3Run.STATUS_RUNNING
    run.error_message = ""
    # 重试/续跑若此前未记录开始时间，这里补上。
    if not run.started_at:
        run.started_at = timezone.now()
    run.save(update_fields=["status", "error_message", "started_at", "updated_at"])

    try:
        _run_assembly(run, run_id, task_token)
    except SoftTimeLimitExceeded:
        if _can_continue(run_id, task_token):
            run.status = Flow3Run.STATUS_FAILED
            run.error_message = "达到时间上限，任务未完成。"
            run.finished_at = timezone.now()
            run.save(update_fields=["status", "error_message", "finished_at", "updated_at"])
    except Exception as exc:
        if _can_continue(run_id, task_token):
            run.status = Flow3Run.STATUS_FAILED
            run.error_message = str(exc)
            run.finished_at = timezone.now()
            run.save(update_fields=["status", "error_message", "finished_at", "updated_at"])
        _log_step(run, "assembly", "failed", error=str(exc))
        raise


def _media_abs(rel_or_name):
    """把 FileField.name / 相对路径转成 MEDIA_ROOT 下绝对路径。"""
    return os.path.join(settings.MEDIA_ROOT, str(rel_or_name))


def _run_assembly(run, run_id, token):
    """Step4~7 主体。"""
    # ---- Step4：Agent 生成（并行提速）。独立步骤并发跑，依赖步骤放第二波。幂等跳过保留。----
    # 线程内只「生成 + 写内存属性/磁盘文件(save=False)」，不触发整行 save；主线程统一落库，避免并发写同一行。
    def _gen_narration():
        if (run.narration or {}).get("shots"):
            return ("narration_script", "skipped", {"reason": "已存在，跳过"})
        t = time.monotonic()
        data, log = generate_narration_script(run, SEGB_TARGET_SHOT_COUNT, SEGB_TARGET_SHOT_DURATION)
        run.narration = data
        return ("narration_script", "success", {"model": log.get("model"), "prompt": log.get("prompt"),
                "raw_output": log.get("raw_output"), "shots": data.get("shots"), "__elapsed": time.monotonic() - t})

    def _gen_blur():
        if run.blur_bg_file:
            return ("blur_bg", "skipped", {"reason": "已存在，跳过"})
        t = time.monotonic()
        p, _ = _generate_image_prompt(run, "blur_bg")
        f, ext = generate_image(p)
        run.blur_bg_file.save(f"{run.id}_blur.{ext}", f, save=False)
        return ("blur_bg", "success", {"image_prompt": p, "__elapsed": time.monotonic() - t})

    def _gen_tail():
        if run.tail_image_file:
            return ("tail_image", "skipped", {"reason": "已存在，跳过"})
        t = time.monotonic()
        p, _ = _generate_image_prompt(run, "tail_image")
        f, ext = generate_image(p)
        run.tail_image_file.save(f"{run.id}_tail.{ext}", f, save=False)
        return ("tail_image", "success", {"image_prompt": p, "__elapsed": time.monotonic() - t})

    def _gen_meta():
        if run.title:
            return ("metadata", "skipped", {"reason": "已存在，跳过"})
        t = time.monotonic()
        m, _ = generate_metadata(run)
        run.title, run.description, run.thumbnail_prompt = m["title"], m["description"], m["thumbnail_prompt"]
        return ("metadata", "success", {"title": m["title"], "__elapsed": time.monotonic() - t})

    # 第一波：narration / blur / tail / metadata 并发（互不依赖）。
    with ThreadPoolExecutor(max_workers=4) as ex:
        futs = {"narration": ex.submit(_gen_narration), "blur": ex.submit(_gen_blur),
                "tail": ex.submit(_gen_tail), "meta": ex.submit(_gen_meta)}
        res1 = {k: f.result() for k, f in futs.items()}  # 任一异常在此抛出 → 上层置 failed
    run.save(update_fields=["narration", "blur_bg_file", "tail_image_file",
                            "title", "description", "thumbnail_prompt", "updated_at"])
    for step, st, detail in res1.values():
        el = detail.pop("__elapsed", None)
        _log_step(run, step, st, detail=detail, elapsed=el)
    if not _can_continue(run_id, token):
        return
    narration = run.narration

    # 第二波：TTS（依赖 narration）+ 封面（依赖 metadata.thumbnail_prompt）并发。
    def _gen_tts():
        if run.narration_audio:
            return ("tts", "skipped", {"reason": "已存在，跳过"})
        t = time.monotonic()
        out_dir = os.path.join(settings.MEDIA_ROOT, "flow3", "narration")
        audio_list, log = generate_narration_audio(narration.get("shots") or [], run.language, out_dir, f"{run.id}")
        run.narration_audio = [
            {"index": a["index"], "file": os.path.relpath(a["file"], settings.MEDIA_ROOT).replace("\\", "/"),
             "provider": a["provider"]} for a in audio_list
        ]
        return ("tts", "success", {"segments": log.get("segments"), "audio_count": len(audio_list),
                "__elapsed": time.monotonic() - t})

    def _gen_thumb():
        if run.thumbnail_file:
            return ("thumbnail", "skipped", {"reason": "已存在，跳过"})
        if not run.thumbnail_prompt:
            return ("thumbnail", "skipped", {"reason": "无封面提示词"})
        t = time.monotonic()
        try:
            f, ext = generate_image(run.thumbnail_prompt)
            run.thumbnail_file.save(f"{run.id}_thumb.{ext}", f, save=False)
            return ("thumbnail", "success", {"__elapsed": time.monotonic() - t})
        except Exception as exc:
            # 封面失败不阻断出片。
            return ("thumbnail", "failed", {"error__": str(exc), "__elapsed": time.monotonic() - t})

    with ThreadPoolExecutor(max_workers=2) as ex:
        ft, fth = ex.submit(_gen_tts), ex.submit(_gen_thumb)
        r_tts, r_thumb = ft.result(), fth.result()
    run.save(update_fields=["narration_audio", "thumbnail_file", "updated_at"])
    for step, st, detail in (r_tts, r_thumb):
        el = detail.pop("__elapsed", None)
        err = detail.pop("error__", "")
        _log_step(run, step, st, detail=detail or None, error=err, elapsed=el)
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

    # 取素材：9:16 录屏。创建时指定 screen_material 优先；否则在启用的录屏里随机（layout_seed 可复现）。
    screen = run.screen_material if run.screen_material_id else None
    if screen is None or not screen.enabled:
        pool = list(Flow3Material.objects.filter(material_type=Flow3Material.TYPE_SCREEN, enabled=True))
        if not pool:
            raise RuntimeError("素材库未配置 9:16 录屏素材，无法合成 SegB。")
        screen = random.Random(run.layout_seed).choice(pool)
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
            promo_variant=(run.promo_seed or 0) % 5,
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
    run.finished_at = timezone.now()
    run.save(update_fields=["rendered_file", "status", "finished_at", "updated_at"])
    _log_step(run, "mix_dedup", "success", detail={"bgm": run.bgm_file or "(无)"},
              elapsed=time.monotonic() - started)
    run_log = run.run_log or {}
    run_log["finished_at"] = timezone.now().isoformat()
    run.run_log = run_log
    run.save(update_fields=["run_log", "updated_at"])
