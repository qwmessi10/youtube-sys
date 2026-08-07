# Remotion 视频渲染 操作文档（流程一）

> 本文面向不熟悉 Remotion 的使用者，讲清楚：Remotion 是什么、在本系统里干什么、怎么本地预览调样式、怎么批量渲染、Remotion 官方 AI Skills 怎么用、以及部署和排错。
>
> 配套代码在 `render/` 目录；模板本体是 `render/src/PromoVideo.tsx`。另有一份偏「改样式」的速查见 `render/使用说明.md`，本文是更完整的操作手册。

---

## 0. 一分钟理解 Remotion

Remotion 是「**用代码写视频**」的工具：你写一个 React 网页（标题放哪、背景是什么、文字怎么动、配哪段音频），Remotion 用一个无头 Chromium 浏览器把这个网页**逐帧截图**，再用 ffmpeg 拼成 mp4。

它的核心价值就一句话：

> **同一个模板 + 每次喂不同的数据（inputProps）= 批量产出成百上千条不同的视频。**

这正好是流程一「一个模板、每次换元素、批量出片」的诉求。你要关心的只有两件事：

1. **模板长什么样** —— 改 `PromoVideo.tsx`（React + CSS，能所见即所得预览）。
2. **喂什么数据** —— 后端已经自动为每个关键词拼好 `inputProps`，你一般不用管。

---

## 1. 它在整个系统里的位置

流程一（全自动）后台完整链路：

```
关键词
  → 元数据 Agent 生成 标题 / 描述 / 封面提示词
  → Gemini 出封面图（jpg）
  → 分镜 Agent 生成 8+8 分镜脚本 + 每段旁白文案 narration
  → TTS（edge-tts 免费 / ElevenLabs 付费）把旁白文案合成语音（mp3）
  → 【Remotion 渲染服务】把封面 + 文字 + 旁白拼成竖屏成品 mp4   ← 本文主角
  → 成品打包 zip 下载
```

前面几步都在 Python 后端（`worker` 容器）里跑，最后「拼成视频」交给独立的 `render` 容器。

### 为什么单独开一个容器？

Remotion 是 Node.js 生态、依赖无头 Chromium，跟 Python/Django 后端不是一套运行环境。所以单独做一个 Node 容器，后端通过 HTTP 调它：

```
worker 容器  ──HTTP POST /render──▶  render 容器（Node + Chromium + Remotion）
     │                                      │
     └──────── 共享 media 数据卷 ────────────┘
        （封面、旁白 mp3、成品 mp4 都放这里互相传递）
```

关键点：`worker` 和 `render` 都把同一个 `media_data` 卷挂到 `/app/media`。worker 生成的封面/音频，render 直接读得到；render 渲出的成品，worker 也直接拿得到，**不需要来回拷贝文件**。这段在 `docker-compose.yml` 的 `render` 服务里配置。

---

## 2. 目录结构

```
render/
├── Dockerfile          # Node 22 + Chromium 系统库 + 中文/emoji 字体
├── package.json        # 依赖：remotion 全家桶 + express
├── server.mjs          # HTTP 渲染服务：后端调用入口（POST /render）
├── remotion.config.ts  # Remotion 全局配置（主要给 studio 预览用）
├── tsconfig.json
└── src/
    ├── index.ts        # 渲染入口：registerRoot
    ├── Root.tsx        # 声明有哪些「作品(Composition)」、画布尺寸、帧率、时长
    └── PromoVideo.tsx  # ★ 视频模板本体，改样式主要改这里 ★
```

**你 90% 的时间只需要动 `src/PromoVideo.tsx`。**

三个文件的分工：

| 文件 | 作用 | 你会不会改 |
| --- | --- | --- |
| `PromoVideo.tsx` | 模板画面：文字、背景、动画、分镜、音频 | ★ 经常 |
| `Root.tsx` | 注册作品、画布尺寸(1080×1920)、帧率(30fps)、按 `totalDuration` 算时长 | 偶尔（改尺寸/加模板时） |
| `server.mjs` | 起 HTTP 服务、bundle 一次、收到请求调 `renderMedia` 出片、把共享卷路径改写成 HTTP URL | 基本不用改 |

---

## 3. 视频数据（inputProps）字段对照

后端渲染时会 POST 一段 JSON（`inputProps`）给渲染服务。这是模板和后端之间的「契约」，改模板时按这些字段取数据即可。

由 `backend/content_gen/services.py` 的 `render_video()` 拼装，结构如下：

```json
{
  "title": "1xBet Promo Code 2026",
  "keyword": "1xbet promo code",
  "promoCode": "NEW100",
  "coverSrc": "/app/media/content/thumbnails/12_34.jpg",
  "totalDuration": 16,
  "shots": [
    { "index": 1, "duration": 8, "scene": "画面描述", "narration": "旁白文字", "audioSrc": "/app/media/content/narration/12_34_1.mp3" },
    { "index": 2, "duration": 8, "scene": "...", "narration": "...", "audioSrc": "..." }
  ]
}
```

| 字段 | 含义 | 来源 |
| --- | --- | --- |
| `title` | 视频标题（顶部大字） | 元数据 Agent |
| `keyword` | 关键词（标题下黄字） | 任务关键词 |
| `promoCode` | promo code（绿底高亮块，空则不显示） | 任务的 `promo_code` |
| `coverSrc` | 封面图绝对路径，作背景（空则纯色背景） | Gemini 封面 |
| `totalDuration` | 总时长（秒），决定视频帧数 | 各分镜时长之和 |
| `shots[]` | 分镜数组，每段一屏文字 + 一段旁白音频 | 分镜 Agent + TTS |
| `shots[].scene` | 该段画面文字（字幕，优先用 scene，空则用 narration） | 分镜 Agent |
| `shots[].audioSrc` | 该段旁白 mp3 绝对路径（空则该段无声） | TTS |

> **路径改写机制（了解即可，不用改）**：`coverSrc` / `audioSrc` 传进来是容器内绝对路径（`/app/media/...`）。Chromium 出于安全不直接加载 `file://`，所以 `server.mjs` 的 `rewriteMediaPaths()` 会把这些绝对路径改写成 `http://localhost:3000/media/...` 的 HTTP 地址（express 把 media 卷当静态资源托管），Chromium 再通过 HTTP 加载。这一步已处理好。

**模板里 `PromoVideo.tsx` 的 `promoSchema`（zod）定义了这些字段的类型和默认值**，改字段时两边要对齐。

---

## 4. 本地预览调样式（最常用）

Remotion 最好用的就是有个所见即所得的可视化编辑器 **Remotion Studio**：改代码实时刷新预览，不用每次都渲染。

### 4.1 装依赖（只需一次）

在自己电脑上（不是容器里），进入 `render` 目录：

```bash
cd render
npm install
```

> Windows 上 `npm install` 慢，可先换国内镜像：
> `npm config set registry https://registry.npmmirror.com`

### 4.2 启动可视化编辑器

```bash
npm run studio
```

浏览器自动打开 `http://localhost:3000`，左侧选 `PromoVideo`，右侧实时预览。**改 `PromoVideo.tsx` 保存，预览立刻变。**

预览用的假数据是 `PromoVideo.tsx` 里的 `defaultPromoProps`，可随便改成自己的测试内容（改标题、加分镜等）。

### 4.3 改样式的常见位置

`PromoVideo.tsx` 已带中文注释，最常改的几处：

| 想改什么 | 改哪里 |
| --- | --- |
| 标题/关键词/优惠码 的字号、颜色、位置 | `HeaderBlock` 组件里的 `style` |
| 文字入场动画（弹跳/淡入快慢） | `useEntrance` 里的 `spring` / `interpolate` 参数 |
| 背景遮罩深浅 | 主组件里那层 `linear-gradient` 遮罩的 `background` |
| 每段分镜字幕的样式 | `ShotCaption` 组件 |
| 画布尺寸 / 帧率 / 默认时长 | `Root.tsx` 里的 `Composition`（现为 1080×1920、30fps） |

改完存盘即可，不用手动编译。

### 4.4 本地渲一条看效果（可选）

```bash
# 用默认数据渲染
npm run render PromoVideo out.mp4

# 用自定义数据渲染（把 JSON 存成文件）
npx remotion render PromoVideo out.mp4 --props=./my-props.json
```

---

## 5. 批量渲染是怎么实现的

「批量出大量视频」在本系统里**不是你手动跑命令**，而是后端全自动完成的。理解原理即可：

### 5.1 系统内的批量（已实现，日常用这个）

一个流程一任务可以含多个关键词。`worker` 逐个关键词处理：生成元数据 → 封面 → 分镜+旁白文案 → TTS → **调 render 服务渲染**。每个关键词拼出一份不同的 `inputProps`，发给**同一个模板**，于是批量产出各不相同的视频。

对应代码：`backend/content_gen/tasks.py` 的 `_finalize_flow1_item()` → `services.render_video()` → HTTP `POST http://render:3000/render`。

你要做的就是在前端「流程一·全自动任务管理」里创建任务、填多个关键词，剩下的自动跑。

### 5.2 渲染服务的性能设计

- **只 bundle 一次**：`server.mjs` 启动时预热打包模板（`getBundle()`），后续每次渲染复用，不重复打包。
- **多进程 Chromium**：`renderMedia` 开了 `enableMultiProcessOnLinux`，Docker 内渲染更快。
- **串行调用**：worker 逐条调用 render 服务。要更高吞吐可后续加并发，但要控住内存（每个 Chromium 实例吃内存）。

### 5.3 命令行手动批量（调试用）

想脱离系统、自己批量测模板，可以写个小脚本循环调 CLI：

```bash
# 假设有多份 props：props/kw1.json props/kw2.json ...
for f in props/*.json; do
  npx remotion render PromoVideo "out/$(basename "$f" .json).mp4" --props="$f"
done
```

或用 Node 的 SSR API（`server.mjs` 就是这么做的）：`bundle()` 打包一次 → 循环 `selectComposition()` + `renderMedia()` 传不同 `inputProps`。

---

## 6. Remotion 官方 AI Skills（让 AI 帮你写模板）

你不熟悉 Remotion 也没关系，官方提供了给 AI 编程助手用的「Skills」，能让 AI 按最佳实践帮你搭/改模板。

### 6.1 安装

```bash
npx skills add remotion-dev/skills
```

（新建项目时用 `bun create video` 也会问要不要装。）

### 6.2 常用 Skill（在 AI 助手里用斜杠命令触发）

| Skill | 用途 |
| --- | --- |
| `/remotion-best-practices` | 拿不准用哪个时的兜底，涵盖所有其他 skill |
| `/remotion-create` | 新建项目 / 新建作品(Composition) |
| `/remotion-markup` | 写模板：布局、动画、排版、媒体、音频、字体、时间控制 |
| `/remotion-studio` | 启动 Studio 预览 |
| `/remotion-render` | 触发渲染 |
| `/remotion-captions` | 字幕 / subtitles |
| `/remotion-docs` | 搜官方文档、按需拉取最新 API |
| `/remotion-upgrade` | 升级 remotion 及相关包 |

### 6.3 最省事的用法（推荐）

不用自己学 API。直接把 `PromoVideo.tsx` 贴给 AI 助手，用大白话描述想要的效果，例如：

> 「标题从左边滑进来，promo code 做一个放大高亮的脉冲动画，背景加一点缓慢的放大(Ken Burns)」

让 AI 改 `PromoVideo.tsx`，你 `npm run studio` 看预览，不满意继续说。

**建议闭环**：你描述效果 → AI 改 `PromoVideo.tsx` → `npm run studio` 预览 → 反复调 → 满意后 rebuild render 容器（见第 7 节）。

### 6.4 核心概念（改模板前最好懂这三个）

Remotion 动画就靠这三个，看懂基本够用（`/remotion-docs` 或官网可查）：

- `useCurrentFrame()`：当前是第几帧。动画本质是「第 N 帧该长什么样」。
- `interpolate(frame, [0,30], [0,1])`：把帧号映射成数值（如 0→30 帧内透明度从 0 到 1）。
- `spring()`：弹簧动画，做自然的弹入效果（模板里的 `useEntrance` 就用它）。
- `<Sequence from={} durationInFrames={}>`：把某段内容限定在某个时间段播放（模板用它做分镜分段）。
- `<Audio src={}>`：加音频（模板用它逐段播旁白）。

---

## 7. 部署与线上生效

渲染服务跑在 Docker 容器里，**改了 `src/` 下的模板代码后要重建 render 镜像才生效**：

```bash
# 只重建并重启渲染服务
docker compose build render
docker compose up -d render
```

> 和后端一样：改容器里的代码必须 rebuild 镜像。改前端 Vue 不影响它。

首次构建 render 镜像时，`Dockerfile` 会：装 Chromium 系统库和中文/emoji 字体 → `npm install` → `npx remotion browser ensure`（下载匹配的 Chrome Headless Shell）。所以第一次 build 较慢，属正常。

相关全局设置（在「全局设置」页维护，见 `backend`）：

| Key | 说明 | 默认 |
| --- | --- | --- |
| `REMOTION_RENDER_URL` | 渲染服务地址 | `http://render:3000/render` |
| `TTS_PROVIDER` | 旁白引擎 `edge` / `elevenlabs` | `edge` |
| `TTS_VOICE` | 指定音色（留空按语言自动选） | 空 |
| `ELEVENLABS_API_KEY` | ElevenLabs Key（用 elevenlabs 时必填） | 空 |
| `ELEVENLABS_VOICE_ID` | ElevenLabs 音色 | Rachel |

> TTS 是后端能力（`worker` 容器），不在 render 里。edge-tts 免费无 key，已装进后端依赖；ElevenLabs 需自备 Key。

---

## 8. 渲染服务接口（调试用）

render 容器只对内网暴露，`docker-compose.yml` 未映射端口。要本地直接测，可临时加端口映射或进容器 `curl`。

- 健康检查：`GET /health` → `{"ok": true}`
- 渲染：`POST /render`，body：

```json
{
  "inputProps": { "title": "...", "keyword": "...", "promoCode": "...", "coverSrc": "/app/media/...", "totalDuration": 16, "shots": [ ... ] },
  "outPath": "/app/media/content/rendered/12_34.mp4"
}
```

成功返回 `{"ok": true, "outPath": "...", "durationInFrames": 480}`；失败返回 `{"error": "..."}`（HTTP 500）。

`inputProps` 里的 `coverSrc` / `audioSrc` / `outPath` 都用 render 容器可见的绝对路径（共享卷 `/app/media/...`）。

查看日志：

```bash
docker compose logs render --tail 50
```

---

## 9. 排错速查

| 现象 | 可能原因 / 处理 |
| --- | --- |
| 渲染出来黑屏 | `coverSrc` 路径没传对或文件不存在；无封面时应回退纯色背景，检查 media 卷是否挂上 |
| 视频没声音 | 旁白 TTS 那步失败（看后台日志抽屉「旁白配音」步骤），该段会静音；edge/elevenlabs 都失败会跳过 |
| 渲染很慢 | 首次请求要 bundle 打包，之后有缓存；确认 Chromium 多进程已开；长视频/多关键词本就耗时 |
| 图片报 `file://` 加载错误 | 路径改写没生效，检查 `server.mjs` 的 `rewriteMediaPaths` 与 `MEDIA_ROOT` |
| 改了模板线上没变化 | 忘了 `docker compose build render` |
| `npx remotion browser ensure` 失败 | 网络问题导致下不到 Chrome Headless Shell，重试 build 或配代理 |
| 中文/emoji 显示成方块 | 字体缺失，`Dockerfile` 已装 `fonts-noto-cjk` / `fonts-noto-color-emoji`，本地预览缺字体则装对应系统字体 |
| render 容器起不来 | `docker compose logs render` 看报错；多为 Chromium 系统库缺失（对照 `Dockerfile` 的 apt 清单） |

---

## 10. 后续精细化方向（不急）

当前是纯文字动效版（v1），够跑通链路。后续可往这些方向走，都在 `PromoVideo.tsx` / `Root.tsx` 能力范围内：

1. **多套模板**：`Root.tsx` 注册多个 Composition（`PromoVideoA/B`），创建任务时选模板。
2. **B-roll 背景素材**：每段配不同短视频/图片，而不只用封面当背景（需接素材库）。
3. **字幕跟读高亮**：旁白逐句/逐字高亮（karaoke），需 TTS 返回时间戳。
4. **段间转场**：淡入淡出、滑动等。
5. **背景音乐**：叠一层 BGM（`<Audio>` + 音量控制/ducking）。

---

## 参考链接

| 资源 | 链接 |
| --- | --- |
| Remotion 官方文档 | https://www.remotion.dev/docs/ |
| 音频 | https://www.remotion.dev/docs/audio |
| 参数化渲染（传 props） | https://www.remotion.dev/docs/parameterized-rendering |
| 服务端渲染 SSR | https://www.remotion.dev/docs/ssr |
| Agent Skills | https://www.remotion.dev/docs/ai/skills |
| Edge TTS（免费、无 key） | https://github.com/rany2/edge-tts |
