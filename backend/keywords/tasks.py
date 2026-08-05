from collections import deque

from celery import shared_task
from celery.exceptions import SoftTimeLimitExceeded

from .models import KeywordResult, KeywordRun, SuggestExpansionRun
from .services import (
    calculate_score,
    calculate_score_v2,
    enrich_videos,
    filter_betting_intent,
    filter_by_language,
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

        # 2.0：先按目标语言过滤 Suggest 词，剔除结果语言不符的（如要英语却返回俄语/中文词）。
        dropped_by_language = []
        if is_v2:
            suggestions, dropped_by_language = filter_by_language(suggestions, run.language)

        # 输入词本身也纳入评分：即使 Suggest 拓展不出长尾词，也能评估输入词本身。
        all_keywords = list(dict.fromkeys([run.root_keyword, *suggestions]))

        # 记录 Suggest 工作日志（拓展的全部词 + 被语言过滤掉的词）。
        log = dict(run.run_log or {})
        log["suggest"] = {
            "root_keyword": run.root_keyword,
            "suggested": list(suggestions),
            "all_keywords": all_keywords,
            "count": len(all_keywords),
            "language": run.language,
            "dropped_by_language": dropped_by_language,
            "dropped_count": len(dropped_by_language),
        }
        run.run_log = log
        run.save(update_fields=["run_log", "updated_at"])

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
    intents, ai_log = filter_betting_intent(all_keywords)
    hit = [kw for kw in all_keywords if kw in intents][:run.max_keywords]
    hit_set = set(hit)

    # 把 AI 完整输入输出写进任务日志，供「查看日志」抽屉展示与提示词调试。
    log = dict(run.run_log or {})
    ai_log["hit_keywords"] = list(hit)
    ai_log["eliminated_keywords"] = [kw for kw in all_keywords if kw not in hit_set]
    log["agent"] = ai_log
    run.run_log = log
    run.save(update_fields=["run_log", "updated_at"])

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


def _expansion_can_continue(run_id, token):
    """判断 Suggest 拓展任务是否还该继续（未被停止、token 未失效）。"""
    run = SuggestExpansionRun.objects.only("status", "task_token").get(pk=run_id)
    return run.status == SuggestExpansionRun.STATUS_RUNNING and str(run.task_token) == str(token)


# Suggest 递归拓展可能跑很久（几千词、串行查询），单独放宽超时，不受全局 600s 限制。
# soft_time_limit 会先抛可捕获的 SoftTimeLimitExceeded，让我们保存已拓词后优雅收尾；
# time_limit（硬超时）再留 5 分钟缓冲兜底。
@shared_task(bind=True, soft_time_limit=7200, time_limit=7500)
def process_suggest_expansion(self, run_id, task_token):
    """
    对词根做 BFS 递归拓展：
    队列初始为 [词根]，对每个种子直接查一次 Suggest API，
    返回的词即为该种子的长尾词；新词加入已见集合并继续入队当种子，
    直到队列空（再没有新的长尾词返回）或达到 max_keywords 上限。
    轮次不限（current_round 仅作进度展示）。
    到达时间上限时保存已拓展的词并标记完成，不丢结果。
    """
    run = SuggestExpansionRun.objects.get(pk=run_id)
    if not _expansion_can_continue(run_id, task_token):
        return
    try:
        seen = set()          # 已收集的全部长尾词（去重）
        queue = deque()       # 待拓展的种子队列
        # 词根本身先入队做种子，但不计入结果词（结果只要拓展出来的长尾词）
        queue.append((run.root_keyword, 0))
        processed = 0
        max_kw = run.max_keywords or 5000

        seeds_since_save = 0  # 距上次完整词表落库处理的种子数
        while queue:
            if not _expansion_can_continue(run_id, task_token):
                return
            seed, depth = queue.popleft()
            reached_limit = False
            # 直接用种子本身查一次，Suggest API 返回什么词就收什么词。
            try:
                suggestions = suggest_keywords(seed, run.country, run.language)
            except Exception:
                suggestions = []  # 单个查询失败跳过，不中断整体拓展
            for kw in suggestions:
                if kw in seen or kw == run.root_keyword:
                    continue
                seen.add(kw)
                queue.append((kw, depth + 1))
                if len(seen) >= max_kw:
                    reached_limit = True
                    break

            processed += 1
            seeds_since_save += 1
            # 每处理完一个种子就刷新进度，让前端能看到词数实时增长。
            run.keyword_count = len(seen)
            run.processed_seeds = processed
            run.current_round = depth + 1
            if seeds_since_save >= 20:  # 完整词表较大，隔一批种子才落库一次
                run.keywords = sorted(seen)
                run.save(update_fields=["keywords", "keyword_count", "processed_seeds", "current_round", "updated_at"])
                seeds_since_save = 0
            else:
                run.save(update_fields=["keyword_count", "processed_seeds", "current_round", "updated_at"])
            if reached_limit:
                break

        if _expansion_can_continue(run_id, task_token):
            run.status = SuggestExpansionRun.STATUS_COMPLETED
            run.keywords = sorted(seen)
            run.keyword_count = len(seen)
            run.save(update_fields=["status", "keywords", "keyword_count", "updated_at"])
    except SoftTimeLimitExceeded:
        # 到达时间上限：已拓展的词是有效结果，保存并标记完成，不当作失败丢弃。
        if _expansion_can_continue(run_id, task_token):
            run.status = SuggestExpansionRun.STATUS_COMPLETED
            run.keywords = sorted(seen)
            run.keyword_count = len(seen)
            run.error_message = f"达到时间上限，已保存前 {len(seen)} 个词后结束"
            run.save(update_fields=["status", "keywords", "keyword_count", "error_message", "updated_at"])
    except Exception as exc:
        if _expansion_can_continue(run_id, task_token):
            run.status = SuggestExpansionRun.STATUS_FAILED
            run.error_message = str(exc)
            run.save(update_fields=["status", "error_message", "updated_at"])
        raise
