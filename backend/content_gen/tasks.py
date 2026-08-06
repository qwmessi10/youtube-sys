import os

from celery import shared_task
from celery.exceptions import SoftTimeLimitExceeded
from django.conf import settings

from .models import ContentItem, ContentRun
from .services import generate_metadata, generate_storyboard, generate_thumbnail, merge_clips


def _can_continue(run_id, token):
    """任务是否还该继续（未被暂停/停止、token 未失效）。"""
    run = ContentRun.objects.only("status", "task_token").get(pk=run_id)
    return run.status == ContentRun.STATUS_RUNNING and str(run.task_token) == str(token)


def _generate_one_item(item, run):
    """
    单个关键词的 AI 生成：元数据 → 封面出图 → 分镜脚本。
    任一子步骤失败都记录到 item，但不同子步骤相互独立（封面失败不影响分镜）。
    """
    item.status = ContentItem.STATUS_GENERATING
    item.error_message = ""
    item.save(update_fields=["status", "error_message", "updated_at"])

    errors = []

    # 1) 元数据（标题/描述/封面提示词）
    try:
        meta, _ = generate_metadata(item.keyword)
        item.title = meta["title"]
        item.description = meta["description"]
        item.thumbnail_prompt = meta["thumbnail_prompt"]
    except Exception as exc:
        errors.append(f"元数据生成失败：{exc}")

    # 2) 封面出图（依赖上一步的封面提示词）
    if item.thumbnail_prompt:
        try:
            content_file, ext = generate_thumbnail(item.thumbnail_prompt)
            item.thumbnail_file.save(f"{run.id}_{item.id}.{ext}", content_file, save=False)
        except Exception as exc:
            errors.append(f"封面出图失败：{exc}")

    # 3) 分镜脚本（段数可变，默认 8+8）
    try:
        storyboard, _ = generate_storyboard(item.keyword, run.shot_count, run.shot_duration)
        item.storyboard = storyboard
    except Exception as exc:
        errors.append(f"分镜脚本生成失败：{exc}")

    if errors:
        item.error_message = "；".join(errors)
        # 只要有任一产出就算「已生成」，全失败才标失败。
        item.status = ContentItem.STATUS_FAILED if len(errors) == 3 else ContentItem.STATUS_GENERATED
    else:
        item.status = ContentItem.STATUS_GENERATED
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
            # 已生成过的（重启场景）跳过，避免重复消耗 AI 额度。
            if item.status in [ContentItem.STATUS_GENERATED, ContentItem.STATUS_MERGED]:
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
