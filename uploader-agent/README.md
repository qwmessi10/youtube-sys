# Uploader Agent（AdsPower → YouTube 自动上传执行器）

宿主独立进程。不进 Docker，直接跑在装了 AdsPower 的 mac 上，通过 HTTP 与 youtube-sys 后端通信。

## 职责

轮询后端上传任务队列 → 下载视频/封面 → 调 AdsPower 本地 API 起浏览器 →
Playwright 接管浏览器在 YouTube Studio 上传 → **保存草稿（开发阶段不发布）** →
抓草稿链接回填后端 → 关浏览器 → 下一个。

## 安装

```bash
cd uploader-agent
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
playwright install chromium          # 首次需装浏览器驱动（一次性）
cp .env.example .env                 # 按需改配置
```

## 配置（.env）

| 项 | 说明 |
|----|------|
| `BACKEND_BASE` | 后端地址，默认 `http://127.0.0.1:8000` |
| `AGENT_TOKEN` | 执行器回调鉴权 token，需与后端全局设置 `UPLOADER_AGENT_TOKEN` 一致（留空=不校验） |
| `ADSPOWER_API_BASE` | AdsPower 本地 API，默认 `http://local.adspower.net:50325` |
| `ADSPOWER_API_KEY` | AdsPower API Key |
| `POLL_INTERVAL` | 轮询间隔秒数，默认 10 |
| `DRAFT_ONLY` | `True`=只存草稿不发布（开发阶段强烈建议保持） |
| `HEADLESS` | 接管真实浏览器，保持 `False` |

## 运行

```bash
source .venv/bin/activate
python agent.py
```

启动后常驻轮询。前台日志会打印每个任务的进度；每步截图存 `_work/task_<id>/`。
Ctrl+C 退出。

## 使用流程

1. 确保 AdsPower 客户端在运行、本地 API 已开启、目标浏览器已登录 YouTube。
2. 在后台「AdsPower 自动化系统 - 任务管理」手动建任务，或在「内容生成 - 任务管理」对已完成任务点「上传YouTube」。
3. 启动本 Agent，它会领取排队任务并执行到"草稿已保存"。
4. 到对应浏览器的 YouTube Studio 核对草稿，确认无误后手动发布。

## 注意

- **串行执行**：一次只处理一个任务，符合"一天一个"的节奏。
- YouTube Studio DOM 常改版，若上传卡住，更新 `youtube_uploader.py` 顶部的 `SEL` 选择器常量。
- 失败任务在后台可点「重试」重新排队。
