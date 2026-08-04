from celery import shared_task

from .models import KeywordResult, KeywordRun
from .services import (
    calculate_score,
    calculate_score_v2,
    enrich_videos,
    filter_betting_intent,
    search_youtube,
    suggest_keywords,
)


def _can_continue(run_id, token):
    run = KeywordRun.objects.only("status", "task_token").get(pk=run_id)
    return run.status == KeywordRun.STATUS_RUNNING and str(run.task_token) == str(token)


def _score_one_keyword(result, keyword, run, score_fn, serp_limit):
    """
    处理单个关键词：SerpApi 搜索 → V3 补数 → 打分入库。
    score_fn 决定用 1.0 还是 2.0 打分；serp_limit 决定取前 5 还是全部视频。
    """
    serp_videos = search_youtube(keyword, run.country, run.language, limit=serp_limit)
    videos, enrich_ok = enrich_videos(serp_videos)
    if not videos:
        result.status = KeywordResult.STATUS_RULE_SCORED
        result.serpapi_status = "no_result"
        result.top5_video_data = []
        result.score_breakdown = {}
        result.rule_score = None
        result.elimination_stage = "serpapi_no_result"
        result.elimination_reason = "SerpApi 未返回有效视频结果"
        result.save()
        return
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
            result.elimination_reason = "YouTube Data API V3 未配置或调用失败，缺少订阅/播放/发布时间数据"
        else:
            result.elimination_reason = f"{len(incomplete)} 条视频缺少订阅数、播放量或发布时间，无法可靠打分"
        result.save()
        return
    score, breakdown = score_fn(keyword, videos)
    result.status = KeywordResult.STATUS_RULE_SCORED
    result.serpapi_status = "completed"
    result.top5_video_data = videos
    result.score_breakdown = breakdown
    result.rule_score = score
    result.elimination_stage = ""
    result.elimination_reason = ""
    result.save()


@shared_task(bind=True, autoretry_for=(Exception,), retry_backoff=True, retry_kwargs={"max_retries": 2})
def process_keyword_run(self, run_id, task_token):
    run = KeywordRun.objects.get(pk=run_id)
    if not _can_continue(run_id, task_token):
        return
    run.error_message = ""
    run.save(update_fields=["error_message", "updated_at"])
    try:
        is_v2 = run.scoring_model == KeywordRun.SCORING_MODEL_V2
        score_fn = calculate_score_v2 if is_v2 else calculate_score
        serp_limit = None if is_v2 else 5  # 2.0 取全部视频，1.0 取前 5

        suggestions = suggest_keywords(run.root_keyword, run.country, run.language)
        # 输入词本身也纳入评分：即使 Suggest 拓展不出长尾词，也能评估输入词本身。
        all_keywords = list(dict.fromkeys([run.root_keyword, *suggestions]))

        if is_v2:
            # 2.0：先用 AI 批量筛选博彩意向，只有高意向词才进入打分。
            keywords_to_process, intents = _apply_betting_filter(run, all_keywords, run_id, task_token)
            if keywords_to_process is None:  # 任务已被暂停/停止
                return
        else:
            keywords_to_process = all_keywords[:run.max_keywords]
            intents = {}

        for keyword in keywords_to_process:
            if not _can_continue(run_id, task_token):
                return
            result, _ = KeywordResult.objects.get_or_create(run=run, keyword=keyword)
            if result.status in [KeywordResult.STATUS_RULE_SCORED, KeywordResult.STATUS_SERP_ERROR]:
                continue
            if keyword in intents:  # 2.0 命中意向的词，回填 AI 判定
                result.agent_result = intents[keyword]
            try:
                _score_one_keyword(result, keyword, run, score_fn, serp_limit)
            except Exception as exc:  # 单个词失败不影响整批，记录后继续。
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


def _apply_betting_filter(run, all_keywords, run_id, task_token):
    """
    2.0 专用：AI 批量筛选博彩意向。
    - 命中意向的词按 max_keywords 截断后返回，供后续打分。
    - 未命中的词写入结果表并标淘汰（low_monetization_intent）。
    返回 (待打分词列表, {词: AI判定})；若任务已被中断返回 (None, None)。
    """
    if not _can_continue(run_id, task_token):
        return None, None
    intents = filter_betting_intent(all_keywords)
    hit = [kw for kw in all_keywords if kw in intents][:run.max_keywords]
    hit_set = set(hit)

    # 未命中意向的词批量记录淘汰，方便复盘为什么被筛掉。
    for keyword in all_keywords:
        if keyword in hit_set:
            continue
        result, _ = KeywordResult.objects.get_or_create(run=run, keyword=keyword)
        if result.status in [KeywordResult.STATUS_RULE_SCORED, KeywordResult.STATUS_SERP_ERROR]:
            continue
        result.status = KeywordResult.STATUS_ELIMINATED
        result.elimination_stage = "low_monetization_intent"
        result.elimination_reason = "AI 未判定为博彩意向"
        result.rule_score = None
        result.save()
    return hit, intents
