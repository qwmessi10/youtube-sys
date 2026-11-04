# SMM 面板系统 — 需求文档

> 版本：v1.0
> 创建日期：2026-11-04
> 所属系统：youtube-sys
> 关联模块：内容生成系统（flow3，产出视频后自动送刷量）
> 逆向成果：`telegram-re/REVERSE_FINDINGS.md` + `telegram-re/autolak_client.py`

---

## 一、背景与目标

内容生成系统（flow3）产出成片视频后，需要把视频投放到 AutoLak Cloud Bot（Telegram 小程序 SMM 面板）刷量（SEO 搜索、播放、点赞等）。目前只能人工在小程序里手动创建任务。

本系统目标：在后台新增「SMM 面板系统」一级目录，把「管理面板账号 → 创建刷量任务 → 跟踪状态/进度」全流程自动化，相关参数暴露给运营配置。

**逆向已完成**：面板后端 API（`https://atpsv.autolak.in/client`）已破解。token 可通过 `POST /user/publishTelegramAuth` 直接获取（无需浏览器、无需 Telegram 签名）；创建任务 `POST /publish/sendTask`；任务列表/状态/进度 `POST /publish/searchTaskRecord`。均已实测跑通（已真实创建 1 单测试任务）。

---

## 二、关键决策（已拍板）

| # | 议题 | 决策 |
|---|------|------|
| 1 | 账户录入方式 | 运营填 Telegram 数字 ID（tgUserId，可手动获取，见附录），系统自动提取 token + 余额 |
| 2 | 任务状态同步 | **两者结合**：进页刷新 + 手动刷新 + 后台定时同步（**有运行中任务时每 30s 同步，无任务不自动同步**） |
| 3 | UA/Origin/Referer 更新 | 「抓最新 UA 一键更新」：从真实浏览器取当前 UA 覆盖配置，应对 WAF 升级 |
| 4 | 菜单位置 | SMM 面板系统放在 AdsPower 自动化系统下面；实用工具移到最下面 |
| 5 | 全局设置 | 按系统分组展示（el-tabs），不再一列到底 |
| 6 | UI 一致性 | 复用现有 el-card/el-table/el-tag/el-pagination/el-page-header 模式，独立组件 SmmPanelSystem.vue |
| 7 | 完成后联动 | **仅标记完成，不回填数据**（播放量等后续做独立数据面板） |

---

## 三、菜单与导航调整

调整后左侧菜单顺序（App.vue）：

```
关键词系统
内容生成系统
AdsPower 自动化系统
SMM 面板系统            ← 新增一级目录（放 AdsPower 下面）
  ├ 个人中心   (smm-accounts)
  └ 任务管理   (smm-tasks)
全局设置
实用工具                ← 从第 3 位移到最后
数据抓取系统（后续，disabled）
```

- `menuTitles` 新增：`smm-accounts: "SMM 面板 - 个人中心"`、`smm-tasks: "SMM 面板 - 任务管理"`。
- `default-openeds` 加入 `smm`。

---

## 四、功能需求

### 4.1 个人中心（账户管理）

**列表字段**：Telegram 用户名（@xxx）、tgUserId、面板昵称、余额（₹）、token 状态（有效/失效）、更新时间。

**功能**：
1. 新增账户：弹窗填 `tgUserId`（Telegram 数字 ID，运营手动获取，方式见附录；可选填 @用户名仅作展示）→ 系统调 `publishTelegramAuth` 提取 token + 余额 → 存库。
2. 编辑账户：改备注/用户名等；token 不可手动改（自动管理）。
3. 删除账户：二次确认。
4. 「刷新余额」：单条 + 批量，实时调面板 `get_balance` 回填。
5. 「校验 token」：调 `get_balance` 探测，失效则标记并提示重新提取。

### 4.2 任务管理

**列表字段**：任务号（showId）、所属账号、YouTube 链接、关键词、人数、成本、状态（标签色）、进度（已完成/总数 + 成功率）、创建时间、结束时间。

**功能**：
1. 新增任务（子页/弹窗，与关键词系统「新增任务」一致）：暴露参数表单 ——
   - 所属账号（下拉选个人中心的账户）
   - YouTube 链接（必填）
   - 关键词（必填，多个用 `;` 分隔）
   - 刷量人数（必填，≥300 有折扣提示）
   - 每人奖励 ₹（默认 2，≥2）
   - 服务类型（下拉：SEO 等，默认 SEO=type 42）
   - 结束时间（日期时间选择器，默认 +48h，按印度时区）
   - 其余（评论数、允许直播等）用默认值
2. 提交：调 `sendTask`，成功后存库（含面板 taskId/showId），列表实时展示。
3. 状态/进度：展示面板实时 `status` + `completeSize/totalUsers` + `successRate`。
4. 完成标记：面板状态为 Completed 时，本地状态同步为「已完成」（标签绿色）。
5. 删除任务：仅删本地记录（不撤销面板任务，需提示）。

### 4.3 全局设置

1. **分组展示**（el-tabs 或折叠面板），分组见「五、分类方案」。
2. **SMM 面板分组**新增字段：`AUTOLAK_API_BASE`、`AUTOLAK_UA`、`AUTOLAK_ORIGIN`、`AUTOLAK_REFERER`。
3. **「一键更新 UA/Origin/Referer」按钮**：从真实浏览器（Playwright）取当前 `navigator.userAgent` 等最新值，覆盖对应设置项；无浏览器时用内置最新 Chrome UA 兜底。
4. **「测试连通性」按钮**：调 `get_balance` 探测直连是否被 WAF 拦，返回结果。

---

## 五、全局设置分类方案

| 分组 | 现有 key | 说明 |
|------|----------|------|
| 关键词系统 | SERPAPI_API_KEY、YOUTUBE_API_KEY、SERPAPI_QPS、SERPAPI_MAX_RETRIES | |
| AI 模型 | AI_BASE_URL、AI_API_KEY、AI_MODEL、AI_MODELS、AI_MODEL_KEYS、GEMINI_IMAGE_API_KEY、GEMINI_IMAGE_MODEL | |
| 内容生成（语音/渲染） | TTS_PROVIDER、TTS_VOICE、ELEVENLABS_API_KEY、ELEVENLABS_VOICE_ID、REMOTION_RENDER_URL | |
| AdsPower 自动化 | ADSPOWER_API_KEY、ADSPOWER_API_BASE、ADSPOWER_API_RATE_LIMIT、UPLOADER_AGENT_TOKEN、UPLOADER_TASK_LOCK_TIMEOUT_MINUTES、IP2LOCATION_API_KEY | |
| SMM 面板（新增） | AUTOLAK_API_BASE、AUTOLAK_UA、AUTOLAK_ORIGIN、AUTOLAK_REFERER | |

实现：给 `GlobalSetting` 增加 `category` 字段（或按 key 前缀归类），前端按分组渲染。为兼容历史数据，默认按前缀映射分组。

---

## 六、数据模型（后端新建 `smm` app）

### SMMAccount（个人中心账号）
| 字段 | 类型 | 说明 |
|------|------|------|
| username | CharField(unique) | Telegram @用户名（运营填） |
| tg_user_id | CharField(unique) | Telegram 数字 ID |
| first_name / last_name | CharField | Telegram 昵称 |
| panel_user_name | CharField | 面板内部用户名（接口返回） |
| token | CharField | 面板登录 token |
| user_identifier | CharField | 面板 Identifier |
| balance | DecimalField | 缓存余额，可刷新 |
| status | CharField | active / token_invalid |
| created_at / updated_at | | |

### SMMTask（刷量任务）
| 字段 | 类型 | 说明 |
|------|------|------|
| account | FK(SMMAccount) | 所属账号 |
| panel_task_id | CharField(unique) | 面板 taskId |
| show_id | CharField | 面板任务号（如 YTSEO4775Взлома） |
| youtube_link | CharField | 视频链接 |
| key_words | CharField | 关键词（`;` 分隔） |
| total_user | IntField | 人数 |
| per_user | DecimalField | 每人奖励 ₹ |
| task_type | IntField | 服务类型，默认 42（SEO） |
| plant_form | IntField | 平台，默认 1（Youtube） |
| comment_num | IntField | 评论数，默认 1 |
| end_time | CharField | 结束时间（面板印度时区） |
| cost | DecimalField | 成本 |
| status | CharField | 本地状态 pending/running/completed/failed |
| panel_status | CharField | 面板原始状态字符串 |
| progress | JSONField | {pending_users, complete_size, success_rate, fail_rate, fail_num} |
| created_at / updated_at | | |

---

## 七、接口设计（后端）

复用 `autolak_client.py` 的封装（纯标准库，已含 UA/Origin/Referer + token 头）。

- `GET/POST /api/smm-accounts/` + `POST /api/smm-accounts/{id}/refresh/`（刷新余额 + 校验 token）
- `GET/POST /api/smm-tasks/` + `POST /api/smm-tasks/{id}/sync_status/`（拉面板最新状态）
- `POST /api/smm/refresh-ua/`（一键更新 UA/Origin/Referer）
- 认证：沿用现有 JWT/Session（与其它系统一致）

---

## 八、关键流程

### 8.1 新增账户
1. 运营填 tgUserId（数字 ID，手动获取）。
2. 后端调 `publishTelegramAuth`（body 仅需 `tgUserId`，名字可空）→ token + userIdentifier + panel_user_name。
3. 调 `get_balance` → 余额。
4. 落库并返回。

### 8.2 新建任务
1. 运营填参数（账号、链接、关键词、人数、每人奖励、类型、结束时间）。
2. 后端按该账号的 token 调 `sendTask`。
3. 成功 → 存库（taskId/showId/cost 等）→ 列表展示。

### 8.3 状态同步
1. 前端进入任务管理页 / 点「刷新」→ 后端批量调 `searchTaskRecord` → 回填 status/progress。
2. 后台定时任务：**仅当存在「未完成」任务时**每 30s 同步一次状态，Completed 则本地标记完成；无未完成任务则不自动同步。

---

## 九、风险与依赖

| 风险 | 说明 | 应对 |
|------|------|------|
| 抓最新 UA 依赖浏览器 | 一键更新 UA 需从真实浏览器取 UA | 无浏览器时用内置最新 Chrome UA 兜底 |
| 服务器 IP 被 WAF 拦 | 数据中心 IP 比住宅 IP 更易被 Cloudflare 拦 | 部署后测连通，必要时走住宅代理 |
| token 失效 | 面板 token 可能过期 | 校验 token + 一键重新提取 |
| 面板接口变更 | 第三方无承诺，可能改接口 | 客户端集中封装，变更只改一处 |
| 状态枚举不全 | 面板 status 全值需实测 | 实现阶段抓全值做映射 |

---

## 十、待确认项

1. 「抓最新 UA」所依赖的浏览器部署位置：继续跑在宿主机（同 AdsPower 执行器），还是搬到服务器？（其余均已确认）

---

## 附录：如何手动获取 Telegram 数字 ID（tgUserId）

新增账户时只需提供 `tgUserId`（数字 ID），获取方式任选其一：

1. **@userinfobot（推荐）**：Telegram 搜索 `@userinfobot` → 发任意消息 → 机器人回复你的数字 ID（形如 `Id: 8196195827`）。
2. **Telegram 网页版收藏夹**：打开 `web.telegram.org` → 点左侧「Saved Messages」→ 地址栏 `#` 后那串数字即你的 ID。
3. 数字 ID 每账号固定唯一；每加一个新账号，登录该账号后按方法 1 取一次即可。
