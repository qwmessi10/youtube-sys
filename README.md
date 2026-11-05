# YouTube 内容生成与自动化后台

面向 YouTube 博彩/体育推广场景的**内容自动化流水线**，覆盖「选词 → 做视频 → 上传 → 刷量 → 数据分析」全链路。共六大功能系统 + 一个总览首页：

| 系统 | 作用 | 后端 app |
|------|------|---------|
| **首页** | 总览驾驶舱，聚合各系统关键指标与最近动态（纯查看） | analytics |
| **数据分析系统** | 视频库数据看板、竞品 SEO 分析、关键词排名追踪 | analytics |
| **关键词系统** | Suggest 拓词 + SerpApi/V3 补数 + 规则/AI 打分选题 | keywords |
| **内容生成系统（流程三）** | 三段式长视频生成（Hook + 画中画 + 尾图） | flow3 |
| **AdsPower 自动化** | 浏览器/IP 管理 + 自动上传视频到 YouTube 草稿 | uploader |
| **SMM 面板系统** | 刷量任务下单 + 轮询刷量维持 VPH | smm |

> 历史说明：早期曾有流程一（全自动短视频）与流程二（半自动分镜合并），现已下线移除；内容生成系统目前仅保留流程三（独立 Django app `flow3`）。

---

## 技术栈

- 后端：Python 3.12、Django、Django REST Framework、Gunicorn
- 异步任务：Celery、Redis（含 `beat` 定时调度）
- 数据库：PostgreSQL 16
- 前端：Vue 3、Vite、Element Plus
- 视频渲染：Remotion（Node 22 + 无头 Chromium）、ffmpeg
- AI：moretokens（OpenAI 兼容中转）文本/生图模型、Edge TTS 多语言语音合成
- 部署：Docker Compose、Nginx

Docker Compose 共 8 个服务：`db` / `redis` / `backend` / `worker` / `beat` / `render` / `uploader` / `frontend`。

---

## 本地开发

### Docker 方式（推荐）

1. 安装 Docker Desktop，并确认 Docker Compose 可用。
2. 复制环境配置：`Copy-Item .env.example .env`（PowerShell）。
3. 启动全部服务：`docker compose up --build`。
4. 打开 `http://localhost:8080`。

首次启动会自动执行数据库迁移。默认 API Key 来自 `.env`，第一次打开「全局设置」时会同步为可编辑的数据库配置；此后以全局设置的保存值为准。

开发时修改前端可在 `frontend` 目录执行 `npm install`、`npm run dev`，访问 `http://localhost:5173`；后端仍通过 Docker 运行。若原生运行后端且没有 Redis，可设置 `CELERY_TASK_ALWAYS_EAGER=true`，任务会在请求内执行，仅用于调试。

### 本地检查

```powershell
docker compose config
docker compose exec backend python manage.py check
docker compose exec backend python manage.py showmigrations
```

---

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

默认对外端口为 `8080`；后端 `8000` 仅绑定到服务器本机。生产环境建议用 Caddy、Nginx 或云负载均衡器将域名 443 HTTPS 反代到 `127.0.0.1:8080`，并把 Compose 的前端端口映射改为 `127.0.0.1:8080:80`。

升级发布：

```bash
git pull
docker compose up -d --build
docker compose exec backend python manage.py migrate
```

PostgreSQL 数据由 Docker 卷 `postgres_data` 保存，升级前先备份：

```bash
docker compose exec -T db pg_dump -U youtube_sys youtube_sys > backup.sql
```

---

## 首页（总览驾驶舱）

菜单置顶的一级项，**纯查看、不跳转、不做操作**。进入时调用聚合接口 `GET /api/dashboard/summary/` 一次返回：

- **指标卡（4）**：SMM 剩余可用余额、今日出片数、待核对草稿数、进行中任务总数
- **系统概况（5）**：关键词 / 内容生成 / AdsPower / SMM / 实用工具 各自的总数、进行中、已完成、失败等统计
- **最近动态（10）**：合并各系统最近记录，按时间倒序展示

---

## 数据分析系统

流水线的「数据反馈」环节，含三个板块（菜单「数据分析系统」下）：

- **视频库**：自动关联 AdsPower 上传的视频（`UploadTask.video_url`）+ 手动添加链接；展示播放/点赞/评论/发布时间，支持单条刷新与指标趋势图。
- **竞品 SEO 分析**：输入关键词 → 搜 YouTube top N → 逐条拆解标题（长度/关键词位置/数字/emoji）、描述（首行/关键词密度/链接/时间戳）、Tag（数量/长尾/含关键词），并汇总共性洞察。
- **排名追踪**：维护追踪关键词，定时（频率在全局设置 `ANALYTICS_REFRESH_INTERVAL_MINUTES` 配置）抓取 top N 排名存快照，支持手动抓取与排名趋势图。

数据源复用关键词系统的 SerpApi 搜索 + YouTube V3 补数，技术风险低。

---

## 关键词系统

输入基础关键词 → YouTube Suggest 发现长尾词 → SerpApi 搜索 + YouTube V3 补齐视频/频道/订阅数据 → 规则（或 AI 博彩意图筛选）评分 → 后台查看并导出 CSV。

### 评分规则

每个关键词取前 5 条视频，每个维度最高 5 分，总分最高 20 分（分数越高代表内容空位越大）：

- 标题未完全包含长尾词：每条 +1
- 频道订阅数低于 2,000：每条 +1
- 视频播放量低于 5,000：每条 +1
- 发布时间超过 24 小时：每条 +1

补充说明：

- **输入词也参与评分**：输入词本身纳入待处理列表，Suggest 拓不出词时仍能评估输入词本身。
- **数据不全标记人工复核**：V3 未配置/失败或数据缺失时标记「数据不全」，不给误导分数。
- **SerpApi 限流防护**：按 `SERPAPI_QPS` 节流（默认 1/s），遇 429/5xx 按 `SERPAPI_MAX_RETRIES` 指数退避重试。参数可在全局设置调整。
- **任务控制**：暂停（当前查询结束后停止）、停止（立即停止）、重启（续跑未完成项，不重复查询已完成项）。

---

## 内容生成系统（流程三）

独立模块（后端 `backend/flow3`，菜单「内容生成系统」下：任务管理 / Agent 管理 / 素材库 / 关键词库），单任务产出一个 16:9 1080P 长视频。

### 成片结构

| 段 | 时间 | 画面 | 生成方式 |
|---|---|---|---|
| SegA | 0–10s | Hook 开场（下载引导） | AI 出视频 Prompt → 人工用外部文生视频引擎生成 mp4 → 回传上传 |
| SegB | 10s–旁白结束 | 左右分屏画中画：模糊底图 + Promo Code 文字 + 9:16 录屏 | Remotion 渲染，录屏左右位置按随机种子 |
| SegC | 至总时长 | 尾图 + 呼吸/抖动微动 | AI 生图 → ffmpeg zoompan |

总时长在创建任务时填写；SegC 时长 = 总时长 − 10 − 旁白实际时长。合成后叠加 BGM 混音与像素级防封去重。

### 五个独立 Agent（「Agent 管理」可编辑提示词）

- **Hook 视频文案 Agent**：10 秒强 Hook，核心为「引导下载 App」（加 Telegram 频道下载 / 搜官网注册），台词按任务语言生成
- **语音文案 Agent**：多语言旁白（按任务语言），优惠码自然朗读
- **模糊底图 Agent** / **尾图 Agent**：生图 Prompt
- **元数据 Agent**：标题 + 结构化描述（首段/正文/章节/关键词堆砌/CTA/#tag，目标 3000–4000 字符）+ 高点击封面提示词

占位符规则：`[input]`=关键词、`[language]`=任务语言、`[keywords]`=关键词库（仅元数据）、`[output]`=输出格式说明；`{PROMO_CODE}` 为全局注入。标题/描述/旁白/Hook 台词均按任务 `language` 参数生成（印地英语、巴西葡语、俄语等）。

> **Agent 提示词的真相源**是 `backend/flow3/prompts/<agent_type>.md` 文件（容器启动 `sync_prompts` 读文件覆盖数据库），改提示词需同步 `.md` 文件与数据库，否则重启回滚。

### 多语言 TTS

Edge TTS 免费合成，音色按任务语言自动映射（巴西葡语 `pt-BR-AntonioNeural`、英语 `en-US-GuyNeural`、俄语 `ru-RU-DmitryNeural`、印度英语 `en-IN-PrabhatNeural` 等 12 种），全局设置 `FLOW3_TTS_VOICE` 可手动覆盖；失败降级 ElevenLabs。

### 素材库

- **9:16 手机录屏**：库内保留，所有任务自动取用
- **背景音乐 BGM**：批量上传，任务随机抽 1 个（种子记录可复现）
- **Hook 视频**：批量上传、分组管理、未使用/已使用标签，创建任务时指定或随机取用

### 关键词库

元数据 Agent 描述「关键词堆砌」的数据源，支持 CSV 导入（主词库带搜索量权重 + 长尾词）自动按语言分类，也可手动增删改。

### 使用流程

1. 创建任务（填关键词、语言、总时长、优惠码等）→ 系统生成 Hook Prompt，任务暂停等待上传。
2. 用 Hook Prompt 在外部引擎生成 mp4，在任务列表「上传 Hook」后点「继续」。
3. 系统自动完成：旁白 → 多语言 TTS → 模糊底图 → 尾图 → 元数据 → SegB → SegC → 三段合并 → BGM 混音 + 防封。
4. 完成后「下载」得到 zip（含 `metadata.txt` + 封面 `cover.jpg` + 成品 `final_video.mp4`）。

> AI Key 与模型在「全局设置」维护，不写死代码；AI 调用对偶发断连自动重试；各步骤幂等，重启/续跑不重复消耗额度。

---

## AdsPower 自动化系统

后端 `backend/uploader`，菜单「AdsPower 自动化系统」下三块：

- **AdsPower 浏览器管理**：管理 AdsPower 浏览器环境（`AdsPowerProfile`）
- **IP 管理**：代理 IP 池（`ProxyConfig`，含地理位置信息）
- **任务管理**：自动上传视频到 YouTube（`UploadTask`）——选浏览器环境 → 自动填标题/描述/封面 → 存草稿。状态机 `queued → launching → uploading → draft_saved`（草稿待人工核对发布），上传后回填 `video_url`（供数据分析系统自动关联）。

---

## SMM 面板系统

后端 `backend/smm`，对接第三方 Telegram 刷量面板（AutoLak Cloud），菜单「SMM 面板系统」下：

- **个人中心**：面板账号 CRUD，新增时填 Telegram 数字 ID 自动提取 token 并拉取余额；展示实际余额 / 锁定中 / 剩余可用。
- **任务管理**：
  - **普通刷量任务**：填 YouTube 链接、关键词、人数等提交下单，状态/进度从面板同步，完成后标记。
  - **轮询刷量任务**：维持 VPH——首次刷量 + 窗口内每小时自动刷随机人数（可跨天直到刷满轮询次数），按最大估算成本锁定余额，支持停止/重启。

数据更新走纯 HTTP 直连（不依赖浏览器），认证靠 `tgUserId` 换取 token。定时同步任务 `sync_smm_task_statuses`（有未完成任务时 30s 一次）与轮询调度 `sync_smm_poll_tasks`（每分钟）。

---

## 当前接口

**关键词系统**（`/api/` 前缀，下同）：
- `POST/GET/DELETE keyword-runs/`、`keyword-runs/bulk_delete/`、`keyword-runs/<id>/{pause,stop,restart}/`
- `GET keyword-results/?run=<id>`、`keyword-results/export/?run=<id>`
- `GET/PUT settings/`（全局设置）
- `suggest-expansions/`（长尾词拓展工具）、`agent-prompts/`

**内容生成系统（流程三）**：
- `flow3-runs/`（创建/列表/删除，`upload_hook`、`resume`、`retry`、`pause`、`stop`、`restart`、`log`、`package` 等 action）
- `flow3-agents/`（含 `run_once` 试运行、`default_prompt`、`models`）
- `flow3-materials/`、`flow3-material-groups/`
- `flow3-keywords/`（关键词库，含 `import_csv` 导入）

**AdsPower 自动化**：
- `adspower-profiles/`、`adspower-proxies/`、`upload-tasks/`

**SMM 面板**：
- `smm-accounts/`（含 `refresh`、`refresh_ua`）、`smm-tasks/`（含 `sync_status`）、`smm-poll-tasks/`（含 `stop`、`restart`）

**数据分析系统 + 首页**：
- `dashboard/summary/`（首页聚合）
- `analytics-videos/`（含 `sync`、`refresh`、`snapshots`）
- `analytics-competitor/`（含 `analyze`）
- `analytics-rank-trackings/`（含 `capture`、`snapshots`）

---

## Git

远程仓库：`git@github.com:qwmessi10/youtube-sys.git`。
