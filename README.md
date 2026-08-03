# YouTube 内容生成与自动化后台

当前已实现第一期“关键词系统”：输入基础关键词后，系统通过 YouTube Suggest 发现长尾词，依次调用 SerpApi 与 YouTube Data API V3 获取前 5 条视频的标题、链接、播放量、点赞、评论、发布时间与频道订阅数据，按既定规则评分，并在后台查看和导出完整 CSV。

本期不包含 AI Agent 调用、内容生成、视频上传发布或 AdsPower 自动化；这些模块与关键词系统保持隔离。

## 技术栈

- 后端：Python 3.12、Django、Django REST Framework、Gunicorn
- 异步任务：Celery、Redis
- 数据库：PostgreSQL 16
- 前端：Vue 3、Vite、Element Plus
- 部署：Docker Compose、Nginx

## 本地开发

### Docker 方式（推荐）

1. 安装 Docker Desktop，并确认 Docker Compose 可用。
2. 复制环境配置：`Copy-Item .env.example .env`（PowerShell）。
3. 启动全部服务：`docker compose up --build`。
4. 打开 `http://localhost:8080`。

首次启动会自动执行数据库迁移。默认 API Key 来自 `.env`，第一次打开“全局设置”时会同步为可编辑的数据库配置；此后以全局设置的保存值为准。

开发时修改前端可在 `frontend` 目录执行 `npm install`、`npm run dev`，访问 `http://localhost:5173`；后端仍通过 Docker 运行。若原生运行后端且没有 Redis，可设置 `CELERY_TASK_ALWAYS_EAGER=true`，任务会在请求内执行，仅用于调试。

### 本地检查

```powershell
docker compose config
docker compose exec backend python manage.py check
docker compose exec backend python manage.py showmigrations
```

## 云服务器部署

本地与服务器共用同一份 Docker Compose，不同点仅是环境变量、域名和网络防护。

1. 在服务器安装 Docker Engine 和 Docker Compose Plugin，开放 HTTP/HTTPS 所需端口。
2. 克隆仓库：`git clone git@github.com:qwmessi10/youtube-sys.git`，进入目录后复制 `.env.example` 为 `.env`。
3. 修改服务器 `.env`：
   - `DJANGO_DEBUG=false`
   - `DJANGO_SECRET_KEY` 改为服务器专用值
   - `DJANGO_ALLOWED_HOSTS` 改为服务器域名或 IP
   - `POSTGRES_PASSWORD` 改为服务器专用数据库密码
   - 填写或在后台全局设置中维护 SerpApi、YouTube V3、AI 参数
4. 构建并在后台启动：`docker compose up -d --build`。
5. 检查状态：`docker compose ps`；查看后台任务日志：`docker compose logs -f worker`。

默认对外端口为 `8080`；后端 `8000` 仅绑定到服务器本机，供 Nginx 和本地调试使用。生产环境建议使用 Caddy、Nginx 或云负载均衡器将域名的 443 HTTPS 流量反代到 `127.0.0.1:8080`，并把 Compose 的前端端口映射改为 `127.0.0.1:8080:80`，避免直接暴露应用端口。

升级发布时执行：

```bash
git pull
docker compose up -d --build
docker compose exec backend python manage.py migrate
```

PostgreSQL 数据由 Docker 卷 `postgres_data` 保存。升级或迁移服务器前先备份：

```bash
docker compose exec -T db pg_dump -U youtube_sys youtube_sys > backup.sql
```

## 关键词评分规则

每个关键词取前 5 条视频，每个维度最高 5 分，总分最高 20 分；分数越高表示潜在内容空位越大：

- 标题未完全包含长尾词：每条 +1
- 频道订阅数低于 2,000：每条 +1
- 视频播放量低于 5,000：每条 +1
- 发布时间超过 24 小时：每条 +1

YouTube V3 使用 `videos.list` 和 `channels.list` 批量补齐视频、频道和订阅信息，以避免 SerpApi 搜索结果字段不完整。

## 关键词结果查看

- 任务记录和关键词结果均为每页 10 条，支持按基础关键词或长尾关键词搜索。
- 点击任务记录可筛选对应任务的结果。
- 展开每条关键词结果可查看前 5 个视频的完整评选依据；标题可直接跳转到 YouTube 视频。
- CSV 为每个关键词展开 5 组视频字段，包含视频标题、链接、频道、频道订阅数、播放/点赞/评论数与发布时间，方便人工核对。
- 国家和语言只能从后台提供的候选列表选择；“最大长尾数”默认是 15。

## 任务控制

- **暂停**：当前正在执行的单次 API 查询结束后，任务不再处理下一个关键词；已完成结果保留。
- **停止**：立即禁止后续关键词处理，已完成结果保留。
- **重启**：从暂停、停止或失败状态继续处理未完成的关键词，不会重复查询已完成或已记录错误的关键词。

## 当前接口

- `POST /api/keyword-runs/`：创建关键词任务
- `GET /api/keyword-runs/`：查询任务
- `GET /api/keyword-results/?run=<id>`：查询关键词结果
- `GET /api/keyword-results/export/?run=<id>`：导出 CSV
- `GET/PUT /api/settings/`：读取和修改全局 API、AI 配置

## Git

远程仓库已配置为：`git@github.com:qwmessi10/youtube-sys.git`。
