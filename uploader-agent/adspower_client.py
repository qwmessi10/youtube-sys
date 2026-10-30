"""AdsPower 本地 API 客户端（宿主执行器用）。限频：每秒最多 1 次。"""
import threading
import time

import requests

import config

_lock = threading.Lock()
_last = [0.0]


def _throttle():
    with _lock:
        elapsed = time.time() - _last[0]
        if elapsed < 1.0:
            time.sleep(1.0 - elapsed)
        _last[0] = time.time()


def _headers():
    return {"Authorization": f"Bearer {config.ADSPOWER_API_KEY}"} if config.ADSPOWER_API_KEY else {}


def _get(path, params=None, timeout=60):
    _throttle()
    url = f"{config.ADSPOWER_API_BASE}{path}"
    resp = requests.get(url, params=params, headers=_headers(), timeout=timeout)
    resp.raise_for_status()
    body = resp.json()
    if body.get("code") != 0:
        raise RuntimeError(f"AdsPower 错误：{body.get('msg')}")
    return body.get("data") or {}


def status():
    _throttle()
    try:
        return requests.get(f"{config.ADSPOWER_API_BASE}/status", timeout=10).json().get("code") == 0
    except Exception:
        return False


def active(user_id):
    """查询浏览器是否已打开。返回 data（含 status、ws）。"""
    return _get("/api/v1/browser/active", {"user_id": user_id})


def start(user_id, headless=0):
    """
    启动浏览器，返回 data：
      { ws: {selenium, puppeteer}, debug_port, webdriver }
    puppeteer 字段即 CDP endpoint，供 Playwright connect_over_cdp。
    """
    return _get("/api/v1/browser/start", {
        "user_id": user_id, "headless": headless, "open_tabs": 1,
    })


def stop(user_id):
    return _get("/api/v1/browser/stop", {"user_id": user_id})
