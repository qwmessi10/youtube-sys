"""与 youtube-sys 后端通信：领任务、拿 payload、回调结果、上报进度、下载文件。"""
import os

import requests

import config


def _headers():
    return {"X-Agent-Token": config.AGENT_TOKEN} if config.AGENT_TOKEN else {}


def next_task():
    """领取下一个排队任务。无任务返回 None。"""
    url = f"{config.BACKEND_BASE}/api/upload-tasks/next/"
    resp = requests.get(url, headers=_headers(), timeout=30)
    if resp.status_code == 204:
        return None
    resp.raise_for_status()
    return resp.json()


def get_payload(task_id):
    url = f"{config.BACKEND_BASE}/api/upload-tasks/{task_id}/payload/"
    resp = requests.get(url, headers=_headers(), timeout=30)
    resp.raise_for_status()
    return resp.json()


def callback(task_id, status, *, video_url="", error_message="", upload_log=None):
    url = f"{config.BACKEND_BASE}/api/upload-tasks/{task_id}/callback/"
    payload = {"status": status, "video_url": video_url, "error_message": error_message}
    if upload_log is not None:
        payload["upload_log"] = upload_log
    resp = requests.post(url, json=payload, headers=_headers(), timeout=30)
    resp.raise_for_status()
    return resp.json()


def progress(task_id, step, note="", screenshot=""):
    url = f"{config.BACKEND_BASE}/api/upload-tasks/{task_id}/progress/"
    try:
        requests.post(url, json={"step": step, "note": note, "screenshot": screenshot},
                      headers=_headers(), timeout=20)
    except Exception:
        pass  # 进度上报失败不阻断主流程


def download(url, dest_path):
    """下载文件到本地。返回本地路径。"""
    if not url:
        return ""
    with requests.get(url, stream=True, timeout=300) as r:
        r.raise_for_status()
        with open(dest_path, "wb") as f:
            for chunk in r.iter_content(chunk_size=1 << 16):
                f.write(chunk)
    return dest_path
