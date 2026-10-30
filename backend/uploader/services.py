"""
AdsPower 本地 API 客户端 + 环境同步服务。

说明：
  - 本地 API 基址默认 http://local.adspower.net:50325（可被全局设置 ADSPOWER_API_BASE 覆盖）。
  - 鉴权：header Authorization: Bearer <ADSPOWER_API_KEY>。
  - 限频：每接口每秒最多 1 次，内部做最小间隔节流。
  - 后端只用到「读列表 / 查分组 / 启停浏览器 / 查状态」；真正的 Playwright 自动化在宿主执行器里。
"""
import threading
import time

import requests

from keywords.models import GlobalSetting


def get_setting(key, default=""):
    """读取全局设置：DB 优先，回退默认。与 flow3.services.get_setting 同策略。"""
    import os
    value = GlobalSetting.objects.filter(key=key).values_list("value", flat=True).first()
    return value if value not in (None, "") else os.getenv(key, default)


DEFAULT_API_BASE = "http://local.adspower.net:50325"

# AdsPower 本地 API 全局限频：每秒最多 1 次。用进程级锁 + 时间戳保证最小间隔。
_rate_lock = threading.Lock()
_last_call_ts = [0.0]


def _throttle():
    try:
        min_interval = 1.0 / float(get_setting("ADSPOWER_API_RATE_LIMIT", "1") or 1)
    except (ValueError, ZeroDivisionError):
        min_interval = 1.0
    with _rate_lock:
        elapsed = time.time() - _last_call_ts[0]
        if elapsed < min_interval:
            time.sleep(min_interval - elapsed)
        _last_call_ts[0] = time.time()


def _api_base():
    return (get_setting("ADSPOWER_API_BASE", DEFAULT_API_BASE) or DEFAULT_API_BASE).rstrip("/")


def _headers():
    key = get_setting("ADSPOWER_API_KEY", "")
    return {"Authorization": f"Bearer {key}"} if key else {}


class AdsPowerError(Exception):
    """AdsPower 本地 API 调用失败（code != 0 或网络错误）。"""


def _request(method, path, *, params=None, json=None, timeout=30):
    """统一请求：节流 + Bearer 鉴权 + code 校验。返回 data 字段。"""
    _throttle()
    url = f"{_api_base()}{path}"
    try:
        resp = requests.request(method, url, params=params, json=json, headers=_headers(), timeout=timeout)
        resp.raise_for_status()
        body = resp.json()
    except requests.RequestException as e:
        raise AdsPowerError(f"无法连接 AdsPower 本地 API（{url}）：{e}") from e
    except ValueError as e:
        raise AdsPowerError(f"AdsPower 返回非 JSON：{e}") from e
    if body.get("code") != 0:
        raise AdsPowerError(body.get("msg") or "AdsPower 返回错误")
    return body.get("data") or {}


# ===========================================================================
# 基础 API 封装
# ===========================================================================
def check_status():
    """探活：GET /status。返回 True/False（不抛异常）。"""
    _throttle()
    try:
        resp = requests.get(f"{_api_base()}/status", timeout=10)
        return resp.json().get("code") == 0
    except (requests.RequestException, ValueError):
        return False


def list_profiles(page=1, page_size=100, group_id=""):
    """GET /api/v1/user/list → {list:[...], page, page_size}。"""
    params = {"page": page, "page_size": page_size}
    if group_id:
        params["group_id"] = group_id
    return _request("GET", "/api/v1/user/list", params=params)


def list_groups(page=1, page_size=100):
    """GET /api/v1/group/list → {list:[{group_id, group_name, remark}]}。"""
    return _request("GET", "/api/v1/group/list", params={"page": page, "page_size": page_size})


def start_browser(user_id, *, headless=0, open_tabs=1):
    """
    GET /api/v1/browser/start?user_id=xxx。
    返回含 ws（selenium/puppeteer CDP 端口）、debug_port、webdriver。
    供执行器 Playwright connect_over_cdp 使用。该 profile 自带绑定的 socks5，IP 自动注入。
    """
    return _request("GET", "/api/v1/browser/start", params={
        "user_id": user_id, "headless": headless, "open_tabs": open_tabs,
    })


def stop_browser(user_id):
    """GET /api/v1/browser/stop?user_id=xxx。"""
    return _request("GET", "/api/v1/browser/stop", params={"user_id": user_id})


def browser_active(user_id):
    """GET /api/v1/browser/active?user_id=xxx → {status: 'Active'/'Inactive', ws?}。"""
    return _request("GET", "/api/v1/browser/active", params={"user_id": user_id})


# ===========================================================================
# 同步：拉全量环境列表 → 写入 AdsPowerProfile 缓存
# ===========================================================================
def _proxy_summary(proxy_cfg):
    """从 user_proxy_config 提炼代理摘要（不含账号密码）。"""
    if not isinstance(proxy_cfg, dict):
        return ""
    soft = proxy_cfg.get("proxy_soft") or ""
    if soft in ("", "no_proxy"):
        return "无代理"
    ptype = proxy_cfg.get("proxy_type") or ""
    host = proxy_cfg.get("proxy_host") or ""
    port = proxy_cfg.get("proxy_port") or ""
    return f"{ptype} {host}:{port}".strip()


def _sanitize_raw(item):
    """脱敏原始环境数据：清掉代理账号密码、平台账号密码。"""
    import copy
    safe = copy.deepcopy(item)
    pc = safe.get("user_proxy_config")
    if isinstance(pc, dict):
        if pc.get("proxy_password"):
            pc["proxy_password"] = "***"
        if pc.get("proxy_user"):
            pc["proxy_user"] = pc["proxy_user"][:3] + "***"
    for acc in safe.get("platform_account") or []:
        if isinstance(acc, dict) and acc.get("password"):
            acc["password"] = "***"
    return safe


def sync_profiles():
    """
    拉全量环境（翻页直到取完）写入缓存。返回 {synced: n, groups: m}。
    采用"全量覆盖"：AdsPower 现有的更新，本地多余的保留（不删，避免误删正在用的任务外键）。
    """
    from .models import AdsPowerProfile

    page, page_size, total = 1, 100, 0
    seen_ids = set()
    while True:
        data = list_profiles(page=page, page_size=page_size)
        items = data.get("list") or []
        if not items:
            break
        for item in items:
            uid = item.get("user_id")
            if not uid:
                continue
            seen_ids.add(uid)
            AdsPowerProfile.objects.update_or_create(
                user_id=uid,
                defaults={
                    "serial_number": str(item.get("serial_number") or ""),
                    "name": item.get("name") or "",
                    "group_id": str(item.get("group_id") or ""),
                    "group_name": item.get("group_name") or "",
                    "domain_name": item.get("domain_name") or "",
                    "username": item.get("username") or "",
                    "remark": item.get("remark") or "",
                    "ip": item.get("ip") or "",
                    "ip_country": item.get("ip_country") or "",
                    "proxy_summary": _proxy_summary(item.get("user_proxy_config")),
                    "last_open_time": str(item.get("last_open_time") or ""),
                    "raw": _sanitize_raw(item),
                },
            )
            total += 1
        if len(items) < page_size:
            break
        page += 1

    groups = list_groups().get("list") or []
    return {"synced": total, "groups": len(groups)}
