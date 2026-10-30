# AdsPower 自动化上传系统 — 需求文档

> 版本：v1.1（开发阶段 / 已完成本机 API 实测）
> 创建日期：2026-10-30
> 更新日期：2026-10-30（付费账号验证通过，确定走 API 自动同步路线）
> 所属系统：youtube-sys
> 关联模块：内容生成系统（flow3）

---

## 一、背景与目标

内容生成系统（flow3）已能产出成片视频及结构化元数据（标题 / 描述 / 封面）。当前最后一公里——把成片上传到 YouTube——仍需人工：手动下载 zip、打开 AdsPower 客户端、逐个浏览器登录 YouTube Studio、手动填标题描述封面、发布。

本系统的目标：**在现有后台中新增一套 AdsPower 自动化上传能力**，把「选任务 → 选浏览器 → 自动填好元数据 → 上传」这条链路自动化，人工只在最后发布环节把关（开发阶段先做到"草稿"，不自动发布）。

### 核心诉求（来自用户拍板）

1. 后台能接入本机 AdsPower，直接查看浏览器环境信息，**免去打开 AdsPower 客户端**。
2. 一套自动化上传任务的增删改查。
3. flow3 完成的任务，可直接把成片 + 元数据送入选中的浏览器上传。
4. 浏览器自动化上传到 YouTube，自动把元数据填入标题 / 描述 / 封面。
5. **开发阶段只做到"保存草稿"**，人工去浏览器核对无误后再手动发布；后续再开启全自动发布。
6. 上传完成（或草稿建好）后，把 YouTube 视频链接回填到系统任务。

---

## 二、关键决策（已拍板）

| # | 议题 | 决策 |
|---|------|------|
| 1 | 执行器部署位置 | **宿主独立进程（方案 A）**：不进 Docker，直接跑在装了 AdsPower 的 mac 上 |
| 2 | AdsPower 所在机器 | 与 Docker 系统**同一台 mac** |
| 3 | 上传节奏 | 暂时**一天一个**，不做定时 / 限速逻辑 |
| 4 | YouTube 登录态 | 浏览器里 YT 账号**已人工登录**，系统不做自动登录 |
| 5 | 开发阶段发布策略 | **只保存草稿（Save draft），不自动发布**，人工核对后手动发布 |
| 6 | AdsPower 账号 | **已开通付费订阅**，列表类接口（user/list、group/list）已解禁 |
| 7 | 浏览器接入方式 | **走本地 API 自动同步**（非手动录入），实测通过 |

---

## 二、补充 · 本机 API 实测结论（2026-10-30）

在本机（装有 AdsPower 的 mac）用提供的 API Key 实测，确认方案可落地：

| 接口 | 结果 | 说明 |
|------|------|------|
| `GET /status` | ✅ `{"code":0,"msg":"success"}` | 端口 50325 正常，Key 有效 |
| `GET /api/v1/user/list` | ✅ 付费后返回完整环境列表 | 浏览器管理页的核心数据源 |
| `GET /api/v1/group/list` | ✅ 返回全部分组 | 共 7 个分组（huo / B端 / 跨境电商-tiktok 等） |
| `GET /api/v1/browser/active` | ✅ 返回 `Inactive/Active` | 上传前查浏览器开没开 |

**user/list 返回的真实字段**（已据此定稿数据模型）：

```
user_id, name, serial_number, group_id, group_name, domain_name,
username, remark, last_open_time, created_time,
ip, ip_country, ipchecker,
user_proxy_config: { proxy_soft, proxy_type, proxy_host, proxy_port,
                     proxy_user, proxy_password, proxy_url, latest_ip },
platform_account: [{ domain_name, login_user, password }]
```

> 观察到的现网环境示例：`x-3`（socks5 → 31.58.227.237:45001，印度 IP，绑 accounts.google.com）、`G-3`（香港 IP）等，分组 `huo`。socks5 已直接配在 profile 的 `user_proxy_config` 里，**IP 隔离由 AdsPower 注入，执行器无需任何切 IP 操作**，印证了原方案。

> ⚠️ 代理账号密码等敏感字段会出现在 `user/list` 返回中。后端缓存时**只存代理摘要**（类型 + IP 末段），不落库完整凭据；前端详情页对密码脱敏。

---

## 三、架构设计

### 3.1 为什么要独立执行器（而非塞进现有 worker）

- AdsPower 本地 API 只监听**宿主机** `localhost:50325`；现有 backend / worker 跑在 Docker 容器里，**容器网络访问不到宿主的 AdsPower**。
- Playwright 要接管的是 AdsPower 启动的**带 GUI 的 Chromium**，容器内无头环境碰不到。
- 因此上传能力做成一个**独立的宿主进程（Uploader Agent）**，与 Docker 系统通过 HTTP API 通信：系统负责"排任务、存结果"，执行器负责"干活"。

### 3.2 整体拓扑

```
┌──────────────────────── 同一台 mac ────────────────────────┐
│                                                            │
│  ┌─────────────── Docker 容器 ───────────────┐             │
│  │  backend(Django+DRF)  worker(Celery)      │             │
│  │  db(pg)  redis  render  frontend(:8080)   │             │
│  │  共享卷 media_data → /app/media            │             │
│  └───────────────┬───────────────────────────┘             │
│                  │ HTTP (127.0.0.1:8000)                    │
│                  │  ① 领任务  ② 拉文件  ③ 回调结果           │
│  ┌───────────────▼─────────────── 宿主进程 ──────────────┐  │
│  │  Uploader Agent (独立 Python 进程，非容器)             │  │
│  │    - 轮询后端上传任务队列                              │  │
│  │    - 调 AdsPower 本地 API 起/停浏览器                  │  │
│  │    - Playwright 接管浏览器 → YouTube Studio            │  │
│  └───────────────┬───────────────────────────────────────┘  │
│                  │ HTTP (local.adspower.net:50325)           │
│  ┌───────────────▼───────────────┐                          │
│  │  AdsPower 客户端 + 各 profile  │                          │
│  │  每个 profile 绑定独立 socks5  │                          │
│  └────────────────────────────────┘                          │
└────────────────────────────────────────────────────────────┘
```

### 3.3 职责边界

| 组件 | 职责 |
|------|------|
| **backend（容器）** | 新增数据模型、DRF 接口；缓存 AdsPower 环境列表；上传任务 CRUD；提供"任务 payload"给执行器；接收执行器回调 |
| **frontend（容器）** | 新增一级菜单「AdsPower 自动化系统」下两个二级页：浏览器管理、任务管理 |
| **Uploader Agent（宿主）** | 轮询领任务 → 拉文件 → 调 AdsPower → Playwright 填元数据存草稿 → 回调结果 |
| **AdsPower（宿主）** | 提供浏览器环境 + 代理注入，启停由执行器通过本地 API 控制 |

---

## 四、数据模型（backend，建议新建 app：`uploader`）

与 flow3 隔离，新建一个 Django app `uploader`，含两张表。

### 4.1 `AdsPowerProfile`（浏览器环境缓存）

后端定时/手动从 AdsPower 本地 API 拉取环境列表，缓存到本表，供前端展示，避免每次都打客户端。

| 字段 | 类型 | 说明 |
|------|------|------|
| `user_id` | CharField | AdsPower 环境 ID（API 返回的 `user_id`，唯一） |
| `serial_number` | CharField | 环境编号（AdsPower 的"序号"） |
| `name` | CharField | 环境名称 |
| `group_name` | CharField | 所属分组名 |
| `domain_name` | CharField | 绑定平台（youtube.com 等） |
| `username` | CharField | 环境内账号（如有，脱敏展示） |
| `remark` | TextField | 备注 |
| `proxy_summary` | CharField | 代理摘要（类型 + IP 末段，不存完整凭据） |
| `last_open_time` | CharField | AdsPower 返回的最近打开时间 |
| `raw` | JSONField | 原始返回，便于"查看详情"直接展示 |
| `synced_at` | DateTimeField | 最近一次同步时间 |

> 说明："查看浏览器详情，就和打开 AdsPower 一样"——通过 `raw` 字段把 AdsPower 返回的完整环境信息在前端展开展示；"像打开浏览器一样操作"则通过调用 `browser/start` 直接拉起该环境的真实 Chromium（见接口）。

### 4.2 `UploadTask`（上传任务）

| 字段 | 类型 | 说明 |
|------|------|------|
| `id` | AutoField | 任务 ID |
| `name` | CharField | 任务备注名（可空，默认取视频标题） |
| `source_run` | FK → flow3.Flow3Run | 关联的 flow3 成品任务（手动创建时可为空） |
| `profile` | FK → AdsPowerProfile | 目标浏览器环境 |
| `video_path` | CharField | 视频文件路径 / 下载 URL（来源 flow3 的 `rendered_file`） |
| `title` | CharField(500) | 视频标题（来源 flow3 的 `title`，可编辑） |
| `description` | TextField | 视频描述（来源 flow3 的 `description`，可编辑） |
| `cover_path` | CharField | 封面图路径（来源 flow3 的 `thumbnail_file`，可空） |
| `publish_mode` | CharField | `draft`（开发阶段默认）/ `public` / `unlisted` / `private` |
| `status` | CharField | 状态机，见下 |
| `video_url` | CharField | 上传后回填的 YouTube 链接 |
| `retry_count` | IntegerField | 重试次数 |
| `error_message` | TextField | 失败原因 |
| `upload_log` | JSONField | 每步耗时 / 截图路径 / YT 返回（复用 flow3 的 run_log 模式） |
| `created_at` / `updated_at` / `finished_at` | DateTime | 时间戳 |

**状态机**：

```
queued（排队）
  → launching（起浏览器 + 接管）
  → uploading（上传视频文件 + 填元数据）
  → draft_saved（草稿已保存，开发阶段终态，等人工核对）
  → [人工确认后]（后续阶段）→ publishing → completed
  → failed（任一步失败）
```

> 开发阶段终点是 `draft_saved`：执行器把视频传好、标题 / 描述 / 封面填好、保存为草稿，回填草稿对应的视频链接，然后停止，等你人工去 Studio 核对后手动发布。

---

## 五、后端接口（DRF）

统一挂在 `/api/` 下，风格与现有 flow3 接口一致。

### 5.1 浏览器管理

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/adspower-profiles/` | 列出缓存的环境（分页，支持按分组 / 名称过滤） |
| GET | `/api/adspower-profiles/{user_id}/` | 单个环境详情（返回 `raw` 全量字段） |
| POST | `/api/adspower-profiles/sync/` | 触发后端从 AdsPower API 重新拉取并更新缓存 |
| POST | `/api/adspower-profiles/{user_id}/open/` | 在宿主拉起该环境的真实浏览器（经执行器代理调用 `browser/start`） |

### 5.2 任务管理

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/upload-tasks/` | 任务列表（分页 + 状态过滤） |
| POST | `/api/upload-tasks/` | 创建任务（手动：填 video/title/desc/cover + profile） |
| GET | `/api/upload-tasks/{id}/` | 任务详情 |
| PATCH | `/api/upload-tasks/{id}/` | 编辑任务（queued 状态下可改标题 / 描述 / profile） |
| DELETE | `/api/upload-tasks/{id}/` | 删除任务 |
| POST | `/api/upload-tasks/from-run/` | **从 flow3 已完成任务创建上传任务**（传 `run_id` + `profile` + `publish_mode`，后端自动填充 video/title/desc/cover） |
| POST | `/api/upload-tasks/{id}/retry/` | 失败任务重试（从失败点续跑） |

### 5.3 执行器专用接口（供宿主 Uploader Agent 调用，需 token 鉴权）

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/upload-tasks/next/` | 领取下一个 `queued` 任务（原子置为 `launching`） |
| GET | `/api/upload-tasks/{id}/payload/` | 返回结构化上传数据 + 文件下载直链（**不走 zip**） |
| POST | `/api/upload-tasks/{id}/callback/` | 回调上传结果：`{status, video_url, upload_log, error_message}` |
| POST | `/api/upload-tasks/{id}/progress/` | 上报中间进度 / 截图路径（可选） |

> **重要优化**：执行器拿数据走 `payload` 接口读结构化字段（title/description/video下载链/cover下载链），**不再解析 zip**。flow3 的 `Flow3Run` 已经把这些存成独立字段，zip 仅保留给人工下载场景，两条路径解耦。

---

## 六、前端（Vue3）

### 6.1 导航结构

新增一级菜单 **「AdsPower 自动化系统」**，下挂两个二级页：

```
AdsPower 自动化系统
├── AdsPower 浏览器管理
└── 任务管理
```

### 6.2 AdsPower 浏览器管理页

- 顶部「同步」按钮：触发 `POST /adspower-profiles/sync/`，后端调 `user/list` + `group/list` 全量拉取并更新缓存（付费账号已验证可用）。
- **分组筛选下拉**：数据来自 `group/list`（现网 7 个分组：Facebook投放 / huo / 助为科技 / ffl / B端 / 跨境电商-tiktok / Reddit营销）。
- 表格列：序号（serial_number）、名称、分组、绑定平台（domain_name）、IP / 国家、代理摘要、最近打开时间、操作。
- 操作列：
  - **查看详情**：弹窗展示该环境完整信息（展开 `raw`，代理密码脱敏），等同于在 AdsPower 客户端看环境配置。
  - **打开浏览器**：调 `/{user_id}/open/`，在宿主拉起真实 Chromium（满足"懒得开客户端也能开浏览器"）。

### 6.3 任务管理页

- 列表：任务名、关联视频标题、目标浏览器、状态、视频链接、创建时间、操作。
- **手动创建任务**：表单填 视频文件 / 标题 / 描述 / 封面 / 选 profile / 发布模式（开发阶段固定 `draft`）。
- 操作列：查看详情（含 `upload_log` 分步日志 + 截图）、重试、删除。
- 状态用色块区分（queued / launching / uploading / draft_saved / failed）。

### 6.4 内容生成系统任务管理页（flow3）增强

- 在 flow3 任务列表中，对 `completed` 的任务，操作列新增 **「上传到 YouTube」** 按钮。
- 点击弹窗：选择目标 AdsPower 浏览器 + 发布模式 → 调 `POST /upload-tasks/from-run/` 创建上传任务，跳转到任务管理页查看进度。

---

## 七、Uploader Agent（宿主独立进程）

### 7.1 运行方式

- 一个独立 Python 脚本 / 小项目（建议目录 `uploader-agent/`，**不进 Docker**）。
- 依赖：`requests`（调后端 + AdsPower HTTP API）、`playwright`（接管浏览器）。
- 启动：`python agent.py`，常驻轮询；配置项（后端地址、token、AdsPower API Key、轮询间隔）放 `.env`。
- **AdsPower 调用层选型**：直连本地 HTTP API（`local.adspower.net:50325`，已实测通），不依赖 `adspower-browser` CLI / MCP。
  - CLI（`ads ...`）与 MCP（`local-api-mcp-typescript`）本质是同一套 API 的封装，且主要面向"AI 助手交互式调用"的场景；生产执行器直连 HTTP 更可控、依赖更少。CLI 可留作人工排障时的手动工具。

### 7.2 执行流程（单任务）

```
1. GET /upload-tasks/next/          领一个 queued 任务（后端原子置 launching）
2. GET /upload-tasks/{id}/payload/  拿 title/desc/video_url/cover_url
3. 下载 video、cover 到本地临时目录
4. AdsPower: GET /api/v1/browser/active?user_id=xxx   查是否已开
5. AdsPower: GET /api/v1/browser/start?user_id=xxx    起浏览器，拿 CDP ws 端口
   （该 profile 自带绑定的 socks5，IP 自动注入，无需执行器切 IP）
6. Playwright connect_over_cdp(ws端口) 接管浏览器
7. 打开 studio.youtube.com → 点上传 → 选视频文件
8. 等待上传进度 → 填标题 / 描述 → 上传封面图
9. 【开发阶段】停在"保存草稿"，不点发布；抓取草稿视频链接
10. AdsPower: GET /api/v1/browser/stop?user_id=xxx    关浏览器
11. POST /upload-tasks/{id}/callback/  回填 {status: draft_saved, video_url, upload_log}
12. 回到步骤 1
```

### 7.3 可靠性要求

- **串行执行**：同一时刻只处理一个任务（一天一个，天然满足；执行器端加进程锁兜底）。
- **分步截图**：每个关键步骤截图存本地并上报路径，失败时能回看卡在哪。
- **失败分类**：网络错（可重试）/ DOM 变更（需人工）/ 账号异常（停该号）。不无脑重试。
- **AdsPower 限频**：本地 API 每秒最多 1 次请求，调用间加节流。
- **选择器健壮**：YouTube Studio DOM 多 iframe、异步渲染且常改版，用显式等待 + 多重定位兜底。

---

## 八、AdsPower 本地 API 速查（实现参考）

- **访问地址**：`http://local.adspower.net:50325` 或 `http://localhost:50325`
  （准确地址可读客户端缓存目录下的 `local_api` 文件）
- **鉴权**：开启"安全校验"后，请求头加 `Authorization: Bearer <api-key>`
- **限频**：每个接口每秒最多 1 次请求

| 功能 | 方法 | 路径 |
|------|------|------|
| 查询环境列表 | GET | `/api/v1/user/list` |
| 查询分组 | GET | `/api/v1/group/list` |
| 启动浏览器 | GET | `/api/v1/browser/start?user_id=xxx` |
| 停止浏览器 | GET | `/api/v1/browser/stop?user_id=xxx` |
| 查询浏览器打开状态 | GET | `/api/v1/browser/active?user_id=xxx` |
| 检测代理 | POST | `/api/v1/user/proxy/check`（视版本） |

`browser/start` 返回里含 `ws.selenium` / `ws.puppeteer`（CDP 调试端口）与 `debug_port`，Playwright 用 `connect_over_cdp` 接管。

---

## 九、凭据与前置条件清单

> 本节记录系统实际要用到的凭据与配置。以下均为用户的**内部测试项目**凭据，不涉及对外安全问题，直接写入文档便于实现时参照。实现时统一存入后端全局设置（复用现有 `GlobalSetting` key-value 机制），不硬编码到代码。

### 9.1 已提供的凭据（直接可用）

| 配置项（GlobalSetting key） | 值 | 用途 | 状态 |
|------|------|------|------|
| `ADSPOWER_API_KEY` | `fb2a85260cf8879965cb02c7f9cda600002690540592a67e` | 本地 API 鉴权 Bearer Token | ✅ 已实测可用 |
| `ADSPOWER_API_BASE` | `http://local.adspower.net:50325` | 本地 API 基址（或 `http://localhost:50325`） | ✅ 已实测可用 |
| `ADSPOWER_API_RATE_LIMIT` | `1`（次/秒） | 执行器调用节流 | 固定值 |

### 9.2 前置条件（均已满足 ✅）

| # | 条件 | 状态 | 备注 |
|---|------|------|------|
| 1 | AdsPower 本地 API 已开启（端口 50325） | ✅ | `/status` 实测返回 success |
| 2 | AdsPower 账号已付费订阅 | ✅ | `user/list`、`group/list` 已解禁 |
| 3 | 各浏览器已登录 YouTube | ✅ | 系统不做自动登录 |
| 4 | 各 profile 已绑定对应 socks5 | ✅ | 实测 `x-3` 等已配 socks5，IP 由 AdsPower 注入 |
| 5 | Docker 系统与 AdsPower 同机 | ✅ | 执行器在宿主直连本地 API |

### 9.3 关于你提供的 CLI / Skill / MCP（结论）

你给的四样东西，用途各不相同，这里明确哪些进系统、哪些不用：

| 东西 | 是什么 | 本项目是否采用 |
|------|--------|----------------|
| **API Key** | 本地 API 鉴权凭证 | ✅ **采用**，核心凭据 |
| **adspower CLI**（`npm i -g adspower-browser`，`ads ...`） | 本地 API 的命令行封装 | ⬜ 不进生产执行器（执行器直连 HTTP 更可控）；保留作人工排障工具 |
| **Claude Skill**（`npx skills add .../adspower-browser`） | 给 Cursor/Claude 等 **AI 助手**的使用说明 | ❌ 不采用（面向交互式 AI，非生产运行时） |
| **Claude Code MCP**（`claude mcp add adspower-local-api`） | 把 AdsPower 能力挂给 **Claude Code** 当工具 | ❌ 不采用（同上；仅我本地开发调试时可能临时用） |

> 一句话：**系统只需要 API Key + 直连 HTTP API**。CLI/Skill/MCP 都是面向"AI 助手"的外围封装，不是生产系统的运行时依赖。

### 9.4 仍需你在实现阶段配合的一件事

- 执行器要跑 Playwright，首次需装浏览器驱动：`playwright install chromium`。我会写进执行器的安装脚本，你按一条命令执行即可（一次性）。

### 9.5 可选 / 后续项

- 若未来要**全自动发布**（跳过人工核对），需明确每个号的发布策略（公开 / 不公开 / 定时）。
- 若未来要**多台机器 / 多 AdsPower 节点**，执行器支持多实例，届时再配。

---

## 十、开发阶段边界（务必对齐）

| 项目 | 开发阶段 | 后续阶段 |
|------|----------|----------|
| 发布动作 | **只存草稿（draft），不发布** | 人工确认后开启自动发布 |
| 上传节奏 | 一天一个，手动触发 | 可加定时 / 限速 / 批量 |
| 回填链接 | 回填草稿对应链接，标记 `draft_saved` | 发布后回填正式链接 `completed` |
| 账号登录 | 人工预先登录 | 维持人工（自动登录风险高，不建议） |

---

## 十一、建议里程碑

1. **M1 — 浏览器管理**：后端 `AdsPowerProfile` 模型 + 同步接口 + 执行器代理 `start/stop/active`；前端浏览器管理页（同步 / 查看详情 / 打开浏览器）。先打通"看得到、开得起"。
2. **M2 — 任务 CRUD**：`UploadTask` 模型 + DRF 接口 + 前端任务管理页（手动创建 / 列表 / 详情）+ flow3 「上传到 YouTube」入口。
3. **M3 — 执行器上传到草稿**：Uploader Agent 骨架 → 领任务 → AdsPower 起浏览器 → Playwright 上传视频 + 填元数据 → **存草稿** → 回填链接。核心闭环。
4. **M4 — 健壮性**：分步截图、失败分类重试、日志可视化。
5. **M5（后续）**：全自动发布开关、定时 / 限速、多节点。

---

## 十二、待确认 / 风险提示

- **YouTube Studio 改版风险**：UI 自动化天然脆弱，选择器需持续维护。建议 M3 做好截图留证，便于快速修复。
- **封面规格**：YT 封面要求 1280×720、<2MB、jpg/png。flow3 生成的 `thumbnail_file` 需校验 / 转码达标，否则 Studio 会拒。上传前执行器做一次尺寸校验。
- **草稿链接时效**：草稿阶段的视频 URL 在你发布前仅自己可见，属正常。
- **一机单点**：当前 AdsPower 与 Docker 同机，执行器挂了上传就停。一天一个量级可接受，后续可加健康检查 + 告警。
- **代理凭据处理**：`user/list` 返回含 socks5 账号密码（如 `x-3` 的 proxy_user/proxy_password）。后端缓存只存摘要、前端脱敏，避免凭据在日志 / 界面泄露（虽为内部项目，仍按规范处理）。

---

## 十三、实施状态（2026-10-30 开发完成）

### 已完成并验证

**后端（新 app `backend/uploader/`）**
- 模型：`AdsPowerProfile`（环境缓存，代理密码脱敏）、`UploadTask`（状态机 queued→launching→uploading→draft_saved→failed）。
- AdsPower 本地 API 客户端 `services.py`：status / user-list / group-list / browser start-stop-active，含每秒限频节流 + Bearer 鉴权。
- 环境同步 `sync_profiles()`：翻页全量拉取 → 更新缓存（实测同步到 7 个环境、7 个分组）。
- DRF 接口：
  - `GET/POST /api/adspower-profiles/`（列表 / sync / groups / api_status）、`{user_id}/`（详情 / open / close / active）。
  - `GET/POST /api/upload-tasks/`（CRUD）、`from-run`（从 flow3 成品创建，实测自动填充标题/视频/封面路径）、`retry`。
  - 执行器专用：`next`（原子领任务）、`payload`（结构化数据+下载直链，不走 zip）、`callback`、`progress`，`X-Agent-Token` 鉴权。
- 全局设置新增 key：`ADSPOWER_API_KEY` / `ADSPOWER_API_BASE` / `ADSPOWER_API_RATE_LIMIT` / `UPLOADER_AGENT_TOKEN`（已预置可用值）。

**前端（`frontend/src/components/AdsPowerSystem.vue`）**
- 新增一级菜单「AdsPower 自动化系统」→ 二级页「AdsPower 浏览器管理」+「任务管理」。
- 浏览器管理：同步、分组筛选、搜索、详情弹窗（展开 raw）、打开 / 关闭浏览器。
- 任务管理：新建任务（选 profile + 上传视频/填路径 + 封面 + 发布模式）、列表、状态筛选、日志抽屉（时间线）、重试、删除。
- flow3 任务管理页：completed 任务加「上传YouTube」按钮 → 弹窗选浏览器 → `from-run` 建任务。

**执行器（`uploader-agent/`，宿主独立进程，不进 Docker）**
- `config.py` / `adspower_client.py` / `backend_client.py` / `youtube_uploader.py` / `agent.py` + README + requirements + .env.example。
- 主循环：领任务 → 下载视频/封面 → AdsPower 起浏览器 → Playwright `connect_over_cdp` 接管 → YouTube Studio 上传 + 填标题/描述/封面 → **保存草稿（DRAFT_ONLY=True）** → 抓链接回调 → 关浏览器。
- YouTube Studio 自动化用多重选择器兜底 + 显式等待 + 每步截图。

### 真机联调结果（测试浏览器 x-3 / user_id=k1aqyue1）
- ✅ 后端 → AdsPower：`local.adspower.net:50325` 在 Docker 容器内也可直连（AdsPower 公网 DNS，非 127.0.0.1），sync 正常。
- ✅ AdsPower `browser/start` x-3 → 取得 CDP endpoint `ws://127.0.0.1:63219/...`。
- ✅ Playwright `connect_over_cdp` 成功接管 x-3，打开 Studio 跳转到频道面板（已登录，52 万订阅频道），右上角 Create 上传入口可见。
- ⏸ **完整上传未执行**：真跑会在真实频道产生草稿，留给用户知情后手动触发 `python agent.py`。

### 部署提示
- backend/worker 镜像已增量固化（含 uploader app）；`uploader.0001_initial` 迁移已应用。
- 执行器首次使用：`cd uploader-agent && python3 -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt && playwright install chromium && cp .env.example .env`。

