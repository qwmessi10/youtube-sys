"""数据分析系统服务层。

复用关键词系统的数据源：
  - search_youtube / enrich_videos：SerpApi 搜索 + YouTube V3 补数（标题/描述/标签/播放/点赞/评论/订阅/发布时间）
  - get_setting / _request_with_retry / _fetch_v3_items：配置读取 + 带重试请求 + V3 批量查询

本模块新增：
  - extract_video_id：从 YouTube 链接解析 video_id
  - fetch_video_details：按 video_id 批量查 V3 详情（视频库刷新用）
  - analyze_video_seo / build_seo_summary：竞品 SEO 逐条拆解 + 汇总洞察
  - search_and_analyze：完整竞品分析流程
  - capture_ranking：排名追踪抓取
"""
import re
from collections import Counter

from keywords.services import (
    _fetch_v3_items,
    enrich_videos,
    get_setting,
    search_youtube,
)

# YouTube 链接里的 video_id 提取（watch?v= / youtu.be/ / shorts/ / embed/）
_VIDEO_ID_RE = re.compile(
    r"(?:youtube\.com/(?:watch\?v=|shorts/|embed/|live/)|youtu\.be/)([A-Za-z0-9_-]{11})"
)

# 常见 emoji 区间（用于标题 emoji 检测）
_EMOJI_RANGES = [
    (0x1F300, 0x1FAFF),  # 表情符号、象形文字
    (0x2600, 0x27BF),    # 杂项符号、装饰符
    (0x2B00, 0x2BFF),    # 杂项符号与箭头
    (0xFE00, 0xFE0F),    # 变体选择符
]

# 描述里的时间戳模式（如 0:00、10:30、1:02:33）
_TIMESTAMP_RE = re.compile(r"\b\d{1,2}:\d{2}(?::\d{2})?\b")


def _normalized(value):
    """把非单词字符统一替换成空格并小写，用于关键词与标题/描述的匹配比较。"""
    return re.sub(r"[^\w]+", " ", (value or "").lower()).strip()


def _has_emoji(text):
    for ch in text:
        code = ord(ch)
        if any(lo <= code <= hi for lo, hi in _EMOJI_RANGES):
            return True
    return False


def _case_style(text):
    """粗略判断标题大小写风格。"""
    if not text:
        return "empty"
    if text == text.upper():
        return "uppercase"
    if text == text.lower():
        return "lowercase"
    words = [w for w in text.split() if w]
    if words and all(w[0].isupper() for w in words if w[0].isalpha()):
        return "title_case"
    return "mixed"


def extract_video_id(url):
    """从 YouTube 链接解析 video_id；解析不出返回空串。"""
    m = _VIDEO_ID_RE.search(url or "")
    return m.group(1) if m else ""


def fetch_video_details(video_ids):
    """按 video_id 批量查 V3 详情（snippet + statistics），返回 {video_id: {...}}。"""
    youtube_key = get_setting("YOUTUBE_API_KEY")
    if not youtube_key:
        raise RuntimeError("未配置 YOUTUBE_API_KEY")
    items = _fetch_v3_items("videos", "snippet,statistics", list(video_ids), youtube_key)
    result = {}
    for item in items:
        snippet = item.get("snippet", {})
        statistics = item.get("statistics", {})
        vid = item["id"]
        result[vid] = {
            "video_id": vid,
            "title": snippet.get("title", ""),
            "description": snippet.get("description", ""),
            "tags": snippet.get("tags", []),
            "channel_name": snippet.get("channelTitle", ""),
            "channel_id": snippet.get("channelId", ""),
            "view_count": int(statistics["viewCount"]) if statistics.get("viewCount", "").isdigit() else None,
            "like_count": int(statistics["likeCount"]) if statistics.get("likeCount", "").isdigit() else None,
            "comment_count": int(statistics["commentCount"]) if statistics.get("commentCount", "").isdigit() else None,
            "published_at": snippet.get("publishedAt"),
        }
    return result


def analyze_video_seo(video, keyword):
    """对单个视频做 SEO 拆解，返回 title/description/tags 三个维度的分析。"""
    title = video.get("title") or ""
    description = video.get("description") or ""
    tags = video.get("tags") or []
    kw = _normalized(keyword)
    title_norm = _normalized(title)

    # 关键词是否在标题开头（取标题前 25 个字符看是否包含关键词）
    title_head = _normalized(title[:25])
    has_keyword_start = bool(kw) and (title_head.startswith(kw) or kw in title_head)

    # 描述：首行、关键词密度、链接、时间戳
    first_line = description.split("\n")[0].strip() if description else ""
    desc_lower = description.lower()
    kw_count = desc_lower.count(keyword.lower()) if keyword else 0
    desc_words = len(description.split())
    keyword_density = round(kw_count / desc_words, 4) if desc_words else 0

    long_tail = [t for t in tags if " " in t]
    short_tail = [t for t in tags if " " not in t]

    return {
        "title": {
            "text": title,
            "length": len(title),
            "has_keyword_start": has_keyword_start,
            "has_number": bool(re.search(r"\d", title)),
            "has_emoji": _has_emoji(title),
            "case_style": _case_style(title),
        },
        "description": {
            "text": description,
            "length": len(description),
            "first_line": first_line,
            "keyword_density": keyword_density,
            "has_link": bool(re.search(r"https?://", description)),
            "has_timestamps": bool(_TIMESTAMP_RE.search(description)),
        },
        "tags": {
            "count": len(tags),
            "long_tail": long_tail,
            "short_tail": short_tail,
            "keyword_in_tags": bool(kw) and any(kw in _normalized(t) for t in tags),
        },
    }


def build_seo_summary(videos, keyword):
    """基于 top N 视频的拆解，产出汇总洞察（规则统计，不调 AI）。"""
    if not videos:
        return {}

    titles = [v.get("title") or "" for v in videos]
    descs = [v.get("description") or "" for v in videos]
    tags_list = [v.get("tags") or [] for v in videos]

    kw = _normalized(keyword)
    title_has_kw = sum(1 for t in titles if kw and kw in _normalized(t))

    # 高频 tag
    tag_counter = Counter(t for tags in tags_list for t in tags)
    top_tags = [t for t, _ in tag_counter.most_common(10)]

    avg_title_len = round(sum(len(t) for t in titles) / len(titles), 1)
    avg_desc_len = round(sum(len(d) for d in descs) / len(descs), 1)
    avg_tags = round(sum(len(t) for t in tags_list) / len(tags_list), 1)

    insights = []
    if title_has_kw:
        insights.append(f"{len(videos)} 个视频中 {title_has_kw} 个标题包含关键词「{keyword}」（{round(title_has_kw / len(videos) * 100)}%）")
    if 0 < avg_title_len < 100:
        insights.append(f"标题平均 {avg_title_len} 字符，普遍较短、信息密度高")
    if avg_tags >= 5:
        insights.append(f"平均 {avg_tags} 个 Tag，长尾词占比较高")
    if top_tags:
        insights.append(f"高频 Tag：{', '.join(top_tags[:5])}")

    return {
        "avg_title_length": avg_title_len,
        "avg_desc_length": avg_desc_len,
        "avg_tags": avg_tags,
        "keyword_in_title_ratio": round(title_has_kw / len(videos), 2),
        "top_tags": top_tags,
        "insights": insights,
    }


def search_and_analyze(keyword, country, language, top_n=10):
    """搜索关键词 top N 视频并做 SEO 分析，返回完整 result（含 videos + summary）。"""
    serp_videos = search_youtube(keyword, country, language, limit=top_n)
    normalized, _ = enrich_videos(serp_videos)
    videos = [
        {"rank": i + 1, **v, "seo": analyze_video_seo(v, keyword)}
        for i, v in enumerate(normalized)
    ]
    summary = build_seo_summary(normalized, keyword)
    return {"keyword": keyword, "videos": videos, "summary": summary}


def capture_ranking(tracking):
    """抓一次排名快照，返回 top N 视频的排名数据列表。"""
    serp_videos = search_youtube(tracking.keyword, tracking.country, tracking.language, limit=tracking.top_n)
    normalized, _ = enrich_videos(serp_videos)
    return [
        {
            "rank": i + 1,
            "video_id": v.get("video_id"),
            "title": v.get("title"),
            "video_url": v.get("video_url"),
            "channel_name": v.get("channel_name"),
            "view_count": v.get("view_count"),
            "published_at": v.get("published_at"),
        }
        for i, v in enumerate(normalized)
    ]
