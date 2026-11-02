"""
Uploader Agent 主入口（宿主独立进程）。

循环：领任务 → 拿 payload → 下载视频/封面 → AdsPower 起浏览器 → Playwright 上传到草稿
     → 回调结果 → 关浏览器 → 下一个。

串行执行（一次一个任务），符合"一天一个"的节奏。Ctrl+C 退出。
"""
import time
import traceback
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

import config
import adspower_client as ads
import backend_client as be
import youtube_uploader as yt


def _cdp_endpoint(start_data):
    """从 AdsPower start/active 返回里取 CDP endpoint，并适配 Docker 容器到宿主机的地址转换。"""
    ws = start_data.get("ws") or {}
    endpoint = ws.get("puppeteer") or ws.get("selenium") or ""
    if not endpoint:
        return ""
    # AdsPower 在宿主机返回 ws://127.0.0.1:<port>/...；该 localhost 对 Docker 容器指向容器自身。
    # 执行器集成到 Docker 后，需要替换为 Docker Desktop 提供的宿主机网关。
    if config.CDP_HOST_REWRITE:
        parts = urlsplit(endpoint)
        host = parts.hostname
        if host in {"127.0.0.1", "localhost", "::1"}:
            netloc = config.CDP_HOST_REWRITE
            if parts.port:
                netloc = f"{netloc}:{parts.port}"
            endpoint = urlunsplit((parts.scheme, netloc, parts.path, parts.query, parts.fragment))
    return endpoint


def process_task(task):
    task_id = task["id"]
    user_id = task["profile_user_id"]
    print(f"[task {task_id}] 开始，目标浏览器 {user_id}")

    # 1. 拿完整 payload（领任务已返回 payload，但重新拉一次确保最新）
    payload = be.get_payload(task_id)
    title = payload.get("title") or ""
    description = payload.get("description") or ""
    video_url_src = payload.get("video_download_url") or ""
    cover_url_src = payload.get("cover_download_url") or ""

    work = Path(config.WORK_DIR) / f"task_{task_id}"
    work.mkdir(parents=True, exist_ok=True)

    # 2. 下载视频 / 封面
    be.callback(task_id, "uploading")
    video_path = be.download(video_url_src, str(work / "video.mp4"))
    if not video_path:
        raise RuntimeError("视频下载失败：payload 无 video_download_url")
    cover_path = ""
    if cover_url_src:
        ext = Path(cover_url_src.split("?")[0]).suffix or ".jpg"
        cover_path = be.download(cover_url_src, str(work / f"cover{ext}"))
    print(f"[task {task_id}] 文件就绪 video={video_path} cover={cover_path or '无'}")

    # 3. 起浏览器（该 profile 自带 socks5，IP 自动注入）
    act = ads.active(user_id)
    if act.get("status") == "Active":
        start_data = act  # 已开，直接用其 ws
    else:
        start_data = ads.start(user_id)
    cdp = _cdp_endpoint(start_data)
    if not cdp:
        raise RuntimeError(f"未取得 CDP endpoint：{start_data}")
    print(f"[task {task_id}] 浏览器已启动，CDP={cdp}")

    try:
        # 4. Playwright 上传到草稿
        result = yt.upload_to_draft(
            cdp,
            video_path=video_path,
            title=title,
            description=description,
            cover_path=cover_path,
            work_dir=str(work),
            draft_only=config.DRAFT_ONLY,
            on_progress=lambda step, note, shot: be.progress(task_id, step, note, shot),
        )
        # 5. 回调草稿已保存
        be.callback(task_id, "draft_saved",
                    video_url=result.get("video_url", ""),
                    upload_log={"steps": result.get("steps", [])})
        print(f"[task {task_id}] 完成（草稿），链接：{result.get('video_url') or '未抓到'}")
    finally:
        # 6. 关浏览器（stop 后复核 active，没关成功重试一次，避免浏览器残留）
        _safe_stop(user_id, task_id)


def _safe_stop(user_id, task_id, retries=1):
    """关闭浏览器并复核：stop 后查 active，仍 Active 则重试，最终仍失败只告警不抛。"""
    for attempt in range(retries + 1):
        # 已被其它操作关闭时直接结束，不再将正常状态当作失败。
        try:
            if ads.active(user_id).get("status") != "Active":
                return
        except Exception as e:
            print(f"[task {task_id}] 关闭前检查浏览器状态失败：{e}")
            return
        try:
            ads.stop(user_id)
        except Exception as e:
            # AdsPower 在刚关闭后可能返回「User_id is not open」，此时再复核即可。
            print(f"[task {task_id}] 关闭浏览器调用失败（第 {attempt + 1} 次）：{e}")
        # 复核是否真的关了
        try:
            if ads.active(user_id).get("status") != "Active":
                return  # 已关闭
        except Exception as e:
            print(f"[task {task_id}] 复核浏览器状态失败：{e}")
            return  # 查不到状态就不再纠缠，避免卡死
        if attempt < retries:
            print(f"[task {task_id}] 浏览器仍在运行，重试关闭…")
    print(f"[task {task_id}] ⚠️ 浏览器可能未成功关闭（user_id={user_id}），请人工确认 AdsPower")


def main():
    print("=" * 60)
    print("Uploader Agent 启动")
    print(f"  后端：{config.BACKEND_BASE}")
    print(f"  AdsPower：{config.ADSPOWER_API_BASE}")
    print(f"  轮询间隔：{config.POLL_INTERVAL}s  仅草稿：{config.DRAFT_ONLY}")
    print("=" * 60)

    if not ads.status():
        print("⚠️  AdsPower 本地 API 不可用，请确认客户端已开启本地 API")

    while True:
        try:
            task = be.next_task()
            if not task:
                time.sleep(config.POLL_INTERVAL)
                continue
            try:
                process_task(task)
            except Exception as e:
                err = f"{e}\n{traceback.format_exc()}"
                print(f"[task {task.get('id')}] 失败：{err}")
                try:
                    be.callback(task["id"], "failed", error_message=str(e))
                except Exception:
                    pass
        except KeyboardInterrupt:
            print("\n收到退出信号，Agent 停止。")
            break
        except Exception as e:
            print(f"主循环异常（继续）：{e}")
            time.sleep(config.POLL_INTERVAL)


if __name__ == "__main__":
    main()
