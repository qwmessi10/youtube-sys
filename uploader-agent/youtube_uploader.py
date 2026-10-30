"""
YouTube Studio 网页自动化上传（Playwright 接管 AdsPower 浏览器）。

开发阶段策略（DRAFT_ONLY=True）：
  上传视频 → 填标题/描述 → 传封面 → 走到"保存草稿"为止，不点发布。
  抓取草稿视频链接回填。

注意：YouTube Studio DOM 多 iframe、异步渲染且常改版。本模块用多重选择器兜底 +
显式等待，并在每一步截图。若 YT 改版导致选择器失效，优先更新这里的选择器常量。
"""
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

STUDIO_URL = "https://studio.youtube.com"
# 上传入口 / 各控件的候选选择器（按优先级尝试，兼容多语言 UI）
SEL = {
    "create_btn": ["#create-icon", "ytcp-button#create-icon", "[aria-label='创建']", "[aria-label='Create']"],
    "upload_item": ["#text-item-0", "tp-yt-paper-item:has-text('上传视频')", "tp-yt-paper-item:has-text('Upload videos')"],
    "file_input": ["input[type='file']"],
    "title_box": ["#title-textarea #textbox", "ytcp-social-suggestions-textbox[label*='标题'] #textbox",
                  "div#textbox[aria-label*='title' i]", "#title-textarea div[contenteditable='true']"],
    "desc_box": ["#description-textarea #textbox", "div#textbox[aria-label*='description' i]",
                 "#description-textarea div[contenteditable='true']"],
    "thumb_input": ["#file-loader", "input[type='file'][accept*='image']"],
    "next_btn": ["#next-button", "ytcp-button#next-button"],
    "done_btn": ["#done-button", "ytcp-button#done-button"],
    "close_btn": ["#close-button", "ytcp-button#close-button", "[aria-label='关闭']", "[aria-label='Close']"],
    "video_url_link": ["a.ytcp-video-info", "span.video-url-fadeable a", "a[href*='youtu.be']",
                       "a[href*='/watch?v=']"],
    # 可见性单选：开发阶段不用，保留供后续
    "radio_private": ["tp-yt-paper-radio-button[name='PRIVATE']", "[name='PRIVATE']"],
}


class UploadError(Exception):
    pass


def _first(page_or_frame, selectors, timeout=15000):
    """在候选选择器里返回第一个可见的 locator；都找不到则抛错。"""
    last_err = None
    for sel in selectors:
        try:
            loc = page_or_frame.locator(sel).first
            loc.wait_for(state="visible", timeout=timeout)
            return loc
        except Exception as e:
            last_err = e
            continue
    raise UploadError(f"找不到元素：{selectors}（{last_err}）")


def _try_click(page_or_frame, selectors, timeout=15000):
    _first(page_or_frame, selectors, timeout).click()


def _shot(page, work_dir, name):
    try:
        path = str(Path(work_dir) / f"{name}.png")
        page.screenshot(path=path)
        return path
    except Exception:
        return ""


def upload_to_draft(cdp_endpoint, *, video_path, title, description, cover_path="",
                    work_dir=".", draft_only=True, on_progress=None):
    """
    接管 AdsPower 浏览器（CDP），在 YouTube Studio 上传视频并填元数据，保存草稿。
    返回 {video_url, steps:[{step,note,screenshot}]}。
    on_progress(step, note, screenshot) 可选回调，用于实时上报。
    """
    steps = []

    def log(step, note="", page=None, shot_name=""):
        shot = _shot(page, work_dir, shot_name) if (page is not None and shot_name) else ""
        steps.append({"step": step, "note": note, "screenshot": shot})
        if on_progress:
            on_progress(step, note, shot)

    with sync_playwright() as p:
        browser = p.chromium.connect_over_cdp(cdp_endpoint)
        context = browser.contexts[0] if browser.contexts else browser.new_context()
        page = context.new_page()
        try:
            log("open_studio", "打开 YouTube Studio")
            page.goto(STUDIO_URL, wait_until="domcontentloaded", timeout=60000)
            page.wait_for_timeout(3000)
            log("studio_loaded", "Studio 已加载", page, "01_studio")

            # 点"创建"→"上传视频"
            _try_click(page, SEL["create_btn"])
            page.wait_for_timeout(1000)
            _try_click(page, SEL["upload_item"])
            page.wait_for_timeout(1500)
            log("upload_dialog", "进入上传对话框", page, "02_dialog")

            # 选文件（input 可能不可见，直接 set_input_files）
            file_input = page.locator(SEL["file_input"][0]).first
            file_input.wait_for(state="attached", timeout=30000)
            file_input.set_input_files(video_path)
            log("file_selected", f"已选择视频 {Path(video_path).name}")

            # 等上传处理 + 标题框出现
            title_box = _first(page, SEL["title_box"], timeout=120000)
            page.wait_for_timeout(1500)

            # 填标题（先清空 YT 默认填入的文件名）
            title_box.click()
            page.keyboard.press("Control+A")
            page.keyboard.press("Delete")
            title_box.type(title[:100], delay=10)
            log("title_filled", f"标题：{title[:60]}", page, "03_title")

            # 填描述
            if description:
                try:
                    desc_box = _first(page, SEL["desc_box"], timeout=8000)
                    desc_box.click()
                    desc_box.type(description[:4900], delay=2)
                    log("desc_filled", "描述已填写")
                except UploadError:
                    log("desc_skip", "未找到描述框，跳过")

            # 传封面（可选）
            if cover_path:
                try:
                    thumb = page.locator(SEL["thumb_input"][0]).first
                    thumb.wait_for(state="attached", timeout=8000)
                    thumb.set_input_files(cover_path)
                    page.wait_for_timeout(2000)
                    log("cover_uploaded", "封面已上传", page, "04_cover")
                except Exception:
                    log("cover_skip", "封面上传失败/未找到入口，跳过")

            if not draft_only:
                # 后续阶段：点 Next ×3 → 选可见性 → 发布。开发阶段不走这里。
                log("publish_disabled", "draft_only=False 未实现自动发布，仍按草稿处理")

            # 抓取草稿视频链接
            video_url = ""
            try:
                link = _first(page, SEL["video_url_link"], timeout=10000)
                video_url = link.get_attribute("href") or ""
            except UploadError:
                pass
            log("draft_saved", f"草稿已保存，链接：{video_url or '未抓到'}", page, "05_draft")

            # 关闭对话框（触发 YT 自动保存草稿）
            try:
                _try_click(page, SEL["close_btn"], timeout=5000)
                page.wait_for_timeout(2000)
            except UploadError:
                pass

            return {"video_url": video_url, "steps": steps}
        finally:
            try:
                page.close()
            except Exception:
                pass
