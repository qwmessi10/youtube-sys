from uuid import UUID

from celery import shared_task
from .models import KeywordResult, KeywordRun
from .services import calculate_score, enrich_videos, search_youtube, suggest_keywords


def _can_continue(run_id, token):
    run = KeywordRun.objects.only("status", "task_token").get(pk=run_id)
    return run.status == KeywordRun.STATUS_RUNNING and str(run.task_token) == str(token)


@shared_task(bind=True, autoretry_for=(Exception,), retry_backoff=True, retry_kwargs={"max_retries": 2})
def process_keyword_run(self, run_id, task_token):
    run = KeywordRun.objects.get(pk=run_id)
    if not _can_continue(run_id, task_token):
        return
    run.error_message = ""
    run.save(update_fields=["error_message", "updated_at"])
    try:
        suggestions = suggest_keywords(run.root_keyword, run.country, run.language)
        # 把输入词本身也纳入评分：即使 Suggest 拓展不出长尾词（如输入词已经很长很具体），
        # 至少也能评估输入词本身。放在最前面并去重，再按 max_keywords 截断（输入词计入总数上限）。
        keywords_to_process = list(dict.fromkeys([run.root_keyword, *suggestions]))[:run.max_keywords]
        for keyword in keywords_to_process:
            if not _can_continue(run_id, task_token):
                return
            result, _ = KeywordResult.objects.get_or_create(run=run, keyword=keyword)
            if result.status in [KeywordResult.STATUS_RULE_SCORED, KeywordResult.STATUS_SERP_ERROR]:
                continue
            try:
                serp_videos = search_youtube(keyword, run.country, run.language)
                videos, enrich_ok = enrich_videos(serp_videos)
                if not videos:
                    # SerpApi 没返回任何视频，直接记为无结果。
                    result.status = KeywordResult.STATUS_RULE_SCORED
                    result.serpapi_status = "no_result"
                    result.top5_video_data = []
                    result.score_breakdown = {}
                    result.rule_score = None
                    result.elimination_stage = "serpapi_no_result"
                    result.elimination_reason = "SerpApi 未返回有效视频结果"
                    result.save()
                    continue
                incomplete = [v for v in videos if not v.get("data_complete")]
                if not enrich_ok or incomplete:
                    # YouTube V3 未补齐关键数据（订阅/播放/发布时间），不给最终分，交人工复核。
                    result.status = KeywordResult.STATUS_NEEDS_REVIEW
                    result.serpapi_status = "completed"
                    result.top5_video_data = videos
                    result.score_breakdown = {}
                    result.rule_score = None
                    result.elimination_stage = "data_incomplete"
                    if not enrich_ok:
                        reason = "YouTube Data API V3 未配置或调用失败，缺少订阅/播放/发布时间数据"
                    else:
                        reason = f"{len(incomplete)} 条视频缺少订阅数、播放量或发布时间，无法可靠打分"
                    result.elimination_reason = reason
                    result.save()
                    continue
                score, breakdown = calculate_score(keyword, videos)
                result.status = KeywordResult.STATUS_RULE_SCORED
                result.serpapi_status = "completed"
                result.top5_video_data = videos
                result.score_breakdown = breakdown
                result.rule_score = score
                result.elimination_stage = ""
                result.elimination_reason = ""
                result.save()
            except Exception as exc:  # Store the failing keyword and continue with the batch.
                result.status = KeywordResult.STATUS_SERP_ERROR
                result.serpapi_status = "error"
                result.elimination_stage = "serpapi_error"
                result.elimination_reason = str(exc)
                result.save()
        if _can_continue(run_id, task_token):
            run.status = KeywordRun.STATUS_COMPLETED
            run.save(update_fields=["status", "updated_at"])
    except Exception as exc:
        if _can_continue(run_id, task_token):
            run.status = KeywordRun.STATUS_FAILED
            run.error_message = str(exc)
            run.save(update_fields=["status", "error_message", "updated_at"])
        raise
