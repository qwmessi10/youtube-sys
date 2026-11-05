#!/usr/bin/env python3
"""
AutoLak Cloud Bot 面板 API 客户端（逆向成果封装）
用于自动化创建任务（YouTube SEO 刷量）。

逆向背景：
- 小程序前端 https://saircaf.autolak.in/#/ （Telegram Mini App）
- 后端 API  https://atpsv.autolak.in/client
- 认证：登录后拿到 token + userIdentifier，请求头带 Authorization/Identifier/userType/tgUserId 等
详细见 REVERSE_FINDINGS.md

依赖：仅用 Python 标准库（urllib），无第三方依赖，可直接集成到 Django 后台。
"""
import json
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone

BASE_URL = "https://atpsv.autolak.in/client"

# 登录凭证（从面板 localStorage 提取）
# 注意：token 可能过期；失效时需重新登录小程序并从 localStorage 重新提取。
AUTH = {
    "Authorization": "hpFpBg/NJe8SuK5l8PqRhtxAbtomJghgPVBuk/wM6kc=",
    "Identifier": "XWHG968505",
    "userType": "publisher",
    "tgUserId": "8196195827",
    "tgFirstName": "Libbie",
    "tgLastName": "M",
    "userName": "okokok1928ok",
}

# 印度标准时间（面板服务器时区 UTC+5:30），endTime 需按此发送
IST = timezone(timedelta(hours=5, minutes=30))


def _request(path, body=None, method="POST"):
    url = BASE_URL + path
    data = json.dumps(body or {}).encode("utf-8")
    headers = {
        "Content-Type": "application/json",
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
        "Origin": "https://saircaf.autolak.in",
        "Referer": "https://saircaf.autolak.in/",
        **AUTH,
    }
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        return {"code": e.code, "msg": "HTTP %s" % e.code, "body": e.read().decode("utf-8", "ignore")}


def get_balance():
    """查询余额。返回 {code, data:{balance}, ...}"""
    return _request("/user/balance", {})


def create_task(youtube_link, keyword, total_user, per_user=2, comment_num=1,
                end_hours=48, plant_form=1, task_type=42):
    """
    创建任务（YouTube SEO 刷量）。

    :param youtube_link: YouTube 视频链接
    :param keyword:      搜索关键词（用户搜索该词找到并观看视频）
    :param total_user:   刷量人数
    :param per_user:     每人奖励（₹，默认 2，>=2）
    :param comment_num:  评论数（默认 1）
    :param end_hours:    任务结束时间 = 现在 + end_hours 小时（默认 48）
    :param plant_form:   平台（1=Youtube）
    :param task_type:    服务类型（42=SEO search/like/comment/view）
    :return: 后端响应 dict，data 内含 taskId / showId / picUrl / endTime / per
    """
    end_time = (datetime.now(IST) + timedelta(hours=end_hours)).strftime("%Y-%m-%d %H:%M:%S")
    body = {
        "totalUser": int(total_user),
        "perUser": int(per_user),
        "plantForm": int(plant_form),
        "type": int(task_type),
        "youtubeLink": youtube_link,
        "commentNum": int(comment_num),
        "endTime": end_time,
        "redirectFlag": 0,
        "taskEnv": 0,
        "viewFlag": 1,
        "channelName": "",
        "keyWords": keyword,
    }
    return _request("/publish/sendTask", body)


if __name__ == "__main__":
    import sys

    if len(sys.argv) < 4:
        print("用法: python autolak_client.py <youtube链接> <关键词> <人数> [每人奖励₹]")
        sys.exit(1)

    link = sys.argv[1]
    kw = sys.argv[2]
    total = int(sys.argv[3])
    per = int(sys.argv[4]) if len(sys.argv) > 4 else 2

    bal = get_balance()
    print("当前余额:", bal.get("data", {}).get("balance"), "₹")

    r = create_task(link, kw, total, per_user=per)
    print("创建任务结果:")
    print(json.dumps(r, ensure_ascii=False, indent=2))
