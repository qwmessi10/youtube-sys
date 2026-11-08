"""SMM 面板定时任务：任务状态同步 + 轮询刷量调度。"""
import random

from celery import shared_task
from django.utils import timezone

from .models import SMMPollTask, SMMTask
from .services import (
    POLL_END_HOURS,
    map_panel_status,
    next_slot_after,
    search_task_record,
    send_task,
)


@shared_task
def sync_smm_task_statuses():
    """扫描「未完成」任务，按账号批量拉面板最新状态并回填。

    无未完成任务时直接返回（即「没有任务就不自动同步」）。
    """
    unfinished = list(
        SMMTask.objects.filter(status__in=[SMMTask.STATUS_PENDING, SMMTask.STATUS_RUNNING])
        .select_related("account")
    )
    if not unfinished:
        return 0

    # 按账号分组，每个账号只调一次 searchTaskRecord，减少请求。
    by_account = {}
    for task in unfinished:
        by_account.setdefault(task.account_id, []).append(task)

    updated = 0
    for account_id, tasks in by_account.items():
        account = tasks[0].account
        res = search_task_record(account.token, account.user_identifier, account.tg_user_id)
        if res.get("code") not in (0, None):
            continue
        records = (res.get("data") or {}).get("result") or []
        by_task_id = {r.get("taskId"): r for r in records}
        for task in tasks:
            r = by_task_id.get(task.panel_task_id)
            if not r:
                continue
            task.panel_status = r.get("status") or ""
            task.show_id = r.get("showId") or task.show_id
            task.cost = r.get("cost") or task.cost
            task.progress = {
                "total_users": r.get("totalUsers"),
                "pending_users": r.get("pendingUsers"),
                "complete_size": r.get("completeSize"),
                "success_rate": r.get("successRate"),
                "fail_rate": r.get("failRate"),
                "fail_num": r.get("failNum"),
            }
            task.status = map_panel_status(task.panel_status)
            task.save(update_fields=["panel_status", "show_id", "cost", "progress", "status", "updated_at"])
            updated += 1
    return updated


@shared_task
def sync_smm_poll_tasks():
    """轮询刷量调度：扫描运行中的轮询任务，到点就下一单（随机人数），跨天直到刷满。"""
    now = timezone.localtime(timezone.now())  # 北京时间
    running = SMMPollTask.objects.filter(status=SMMPollTask.STATUS_RUNNING).select_related("account")
    for pt in running:
        if pt.poll_done >= pt.poll_total:
            pt.status = SMMPollTask.STATUS_COMPLETED
            pt.save(update_fields=["status", "updated_at"])
            continue
        if pt.next_poll_at is None:
            pt.next_poll_at = next_slot_after(now, pt.window_start_hour, pt.window_end_hour)
            pt.save(update_fields=["next_poll_at", "updated_at"])
            continue
        if now < pt.next_poll_at:
            continue  # 还没到点

        # 到点：下一单（随机人数）
        count = random.randint(pt.batch_min, pt.batch_max)
        res = send_task(
            pt.account.token, pt.account.user_identifier, pt.account.tg_user_id,
            pt.youtube_link, pt.key_words, count,
            per_user=pt.per_user, comment_num=pt.comment_num,
            end_hours=POLL_END_HOURS, plant_form=pt.plant_form, task_type=pt.task_type,
        )
        if res.get("code") in (0, None):
            d = res.get("data") or {}
            SMMTask.objects.create(
                account=pt.account,
                poll_task=pt,
                panel_task_id=d.get("taskId") or "",
                show_id=d.get("showId") or "",
                youtube_link=pt.youtube_link,
                key_words=pt.key_words,
                total_user=count,
                per_user=pt.per_user,
                task_type=pt.task_type,
                plant_form=pt.plant_form,
                comment_num=pt.comment_num,
                end_time=d.get("endTime") or "",
                cost=count * float(pt.per_user),
                status=SMMTask.STATUS_PENDING,
            )
            pt.poll_done += 1
            pt.fail_count = 0
            pt.last_error = ""
        else:
            pt.fail_count += 1
            pt.last_error = str(res.get("msg") or res)
            if pt.fail_count >= 3:
                pt.status = SMMPollTask.STATUS_FAILED
                pt.save(update_fields=["status", "fail_count", "last_error", "updated_at"])
                continue

        # 推进到当前时间之后的下一个窗口内整点（跳过漏掉的时段，不做补刷）
        pt.next_poll_at = next_slot_after(now, pt.window_start_hour, pt.window_end_hour)
        if pt.poll_done >= pt.poll_total:
            pt.status = SMMPollTask.STATUS_COMPLETED
        pt.save()
    return len(running)
