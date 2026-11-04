"""SMM 面板定时任务：有未完成任务时同步状态/进度，无任务则不做任何事。"""
from celery import shared_task

from .models import SMMTask
from .services import map_panel_status, search_task_record


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
