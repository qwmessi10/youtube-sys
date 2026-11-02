# Uploader Agent（AdsPower → YouTube 自动上传执行器）

> 已集成到主项目的 Docker Compose，服务名为 `uploader`。正常使用时**不需要运行 Python 命令、不需要打开终端**：确保 Docker Desktop 与 AdsPower 客户端正在运行，然后在后台创建任务即可自动上传到草稿。

## 自动运行方式（默认）

项目启动时会一并启动 `uploader` 服务，它会常驻领取上传任务：

```bash
# 仅供部署或排障时使用；日常后台操作不需要执行这条命令
# docker compose up -d
```

运行链路：后台创建任务 → `uploader` 自动领取 → 调用宿主机 AdsPower → 接管浏览器 → 上传 YouTube 草稿 → 回填任务链接 → 关闭浏览器。

前置条件：

1. Docker Desktop 正在运行；
2. AdsPower 客户端正在运行，且本地 API 已开启；
3. 目标 AdsPower 浏览器环境已登录 YouTube，并正确配置代理；
4. 项目环境变量 `ADSPOWER_API_KEY` 已配置（首次集成时已写入项目 `.env`）。

如果 AdsPower 客户端关闭，执行器会持续等待；重新打开 AdsPower 后会自动领取后续排队任务。

## 配置说明

| 项 | Docker 集成模式 |
|----|------|
| `BACKEND_BASE` | Compose 内部固定为 `http://backend:8000` |
| `ADSPOWER_API_BASE` | Compose 内固定为 `http://host.docker.internal:50325`，以访问 macOS 宿主 AdsPower |
| `ADSPOWER_API_KEY` | 从项目根目录 `.env` 的 `ADSPOWER_API_KEY` 读取 |
| `CDP_HOST_REWRITE` | Compose 自动设置为 `host.docker.internal`，把 AdsPower 返回的本机 CDP 地址改写为 Docker 可访问的宿主地址 |
| `AGENT_TOKEN` | 可选执行器回调鉴权；与后端全局设置一致，留空则不校验 |
| `POLL_INTERVAL` | 默认 10 秒 |
| `DRAFT_ONLY` | 保持 `True`，只保存草稿不发布 |

## 排障（仅管理员）

执行器日志可用以下方式查看：

```bash
docker compose logs -f uploader
```

若执行器意外停止，Compose 的 `restart: unless-stopped` 会自动拉起。任务在执行器崩溃或机器休眠后超过默认 30 分钟会自动回到队列，避免永久卡住。
