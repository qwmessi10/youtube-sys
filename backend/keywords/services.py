import os
import re
import time
from datetime import datetime, timedelta

import requests
from django.utils import timezone

from .models import GlobalSetting

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


def search_youtube(keyword, country, language):
    api_key = get_setting("SERPAPI_API_KEY")
    if not api_key:
        raise RuntimeError("未配置 SERPAPI_API_KEY")
    response = _request_with_retry(
        "GET",
        "https://serpapi.com/search.json",
        throttle=True,
        params={"engine": "youtube", "search_query": keyword, "num": 5, "gl": country, "hl": language, "api_key": api_key},
        timeout=30,
    )
    data = response.json()
    if data.get("error"):
        raise RuntimeError(data["error"])
    return (data.get("video_results") or [])[:5]


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
        video_response = _request_with_retry(
            "GET",
            "https://www.googleapis.com/youtube/v3/videos",
            params={"part": "snippet,statistics", "id": ",".join(video_ids), "key": youtube_key},
            timeout=30,
        )
        for item in video_response.json().get("items", []):
            details_by_id[item["id"]] = item
        channel_ids = list({item["snippet"]["channelId"] for item in details_by_id.values() if item.get("snippet", {}).get("channelId")})
        if channel_ids:
            channel_response = _request_with_retry(
                "GET",
                "https://www.googleapis.com/youtube/v3/channels",
                params={"part": "statistics", "id": ",".join(channel_ids), "key": youtube_key},
                timeout=30,
            )
            channel_subscribers = {
                item["id"]: int(item.get("statistics", {}).get("subscriberCount", 0))
                for item in channel_response.json().get("items", [])
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


def calculate_score(keyword, videos):
    """Each dimension is 0-5. A higher score indicates a greater potential content gap."""
    target = _normalized_text(keyword)
    title_score = sum(target not in _normalized_text(video.get("title")) for video in videos)
    low_subscriber_score = sum(
        video.get("subscriber_count") is not None and video["subscriber_count"] < 2000 for video in videos
    )
    low_view_score = sum(video.get("view_count") is not None and video["view_count"] < 5000 for video in videos)
    cutoff = timezone.now() - timedelta(hours=24)
    old_video_score = 0
    for video in videos:
        published_at = video.get("published_at")
        if published_at:
            try:
                if datetime.fromisoformat(published_at.replace("Z", "+00:00")) < cutoff:
                    old_video_score += 1
            except ValueError:
                pass
    breakdown = {
        "title_mismatch": title_score,
        "low_subscriber": low_subscriber_score,
        "low_view": low_view_score,
        "published_over_24h": old_video_score,
    }
    return sum(breakdown.values()), breakdown
