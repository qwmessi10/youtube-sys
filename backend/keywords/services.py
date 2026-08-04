import json
import os
import re
import time
from datetime import datetime, timedelta

import requests
from django.utils import timezone

from .models import GlobalSetting

# 2.0 博彩意图筛选的默认提示词（可在全局设置 AI_BETTING_INTENT_PROMPT 覆盖）。
DEFAULT_BETTING_INTENT_PROMPT = """# 角色
你是一个YouTube专业的关键词分析与体育、娱乐游戏运营，有10年的运营经验

# 目标
通过批量获取到的搜索词，判断搜索词是否有博彩意向；如果有博彩意向，则以json格式全部输出

# 输入
[input]

# 输出
[output]"""

# 要求 AI 固定输出的 JSON 结构说明，拼到提示词的 [output] 处。
BETTING_INTENT_OUTPUT_SPEC = """严格只输出一个 JSON 对象，不要输出任何解释文字或 markdown 代码块标记，格式如下：
{"betting_keywords": [{"keyword": "原样的搜索词", "intent": "high 或 medium", "reason": "判定理由"}]}
只包含有博彩意向的词；没有任何有意向的词时输出 {"betting_keywords": []}。"""

# worker 进程内记录上一次 SerpApi 请求的时间戳，用于按 QPS 节流（第一版单 worker 串行处理够用）。
_last_serpapi_request_at = 0.0


def get_setting(key, default=""):
    value = GlobalSetting.objects.filter(key=key).values_list("value", flat=True).first()
    return value if value not in (None, "") else os.getenv(key, default)


def _get_float_setting(key, default):
    """读取数值型配置，非法值时回退默认，避免配置写错把任务打挂。"""
    try:
        value = float(get_setting(key, str(default)))
        return value if value > 0 else default
    except (TypeError, ValueError):
        return default


def _throttle_serpapi():
    """按 SERPAPI_QPS 控制请求间隔：距上次请求不足 1/QPS 秒则先 sleep。"""
    global _last_serpapi_request_at
    qps = _get_float_setting("SERPAPI_QPS", 1)
    min_interval = 1.0 / qps
    elapsed = time.monotonic() - _last_serpapi_request_at
    if elapsed < min_interval:
        time.sleep(min_interval - elapsed)
    _last_serpapi_request_at = time.monotonic()


def _request_with_retry(method, url, *, throttle=False, **kwargs):
    """
    统一的带重试 HTTP 请求：
    - 429（限流）和 5xx（服务端错误）按指数退避重试，最多 SERPAPI_MAX_RETRIES 次。
    - 其他 4xx（如 401 无效 Key）不重试，直接抛错，避免无谓浪费额度。
    - throttle=True 时请求前按 QPS 节流（用于 SerpApi）。
    """
    max_retries = int(_get_float_setting("SERPAPI_MAX_RETRIES", 2))
    last_exc = None
    for attempt in range(max_retries + 1):
        if throttle:
            _throttle_serpapi()
        try:
            response = requests.request(method, url, **kwargs)
            if response.status_code == 429 or response.status_code >= 500:
                last_exc = RuntimeError(f"请求返回 {response.status_code}")
                if attempt < max_retries:
                    time.sleep(2 ** attempt)  # 指数退避：1s、2s、4s...
                    continue
            response.raise_for_status()
            return response
        except requests.RequestException as exc:
            # 连接超时等网络异常也重试
            last_exc = exc
            if attempt < max_retries:
                time.sleep(2 ** attempt)
                continue
            raise
    raise last_exc


def suggest_keywords(root_keyword, country, language):
    response = requests.get(
        "https://suggestqueries.google.com/complete/search",
        params={"client": "chrome", "ds": "yt", "q": root_keyword, "gl": country, "hl": language},
        timeout=15,
    )
    response.raise_for_status()
    payload = response.json()
    suggestions = payload[1] if isinstance(payload, list) and len(payload) > 1 else []
    return list(dict.fromkeys(item for item in suggestions if isinstance(item, str) and item.strip()))


def search_youtube(keyword, country, language, limit=5):
    """
    调用 SerpApi 搜索 YouTube。
    - limit=5：1.0 只取前 5 条。
    - limit=None：2.0 取返回的全部视频。
    """
    api_key = get_setting("SERPAPI_API_KEY")
    if not api_key:
        raise RuntimeError("未配置 SERPAPI_API_KEY")
    params = {"engine": "youtube", "search_query": keyword, "gl": country, "hl": language, "api_key": api_key}
    if limit:
        params["num"] = limit
    response = _request_with_retry("GET", "https://serpapi.com/search.json", throttle=True, params=params, timeout=30)
    data = response.json()
    if data.get("error"):
        raise RuntimeError(data["error"])
    videos = data.get("video_results") or []
    return videos[:limit] if limit else videos


def _fetch_v3_items(resource, part, ids, youtube_key):
    """分批调用 YouTube Data API V3（每批最多 50 个 ID），返回合并后的 items 列表。"""
    items = []
    for i in range(0, len(ids), 50):
        batch = ids[i:i + 50]
        response = _request_with_retry(
            "GET",
            f"https://www.googleapis.com/youtube/v3/{resource}",
            params={"part": part, "id": ",".join(batch), "key": youtube_key},
            timeout=30,
        )
        items.extend(response.json().get("items", []))
    return items


def enrich_videos(serp_videos):
    """
    用 YouTube Data API V3 批量补齐可靠的视频统计和频道订阅数。
    返回 (normalized, enrich_ok)：
      - normalized：标准化后的视频列表，每条带 data_complete 标记（订阅/播放/发布时间是否齐全）。
      - enrich_ok：V3 是否成功补数。未配置 Key 或请求失败时为 False，交给上层标记人工复核。
    """
    video_ids = [item.get("video_id") for item in serp_videos if item.get("video_id")]
    youtube_key = get_setting("YOUTUBE_API_KEY")
    details_by_id = {}
    channel_subscribers = {}
    enrich_ok = True

    if not youtube_key:
        enrich_ok = False  # 没有 V3 Key，订阅/播放/时间都拿不到，后续标记人工复核。
    elif video_ids:
        # V3 的 videos.list / channels.list 单次最多 50 个 ID，超过需分批（2.0 会传全量视频）。
        for item in _fetch_v3_items("videos", "snippet,statistics", video_ids, youtube_key):
            details_by_id[item["id"]] = item
        channel_ids = list({item["snippet"]["channelId"] for item in details_by_id.values() if item.get("snippet", {}).get("channelId")})
        if channel_ids:
            channel_subscribers = {
                item["id"]: int(item.get("statistics", {}).get("subscriberCount", 0))
                for item in _fetch_v3_items("channels", "statistics", channel_ids, youtube_key)
            }

    normalized = []
    for raw in serp_videos:
        detail = details_by_id.get(raw.get("video_id"), {})
        snippet = detail.get("snippet", {})
        statistics = detail.get("statistics", {})
        channel_id = snippet.get("channelId")
        subscriber_count = channel_subscribers.get(channel_id)
        view_count = int(statistics["viewCount"]) if statistics.get("viewCount", "").isdigit() else None
        published_at = snippet.get("publishedAt")
        # 打分依赖的三项：订阅数、播放量、发布时间。任一缺失则该条数据不完整。
        data_complete = None not in (subscriber_count, view_count, published_at)
        normalized.append({
            "video_id": raw.get("video_id"),
            "title": snippet.get("title") or raw.get("title", ""),
            "video_url": f"https://www.youtube.com/watch?v={raw['video_id']}" if raw.get("video_id") else "",
            "channel_name": snippet.get("channelTitle") or raw.get("channel", {}).get("name", ""),
            "channel_id": channel_id,
            "subscriber_count": subscriber_count,
            "view_count": view_count,
            "like_count": int(statistics["likeCount"]) if statistics.get("likeCount", "").isdigit() else None,
            "comment_count": int(statistics["commentCount"]) if statistics.get("commentCount", "").isdigit() else None,
            "published_at": published_at,
            "data_complete": data_complete,
            "serp_raw": raw,
        })
    return normalized, enrich_ok


def _normalized_text(value):
    # 把非单词字符（标点、空格等）统一替换成单个空格，用于标题与关键词的匹配比较。
    # 注意：这里必须用 r"[^\w]+"，之前写成 r"[^\\w]+" 会把反斜杠当字面量，导致匹配逻辑错误。
    return re.sub(r"[^\w]+", " ", (value or "").lower()).strip()


def _count_published_over_24h(videos):
    """统计发布时间超过 24 小时的视频数量。"""
    cutoff = timezone.now() - timedelta(hours=24)
    count = 0
    for video in videos:
        published_at = video.get("published_at")
        if published_at:
            try:
                if datetime.fromisoformat(published_at.replace("Z", "+00:00")) < cutoff:
                    count += 1
            except ValueError:
                pass
    return count


def _count_title_mismatch(keyword, videos):
    """统计标题未完全包含关键词的视频数量。"""
    target = _normalized_text(keyword)
    return sum(target not in _normalized_text(video.get("title")) for video in videos)


def calculate_score(keyword, videos):
    """1.0 打分：全部维度都看前 5 条视频，每维 0-5，分越高潜在内容空位越大。"""
    breakdown = {
        "title_mismatch": _count_title_mismatch(keyword, videos),
        "low_subscriber": sum(
            v.get("subscriber_count") is not None and v["subscriber_count"] < 2000 for v in videos
        ),
        "low_view": sum(v.get("view_count") is not None and v["view_count"] < 5000 for v in videos),
        "published_over_24h": _count_published_over_24h(videos),
    }
    return sum(breakdown.values()), breakdown


def calculate_score_v2(keyword, videos):
    """
    2.0 打分：分维度看不同范围的视频。videos 传入的是 SerpApi 返回的全部视频。
    - 播放量：只看前 5 条，< 500 每个 +1。
    - 频道订阅：看全部视频，< 1000 每个 +1。
    - 标题匹配：看全部视频，未完全包含关键词每个 +1。
    - 发布时间：只看前 5 条，> 24h 每个 +1。
    """
    top5 = videos[:5]
    breakdown = {
        "title_mismatch": _count_title_mismatch(keyword, videos),
        "low_subscriber": sum(
            v.get("subscriber_count") is not None and v["subscriber_count"] < 1000 for v in videos
        ),
        "low_view": sum(v.get("view_count") is not None and v["view_count"] < 500 for v in top5),
        "published_over_24h": _count_published_over_24h(top5),
    }
    return sum(breakdown.values()), breakdown


def _call_ai_stream(messages):
    """
    调用 moretokens（OpenAI 兼容）聊天接口。该平台强制 stream:true（见需求 7.5），
    这里按 SSE 逐行解析，拼接 choices[0].delta.content，返回完整文本。
    """
    base_url = get_setting("AI_BASE_URL", "https://moretokens.ai/v1").rstrip("/")
    api_key = get_setting("AI_API_KEY")
    model = get_setting("AI_MODEL", "gemini-3.6-flash-medium")
    if not api_key:
        raise RuntimeError("未配置 AI_API_KEY")

    response = requests.post(
        f"{base_url}/chat/completions",
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        json={"model": model, "stream": True, "messages": messages},
        timeout=120,
        stream=True,
    )
    response.raise_for_status()

    chunks = []
    for line in response.iter_lines(decode_unicode=True):
        if not line or not line.startswith("data:"):
            continue
        payload = line[len("data:"):].strip()
        if payload == "[DONE]":
            break
        try:
            delta = json.loads(payload)["choices"][0].get("delta", {})
        except (json.JSONDecodeError, KeyError, IndexError):
            continue
        content = delta.get("content")
        if content:
            chunks.append(content)
    return "".join(chunks)


def _extract_json(text):
    """从 AI 返回文本中提取 JSON 对象（容忍 ```json 代码块包裹或前后多余文字）。"""
    text = text.strip()
    # 去掉 markdown 代码块围栏
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text, flags=re.IGNORECASE).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        # 兜底：截取第一个 { 到最后一个 } 之间的内容
        start, end = text.find("{"), text.rfind("}")
        if start != -1 and end != -1 and end > start:
            return json.loads(text[start:end + 1])
        raise


def filter_betting_intent(keywords):
    """
    批量把长尾词交给 AI，判断博彩意向。
    返回 dict：{关键词: {"intent": "...", "reason": "..."}}，只含 AI 判定有意向的词。
    """
    if not keywords:
        return {}
    prompt = get_setting("AI_BETTING_INTENT_PROMPT") or DEFAULT_BETTING_INTENT_PROMPT
    keyword_list = "\n".join(f"- {kw}" for kw in keywords)
    prompt = prompt.replace("[input]", keyword_list).replace("[output]", BETTING_INTENT_OUTPUT_SPEC)

    raw = _call_ai_stream([{"role": "user", "content": prompt}])
    data = _extract_json(raw)

    result = {}
    for item in data.get("betting_keywords", []):
        kw = (item.get("keyword") or "").strip()
        if kw:
            result[kw] = {"intent": item.get("intent", ""), "reason": item.get("reason", "")}
    return result
