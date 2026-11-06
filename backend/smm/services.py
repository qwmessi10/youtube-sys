"""SMM 面板 API 客户端（AutoLak Cloud Bot 逆向成果封装，纯标准库 urllib）。

认证要点（详见 telegram-re/REVERSE_FINDINGS.md）：
- publishTelegramAuth 只认 tgUserId，不校验 initData 签名，名字可为空；
- 直连需带浏览器 UA + Origin/Referer（否则 403）；
- endTime 面板按印度时区(UTC+5:30)。
"""
import json
import os
import re
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone

from keywords.models import GlobalSetting

IST = timezone(timedelta(hours=5, minutes=30))

# 轮询每次下单的结束时间（小时）：单批 1~5 人很快跑完，2 小时足够且满足最小校验。
POLL_END_HOURS = 2

# 内置最新 Chrome UA（「一键更新 UA」兜底值，以及 UA 设置被清空时的默认值）。
LATEST_CHROME_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
)


def get_setting(key, default=""):
    value = GlobalSetting.objects.filter(key=key).values_list("value", flat=True).first()
    return value if value not in (None, "") else os.getenv(key, default)


def api_base():
    return get_setting("AUTOLAK_API_BASE", "https://atpsv.autolak.in/client")


def _headers(token="", identifier="", tg_user_id=""):
    return {
        "Content-Type": "application/json",
        "User-Agent": get_setting("AUTOLAK_UA", LATEST_CHROME_UA),
        "Origin": get_setting("AUTOLAK_ORIGIN", "https://saircaf.autolak.in"),
        "Referer": get_setting("AUTOLAK_REFERER", "https://saircaf.autolak.in/"),
        "Authorization": token,
        "Identifier": identifier,
        "userType": "publisher",
        "tgUserId": tg_user_id,
        "tgFirstName": "",
        "tgLastName": "",
        "userName": "",
    }


def _request(path, body=None, token="", identifier="", tg_user_id=""):
    url = api_base() + path
    data = json.dumps(body or {}).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers=_headers(token, identifier, tg_user_id), method="POST")
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        return {"code": e.code, "msg": "HTTP %s" % e.code, "body": e.read().decode("utf-8", "ignore")}
    except Exception as e:
        return {"code": -1, "msg": repr(e)}


def publish_telegram_auth(tg_user_id, first_name="", last_name="", username=""):
    """用 tgUserId 换取 token 等凭证（无需 Telegram 签名）。"""
    return _request("/user/publishTelegramAuth", {
        "tgUserId": str(tg_user_id),
        "tgFirstName": first_name or "",
        "tgLastName": last_name or "",
        "userName": username or "",
    })


def get_balance(token, identifier, tg_user_id):
    return _request("/user/balance", {}, token=token, identifier=identifier, tg_user_id=tg_user_id)


def send_task(token, identifier, tg_user_id, youtube_link, key_words, total_user,
              per_user=2, comment_num=1, end_hours=48, plant_form=1, task_type=42):
    """创建刷量任务。endTime 按印度时区，默认 = 现在 + end_hours 小时。"""
    end_time = (datetime.now(IST) + timedelta(hours=end_hours)).strftime("%Y-%m-%d %H:%M:%S")
    body = {
        "totalUser": int(total_user),
        "perUser": float(per_user),
        "plantForm": int(plant_form),
        "type": int(task_type),
        "youtubeLink": youtube_link,
        "commentNum": int(comment_num),
        "endTime": end_time,
        "redirectFlag": 0,
        "taskEnv": 0,
        "viewFlag": 1,
        "channelName": "",
        "keyWords": key_words,
    }
    return _request("/publish/sendTask", body, token=token, identifier=identifier, tg_user_id=tg_user_id)


def search_task_record(token, identifier, tg_user_id, page=1, page_size=100):
    """查任务列表（含状态/进度）。空 status 返回全部。"""
    now = datetime.now(IST)
    start = (now - timedelta(days=90)).strftime("%Y-%m-%d 00:00:00")
    end = (now + timedelta(days=1)).strftime("%Y-%m-%d 23:59:59")
    body = {
        "startTime": start,
        "endTime": end,
        "page": page,
        "pageSize": page_size,
        "status": "",
        "taskId": "",
    }
    return _request("/publish/searchTaskRecord", body, token=token, identifier=identifier, tg_user_id=tg_user_id)


def map_panel_status(panel_status):
    """把面板返回的 status 字符串映射成本地状态。进行中/未知归 running（保守，继续同步）。"""
    if not panel_status:
        return "running"
    s = str(panel_status).strip().lower()
    if s in ("completed", "complete", "success", "finished", "done"):
        return "completed"
    if s in ("failed", "fail", "cancel", "cancelled", "refund", "refunded", "expired"):
        return "failed"
    return "running"


def next_slot_after(after_dt, start_hour, end_hour):
    """返回窗口 [start_hour, end_hour) 内 after_dt 之后的下一个整点（北京时间 aware datetime）。

    用于轮询任务的调度：每个整点刷一次，跳过窗口外时段并跨天。
    """
    candidate = (after_dt + timedelta(hours=1)).replace(minute=0, second=0, microsecond=0)
    while not (start_hour <= candidate.hour < end_hour):
        candidate += timedelta(hours=1)
    return candidate


# ===========================================================================
# YouTube 视频统计（任务详情用，纯读，不碰 AutoLak 面板、不影响调度）
# ===========================================================================
def extract_video_id(url):
    """从 YouTube 链接提取 11 位 video_id。支持 youtu.be / watch?v= / shorts / embed / live / 纯 ID。"""
    if not url:
        return ""
    url = url.strip()
    m = re.search(r"youtu\.be/([A-Za-z0-9_-]{11})", url)
    if m:
        return m.group(1)
    m = re.search(r"(?:[?&]v=|/shorts/|/embed/|/live/|youtube\.com/v/)([A-Za-z0-9_-]{11})", url)
    if m:
        return m.group(1)
    m = re.search(r"^([A-Za-z0-9_-]{11})$", url)
    if m:
        return m.group(1)
    return ""


def get_video_stats(video_id):
    """YouTube Data API V3 查单个视频的统计（viewCount/likeCount/commentCount + 标题）。

    未配置 YOUTUBE_API_KEY、视频不存在或接口异常时返回 None。
    """
    import requests
    key = get_setting("YOUTUBE_API_KEY", "")
    if not key or not video_id:
        return None
    try:
        resp = requests.get(
            "https://www.googleapis.com/youtube/v3/videos",
            params={"part": "statistics,snippet", "id": video_id, "key": key},
            timeout=20,
        )
        resp.raise_for_status()
        items = resp.json().get("items") or []
        if not items:
            return None
        item = items[0]
        stats = item.get("statistics") or {}
        snippet = item.get("snippet") or {}

        def _int(k):
            v = stats.get(k)
            return int(v) if isinstance(v, str) and v.isdigit() else None

        return {
            "video_id": video_id,
            "title": snippet.get("title") or "",
            "view_count": _int("viewCount"),
            "like_count": _int("likeCount"),
            "comment_count": _int("commentCount"),
        }
    except Exception:
        return None
