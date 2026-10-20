# YouTube 内容生成与自动化后台

面向 YouTube 博彩/体育推广场景的内容自动化后台，目前包含两大系统：

1. **关键词系统**：输入基础关键词后，通过 YouTube Suggest 发现长尾词，依次调用 SerpApi 与 YouTube Data API V3 获取视频的标题、链接、播放量、点赞、评论、发布时间与频道订阅数据，按规则（或 AI 博彩意图筛选）评分，后台查看并导出 CSV。
2. **内容生成系统**：基于关键词批量生成 YouTube 视频（标题/描述/封面/旁白/成品），含三条相互隔离的流程：
   - **流程一（全自动）**：关键词 + 视频模板 + 变量 → AI 元数据/封面/旁白 → Edge TTS → Remotion 渲染出片。
   - **流程二（半自动）**：AI 出元数据 + 分镜脚本 → 人工上传分镜视频 → ffmpeg 合并。
   - **流程三（全新三段式长视频）**：独立 `flow3` 模块，产出 16:9 1080P、最长 4 分钟的长视频——SegA Hook（AI 出 Prompt + 人工上传 mp4）+ SegB 左右分屏画中画（Remotion）+ SegC 尾图呼吸微动（ffmpeg zoompan），叠加 BGM 混音与防封去重。详见下文「流程三」。

> 流程三与流程一/二**完全代码隔离**（独立 Django app `flow3`、独立前端页、独立 Agent 与素材库），后续可整块移除流程一/二而不影响流程三。

## 技术栈

- 后端：Python 3.12、Django、Django REST Framework、Gunicorn
- 异步任务：Celery、Redis
- 数据库：PostgreSQL 16
- 前端：Vue 3、Vite、Element Plus
- 视频渲染：Remotion（Node 22 + 无头 Chromium）、ffmpeg
- AI：moretokens（OpenAI 兼容中转）文本/生图模型、Edge TTS 语音合成
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

- **输入词也参与评分**：输入词本身会一并纳入待处理列表（排在最前、去重后按最大长尾数截断）。当输入词已很具体、Suggest 拓展不出更多长尾词时，仍能评估输入词本身，不会出现空结果。
- **数据不全标记人工复核**：当 YouTube V3 未配置或调用失败、或前 5 视频缺少订阅数/播放量/发布时间时，该关键词标记为「数据不全，需人工复核」，不给出可能误导的分数，淘汰阶段记为 `data_incomplete`。
- **SerpApi 限流防护**：请求按 `SERPAPI_QPS` 节流（默认每秒 1 次），遇 429 或 5xx 按 `SERPAPI_MAX_RETRIES`（默认 2 次）指数退避重试；401 等其他错误不重试以节省额度。这些参数可在「全局设置」中调整。

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

## 流程三：全新三段式长视频

流程三是独立模块（后端 `backend/flow3`、前端菜单「内容生成 · 流程3」），单任务产出一个 16:9 1080P 长视频。

### 成片结构
| 段 | 时间 | 画面 | 生成方式 |
|---|---|---|---|
| SegA | 0–7s | Hook 开场 | AI 出视频 Prompt → 人工用外部文生视频引擎生成 mp4 → 回传上传 |
| SegB | 7s–旁白结束 | 左右分屏画中画：模糊底图 + Promo Code 文字 + 9:16 录屏 | Remotion 渲染，录屏左右位置按随机种子 |
| SegC | 至总时长 | 尾图 + 呼吸/抖动微动 | AI 生图 → ffmpeg zoompan |

总时长在创建任务时填写；SegC 时长 = 总时长 − 7 − 旁白实际时长。合成后叠加 BGM 混音与像素级防封去重。

### 五个独立 Agent（「流程3 → Agent 管理」可配置提示词）
- Hook 视频文案 Agent、语音文案 Agent（印度英语旁白）、模糊底图 Agent、尾图 Agent、元数据 Agent
- 支持 `{PROMO_CODE}` / `{COUNTRY}` / `{EVENT_NAME}` 占位符注入

### 素材库（「流程3 → 素材库」）
- **9:16 手机录屏**：库内保留 1 个，所有任务自动取用
- **背景音乐 BGM**：可批量上传，任务执行时随机抽取 1 个（种子记录便于复现）

### 使用流程
1. 创建任务（填关键词、总时长、优惠码等）→ 系统生成 Hook Prompt，任务暂停等待上传。
2. 用 Hook Prompt 在外部引擎生成 mp4，在任务列表「上传 Hook」后点「继续」。
3. 系统自动完成：旁白 → 印式 TTS → 模糊底图 → 尾图 → 元数据 → SegB → SegC → 三段合并 → BGM 混音 + 防封。
4. 完成后「下载」得到 zip（含 `metadata.txt` + 封面 `cover.jpg` + 成品 `final_video.mp4`）。

> AI Key 与模型在「全局设置」维护（文本模型 `AI_MODEL`、生图模型 `GEMINI_IMAGE_MODEL`、`AI_API_KEY` 等），不写死在代码。AI 调用对偶发断连做自动重试；各生成步骤幂等，重启/续跑不会重复消耗额度。

## 当前接口

关键词系统：
- `POST /api/keyword-runs/`：创建关键词任务
- `GET /api/keyword-runs/`：查询任务
- `GET /api/keyword-results/?run=<id>`：查询关键词结果
- `GET /api/keyword-results/export/?run=<id>`：导出 CSV
- `GET/PUT /api/settings/`：读取和修改全局 API、AI 配置

内容生成（流程一/二）：
- `/api/content-runs/`、`/api/content-items/`、`/api/content-agents/`、`/api/video-templates/`

流程三（独立）：
- `POST /api/flow3-runs/`：创建任务（出 Hook Prompt 后暂停）
- `POST /api/flow3-runs/<id>/upload_hook/`：上传 Hook 视频
- `POST /api/flow3-runs/<id>/resume/`：继续执行 Step4~7
- `POST /api/flow3-runs/<id>/{pause,stop,restart}/`：任务控制
- `GET /api/flow3-runs/<id>/log/`：工作日志
- `GET /api/flow3-runs/<id>/package/`：下载成品 zip
- `/api/flow3-agents/`、`/api/flow3-materials/`：Agent 管理与素材库

## Git

远程仓库已配置为：`git@github.com:qwmessi10/youtube-sys.git`。
