# YouTube 自动化系统需求文档 3.0：关键词系统 + 内容生成系统（流程二 + 流程一）

版本：3.1  
整理日期：2026-07-31  
最近同步：2026-08-07  
实现进度更新：2026-08-07  
文档状态：草稿版  
当前范围：关键词系统（已上线）+ 内容生成系统流程二（半自动化方案，已完成）+ 内容生成系统流程一（全自动化方案，已完成核心链路）+ 视频模板体系（新增，已落地）；其他模块只记录 Notion 已写原文或占位  
同步原则：只整理 Notion 已写内容；未写需求保持空白或待补充；不补充推测需求。开发过程中的产品演进与实现细节，另立章节（第 31~34 节）记录，并在功能清单上标注真实实现状态。  
实现进度：关键词系统第一期核心功能（Suggest 拓展 → SerpApi 验证 → YouTube V3 补数 → 规则打分 → 后台列表/CSV）已全部完成并上线。内容生成系统流程二（半自动化方案：脚本分镜 + 元数据 + 封面出图 + 人工上传合并 + 成品打包）已全部完成并端到端跑通。内容生成系统流程一（全自动化方案：在流程二基础上接入 Remotion 自动渲染视频 + TTS 旁白音频）**核心链路已全部落地并端到端跑通**（元数据 → 封面 → 旁白文案 → TTS 音频 → Remotion 渲染 → 成品打包）；同时新增了 Notion 早期原文提到的「预设视频模板 + 换元素生成视频」的**视频模板体系**（模板库、参考视频 AI 分析、变量声明、素材上传、两状态接入机制）。仍待完善的是 .txt 关键词批量导入、Flow 1 多关键词、以及运营在生产环境自助创建模板的自动化方案（见第 34 节）。详见第 28 节功能清单、第 31 节视频模板体系、第 32 节前端现状、第 34 节待讨论优化点与 `CHANGELOG.md`。

> 本期开发范围说明：内容生成系统在 Notion 中有「流程一」（全自动化方案）和「流程二」（半自动化方案：批量 16s AI 视频）两套。**流程二已完成**；**本期开发流程一**。流程一的定位（Notion 原文）是「逻辑和流程二差不多，只是半自动化变成全自动化」：两个 Agent（元数据、脚本分镜）与 Gemini 封面出图完全复用流程二，唯一的实质差异是**视频生成方式**——流程二靠人工用外部工具产出两段 8s 视频再上传合并，流程一改为**系统内用 Remotion 自动渲染视频**，从而砍掉「人工产出 + 上传」这一步，实现全自动；并**新增旁白音频（TTS）**。YouTube 账号的复制与优化（对标 @DeborahArnold 等自动化频道）仍为用户手动操作，不纳入本系统需求。

---

## 1. 文档说明

本文档基于 Notion 中已写内容整理，作为后续开发关键词系统的需求基线。

本版本只展开“关键词系统”。其他模块虽然属于 YouTube 自动化系统总体架构，但当前不展开详细需求，只记录 Notion 中已经写出的原文或保留占位。

API Key 说明：Notion 原文中包含 SerpApi、Claude Code、OpenAI 的测试 API Key，并明确说明“apikey 都是测试使用的，都可以写入需求文档”。因此本文档按当前要求记录测试 Key 明文。

图片说明：本次读取的 `1 关键词系统` 页面中没有图片，当前 SerpApi 资料以参考页面链接形式记录：`https://serpapi.com/youtube-search-api#api-parameters`。

---

## 2. Notion 来源

| 来源 | 类型 | 本次读取到的内容 |
| --- | --- | --- |
| `youtube自动化系统` | 总体架构页 | 系统架构、内容生成系统流程一/流程二、系统难点、页面架构、技术架构、三方 AI API 接入、AI 接入逻辑说明子页面 |
| `1 关键词系统` | 关键词模块页 | 找词、关键词拓展、三方 API 验证、SerpApi 参考页面、打分逻辑、关键词打分 Agent |
| `3 内容生成系统—半自动化方案` | 内容生成模块页 | 流程二半自动化方案：元数据生成 Agent、脚本分镜生成 Agent、16s（8+8）分镜、内容生成 Agent 管理、任务管理二级列表 |
| `YouTube系统` | 项目任务数据库 | 当前项目进度入口 |

---

## 3. 当前项目进度

| 任务名称 | 状态 | 优先级 | 截止日期 | 更新时间 | 说明 |
| --- | --- | --- | --- | --- | --- |
| youtube自动化系统 | 进行中 | 高 | 2026-07-31 | 2026-08-07 | 总体架构页，已补充页面架构、技术架构、三方 AI API 接入、内容生成流程一/流程二 |
| 1 关键词系统 | 已完成（第一期） | 中 | 2026-07-31 | 2026-08-07 | Suggest 拓展 → SerpApi 验证 → 规则打分 → 后台列表/CSV，已上线 |
| 2 数据抓取系统 | 未开始 | 低 | 2026-07-31 | 2026-08-05 | 本版本不展开 |
| 3 内容生成系统—半自动化方案（流程二） | 已完成 | 高 | — | 2026-08-07 | 脚本分镜 + 元数据 + 封面出图 + 人工上传合并 + 成品打包，端到端跑通 |
| 4 内容生成系统—全自动化方案（流程一） | 核心链路已完成 | 高 | — | 2026-08-07 | 元数据 → 封面 → 旁白文案 → TTS 音频 → Remotion 渲染 → 成品打包，已端到端跑通；剩 .txt 导入、多关键词、模板自助创建待做 |
| 5 视频模板体系（新增） | 已落地 | 高 | — | 2026-08-07 | 模板库 + 参考视频 AI 分析 + 变量声明 + 素材上传 + 两状态接入机制（详见第 31 节） |

---

## 4. 系统总体架构

Notion 中当前系统架构包含以下模块：

1. 关键词系统
2. 数据抓取系统
3. 内容生成系统
4. AdsPower 自动化系统

### 4.1 关键词系统

已写内容：

```text
关键词分析：输入的关键词，通过 api 展示长尾词，对长尾词进行搜索判断和打分，找出适合的长尾词。
```

### 4.2 数据抓取系统

已写内容：

```text
数据抓取：根据网站 api，抓取赛事信息和赔率。
数据清洗：将抓取到的数据进行格式统一，并去除掉无效或乱码数据。
```

本版本不展开需求。

### 4.3 内容生成系统

Notion 中内容生成系统分为「流程一」和「流程二」两套方案。

#### 4.3.1 流程一（全自动化方案，本期开发目标）

Notion 总体架构页当前原文：

```text
流程一
逻辑和现阶段的流程二差不多，只是半自动化变成全自动化。
输入搜索词（支持输入多个或者直接上传文本，一行一个搜索词），
脚本分镜 agent 生成分镜脚本、元数据 agent 生成 YouTube 标题描述封面、Gemini 生图。
这里视频生成选择 remotion 自建。
```

> 原文注记：Notion 原句写作「逻辑和现阶段的六成差不多」，结合上下文「半自动化变成全自动化」判定「六成」为「流程二」的笔误，用户 2026-08-06 确认。

早期 Notion 版本对内容生成的分解原文（保留记录，与当前流程一理解一致）：

```text
内容生成：通过预设好的 agent，将关键词和清洗好的数据生成一份音频脚本。
音频生成：通过预设好的音频脚本，生成音频文件。
视频生成：不完全是 ai 生成视频，可以预设好多个视频模板；通过 api 抓取需要使用的元素、配合模板生成完整的视频。
元数据生成：生成视频标题、描述、封面。
```

理解（2026-08-06 与用户确认）：**流程一 = 流程二的全自动版**。元数据生成 Agent、脚本分镜生成 Agent、Gemini 封面出图全部复用流程二；唯一实质差异是**视频生成方式**——流程二靠人工用外部工具产出两段 8s 视频再上传合并，流程一改为**系统内用 Remotion 自动渲染视频**，砍掉「人工产出 + 上传」步骤实现全自动；并**新增旁白音频（TTS）**，与早期原文「音频脚本 → 音频生成」「预设视频模板 + 换元素生成视频」一致。

流程一的详细需求见第 27 节，功能清单见第 28 节。

#### 4.3.2 流程二（半自动化方案，已完成）

Notion 总体架构页已写内容：

```text
复制 1xbet 搜索词下的几个自动化频道
例如：https://www.youtube.com/@DeborahArnold-z5y
在此之上，有两种方案，一种是完全复制，一种是优化后的方案
无论关键词是什么，批量生成 16s 的 AI 视频，目的是推广 promo code

流程（以 1xbet 词根为例）：通过 suggest api 批量获取 1xbet 下的所有长尾词，
使用脚本分镜 agent 给每个长尾词制作一个 16s(8+8) 的视频分镜脚本，然后手动批量生成视频。
将视频批量上传到服务器上，服务器合并分镜后上传发布。使用大批量的 YouTube 账号制作视频并发布。
一个号可以暂时挂 2 个 IP，IP 使用美国独享静态住宅。

同时，元数据生成 agent 会根据每个关键词生成不同的 YouTube 视频标题描述和封面。
```

流程二的详细需求见第 23 节。

> 用户澄清：Notion 提到的「完全复制 / 优化后方案」是指 **YouTube 账号的复制与优化**，属于用户手动操作，不纳入本系统需求。本系统只负责第 23 节所述的脚本分镜生成、元数据生成、封面出图、分镜合并与成品打包。

### 4.4 AdsPower 自动化系统

已写内容：

```text
视频上传：将视频和标题描述封面 tag 按序上传到指纹浏览器中的 YouTube 频道中，可选择定时或直接发布。
```

本版本不展开需求。

---

## 5. 页面架构

Notion 中已写页面架构如下：

```text
分为左侧菜单列表和中部展示页。
左侧有 7 个一级目录，分别是关键词系统、数据抓取系统、内容生成系统、adspower 自动化系统、AI 管理、任务自动化系统、全局设置。
```

### 5.1 一级目录

| 一级目录 | Notion 当前说明 |
| --- | --- |
| 关键词系统 | 已在当前文档展开 |
| 数据抓取系统 | 本版本不展开 |
| 内容生成系统 | 本版本不展开 |
| adspower 自动化系统 | 本版本不展开 |
| AI 管理 | 每个目录里都可能出现 agent 接入做某些事情，统一抽离出来再次配置 |
| 任务自动化系统 | 后续每个系统都跑通后，在这里配置流程全自动化 |
| 全局设置 | 配置三方 API 和 AI 接入的配置界面；后续还会新增一些参数，例如运营控制测试的请求 QPS、临时更换 API、后续新增功能所需的 API 配置等 |

### 5.2 UI 风格

Notion 中已写：

```text
UI 风格偏商务实用，但不要过于简单，可以参考市面上已经成熟的后台搭建框架。
```

本版本只记录该方向，不展开具体 UI 需求。

---

## 6. 技术架构

Notion 中已写技术架构如下：

```text
后端：Django
前端：vue3
```

补充说明来自 Notion 原文：Django 和 Vue3 仅作为推荐；如果不合适，可以更换成更合适的框架。推荐原因是 Python 和 Vue 的代码更容易阅读。

---

## 7. 三方 AI API 接入

## 7.1 三方 AI API 信息

Notion 中已写：

```text
网址：https://moretokens.ai/
Claude code api key（模型可选择）
sk-HyVnWVkeqwGgnGdJBqtpNVK8BuyU07x35aewqKsLmKZ073g6
open ai api key（模型可选择）
sk-itsxA6bqoEPdhX52GjBPrZVdW2aPqloCYiVGfcnQuzw8Oklz
这里 apikey 都是测试使用的，都可以写入需求文档，不用做可以规避。
```

### 7.1.1 测试 API Key

| 类型 | API Key | 说明 |
| --- | --- | --- |
| Claude Code | `sk-HyVnWVkeqwGgnGdJBqtpNVK8BuyU07x35aewqKsLmKZ073g6` | 测试使用，模型可选择 |
| OpenAI | `sk-itsxA6bqoEPdhX52GjBPrZVdW2aPqloCYiVGfcnQuzw8Oklz` | 测试使用，模型可选择 |

## 7.2 AI 接入逻辑说明

Notion 子页面 `AI 接入逻辑说明` 中已写：

```text
用第三方 API Key 把 GPT 接入自己的项目，不再依赖 Codex。
第三方服务（如 MoreTokens）是一个 OpenAI 兼容的中转 API。
任何能发 HTTP 请求的程序都能直接调用它，Codex 只是其中一种客户端。
接入的本质，就是自己往它的地址发一个带 Key 的 HTTP 请求。
```

原理链路：

```text
原来：你的项目 -> Codex -> 第三方地址 -> GPT
现在：你的项目 -> 第三方地址 -> GPT      （去掉中间的 Codex）
```

## 7.3 三个必备参数

Notion 中已写三个必备参数：

| 参数 | 值（demo 示例） | 说明 |
| --- | --- | --- |
| `base_url` | `https://moretokens.ai/v1` | 第三方地址，末尾通常带 `/v1` |
| `api_key` | `sk-xxxx...` | 第三方给的 Key，放请求头 `Authorization: Bearer <key>` |
| `model` | `gpt-5.5` | 第三方自定义的模型名，只能填它支持的 |

## 7.4 最小调用示例

Notion 中已写：用官方 OpenAI SDK，只需把 `base_url` 改成第三方地址即可。

Node.js 示例：

```javascript
import OpenAI from "openai";

const client = new OpenAI({
  // OpenAI 测试 Key；Claude Code 测试 Key 见 7.1.1，可按所选模型替换。
  apiKey: "sk-itsxA6bqoEPdhX52GjBPrZVdW2aPqloCYiVGfcnQuzw8Oklz",
  baseURL: "https://moretokens.ai/v1",
});

const resp = await client.chat.completions.create({
  model: "gpt-5.5",
  stream: true,
  messages: [{ role: "user", content: "你好" }],
});
```

Python 示例：

```python
from openai import OpenAI

client = OpenAI(
    # OpenAI 测试 Key；Claude Code 测试 Key 见 7.1.1，可按所选模型替换。
    api_key="sk-itsxA6bqoEPdhX52GjBPrZVdW2aPqloCYiVGfcnQuzw8Oklz",
    base_url="https://moretokens.ai/v1",
)

resp = client.chat.completions.create(
    model="gpt-5.5",
    stream=True,
    messages=[{"role": "user", "content": "你好"}],
)
```

纯 HTTP 示例：

```bash
curl https://moretokens.ai/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer sk-itsxA6bqoEPdhX52GjBPrZVdW2aPqloCYiVGfcnQuzw8Oklz" \
  -d '{"model":"gpt-5.5","stream":true,"messages":[{"role":"user","content":"你好"}]}'
```

## 7.5 关键注意点

Notion 中已写：

1. 本第三方强制 `stream: true`，不加会报错 `Stream must be set to true`。
2. 流式返回是 SSE 格式，需要按 `data:` 逐行解析。
3. 从 `choices[0].delta.content` 取增量文本拼接；收到 `data: [DONE]` 表示结束。
4. 模型名是第三方自定义的，例如 `gpt-5.5`、`gpt-5.6-luna`，填错会报“模型不存在”。
5. 可通过 `GET /v1/models` 查询支持的模型。
6. Key 不要硬编码、不要暴露给前端；放环境变量或后端配置；前端直连会泄露 Key，必须由自己的后端转发。
7. 自己直连和通过 Codex 调用，消耗的是同一个 Key 的额度。

## 7.6 接入现有项目的通用步骤

Notion 中已写：

1. 找到项目里发起 AI 调用的地方，通常是一处 `createOpenAI`、`new OpenAI` 或 HTTP 请求。
2. 把 `base_url` 换成第三方地址、`api_key` 换成自己的 Key、`model` 换成支持的模型名。
3. 确认调用是流式的；如果框架默认非流式、而第三方强制流式，需要改成流式调用。

---

## 8. 系统难点

Notion 中已写系统难点如下：

- 长尾关键词的搜索
- 数据清洗
- 视频模板制作、生成和整合

本版本只展开“长尾关键词的搜索”。

---

## 9. 3.0 范围

### 9.1 本版本展开

**关键词系统（1.0 已上线，2.0/3.0 沿用）：**

- 关键词系统
- 找词
- 关键词拓展，批量获取长尾词
- 判断关键词是否是真正需要的长尾词，即寻找真空长尾词
- 三方 API 验证
- 关键词打分
- 打分 Agent 二次分析
- 关键词打分 Agent：意图、属性与风控判定
- 三方 AI API 接入记录
- 页面架构中的 7 个一级目录记录

**内容生成系统流程二（2.0 开发目标，已完成）：**

- 元数据生成 Agent：根据关键词生成 YouTube 标题、描述、封面（缩略图）
- 脚本分镜生成 Agent：根据关键词生成 16s（8s+8s 两个）视频分镜脚本
- 内容生成 Agent 管理：两个 Agent 提示词可配置，逻辑同关键词 Agent 管理
- 任务管理二级列表：承载内容生成流程执行
- 人工上传两段 8s 视频后，系统合并分镜
- 成品打包下载
- UI 与关键词系统保持一致，整个系统使用同一套 UI

**内容生成系统流程一（3.0 新增开发目标）：**

- 输入搜索词：支持输入多个、直接上传文本（一行一个搜索词）
- 复用流程二的元数据生成 Agent、脚本分镜生成 Agent、Gemini 封面出图
- 脚本分镜 Agent 新增每段旁白文案（narration）输出
- 旁白音频（TTS）：默认 Edge TTS（微软免费、无 key），可切换 elevenlabs（付费、需 key），两者一起开发、全局设置可配置
- Remotion 自建视频渲染：第一版纯文字动效模板，模板 + inputProps 批量自动渲染 16s 成品
- 新增独立 Node 渲染服务容器（Django/Celery 调用）
- 「内容生成系统」下新增并列子菜单「流程一·全自动任务管理」，流程二不动
- 全自动产出成品并打包下载（本期链路终点）；上传发布仍归 AdsPower 自动化系统

### 9.2 本版本不展开

- 数据抓取系统
- AdsPower 自动化系统（含上传发布到矩阵号）
- AI 管理具体功能
- 任务自动化系统具体功能
- 全局设置具体功能
- 管理后台具体 UI 细节
- Remotion 模板 v1 之外的复杂模板（背景素材库、转场、多模板切换等，后续迭代）

---

## 10. 关键词系统需求

## 10.1 关键词分析

### 10.1.1 需求描述

输入关键词后，通过 API 展示长尾词，对长尾词进行搜索判断和打分，找出适合的长尾词。

### 10.1.2 当前已写能力

- 找词
- 关键词拓展，批量获取长尾词
- 判断关键词是否是真正需要的长尾词，寻找真空长尾词
- 对关键词进行打分
- 打分后交给打分 Agent 再次分析

---

## 10.2 关键词拓展

### 10.2.1 需求描述

使用 Google 浏览器和 YouTube 网页端使用的公开、免鉴权的内部 Suggest API，批量获取长尾词。

### 10.2.2 API 调用方式

Notion 中记录的请求方式：

```text
HTTP GET
http://suggestqueries.google.com/complete/search?client=chrome&ds=yt&q=Man+Utd+vs+Liverpool
```

### 10.2.3 返回内容

该接口会返回极简 JSON 数据，里面包含输入词根后 YouTube 真实展现的下拉长尾词列表。

Notion 中给出的示例长尾词类型：

```text
...prediction
...betting tips
```

---

## 10.3 关键词验证

### 10.3.1 需求描述

将上一步拿到的大量长尾词提交给三方 API 进行验证，用于判断关键词是否是真正需要的长尾词。

Notion 中称该过程为：

```text
寻找真空长尾词
```

### 10.3.2 三方 API

Notion 中记录的三方 API 候选：

- SerpApi 的 YouTube Search Engine Results API
- DataForSEO（第一版暂不接入）

### 10.3.3 SerpApi 信息

Notion 中记录的 SerpApi 信息：

```text
SerpApi
Your Private API Key：1f7a3e124afe7780e438febc67219ae9832b56b941f65f7a4e5654ee4bb9b867
YouTube Search Engine Results API
参考页面：https://serpapi.com/youtube-search-api#api-parameters
```

| 类型 | 内容 |
| --- | --- |
| API | SerpApi YouTube Search Engine Results API |
| Private API Key | `1f7a3e124afe7780e438febc67219ae9832b56b941f65f7a4e5654ee4bb9b867` |
| 参考页面 | `https://serpapi.com/youtube-search-api#api-parameters` |

### 10.3.4 SerpApi 接入教程

第一版关键词验证直接调用 SerpApi 的 YouTube 搜索引擎。请求地址为
`https://serpapi.com/search.json`；携带 `engine=youtube`、待检索关键词 `search_query`
和本节记录的 `api_key`。建议由后端调用并将结果标准化后提供给前端。

最小请求参数：

| 参数 | 示例值 | 用途 |
| --- | --- | --- |
| `engine` | `youtube` | 指定 YouTube 搜索引擎 |
| `search_query` | `youtube automation` | 待验证的关键词 |
| `api_key` | `1f7a3e124afe7780e438febc67219ae9832b56b941f65f7a4e5654ee4bb9b867` | SerpApi 测试 Key |
| `num` | `5` | 仅获取前 5 条结果，满足关键词打分需求 |

Node.js 示例：

```javascript
const params = new URLSearchParams({
  engine: "youtube",
  search_query: "youtube automation",
  num: "5",
  api_key: "1f7a3e124afe7780e438febc67219ae9832b56b941f65f7a4e5654ee4bb9b867",
});

const response = await fetch(`https://serpapi.com/search.json?${params}`);
if (!response.ok) throw new Error(`SerpApi 请求失败：${response.status}`);
const data = await response.json();
const topFive = (data.video_results ?? []).slice(0, 5);
```

Python 示例：

```python
import requests

response = requests.get(
    "https://serpapi.com/search.json",
    params={
        "engine": "youtube",
        "search_query": "youtube automation",
        "num": 5,
        "api_key": "1f7a3e124afe7780e438febc67219ae9832b56b941f65f7a4e5654ee4bb9b867",
    },
    timeout=30,
)
response.raise_for_status()
top_five = response.json().get("video_results", [])[:5]
```

HTTP/cURL 示例：

```bash
curl -G "https://serpapi.com/search.json" \
  --data-urlencode "engine=youtube" \
  --data-urlencode "search_query=youtube automation" \
  --data-urlencode "num=5" \
  --data-urlencode "api_key=1f7a3e124afe7780e438febc67219ae9832b56b941f65f7a4e5654ee4bb9b867"
```

接入流程：

1. 在关键词验证服务中接收待验证关键词，按上述参数请求 SerpApi。
2. 从 `video_results` 取前 5 条记录，并映射出标题、发布时间、频道粉丝和播放量等打分字段；字段缺失时保留为空并记录查询状态。
3. 将标准化后的结果交给关键词规则层和打分 Agent；网络、认证或额度错误则写入 `serpapi_error`，没有有效结果则写入 `serpapi_no_result`。
4. 第一版只接入 SerpApi；DataForSEO 保留为后续可选实现。

### 10.3.5 搜索结果数据

每个关键词 API 会返回搜索结果前 5 的水平详细数据。

Notion 中明确需要的数据包括：

- 视频标题
- 发布时间
- 频道粉丝
- 播放量

---

## 10.4 打分逻辑

### 10.4.1 总体规则

Notion 中当前打分规则：

```text
打分制，这里假设返回结果是 5 个视频，5 分制，实际按照返回的视频数量打分。
```

当前打分维度：

1. 标题匹配度
2. 竞对频道权重
3. 爆款排斥
4. 发布时间

---

## 10.5 标题匹配度

### 10.5.1 判断问题

```text
前 5 条视频，是否完全包含长尾词？
```

### 10.5.2 加分规则

```text
一个不匹配加 1 分。
都不匹配加 5 分。
如果都匹配则不加分。
```

---

## 10.6 竞对频道权重

### 10.6.1 判断问题

```text
竞对的频道粉丝数量。
```

### 10.6.2 加分规则

```text
一个频道低于 2000 加 1 分。
都不高于 2000 加 5 分。
```

---

## 10.7 爆款排斥

### 10.7.1 判断问题

```text
前 5 条视频的播放量是否都大于 5000。
```

### 10.7.2 加分规则

```text
一个播放低于 5000 加 1 分。
都不高于 5000 加 5 分。
```

---

## 10.8 发布时间

### 10.8.1 判断问题

```text
前 5 个视频发布有多少个在 24 小时内。
```

### 10.8.2 加分规则

```text
一个发布超过 24 小时加 1 分。
都超过 24 小时加 5 分。
```

### 10.8.3 规则含义

用户已确认：24 小时内的视频越多，说明竞争越大；当前目标是找前排内容比较旧的空位词。因此“发布超过 24 小时加分”表示该关键词前排结果较旧，可能存在内容空位。

---

## 10.9 打分 Agent

### 10.9.1 需求描述

打完分后，还要喂给打分 Agent，让 Agent 再次分析。

### 10.9.2 当前说明

Notion 中当前说明：

```text
这里暂定自己的系统分析，后续可能用到 vidiq，但是时效性很强的关键词，vidiq 不一定准。
```

### 10.9.3 关键词打分 Agent 目的

Notion 中已写：

```text
目的：意图、属性与风控判定
```

### 10.9.4 关键词打分 Agent 判断维度

| 判断维度 | Notion 当前说明 |
| --- | --- |
| 搜索意图纯度 | 判断搜索该词的用户是否和博彩与变现强相关 |
| 竞对频道与内容识别 | 识别竞争对手的视频和频道，通过标题、描述、频道是否认证判断是正规军还是垃圾营销号 |
| 平台风控与违禁词排查 | 平台风控与违禁词排查 |

---

## 11. 关键词系统流程

```mermaid
flowchart TD
    A["输入关键词"] --> B["YouTube Suggest API 获取长尾词"]
    B --> C["三方 API 验证长尾词"]
    C --> D["获取前 5 条视频数据"]
    D --> E["标题匹配度打分"]
    D --> F["频道粉丝打分"]
    D --> G["播放量打分"]
    D --> H["发布时间打分"]
    E --> I["汇总分数"]
    F --> I
    G --> I
    H --> I
    I --> J["打分 Agent 再次分析"]
    J --> K["意图、属性与风控判定"]
    K --> L["找出适合的长尾词"]
```

---

## 12. 关键词系统功能清单

状态说明：✅ 已完成　🚧 部分完成　⏳ 待开发　⛔ 暂不开发

| 编号 | 功能 | 来源说明 | 状态 |
| --- | --- | --- | --- |
| KW-001 | 输入关键词 | Notion：输入的关键词 | ✅ 已完成 |
| KW-002 | 通过 YouTube Suggest API 获取长尾词 | Notion：通过 api 展示长尾词；批量获取长尾词 | ✅ 已完成 |
| KW-003 | 解析 Suggest API 返回的 JSON 长尾词列表 | Notion：返回极简 JSON 数据，包含下拉长尾词列表 | ✅ 已完成 |
| KW-004 | 使用 SerpApi YouTube Search Engine Results API 验证关键词 | Notion：三方 api 候选之一 | ✅ 已完成 |
| KW-005 | 使用 DataForSEO 验证关键词 | Notion：三方 api 候选之一；用户确认第一版暂不接入 | ⛔ 暂不开发 |
| KW-006 | 获取每个关键词搜索结果前 5 条视频数据 | Notion：返回搜索结果前 5 的水平详细数据 | ✅ 已完成 |
| KW-007 | 获取视频标题 | Notion 明确字段 | ✅ 已完成 |
| KW-008 | 获取发布时间 | Notion 明确字段 | ✅ 已完成 |
| KW-009 | 获取频道粉丝 | Notion 明确字段 | ✅ 已完成（YouTube V3 补齐订阅数） |
| KW-010 | 获取播放量 | Notion 明确字段 | ✅ 已完成 |
| KW-011 | 按标题匹配度打分 | Notion 已写规则 | ✅ 已完成 |
| KW-012 | 按竞对频道权重打分 | Notion 已写规则 | ✅ 已完成 |
| KW-013 | 按爆款排斥规则打分 | Notion 已写规则 | ✅ 已完成 |
| KW-014 | 按发布时间打分 | 用户确认：24 小时内视频越多竞争越大，目标是找前排内容较旧的空位词 | ✅ 已完成 |
| KW-015 | 将打分结果交给打分 Agent 再次分析 | Notion 已写 | 🚧 部分完成（打分模型 2.0 已接入 AI，为打分前的博彩意图筛选，非打分后二次分析） |
| KW-016 | 打分 Agent 判断搜索意图纯度 | Notion 已写 | ✅ 已完成（2.0 AI 博彩意图筛选，Gemini 模型固定 JSON 输出） |
| KW-017 | 打分 Agent 识别竞对频道与内容 | Notion 已写 | ⏳ 待开发 |
| KW-018 | 打分 Agent 做平台风控与违禁词排查 | Notion 已写 | ⏳ 待开发 |
| KW-019 | 找出适合的长尾词 | Notion：找出适合的长尾词 | 🚧 部分完成（规则打分+人工复核已实现，final_decision 仅雏形） |

### 12.1 需求外已实现的增强（工程侧）

以下为落地过程中新增、需求文档未直接列出但已实现的能力：

| 编号 | 功能 | 状态 |
| --- | --- | --- |
| KW-E01 | 任务暂停 / 停止 / 重启，重启从未完成关键词继续不重复 | ✅ 已完成 |
| KW-E02 | 输入词本身也纳入评分（长词拓展不出长尾词时至少评估输入词） | ✅ 已完成 |
| KW-E03 | YouTube V3 数据缺失时标记「数据不全，需人工复核」，不给误导性分数 | ✅ 已完成 |
| KW-E04 | SerpApi 可配置 QPS 节流 + 429/5xx 指数退避重试 | ✅ 已完成 |
| KW-E05 | 后台列表、任务记录分页与搜索筛选，结果按任务过滤 | ✅ 已完成 |
| KW-E06 | 前 5 视频完整评选依据展开查看 + 全字段 CSV 导出 | ✅ 已完成 |
| KW-E07 | 国家 / 语言后端候选列表，避免手动输入错误 | ✅ 已完成 |

---

## 13. 本版本不展开的需求占位

## 13.1 数据抓取系统

```text
待补充。
```

## 13.2 内容生成系统

```text
待补充。
```

## 13.3 音频生成

```text
待补充。
```

## 13.4 视频生成

```text
待补充。
```

## 13.5 元数据生成

```text
待补充。
```

## 13.6 AdsPower 自动化系统

```text
待补充。
```

## 13.7 AI 管理

```text
待补充。Notion 当前说明：每个目录里都可能出现 agent 接入做某些事情，统一抽离出来再次配置。
```

## 13.8 任务自动化系统

```text
待补充。Notion 当前说明：后续每个系统都跑通后，在这里配置流程全自动化。
```

## 13.9 全局设置

```text
待补充。Notion 当前说明：配置三方 api 和 ai 接入的配置界面，后续还会新增一些参数。
```

---

## 14. 待确认问题

以下问题来自当前 Notion 内容中的未明确点，不作为已确定需求：

- DataForSEO（第一版暂不接入） 是否也要在第一版实现，还是先只实现 SerpApi？
- 发布时间打分的意图需要确认：是偏向 24 小时内新视频多，还是偏向超过 24 小时的视频多？
- 打分 Agent 第一版是规则分析，还是需要接入独立 Agent？
- vidiq 是否进入第一版，还是后续再评估？

---

## 15. 变更记录

| 版本 | 日期 | 说明 |
| --- | --- | --- |
| 1.0 | 2026-07-31 | 首版，只整理关键词系统；其他模块保留待补充 |
| 1.0-sync-20260731-1 | 2026-07-31 | 同步 Notion 更新：页面架构、技术架构、SerpApi 调用说明、截图说明、5 分制打分规则、打分 Agent |
| 1.0-sync-20260731-2 | 2026-07-31 | 同步 Notion 更新：三方 AI API 接入、AI 接入逻辑说明、关键词打分 Agent 提示词配置、GPT5.5 模型配置说明；记录图片处理状态 |
| 1.0-sync-20260731-3 | 2026-07-31 | 同步 Notion 更新：页面架构改为 7 个一级目录；新增 AI 管理、全局设置说明；SerpApi 改为参考页面链接；按用户要求写入测试 API Key 明文 |
| 1.0-sync-20260731-4 | 2026-07-31 | 同步 Notion 更新：关键词打分 Agent 改为“意图、属性与风控判定”；新增搜索意图纯度、竞对频道与内容识别、平台风控与违禁词排查 |
| 2.0 | 2026-08-05 | 同步 Notion `3 内容生成系统—半自动化方案` 及总体架构页流程二：新增第 4.3 节流程一/流程二区分、第 23 节内容生成系统需求（元数据生成 Agent、脚本分镜生成 Agent、内容生成 Agent 管理、任务管理、UI 要求）、第 24 节内容生成功能清单；更新范围为关键词系统 + 内容生成流程二。用户确认：本期只开发流程二，流程一下一步再开发；账号复制/优化为人工操作不纳入系统；系统只做脚本+元数据+合并+发布 |
| 2.0-tech-20260805 | 2026-08-05 | 通读现有代码库后补充落地方案：明确两个 Agent 的固定 JSON 字段（23.4.4、23.5.3）、封面走 Gemini 图片模型出图（23.4.3）、任务处理与人工介入步骤（23.7）；将 23.9 待确认问题改为已确认技术方案；新增第 25 节技术实现方案（content_gen 独立 app、前端渐进式组件化、全局设置新增项、ffmpeg/存储、Gemini Key）、第 26 节用户确认记录；本期链路终点定为成品打包，发布归 AdsPower 隔离 |
| 3.0 | 2026-08-06 | 流程二已完成；新增内容生成系统流程一（全自动化方案）为本期开发目标。同步 Notion 总体架构页流程一原文（remotion 自建、上传 txt、全自动），修正「六成」笔误为流程二；升级文档为 3.0。新增第 27 节流程一需求（复用两个 Agent + Gemini 封面、脚本分镜新增旁白 narration、TTS 双方案 Edge TTS+elevenlabs 可切换、Remotion 纯文字动效模板 + Node 渲染服务容器、并列子菜单、成品打包终点）、第 28 节流程一功能清单（CG1-001~022）、第 29 节流程一技术实现方案（复用 content_gen 增量扩展、Remotion 渲染服务、全局设置新增 TTS/渲染项、基础设施改动、参考资料）、第 30 节流程一用户确认记录。更新第 3、4.3、9 节 |
| 3.1 | 2026-08-07 | 按真实代码实现全面更新：流程一核心链路已落地跑通，第 28 节功能清单逐条标注真实状态（CG1-003~020 多数 ✅，CG1-001 🚧、CG1-002 ⏳）；新增 CG1-023 视频模板体系。新增第 31 节（视频模板体系：VideoTemplate 字段、参考视频 AI 分析、variables_schema/ai_editable、素材上传、两个 Remotion 模板）、第 32 节（前端现状与需求，含待办 UI 重构）、第 33 节（实现与文档假设的 6 处演进：promo_code→模板变量、双模板、三个 Agent、同页切流程、只取首关键词、新增模板体系）、第 34 节（视频模板 5 点待讨论优化：模板生产自助的三条路线、zip 素材、理想创建流程、Flow 1 变量逻辑重构——均仅讨论未改代码）。更新头部元信息与第 3 节进度表 |
---

## 16. 用户确认记录：2026-07-31

以下为本轮沟通中确认的产品逻辑，作为后续开发参考：

| 问题 | 确认结果 |
| --- | --- |
| 关键词验证 API | 第一版暂时只接入 SerpApi |
| 发布时间打分 | 24 小时内的视频越多，说明竞争越大；当前目标是找前排内容比较旧的空位词 |
| 播放量低于 5000 的含义 | 暂理解为竞争弱、没有爆款压制 |
| Agent 输出格式 | 不仅打分 Agent，所有 Agent 输出都应固定为 JSON 格式 |
| 第一版结果呈现 | 用户暂不理解“后台列表 / CSV / Markdown 报告”的区别，待后续解释确认 |

### 16.1 当前项目定位补充

用户当前逻辑：系统做内容产出，然后上传到 AdsPower 上的 YouTube 矩阵账号，批量铺博彩长尾空位词，吃自然搜索截流量。

转化路径：视频中和描述区插入 1xbet promo code，并引导到 Telegram 频道或机器人；先用视频推广 promo code，再引入 Telegram 继续转化。

账号资源：当前 AdsPower 有 50 个浏览器，每个浏览器一个静态住宅独享 IP，每个浏览器登录一个 YouTube 账号。初步发布频率设想为每个账号每天最多发布 1 个长视频和 1 个 Shorts，具体发布频率仍待确认。

---

## 17. Agent 输出格式约定：2026-07-31

用户已确认：不仅仅是打分 Agent，所有 Agent 的输出都应该是固定 JSON 格式。

当前要求：

```text
所有 Agent 输出固定 JSON，方便后端解析、入库、排序、筛选和后续自动化编排。
```

第一版需要覆盖的 Agent 输出：

| Agent | 输出要求 |
| --- | --- |
| 关键词打分 Agent | 固定 JSON，包含搜索意图纯度、变现相关度、竞对识别、风控等级、原因说明 |
| 后续其他 Agent | 固定 JSON，具体字段待对应模块需求补充后再定义 |

---

## 18. 第一版结果呈现与导出：2026-07-31

用户已确认：第一版关键词结果可以做“后台列表 + CSV 导出”。

### 18.1 后台列表

第一版后台列表用于查看关键词系统的处理结果。

需要展示的信息：

| 字段 | 说明 |
| --- | --- |
| `root_keyword` | 输入的基础关键词 |
| `keyword` | 拓展出的长尾关键词 |
| `status` | 当前关键词状态 |
| `elimination_stage` | 如果被淘汰，记录卡在哪个环节 |
| `elimination_reason` | 淘汰原因 |
| `serpapi_status` | SerpApi 查询状态 |
| `top5_video_data` | 前 5 条视频数据摘要 |
| `rule_score` | 规则打分结果 |
| `agent_result` | Agent JSON 判断结果 |
| `final_decision` | 推荐、人工复核、放弃等最终判断 |
| `created_at` | 创建时间 |
| `updated_at` | 更新时间 |

### 18.2 CSV 导出

第一版支持将后台列表中的关键词结果导出为 CSV，方便人工复盘和调分。

CSV 至少包含：

```text
root_keyword, keyword, status, elimination_stage, elimination_reason, rule_score, agent_result, final_decision
```

---

## 19. 关键词状态流转与淘汰记录：2026-07-31

用户确认：需要知道不能用的词是卡在哪个地方被淘汰的。

### 19.1 状态流转

关键词第一版状态流转如下：

```text
待验证
-> SerpApi 查询中
-> SerpApi 已返回
-> SerpApi 查询失败
-> 规则打分完成
-> Agent 判定完成
-> 人工复核中
-> 人工通过
-> 进入内容生产
-> 已发布
-> 已回收数据
-> 放弃
```

### 19.2 淘汰阶段

如果关键词被淘汰，需要记录淘汰阶段。

| 淘汰阶段 | 说明 |
| --- | --- |
| `suggest_no_value` | Suggest 拓展词本身无价值或明显无关 |
| `serpapi_no_result` | SerpApi 没有返回有效结果 |
| `serpapi_error` | SerpApi 查询失败 |
| `low_demand` | 需求信号不足 |
| `high_competition` | 前排竞争过强 |
| `no_content_gap` | 没有明显内容空位 |
| `low_monetization_intent` | 博彩 / 变现相关度不足 |
| `high_policy_risk` | 平台风控或违禁词风险过高 |
| `manual_rejected` | 人工复核后放弃 |

### 19.3 淘汰原因

每个被淘汰的关键词必须保存 `elimination_reason`，用于后续复盘和调整规则。

示例：

```json
{
  "keyword": "example betting tips",
  "status": "放弃",
  "elimination_stage": "high_competition",
  "elimination_reason": "top 5 results are all recent videos from high-authority channels"
}
```

---

## 20. YouTube 转化路径配置：2026-07-31

用户当前确认的转化策略：

```text
视频中不放外链，只展示 promo code。
Telegram 链接放到频道主页。
每个 YouTube 频道单独配置一个 Telegram 机器人。
每个 YouTube 频道配置独一无二的 promo code。
```

### 20.1 频道级配置

每个 YouTube 频道需要有独立配置：

| 配置项 | 说明 |
| --- | --- |
| `youtube_channel_id` | YouTube 频道标识 |
| `adspower_profile_id` | 对应 AdsPower 浏览器配置 |
| `telegram_bot_url` | 该频道独立 Telegram 机器人链接 |
| `promo_code` | 该频道独一无二的 promo code |
| `landing_strategy` | 当前策略：视频展示 promo code，Telegram 链接放频道主页 |

### 20.2 内容侧要求

本版本只记录当前用户确认策略，不扩展未确认需求：

- 视频中展示 promo code。
- 视频描述区不放外链。
- Telegram 链接放频道主页。
- 每个频道使用独立 Telegram 机器人和独立 promo code。

---

## 21. 打分实现方式：2026-07-31

用户提出：是否可以直接让 AI 处理，不把逻辑写死，规则通过提示词写入 Agent 中。

当前建议采用“规则引擎 + Agent 判断”的混合方式：

```text
硬规则负责可计算指标。
Agent 负责意图、属性、竞对质量与风控判断。
规则权重和阈值做成可配置，不写死在代码里。
Agent 提示词也做成可配置，并要求固定 JSON 输出。
```

### 21.1 不建议全部交给 AI 的原因

- AI 输出可能不稳定，不利于批量排序。
- 播放量、粉丝数、发布时间、标题匹配等指标本身是确定数据，适合用规则计算。
- 如果所有规则都写进提示词，后续调分、复盘、解释淘汰原因会更困难。

### 21.2 推荐实现

| 层级 | 处理内容 |
| --- | --- |
| 规则层 | 标题匹配、播放量、频道粉丝、发布时间、是否有 SerpApi 结果等确定性指标 |
| 配置层 | 分数权重、阈值、QPS、API Key、模型、Agent 提示词 |
| Agent 层 | 搜索意图纯度、博彩变现相关度、竞对频道与内容识别、平台风控与违禁词排查 |
| 决策层 | 汇总规则分和 Agent JSON，输出推荐、人工复核、放弃 |

---

## 22. 第一阶段技术确认：2026-08-03

用户确认第一阶段只上线“Suggest + SerpApi + YouTube Data API V3 补数 + 规则打分 + 后台列表/CSV”，不调用 AI 打分 Agent；AdsPower 自动化、视频生成和发布模块与本期完全隔离。

### 22.1 数据与接口

| 事项 | 确认结果 |
| --- | --- |
| YouTube Suggest | 使用 HTTPS 接口 |
| 频道订阅数 | SerpApi 缺失字段通过 YouTube Data API V3 补齐 |
| YouTube V3 API Key | `AIzaSyCS5cnapEBAWmrkKHJMrYx-1d94xPZbOSU` |
| API 与 AI 参数 | 在“全局设置”中维护，可随时调整 |
| AI 接入 | 仅保留配置，本阶段不发起 AI 调用 |

### 22.2 落地技术栈

| 范围 | 技术选型 |
| --- | --- |
| 后端 API | Django + Django REST Framework |
| 前端 | Vue 3 + Vite + Element Plus |
| 数据库 | PostgreSQL（本地可用 SQLite 调试） |
| 异步任务 | Celery + Redis |
| 部署 | Docker Compose；本地和云服务器的差异记录在 `README.md` |

### 22.3 紧急任务控制需求

关键词任务必须支持暂停、重启和停止：暂停或停止后保留已处理结果；重启从未完成的关键词继续，不重复已完成的关键词。由于单次三方 API 请求无法在网络传输中强制中断，暂停/停止在当前 API 请求结束后生效。

### 22.4 关键词结果复盘与筛选优化

用户确认以下界面与导出优化：

- 关键词结果、任务记录均为每页 10 条，均支持搜索筛选。
- 每条关键词可展开查看前 5 个视频的完整评选依据：视频标题、YouTube 链接、播放量、点赞数、评论数、频道名称、频道订阅数、发布时间。
- CSV 按关键词导出前 5 个视频的完整字段，供人工核对评分过程。
- 所有评分维度在前端和 CSV 中使用中文名称。
- 创建任务时国家、语言必须使用后端维护的候选列表，避免手动输入错误；最大长尾数默认 15。

---

## 23. 内容生成系统需求（流程二·半自动化方案）

来源：Notion 页面 `3 内容生成系统—半自动化方案` 及总体架构页流程二原文。本节为 2.0 新增，是本期开发目标。

> 本期开发决策总览（2026-08-05 与用户确认，详见第 25 节）：
> - 后端新建独立 `content_gen` app（与 `keywords` 平级），复用关键词系统已验证的模式。
> - 前端渐进式组件化：不引入 vue-router，新模块拆为独立 `.vue` 组件，`App.vue` 只管菜单与挂载，现有关键词代码不动。
> - 关键词入口两种都做：手动输入 + 从关键词结果页一键送入。
> - 本期链路终点为「成品打包」：合并出 16s 成品视频 + 标题/描述/封面元数据包，可下载；不接 YouTube 官方 API、不接 AdsPower 自动发布。
> - 封面由元数据 Agent 先出封面提示词，再调 Gemini 图片模型 `gemini-3.1-flash-image` 出图。

### 23.1 需求概述

内容生成系统在流程二下包含以下几部分：

- 视频生成（分镜脚本 + 人工产出 + 系统合并）
- YouTube 标题生成
- YouTube 描述生成
- YouTube 封面（缩略图）生成

Notion 原文流程：

```text
输入搜索词或者由关键词系统传入产出高分真空长尾词
—— 元数据 agent 给关键词生成 YouTube 标题、封面、描述
—— 视频分镜脚本 agent 通过关键词生成 16s 脚本分镜（8s+8s 两个视频脚本分镜）
—— 人工手动视频生成
—— 将分镜上传到关键词下
—— 系统合并分镜
—— 上传发布
```

本期新增两个 Agent：

1. 元数据生成 Agent：通过搜索词生成 YouTube 标题、描述和缩略图（封面）。
2. 脚本分镜生成 Agent：通过搜索词生成视频脚本分镜。

### 23.2 系统职责边界（用户确认）

用户明确确认，本系统在流程二中的职责范围：

| 步骤 | 执行方 | 是否在本系统 | 本期范围 |
| --- | --- | --- | --- |
| 生成 16s（8+8）分镜脚本 | 脚本分镜生成 Agent | ✅ 系统 | ✅ 本期 |
| 生成 YouTube 标题、描述 | 元数据生成 Agent | ✅ 系统 | ✅ 本期 |
| 生成封面提示词 + 调图片模型出封面图 | 元数据生成 Agent + Gemini 图片模型 | ✅ 系统 | ✅ 本期 |
| 用外部 AI 工具产出两段 8s 视频 | 人工手动 | ❌ 人工，不在系统内 | — |
| 将两段视频上传到对应关键词下 | 人工手动 | ✅ 系统提供上传入口 | ✅ 本期 |
| 合并两段分镜为完整视频 | 系统 | ✅ 系统 | ✅ 本期 |
| 成品打包（成品视频 + 标题/描述/封面）供下载 | 系统 | ✅ 系统 | ✅ 本期（链路终点） |
| 上传发布到 YouTube 矩阵号 | AdsPower 自动化系统 | ✅ 系统（后续模块） | ⛔ 本期不做，隔离到 AdsPower 模块 |
| YouTube 账号复制 / 优化（对标频道） | 人工手动 | ❌ 不纳入系统需求 | — |

一句话概括：**本期系统做「脚本 + 元数据 + 封面出图 + 合并 + 成品打包」**；视频画面本身由人工用外部工具产出后上传；上传发布到矩阵号属于 AdsPower 自动化系统，本期隔离不做。

### 23.3 内容生成流程

```mermaid
flowchart TD
    A["输入搜索词 / 关键词系统传入高分真空长尾词"] --> B["元数据生成 Agent"]
    A --> C["脚本分镜生成 Agent"]
    B --> B1["生成 YouTube 标题"]
    B --> B2["生成 YouTube 描述"]
    B --> B3["生成封面提示词"]
    B3 --> B4["调 Gemini 图片模型生成封面图"]
    C --> C1["生成 16s 分镜脚本（8s 分镜 1）"]
    C --> C2["生成 16s 分镜脚本（8s 分镜 2）"]
    C1 --> D["人工用外部 AI 工具产出两段 8s 视频"]
    C2 --> D
    D --> E["人工将两段视频上传到对应关键词下"]
    E --> F["系统合并两段分镜为完整视频"]
    B1 --> G["成品打包：成品视频 + 标题/描述/封面"]
    B2 --> G
    B4 --> G
    F --> G
    G --> H["下载成品包（本期链路终点）"]
    H -.后续.-> I["AdsPower 自动化系统：上传发布到矩阵号"]
```

关键词来源两种（本期两种都做）：

- 手动输入搜索词（含批量粘贴，来自实用工具「获取 Suggest API 长尾词」或关键词结果的导出）。
- 由关键词系统结果页一键「送入内容生成」，把高分真空长尾词传入（与第 10 节关键词系统衔接）。

### 23.4 元数据生成 Agent

#### 23.4.1 需求描述

根据关键词（搜索词或高分长尾词）生成一条 YouTube 视频的元数据：标题、描述、封面（缩略图）。每个关键词生成各不相同的元数据。

#### 23.4.2 输出内容

| 输出项 | 说明 |
| --- | --- |
| YouTube 标题 | 围绕关键词生成，用于自然搜索截流 |
| YouTube 描述 | 视频描述区文案 |
| 封面提示词 | 用于图片模型出图的英文/描述性提示词 |
| YouTube 封面（缩略图） | 由封面提示词经图片模型生成的图片文件 |

#### 23.4.3 封面生成方案（用户确认）

封面采用「文本 Agent 出提示词 → 图片模型出图」两步：

1. 元数据生成 Agent（文本模型，复用现有 `_call_ai_stream` 链路）在 JSON 里同时产出 `thumbnail_prompt`（封面提示词）。
2. 后端拿 `thumbnail_prompt` 调 Gemini 图片模型 `gemini-3.1-flash-image` 生成封面图，落地为文件，路径记录到 `ContentItem`。

图片模型配置在「全局设置」中维护：Key、模型名可随时调整。图片接口的具体调用格式（OpenAI 兼容的 `/v1/images/generations`，还是 chat 接口返回图片）由开发阶段以 `GET /v1/models` 探测确认。

#### 23.4.4 输出格式（固定 JSON）

按第 17 节全局约定，元数据生成 Agent 输出固定 JSON。建议字段（开发阶段可微调，但需固定）：

```json
{
  "keyword": "原样的关键词",
  "title": "YouTube 视频标题",
  "description": "YouTube 视频描述文案",
  "thumbnail_prompt": "用于图片模型的封面提示词"
}
```

### 23.5 脚本分镜生成 Agent

#### 23.5.1 需求描述

根据关键词生成一个约 16s 视频的分镜脚本。分镜段数为**可变参数**，**默认 8+8（两段各 8s）**，现阶段先用默认值。

#### 23.5.2 固定规则（Notion 原文 + 2026-08-05 用户修正）

```text
Notion 原文：暂时写死脚本分镜是两个，8+8，暂时不变。
用户修正（2026-08-05）：段数做成可变参数，默认 8+8，现阶段先这样。
```

即：实现上把分镜段数、每段时长做成可配置参数，默认值为「两段各 8s」；现阶段沿用默认，后续可调。无论关键词是什么，都批量生成约 16s 的 AI 视频，目的是推广 promo code。

#### 23.5.3 输出格式（固定 JSON）

按第 17 节全局约定，输出固定 JSON。分镜段数由参数控制，默认两段各 8s。建议字段（开发阶段可微调）：

```json
{
  "keyword": "原样的关键词",
  "total_duration": 16,
  "shots": [
    {"index": 1, "duration": 8, "scene": "分镜 1 画面描述", "prompt": "用于外部 AI 视频工具的生成提示词"},
    {"index": 2, "duration": 8, "scene": "分镜 2 画面描述", "prompt": "用于外部 AI 视频工具的生成提示词"}
  ]
}
```

分镜段数默认为 2、每段 8s，可通过参数调整（现阶段用默认）。前端把每个分镜的 `prompt` 直接展示，方便人工复制到外部 AI 视频工具里出片。

### 23.6 内容生成 Agent 管理

Notion 明确要求：

```text
agent 的提示词，要在一级列表「内容生成系统」下新增一个「内容生成 agent 管理」，
这两个 agent 的提示词要在此可配置，逻辑和关键词系统下的关键词 agent 管理一致。
```

需求要点：

- 在一级目录「内容生成系统」下新增「内容生成 Agent 管理」子页面。
- 元数据生成 Agent、脚本分镜生成 Agent 的提示词均在此可配置。
- 交互逻辑与关键词系统下的关键词 Agent 管理保持一致。

### 23.7 任务管理

Notion 明确要求：

```text
新增二级列表「任务管理」，把任务流程放入任务管理中执行。
```

需求要点：

- 在内容生成系统下新增二级列表「任务管理」。
- 内容生成的任务流程在任务管理中执行，一个任务批次可含多个关键词，每个关键词一条记录。
- 参考关键词系统任务的执行与记录模式：支持暂停 / 停止 / 重启，任务与结果分页、搜索筛选，工作日志抽屉。

一个任务批次内每条关键词记录的处理与人工介入步骤：

| 步骤 | 触发方 | 说明 |
| --- | --- | --- |
| 1. 生成元数据 | 系统（Agent） | 标题、描述、封面提示词，随后调图片模型出封面图 |
| 2. 生成分镜脚本 | 系统（Agent） | 固定 8+8 两个分镜 JSON |
| 3. 上传两段 8s 视频 | 人工 | 每条关键词提供两个上传位（分镜 1 / 分镜 2） |
| 4. 合并成品 | 系统 | 两段视频按顺序合并为一个 16s 成品视频 |
| 5. 下载成品包 | 人工 | 成品视频 + 标题/描述/封面 一起打包下载（本期链路终点） |

### 23.8 UI 要求

Notion 明确要求：

```text
要求界面 UI 和关键词系统保持一致。整个系统使用同一套 UI。
```

### 23.9 已确认技术方案（2026-08-05）

原待确认问题已与用户逐条确认，结论如下：

| 原问题 | 确认结论 |
| --- | --- |
| 封面如何生成 | 元数据 Agent 出封面提示词，再调 Gemini 图片模型 `gemini-3.1-flash-image` 出图；Key 与模型名在全局设置维护 |
| 分镜合并处理 | 本期**统一转码后合并**为约 16s 成品（避免编码不一致导致 concat 失败）；转场/字幕/配乐等后续再评估 |
| 上传发布边界 | 本期做到「成品打包」为止，不接 YouTube 官方 API；发布到矩阵号属 AdsPower 自动化系统，本期隔离不做 |
| 关键词如何进入内容生成 | 两种入口都做：手动输入/批量粘贴 + 关键词结果页一键「送入内容生成」 |
| 两个 Agent 的 JSON 字段 | 见 23.4.4、23.5.3 建议结构（开发阶段可微调，但需固定） |
| 分镜段数 | **可变参数，默认 8+8**，现阶段用默认（2026-08-05 用户确认）|
| 视频上传校验 | **只校验格式，不强制 8s 时长**（2026-08-05 用户确认）|

开发阶段细节已确认（不再阻塞）：

- **Gemini 图片接口调用格式（2026-08-05 实测确认）**：`gemini-3.1-flash-image` **不走** `/v1/images/generations`（该接口只支持 imagen 系列，会报 "only imagen models are supported"），**走 `/v1/chat/completions`**（与文本 Agent 同接口），平台强制 `stream:true`，图片以 `![image](data:image/jpeg;base64,...)` markdown 内嵌在 SSE 的 `delta.content` 里；拼接所有 chunk 后用正则抽 base64 解码存文件。实测出图为合法 JPEG（约 800KB）。可复用 demo 见 `调研/gemini_image_demo.py`。
- 上传视频校验规则：只校验格式（是否为视频文件），不强制约 8s 时长。

---

## 24. 内容生成系统功能清单（流程二）

状态说明：✅ 已完成　🚧 部分完成　⏳ 待开发　⛔ 暂不开发

| 编号 | 功能 | 来源说明 | 状态 |
| --- | --- | --- | --- |
| CG-001 | 手动输入 / 批量粘贴关键词创建内容生成任务 | Notion：输入搜索词；用户确认两种入口都做 | ✅ 已完成 |
| CG-002 | 关键词结果页一键「送入内容生成」（传入高分长尾词） | Notion：由关键词系统传入；用户确认 | ✅ 已完成 |
| CG-003 | 元数据生成 Agent：生成 YouTube 标题 | Notion：元数据 agent 生成标题 | ✅ 已完成 |
| CG-004 | 元数据生成 Agent：生成 YouTube 描述 | Notion：元数据 agent 生成描述 | ✅ 已完成 |
| CG-005 | 元数据生成 Agent：生成封面提示词 | 用户确认：Agent 先出封面提示词 | ✅ 已完成 |
| CG-006 | 调 Gemini 图片模型（gemini-3.1-flash-image）生成封面图 | 用户确认：接 Gemini 图片模型出图 | ✅ 已完成（实测出图 JPEG ~800KB）|
| CG-007 | 脚本分镜生成 Agent：生成约 16s（默认 8+8）分镜脚本 | Notion：脚本分镜 agent 生成 16s(8+8) 分镜 | ✅ 已完成 |
| CG-008 | 分镜段数为可变参数，默认两段各 8s | Notion 原文写死 8+8；用户 2026-08-05 修正为可变参数默认 8+8 | ✅ 已完成（创建任务可设段数/时长）|
| CG-009 | 两个 Agent 输出固定 JSON | 第 17 节全局约定 | ✅ 已完成 |
| CG-010 | 内容生成 Agent 管理：两个 Agent 提示词可配置 | Notion：新增内容生成 agent 管理，逻辑同关键词 agent 管理 | ✅ 已完成 |
| CG-011 | 新增二级列表「任务管理」承载流程执行 | Notion：新增二级列表任务管理 | ✅ 已完成 |
| CG-012 | 人工上传分镜视频到对应关键词下（只校验格式，不强制 8s） | Notion：将分镜上传到关键词下 | ✅ 已完成 |
| CG-013 | 系统统一转码后合并分镜为完整视频 | Notion：系统合并分镜；用户确认统一转码后合并 | ✅ 已完成（实测不同分辨率合并出 16s 成品）|
| CG-014 | 成品打包：成品视频 + 标题/描述/封面一键打包下载（供人工在 AdsPower 上传） | 用户确认：本期链路终点为成品打包 | ✅ 已完成（zip 含 metadata.txt+cover+final_video）|
| CG-015 | 任务支持暂停 / 停止 / 重启 | 沿用关键词系统模式 | ✅ 已完成（另加单条「重新生成」重试）|
| CG-016 | 任务与结果分页、搜索筛选、工作日志抽屉 | 沿用关键词系统模式 | ✅ 已完成 |
| CG-017 | UI 与关键词系统保持一致，使用同一套 UI | Notion：界面 UI 和关键词系统保持一致 | ✅ 已完成 |
| CG-018 | 上传发布到 YouTube 矩阵号 | Notion：上传发布 | ⛔ 本期不做，归 AdsPower 自动化系统 |
| CG-019 | 人工用外部工具产出两段 8s 视频 | Notion：人工手动视频生成 | ⛔ 人工操作，不在系统内 |
| CG-020 | YouTube 账号复制 / 优化（对标频道） | Notion：完全复制 / 优化后方案 | ⛔ 人工操作，不纳入系统需求 |

---

## 25. 内容生成系统技术实现方案（2026-08-05 确认）

本节为通读现有代码库后确定的落地方案，供开发参考。核心原则：**复用关键词系统已验证的模式**，两个系统解耦。

### 25.1 后端结构

新建独立 Django app `backend/content_gen/`，与 `keywords` app 平级，注册到 `config/settings.py` 的 INSTALLED_APPS 和 `config/urls.py`。

数据模型（三张表，仿 `keywords` 现有模式）：

| 模型 | 作用 | 关键字段 |
| --- | --- | --- |
| `ContentAgent` | 两个 Agent 的提示词配置（仿 `AgentPrompt`） | agent_type（metadata / storyboard）、name、description、prompt、enabled |
| `ContentRun` | 内容生成任务批次 | 来源关键词、country、language、status、task_token、run_log、created_at |
| `ContentItem` | 每个关键词一条记录 | keyword、title、description、thumbnail_prompt、thumbnail_file、storyboard（JSON）、clip1_file、clip2_file、merged_file、status、elimination_reason |

服务与任务（复用 `keywords/services.py` 已有能力）：

- 复用 `_call_ai_stream()`（moretokens SSE 流式）、`_extract_json()`（容错解析）、`get_setting()`。
- 新增 `generate_metadata()`：文本→标题/描述/封面提示词。
- 新增 `generate_thumbnail()`：调 Gemini 图片模型出封面图，落地为文件。**注意：走 `/v1/chat/completions` + `stream:true`，从 SSE content 里抽 `data:image/...;base64,` 解码存文件**（不是 `/v1/images/generations`，详见 23.9 与 `调研/gemini_image_demo.py`）。
- 新增 `generate_storyboard()`：→分镜 JSON，段数可变默认 8+8。
- 新增 `merge_clips()`：用 ffmpeg **统一转码后**把多段视频合并为成品（先各段转成统一编码/分辨率/帧率，再 concat，避免编码不一致导致合并失败）。
- Celery `@shared_task` 跑生成流程，沿用 `task_token` 暂停/停止机制。

接口（ViewSet + DefaultRouter，仿 `keywords/views.py`）：

- `content-agents`：Agent 提示词列表 / 编辑 / 恢复默认。
- `content-runs`：任务创建 / 列表 / 详情 / 暂停 / 停止 / 重启 / 日志。
- `content-items`：结果列表；视频上传接口（只校验格式）；触发合并；**成品打包 zip 一键下载**（打包成品视频 + 标题/描述/封面，供人工在 AdsPower 手动上传；AdsPower 自动化本期不做）。

### 25.2 前端结构（渐进式组件化）

不引入 vue-router，保留 `App.vue` 的 `activeMenu` + `v-if` 切页方式。新模块拆为独立组件：

- `frontend/src/components/ContentTasks.vue`：任务管理（创建、列表、每行上传两段视频、触发合并、下载成品包）。
- `frontend/src/components/ContentAgents.vue`：内容生成 Agent 管理（两个 Agent 提示词，逻辑同关键词 Agent 管理）。
- `App.vue`：把当前 disabled 的「内容生成系统（后续）」菜单项换成二级菜单（任务管理 + 内容生成 Agent 管理），挂载上述组件；关键词结果页每行加「送入内容生成」按钮。

现有关键词系统的 `App.vue` 代码保持不动，UI 复用 Element Plus 保持一致。

### 25.3 全局设置新增项

在「全局设置」（`GlobalSetting` 表）新增：

| Key | 说明 |
| --- | --- |
| `GEMINI_IMAGE_API_KEY` | Gemini 图片模型 API Key |
| `GEMINI_IMAGE_MODEL` | 图片模型名，默认 `gemini-3.1-flash-image` |

（文本 Agent 复用现有 `AI_BASE_URL` / `AI_API_KEY` / `AI_MODEL`。）

### 25.4 基础设施改动

- **ffmpeg**：合并视频依赖，需在 `backend/Dockerfile` 安装。
- **文件存储**：上传的视频、生成的封面、合并成品用 Django media 目录 + docker volume 持久化。
- 改后端代码后需 rebuild 镜像并跑 migration 才生效。

### 25.5 API Key 记录（测试用）

| 类型 | Key |
| --- | --- |
| Gemini 图片模型 | `sk-yYkPulZaWOs0NuNsNITZyaIxmLpEW4YG1s3M4RaPb2Ms617Y` |

> 与第 7 节测试 Key 一致，均为测试使用，按用户要求明文记录。图片模型走 moretokens 平台（与文本模型同平台）。

### 25.6 开发完成情况（2026-08-06）

内容生成系统（流程二）本期功能已全部开发并端到端跑通，见第 24 节功能清单（CG-001~CG-017 全 ✅）。落地要点与实测记录：

- **后端**：新建 `content_gen` app（models/services/tasks/views/serializers/urls），复用 keywords 的 `_call_ai_stream`/`_extract_json`/`get_setting`。三张表 ContentAgent / ContentRun / ContentItem。迁移 0001+0002（0002 种子两个 Agent 默认提示词）。
- **封面出图关键坑（务必注意）**：图片模型 `gemini-3.1-flash-image` 走 `/v1/chat/completions`（不是 images/generations），已按此实现并实测出图 JPEG ~800KB。**但文本模型用的 `AI_API_KEY` 不一定有图片模型权限**——实测该 Key 调图片模型返回 503；换用 25.5 记录的测试 Key（写入全局设置 `GEMINI_IMAGE_API_KEY`）即成功。**部署时封面 Key 需单独配置有图片权限的 Key。**
- **合并**：ffmpeg 统一转码（scale+pad 到 1080×1920、30fps、H.264+AAC）后 concat；实测把 640×480 与 1280×720 两段合并出 16.02s 成品。音轨缺失时自动退化为仅视频合并。ffmpeg 已装入 backend/worker 镜像。
- **成品打包**：`GET /api/content-items/{id}/package/` 返回 zip（metadata.txt + cover + final_video.mp4），实测 ~1MB。
- **文件存储**：media 目录 + docker volume `media_data`（backend/worker 共享写，nginx `/media/` 只读托管）。nginx 放宽 `client_max_body_size 300m` 以支持上传。
- **额外增强**：单条记录「重新生成 AI 内容」端点（regenerate），用于部分失败（如封面 503）时重试，不影响已上传的分镜视频与已合并成品。
- **前端**：渐进式组件化，新增 `components/ContentTasks.vue` 与 `components/ContentAgents.vue`，App.vue 挂二级菜单「内容生成系统」+ 关键词结果页「送入内容生成」按钮，未引入 vue-router。

---

## 26. 用户确认记录：2026-08-05

以下为本轮沟通中确认的内容生成系统（流程二）产品与技术决策：

| 问题 | 确认结果 |
| --- | --- |
| 流程一 / 流程二取舍 | 当轮（2026-08-05）先开发流程二；流程二完成后，流程一于 2026-08-06 确认为本期开发目标（见第 27~30 节） |
| 账号复制 / 优化方案 | 属用户手动操作，不纳入系统需求 |
| 系统职责边界 | 系统只做脚本 + 元数据 + 封面出图 + 合并 + 成品打包 |
| 关键词入口 | 手动输入 + 关键词结果页一键送入，两种都做 |
| 本期链路终点 | 做到成品打包（成品视频 + 标题/描述/封面），可下载 |
| 上传发布 | 本期不做，归 AdsPower 自动化系统 |
| 封面生成 | Agent 出封面提示词，接 Gemini `gemini-3.1-flash-image` 出图 |
| 后端结构 | 新建独立 `content_gen` app，复用关键词系统模式 |
| 前端结构 | 渐进式组件化，不引入 router，新模块拆为独立组件 |
| 分镜段数 | 可变参数，默认 8+8，现阶段用默认 |
| 视频合并 | 统一转码后再合并（避免编码不一致导致 concat 失败）|
| 上传校验 | 只校验格式，不强制 8s 时长 |
| 封面出图接口（实测确认）| `gemini-3.1-flash-image` 走 `/v1/chat/completions` + `stream:true`，从 SSE 抽 base64 解码；**不走** `/v1/images/generations`。实测出图合法 JPEG ~800KB，可复用 demo `调研/gemini_image_demo.py`。正式上线用此模型；另一窗口另有一份出图 demo，开发完需一并测试 |
| 成品打包 | 一键打包下载全部内容（成品视频+标题+描述+封面），供人工在 AdsPower 上传；AdsPower 自动化本期不做 |

---

## 27. 内容生成系统需求（流程一·全自动化方案）

来源：Notion 总体架构页流程一原文 + 早期内容生成分解原文（见第 4.3.1）。本节为 3.0 新增，是本期开发目标。

> 本期开发决策总览（2026-08-06 与用户确认，详见第 29 节）：
> - **流程一 = 流程二的全自动版**：两个 Agent（元数据、脚本分镜）与 Gemini 封面出图**完全复用流程二**，不新配一套。
> - 唯一实质差异：视频生成方式。流程二靠人工产出两段 8s 视频再上传合并；流程一改为**系统内用 Remotion 自动渲染视频**，砍掉人工产出与上传，实现全自动。
> - **新增旁白音频（TTS）**：脚本分镜 Agent 额外输出每段旁白文案；后端用 TTS 转音频，混入视频。TTS 默认 **Edge TTS**（微软免费、无 key），同时接入 **elevenlabs**（付费、需 key），做成可切换，两者一起开发。
> - **Remotion 模板 v1 为纯文字动效模板**（标题/关键词/promo code 文字动画 + 背景色/渐变 + 封面图作背景 + 旁白音频），不接外部素材库。
> - 界面：「内容生成系统」下**新增并列子菜单「流程一·全自动任务管理」**，流程二完全不动。
> - 本期链路终点同流程二：全自动产出成品 + 元数据包，可下载；不接 YouTube 官方 API、不接 AdsPower 自动发布。

### 27.1 需求概述

流程一在全自动化下，把流程二里「人工产出两段 8s 视频 → 人工上传 → 系统合并」这一整段，替换为「TTS 生成旁白音频 → Remotion 用模板 + 数据自动渲染 16s 成品」。其余环节（两个 Agent、封面出图、成品打包）与流程二一致。

Notion 原文流程（见第 4.3.1）：

```text
输入搜索词（支持输入多个或者直接上传文本，一行一个搜索词）
—— 脚本分镜 agent 生成分镜脚本
—— 元数据 agent 生成 YouTube 标题描述封面
—— Gemini 生图
—— 视频生成选择 remotion 自建（全自动渲染，无需人工产出与上传）
```

本期在流程二两个 Agent 的基础上：

1. 脚本分镜生成 Agent **新增每段旁白文案（narration）** 字段输出。
2. 新增 **TTS 音频生成**（Edge TTS / elevenlabs 可切换）。
3. 新增 **Remotion 渲染服务**（Node 独立容器），用模板 + inputProps 全自动出片。

### 27.2 系统职责边界（用户确认）

| 步骤 | 执行方 | 是否在本系统 | 与流程二对比 |
| --- | --- | --- | --- |
| 输入搜索词（多个 / 上传 txt 一行一个） | 系统 | ✅ 系统 | 流程二无「上传 txt」，流程一新增 |
| 生成 YouTube 标题、描述 | 元数据生成 Agent | ✅ 系统 | 复用流程二 |
| 生成封面提示词 + 调 Gemini 出封面图 | 元数据 Agent + Gemini | ✅ 系统 | 复用流程二 |
| 生成 16s（默认 8+8）分镜脚本 + **每段旁白文案** | 脚本分镜生成 Agent | ✅ 系统 | 流程一新增旁白文案字段 |
| **旁白文案 → 音频（TTS）** | 系统（Edge TTS / elevenlabs） | ✅ 系统 | 流程一新增 |
| **用 Remotion 模板自动渲染 16s 成品视频** | 系统（Remotion 渲染服务） | ✅ 系统 | 流程二为人工产出 + 上传 + 合并；流程一全自动 |
| 用外部 AI 工具产出视频画面 | — | ❌ 不需要 | 流程二需人工，流程一取消 |
| 人工上传视频 | — | ❌ 不需要 | 流程二需人工，流程一取消 |
| 成品打包（成品视频 + 标题/描述/封面）供下载 | 系统 | ✅ 系统（链路终点） | 同流程二 |
| 上传发布到 YouTube 矩阵号 | AdsPower 自动化系统 | ⛔ 本期不做 | 同流程二 |
| YouTube 账号复制 / 优化 | 人工 | ❌ 不纳入系统需求 | 同流程二 |

一句话概括：**流程一系统做「输入（含上传 txt）+ 元数据 + 封面出图 + 分镜脚本 + 旁白音频 + Remotion 自动渲染 + 成品打包」，全程无人工介入**；上传发布仍归 AdsPower，本期隔离不做。

### 27.3 内容生成流程（流程一）

```mermaid
flowchart TD
    A["输入搜索词（多个 / 上传 txt 一行一个）"] --> B["元数据生成 Agent（复用流程二）"]
    A --> C["脚本分镜生成 Agent（复用 + 新增旁白文案）"]
    B --> B1["生成 YouTube 标题"]
    B --> B2["生成 YouTube 描述"]
    B --> B3["生成封面提示词"]
    B3 --> B4["调 Gemini 图片模型生成封面图"]
    C --> C1["生成 8+8 分镜（画面描述 + 生成提示词）"]
    C --> C2["每段旁白文案 narration"]
    C2 --> C3["TTS 生成旁白音频（Edge TTS / elevenlabs 可切换）"]
    subgraph R["Remotion 渲染服务（新增 Node 容器）"]
      R1["纯文字动效模板 + inputProps<br/>（标题/关键词/promo/分镜文字/封面图/旁白音频）"] --> R2["自动渲染 16s 成品 mp4"]
    end
    C1 --> R1
    C3 --> R1
    B4 --> R1
    R2 --> G["成品打包：成品视频 + 标题/描述/封面"]
    B1 --> G
    B2 --> G
    B4 --> G
    G --> H["下载成品包（本期链路终点）"]
    H -.后续.-> I["AdsPower 自动化系统：上传发布到矩阵号"]
```

关键词来源（流程一）：

- 手动输入搜索词（支持多个）。
- **上传文本文件（.txt，一行一个搜索词）** —— 流程一新增，Notion 原文明确要求。
- 由关键词系统结果页一键「送入内容生成」（可复用流程二入口）。

### 27.4 两个 Agent 复用与扩展

用户确认：**两个 Agent 完全复用流程二**（元数据生成 Agent、脚本分镜生成 Agent），提示词在「内容生成 Agent 管理」页统一配置，流程一不新建一套。

唯一扩展：**脚本分镜生成 Agent 新增每段旁白文案 `narration`**，供 TTS 转音频。输出仍为固定 JSON（第 17 节全局约定），在流程二结构（第 23.5.3）上加 `narration` 字段：

```json
{
  "keyword": "原样的关键词",
  "total_duration": 16,
  "shots": [
    {"index": 1, "duration": 8, "scene": "分镜 1 画面描述", "prompt": "用于渲染/外部工具的生成提示词", "narration": "分镜 1 旁白文案"},
    {"index": 2, "duration": 8, "scene": "分镜 2 画面描述", "prompt": "...", "narration": "分镜 2 旁白文案"}
  ]
}
```

说明：`narration` 为该段旁白的文字稿（LLM 只能产出文字，出声音必须经 TTS）。段数、每段时长沿用可变参数、默认 8+8。元数据生成 Agent 输出不变（第 23.4.4）。

### 27.5 旁白音频（TTS）方案

用户确认：LLM 只写旁白文案，出声音必须接 TTS 工具。moretokens 平台无音频能力，故单独接 TTS，做成**可切换双方案，两者一起开发**。

| 方案 | 说明 | 成本 / Key |
| --- | --- | --- |
| Edge TTS（默认） | 微软 Edge「大声朗读」背后的在线 TTS 服务（`edge-tts`）。免费、无需 API key、无需 Windows、多语言，直接输出 mp3 | 免费，无 key |
| elevenlabs | 多语言音质最佳的商用 TTS | 付费，需单独 key（用户提供） |

要点：

- TTS 引擎在「全局设置」可切换（`TTS_PROVIDER`：`edge` / `elevenlabs`），并配置对应参数（voice、elevenlabs key 等）。
- 输入为脚本分镜 Agent 产出的每段 `narration`，输出为按段的音频文件；渲染时按分镜顺序对齐到对应时间段。
- 语言跟随任务的 `language`；voice 可配置。
- 参考：Edge TTS（免费、无 key）见 `https://github.com/rany2/edge-tts`。

### 27.6 Remotion 视频渲染方案

用户确认：视频生成用 **Remotion 自建**；用户不熟悉 Remotion，需要开发方搭好并给出中文使用说明。

**Remotion 是什么（大白话）**：用代码写视频的工具——写一个 React 网页模板（标题放哪、背景、文字怎么动、配哪段音频），Remotion 用无头 Chromium 把网页逐帧渲染再拼成 mp4。核心是「**同一个模板 + 每次喂不同数据（inputProps）= 批量出无数条不同视频**」，正好对应「一个模板、每次换元素」的诉求。

| 事项 | 方案 |
| --- | --- |
| 模板 v1 | **纯文字动效模板**：标题 / 关键词 / promo code 文字动画 + 背景色/渐变 + 封面图作背景 + 旁白音频；不接外部素材库 |
| 换元素方式 | 后端为每个关键词生成一份 `inputProps`（标题、关键词、promo code、每段分镜文字、封面图路径、旁白音频路径），传给同一模板 |
| 批量渲染 | 命令行 `npx remotion render 模板 --props=数据.json 输出.mp4`，或 Node API `renderMedia()`；后端循环每个关键词调用 |
| 运行环境 | Remotion 是 **Node.js 生态、需无头 Chromium**；现有后端为 Python/Django，故**新增独立 Node「渲染服务」容器**，Django/Celery 通过它渲染 |
| Remotion Agent Skills | `npx skills add remotion-dev/skills` 安装后可用 `/remotion-create`、`/remotion-render` 等指令辅助搭模板与渲染（`https://www.remotion.dev/docs/ai/skills`） |
| 交付物 | 开发方搭好模板与渲染服务，并交付一份中文说明：如何改模板、Skills 怎么装用、如何批量渲染大量视频 |

时长与分镜：总时长 = 段数 × 每段时长（默认 16s = 8+8）；每段对应一段旁白音频与一屏文字动效。

### 27.7 任务管理（流程一）

- 在「内容生成系统」下新增**并列子菜单「流程一·全自动任务管理」**，与流程二任务管理并列，流程二完全不动。
- 沿用关键词系统 / 流程二的任务执行与记录模式：支持暂停 / 停止 / 重启，任务与结果分页、搜索筛选，工作日志抽屉。
- 一个任务批次可含多个关键词，每个关键词一条记录。

流程一每条关键词记录的处理步骤（全自动、无人工介入）：

| 步骤 | 触发方 | 说明 |
| --- | --- | --- |
| 1. 生成元数据 | 系统（Agent） | 标题、描述、封面提示词，随后调 Gemini 出封面图 |
| 2. 生成分镜脚本 + 旁白文案 | 系统（Agent） | 默认 8+8 分镜 JSON，每段含 `narration` |
| 3. 生成旁白音频 | 系统（TTS） | 按段把 `narration` 转音频（Edge TTS / elevenlabs） |
| 4. 渲染成品 | 系统（Remotion） | 模板 + inputProps 自动渲染出 16s 成品视频 |
| 5. 成品打包 | 系统 | 成品视频 + 标题/描述/封面 打包，可下载（本期链路终点） |

对比流程二：流程二的步骤 3~4 是「人工上传两段视频 + 系统合并」，流程一替换为「TTS + Remotion 自动渲染」。

### 27.8 UI 要求

沿用第 23.8：界面 UI 与关键词系统、流程二保持一致，整个系统使用同一套 UI（Element Plus）。流程一新增的子菜单、上传 txt、任务/结果页均复用现有组件风格。

---

## 28. 内容生成系统功能清单（流程一）

状态说明：✅ 已完成　🚧 部分完成　⏳ 待开发　⛔ 暂不开发

| 编号 | 功能 | 来源说明 | 状态 |
| --- | --- | --- | --- |
| CG1-001 | 手动输入（多个）创建流程一任务 | Notion：输入搜索词，支持多个 | 🚧 部分完成：前端支持多行关键词，但流程一实际只取首个关键词（`views.py::create` 取 keywords[0]）；「多个」在流程一体现为「一个关键词 × 数量/CSV 行数」。多关键词批量待做 |
| CG1-002 | 上传文本文件（.txt 一行一个搜索词）创建任务 | Notion：直接上传文本，一行一个 | ⏳ 待开发：现有文件上传是「变量文件（CSV）」，不是关键词 txt 导入 |
| CG1-003 | 关键词结果页一键「送入内容生成」（可复用流程二入口） | 复用流程二 CG-002 | ✅ 已完成：`ContentTasks.vue` injectedKeywords 回填 |
| CG1-004 | 复用元数据生成 Agent：标题 / 描述 / 封面提示词 | Notion：元数据 agent；用户确认复用 | ✅ 已完成：`services.py::generate_metadata` |
| CG1-005 | 复用 Gemini 封面出图（走 chat/completions 取 base64） | 用户确认复用流程二 | ✅ 已完成：`services.py::generate_thumbnail` |
| CG1-006 | 流程一旁白 Agent：约 16s（默认 8+8）旁白 | Notion：脚本分镜 agent；实际演进为独立 narration Agent | ✅ 已完成（已演进）：流程一走**独立 narration Agent**（`generate_narration_script`），只出旁白文案；流程二才走 storyboard 出画面分镜。见第 33 节 |
| CG1-007 | 旁白 Agent 输出每段旁白文案 narration | 用户确认：流程一新增音频 | ✅ 已完成：NARRATION_OUTPUT_SPEC 每段含 narration，且约束字数贴合段时长 |
| CG1-008 | 分镜段数为可变参数（已挪到模板上，AI 分析建议 + 运营微调） | 沿用流程二，演进为模板属性 | ✅ 已完成（已演进）：段数/每段时长由 `VideoTemplate.shot_count/shot_duration` 决定，创建任务不再填 |
| CG1-009 | 接入 Edge TTS（微软免费、无 key）生成旁白音频 | 用户确认：默认免费方案 | ✅ 已完成：`services.py::_tts_edge`，requirements 含 edge-tts；多语言音色映射 |
| CG1-010 | 接入 elevenlabs 生成旁白音频 | 用户确认：一起开发 | ✅ 已完成：`_tts_elevenlabs` 走 REST 裸调，需配 ELEVENLABS_API_KEY |
| CG1-011 | TTS 引擎可切换（edge / elevenlabs）+ 互为降级容错 | 用户确认：可切换 | ✅ 已完成：`ContentRun.tts_provider`，双向降级，双失败跳过该段不中断 |
| CG1-012 | 新增 Remotion 渲染服务（Node 独立容器） | Notion：视频生成 remotion 自建 | ✅ 已完成：`render/server.mjs`（Express + @remotion/bundler/renderer），compose 中 render 服务 + 共享 media 卷 |
| CG1-013 | 文字动效模板 v1（+ 已扩展分屏模板） | 用户确认：第一版纯文字动效模板 | ✅ 已完成（已扩展）：`PromoVideo.tsx`（竖屏纯文字动效）+ `SplitScreenPromo.tsx`（横屏左右分屏 + 录屏素材），均在 Root.tsx 注册 |
| CG1-014 | 后端生成 inputProps，批量自动渲染成品 | Notion：批量生成；用户确认批量渲染 | ✅ 已完成：`services.py::render_video` 组装 inputProps POST 给 render 服务；`tasks.py::_finalize_flow1_item` 逐条渲染 |
| CG1-015 | 交付中文使用说明（改模板 / Skills 装用 / 批量渲染） | 用户要求：需引导使用 | ✅ 已完成：`视频模板与流程一使用说明.md`、`render/使用说明.md`、`render/Remotion操作文档.md` |
| CG1-016 | 流程一任务管理界面（与流程二同页，用 flow 切换） | 用户确认：新增子菜单 | ✅ 已完成（已演进）：未新建并列子菜单，而是在同一「内容生成-任务管理」页内以 flow1/flow2 切换。见第 32 节 |
| CG1-017 | 任务支持暂停 / 停止 / 重启 | 沿用流程二 | ✅ 已完成：`ContentRunViewSet` pause/stop/restart + task_token |
| CG1-018 | 任务与结果分页、搜索筛选、工作日志抽屉 | 沿用流程二 | ✅ 已完成：分页/search/gen_log 日志抽屉（metadata/thumbnail/narration/render 各步） |
| CG1-019 | 全自动产出成品并成品打包下载 | 用户确认：链路终点为成品打包 | ✅ 已完成：`ContentItemViewSet.package` 打 zip（metadata + cover + final_video，兼容两流程） |
| CG1-020 | UI 与关键词系统 / 流程二保持一致 | Notion：UI 一致 | ✅ 已完成：同一套 Element Plus |
| CG1-021 | 上传发布到 YouTube 矩阵号 | Notion：上传发布 | ⛔ 本期不做，归 AdsPower 自动化系统 |
| CG1-022 | YouTube 账号复制 / 优化（对标频道） | Notion：完全复制 / 优化后方案 | ⛔ 人工操作，不纳入系统需求 |
| CG1-023 | 视频模板体系（模板库 + 参考视频 AI 分析 + 变量声明 + 素材上传 + 两状态） | 开发中演进出的新能力 | ✅ 已落地，详见第 31 节 |

---

## 29. 内容生成系统技术实现方案（流程一，2026-08-06 确认）

本节为落地方案，供开发参考。核心原则：**最大化复用流程二 `content_gen` app**，仅在需要处扩展；Node 渲染服务与 Python 后端解耦。

### 29.1 后端结构（复用 content_gen，增量扩展）

流程一不新建 app，复用现有 `backend/content_gen/`，按需增量扩展：

| 项 | 改动 |
| --- | --- |
| `ContentRun` | 新增字段：`flow`（`flow1` / `flow2`，区分流程；默认 `flow2` 兼容存量）、`tts_provider`（edge / elevenlabs）、`promo_code`（创建任务时手填，整批共用，渲染时注入模板）。上传 txt 解析为多关键词后建 `ContentItem` |
| `ContentItem` | 新增字段：`narration_audio`（按段旁白音频文件列表）、`rendered_file`（Remotion 渲染成品，区别于流程二人工合并的 `merged_file`）。`storyboard` 的 shot 增加 `narration` |
| `ContentAgent` | 不变，两个 Agent 复用；脚本分镜 Agent 的输出规范（OUTPUT_SPEC）增加 `narration` 字段 |

服务与任务：

- `generate_storyboard()`：输出规范加 `narration` 字段（复用现有流式解析）。
- 新增 `generate_narration_audio()`：按段 `narration` 调 TTS（edge / elevenlabs 可切换）产出音频文件。
- 新增 `render_video()`：把关键词的 inputProps（标题、关键词、promo code、分镜文字、封面图路径、旁白音频路径）发给 Remotion 渲染服务，取回成品 mp4。
- Celery `@shared_task` 跑流程一全自动流程：元数据 → 封面 → 分镜+旁白文案 → TTS → Remotion 渲染 → 打包；沿用 `task_token` 暂停/停止机制。

接口（沿用 `content-runs` / `content-items`，用 `flow` 区分或新增流程一专用路由）：

- 创建任务支持 txt 上传（解析为关键词列表）。
- 结果列表 / 详情 / 暂停 / 停止 / 重启 / 日志。
- 成品打包 zip 一键下载（成品视频 + 标题/描述/封面），同流程二。

### 29.2 Remotion 渲染服务（新增 Node 容器）

- 新增 `render/`（或 `remotion/`）目录：一个 Node/Remotion 工程，含纯文字动效模板与渲染入口。
- 容器化：新增一个渲染服务容器（含 Node + 无头 Chromium 依赖），加入 `docker-compose.yml`。
- 调用方式（二选一，开发阶段定）：
  - Django 通过 HTTP 调渲染服务（服务内用 `renderMedia()` SSR API）；或
  - Django/Celery 直接 `subprocess` 调 `npx remotion render --props=...`（若渲染服务与 worker 同镜像）。
- inputProps 里的封面图、旁白音频通过共享 media volume 或 URL 提供给 Remotion。
- 交付：模板改法说明 + Remotion Skills 装用说明 + 批量渲染说明（中文）。

### 29.3 全局设置新增项

在「全局设置」（`GlobalSetting` 表）新增：

| Key | 说明 |
| --- | --- |
| `TTS_PROVIDER` | 旁白 TTS 引擎，`edge`（默认，免费无 key）/ `elevenlabs` |
| `TTS_VOICE` | 旁白音色（跟随 provider 与 language） |
| `ELEVENLABS_API_KEY` | elevenlabs API Key（选 elevenlabs 时用，用户提供） |
| `REMOTION_RENDER_URL` | 渲染服务地址（若走 HTTP 调用方式） |

（文本 Agent 复用 `AI_BASE_URL` / `AI_API_KEY` / `AI_MODEL`；封面复用 `GEMINI_IMAGE_API_KEY` / `GEMINI_IMAGE_MODEL`。）

### 29.4 基础设施改动

- **Node + Remotion + 无头 Chromium**：新增渲染服务镜像，装 Chromium 运行依赖。
- **edge-tts**：Python 侧装 `edge-tts` 依赖（免费、无 key）。
- **文件存储**：旁白音频、渲染成品沿用 media 目录 + docker volume 持久化，与流程二共享。
- 改后端代码后需 rebuild 镜像并跑 migration 才生效。

### 29.5 参考资料

| 资源 | 链接 |
| --- | --- |
| Remotion 音频 | `https://www.remotion.dev/docs/audio` |
| Remotion 参数化渲染 | `https://www.remotion.dev/docs/parameterized-rendering` |
| Remotion 服务端渲染（SSR） | `https://www.remotion.dev/docs/ssr` |
| Remotion Agent Skills | `https://www.remotion.dev/docs/ai/skills` |
| Edge TTS（免费、无 key） | `https://github.com/rany2/edge-tts` |

---

## 30. 用户确认记录：2026-08-06（流程一）

以下为本轮沟通中确认的内容生成系统（流程一·全自动化方案）产品与技术决策：

| 问题 | 确认结果 |
| --- | --- |
| 「六成」是否笔误 | 是笔误，应为「流程二」（Notion 原文「逻辑和现阶段的六成差不多」）|
| 本期是否开发流程一 | 是，把流程一写入文档并升级为 3.0，本期开发；流程二已完成 |
| 流程一与流程二关系 | 流程一 = 流程二全自动版，两个 Agent 与 Gemini 封面复用，差异在视频生成方式 |
| 两个 Agent | 复用流程二，不新配一套 |
| 分镜段数 | 沿用可变参数，默认 8+8 |
| 视频生成 | Remotion 自建；用户不熟悉，需开发方搭好并给中文使用说明（改模板 / Skills 装用 / 批量渲染） |
| Remotion 模板 v1 | 纯文字动效模板 |
| 旁白音频 / TTS | moretokens 无音频；用微软免费方案 Edge TTS 作默认，同时接入 elevenlabs，两者一起开发、可切换 |
| 脚本分镜 Agent 扩展 | 新增每段旁白文案 narration，供 TTS 转音频 |
| 输入方式 | 支持输入多个 + 上传文本文件（一行一个搜索词） |
| 界面摆放 | 「内容生成系统」下新增并列子菜单「流程一·全自动任务管理」，流程二不动 |
| 本期链路终点 | 全自动产出成品 + 成品打包下载；上传发布归 AdsPower，本期不做 |
| Node 渲染服务 | Remotion 为 Node 生态、需无头 Chromium，新增独立渲染服务容器，Django/Celery 调用 |
| **promo code 来源** | **创建任务时手填一个，整批关键词共用**（`ContentRun.promo_code`）。频道级独立 promo code 归后续 AdsPower 模块 |
| **成片质量预期** | **本期先跑通全自动流程，画面质量不作要求**（用户明确「现在的肯定不能用」）；精细化视频后续迭代。Remotion 用户不会用，交付后需开发方中文引导 |
| **TTS 容错** | 认可降级思路：Edge TTS 为默认，失败自动降级（elevenlabs / 跳过音频），不使整批任务中断。elevenlabs key 由用户后续在全局设置自行填写 |
| **旁白时长对齐** | 用提示词约束每段 narration 字数（控制在每段时长内），避免音频超出画面段长 |
| **Remotion 容器成本** | 用户接受镜像重、构建慢、服务器资源要求高；确认 Remotion 为当前唯一可行方案 |

---

## 31. 视频模板体系（2026-08-07 新增，已落地）

> 背景：Notion 早期原文提到「可以预设好多个视频模板；通过 api 抓取需要使用的元素、配合模板生成完整的视频」。开发流程一时把这句话落地成了一套**视频模板体系**——它是流程一「一个模板 + 每次换不同数据 = 批量出不同视频」的核心载体。本节为真实实现记录。

### 31.1 一个「视频模板」由两部分组成

1. **数据库里的一条元信息**（`VideoTemplate` 表）：模板名、画面比例、旁白段数/时长、变量声明、默认素材、AI 分析结果、接入状态等。
2. **render 项目里对应的一段 Remotion 组件代码**（TSX），用 `composition_id` 关联。

**关键认知**：模板的「画面」本质是**组件代码**（决定标题放哪、怎么动、背景、素材位）。改画面 = 改 TSX + 重建 render 镜像 + 重新部署，**只能由开发做，运营在网页上改不了**。这是第 34 节多个优化点的根源。

### 31.2 VideoTemplate 字段

| 字段 | 说明 |
| --- | --- |
| name / description | 模板名 / 说明 |
| width / height / fps | 画面尺寸（前端只让运营选 16:9 或 9:16，映射到具体像素，运营不接触 1920/1080 这种数值） |
| shot_count / shot_duration | 旁白段数 / 每段时长。**段数时长从「任务创建」挪到了「模板」**：由参考视频 AI 分析给建议，运营可在模板编辑里微调；创建任务时不再填 |
| status | 接入状态：`pending`（待接入，运营新建默认）/ `ready`（组件已接好可出片）。**只有 ready 的模板才出现在流程一的可选列表**（后端 `serializers` 校验 + 前端过滤双重保证） |
| adjust_notes | 运营的「调整需求」文本框：画面要怎么改（优惠码更大、换配色、挪位置等），作为**开发改组件的需求单** |
| composition_id | 关联 render 里 Root.tsx 注册的 Composition id。**运营侧隐藏**，由开发在后台填 |
| variables_schema | 变量声明（JSON），见 31.4 |
| assets | 默认素材（JSON），见 31.5 |
| analysis | Gemini 对参考视频的分析结果（布局/文字/配色/转场/分镜时间戳等），供开发调模板参考 |
| source_video | 上传的参考视频（供分析） |
| enabled | 是否启用 |

### 31.3 参考视频 AI 分析流程（设计新模板时用）

接口 `POST /api/video-templates/{id}/analyze/`（`VideoTemplateViewSet.analyze`）：上传参考视频 → 存 source_video → 调 `services.py::analyze_reference_video()`（用 Gemini key + 模型，视频以 `data:video/mp4;base64,...` 塞进 `image_url` 走 chat/completions 流式）→ 返回 `{analysis, shot_count, shot_duration, suggested_variables}`。回填：AI 给的段数/时长写回模板；模板未声明变量时用 `suggested_variables` 预填 `variables_schema`。

**注意**：这是「设计新模板」阶段的动作。模板一旦 ready，日常出片**不需要**再传参考视频分析。

### 31.4 变量声明 variables_schema（重点，与「变量文件」直接相关）

结构：`[{"key","label","required","ai_editable"}]`。

- `ai_editable=false`：该值**必须由运营提供、AI 绝不能编造**（如 promo code、注册链接、优惠金额）。这正是用户理解的「变量文件里的元素」。
- `ai_editable=true`：允许 AI 生成。
- 在 AI 提示词里的用法（`services.py::_build_context_block`）：把变量分 locked / editable 两类拼进 metadata、narration 的提示词，locked 变量告诉 AI「你绝对不能自己编造具体值，只能写占位符 `{key}`」。
- 渲染时（`tasks.py::_finalize_flow1_item::_fill`）再把 `{key}` 占位符替换成真实值。

**变量是「按模板声明」的，不是写死在前端的**。前端只是把当前所选模板声明的变量渲染成输入框——换个没声明 promo_code 的模板，就不会出现 promo code 框。

### 31.5 默认素材 assets

接口 `POST /api/video-templates/{id}/upload_asset/`（key + file）。存到 `media/content/templates/{id}/assets/`，写入 `template.assets`：`[{"key","file","name"}]`。渲染时转绝对路径 → render 服务 `rewriteMediaPaths` 改写成 HTTP URL 供无头 Chromium 加载（如 SplitScreenPromo 用 `assets.screen_record` 放右侧录屏）。

### 31.6 两个已落地的 Remotion 模板

| Composition | 说明 |
| --- | --- |
| `PromoVideo`（竖屏 9:16） | 纯文字动效：封面图作背景 + 标题/关键词/promo code 文字动画 + 分段字幕 + 旁白音频 |
| `SplitScreenPromo`（横屏 16:9） | 左右分屏，复刻 1xBet 教程风格：右侧放录屏素材（走 assets.screen_record），左侧文字动效 + promo code |

---

## 32. 前端现状与需求（2026-08-07 新增记录）

> 用户要求：把前端需求先记录下来。以下为**当前真实前端结构**（现状）+ **待办的前端需求**。技术栈：Vue 3 + Vite + Element Plus；不使用 vue-router，用 `App.vue` 的 `activeMenu` + `v-if` 切换页面，localStorage 记住当前菜单，刷新不跳转。整站共用一套 UI。

### 32.1 左侧菜单结构（现状）

| 一级 | 二级 | 对应组件 | 状态 |
| --- | --- | --- | --- |
| 关键词系统 | 任务管理 | App.vue 内联 | ✅ 已上线 |
| 关键词系统 | 关键词 Agent 管理 | App.vue 内联 | ✅ 已上线 |
| 内容生成系统 | 任务管理 | `ContentTasks.vue` | ✅ 流程一/流程二同页切换 |
| 内容生成系统 | 视频模板 | `VideoTemplates.vue` | ✅ 已上线 |
| 内容生成系统 | 内容生成 Agent 管理 | `ContentAgents.vue` | ✅ 已上线 |
| 实用工具 | 获取 Suggest API 长尾词 | App.vue 内联 | ✅ 已上线 |
| 全局设置 | — | App.vue 内联 | ✅ 已上线 |
| 数据抓取系统 / AdsPower 自动化 | — | — | 菜单占位（disabled），后续开发 |

### 32.2 内容生成-任务管理页现状（`ContentTasks.vue`）

- 顶部用 flow1（流程一·全自动）/ flow2（流程二·半自动）切换（**未按第 27.7 节设想新建并列子菜单，而是同页切流程**）。
- 流程一创建任务表单：内容语言、配音引擎（edge/elevenlabs）、视频模板下拉（只列 ready 模板）、批量方式二选一：
  - **按数量**：`video_count`（1~50）+ 按模板变量动态生成的输入框（填一组共享值）。
  - **上传变量文件（CSV）**：每行一组变量 = 一个视频。
- 目标国家已从流程一移除；段数/时长不再让流程一填（由模板决定）。
- 任务列表 + 内容记录两张表；工作日志抽屉（timeline 展示 metadata/thumbnail/narration/render 各步）。

### 32.3 视频模板页现状（`VideoTemplates.vue`）

- 新建模板：只填 名称 / 说明 / 画面比例（16:9 或 9:16）/ 调整需求（默认 pending，`composition_id` 与 status 运营不填，由开发后台维护）。
- 模板列表：比例、旁白段数×时长、变量数、素材数、已分析、接入状态、启用、操作。
- 编辑抽屉：改基础信息 + 增删变量声明（key/label/必填/允许 AI 生成）+ 上传参考视频分析 + 上传默认素材。

### 32.4 待办前端需求

1. **任务管理 UI 重构（第 27 节 Opt 4 遗留，待做）**：改成视频模板那种「列表 + 弹窗」结构——创建任务走弹窗，主界面只显示任务列表，内容记录放进单个任务的子窗口/抽屉。
2. **Flow 1 变量输入逻辑重构（见第 34.4）**：去掉对 promo_code 的特殊对待，统一为「模板声明什么变量、任务就要什么变量」。
3. **.txt 关键词批量导入入口（CG1-002）**。
4. `ContentAgents.vue` 提示文案仍写「两个 Agent」，实际已是三个，需修正文案（见第 33 节）。

---

## 33. 实现与文档假设的差异 / 演进点（2026-08-07 记录）

开发流程一时，实际实现相对第 27~30 节的「设计假设」有以下演进，此处如实记录，作为后续以代码为准的依据：

| # | 文档原假设 | 实际实现 |
| --- | --- | --- |
| 1 | promo code = `ContentRun.promo_code`，创建任务时手填、整批共用 | 已演进为**模板变量体系**：promo_code 只是模板 `variables_schema` 里一个 `ai_editable=false` 的普通变量；每视频变量存 `ContentItem.variables`（按数量共享 / 按 CSV 每行一组）。`ContentRun.promo_code` 字段仍在但降级为兜底 |
| 2 | 流程一视频 = 单一「纯文字动效模板 v1」，段数在任务创建时填 | 已有**两个模板**（竖屏 PromoVideo + 横屏 SplitScreenPromo）；段数/时长**挪到模板**（AI 分析建议 + 运营微调），任务创建不再填 |
| 3 | 两个 Agent（metadata + storyboard），流程一复用 storyboard | 扩为**三个 Agent**：metadata / storyboard / **narration**。流程一走 metadata + narration（只出旁白，画面交模板）；流程二走 metadata + storyboard（出画面分镜供人工拍） |
| 4 | 流程一新建并列子菜单「流程一·全自动任务管理」 | 未新建子菜单，**同一「任务管理」页内 flow1/flow2 切换** |
| 5 | 「多个搜索词」批量 | 流程一实际**只取首个关键词**，批量维度是「数量 / CSV 行数」。多关键词批量、.txt 导入待做 |
| 6 | — | 新增**视频模板体系**（第 31 节），落地 Notion 早期「预设模板 + 换元素」原文 |

---

## 34. 视频模板体系·待讨论优化点（2026-08-07，仅讨论未改代码）

> 用户在测试视频模板流程前提出 5 点，核心都指向**同一个根本矛盾**：Remotion 模板的「画面」是组件代码，改画面需要开发改 TSX + 重建镜像 + 部署，运营在生产环境网页上做不到。以下记录讨论结论与候选方案，**尚未确认、未改代码**。

### 34.1 模板到底谁来、在哪创建（对应用户点 1/3/5）

现实只有三种可行模式：

- **路线 A（现状）**：开发维护模板库，运营只选不建（可提需求 / 传参考视频，真正接组件由开发做完置 ready）。稳，但每个新模板都要开发介入。
- **路线 B：把 Agent（如 Claude Code）接进生产自动生成 Remotion 组件**。技术可行（render 已装 Remotion 官方 AI Skills），但硬伤：AI 生成的是**代码**，要写进 render 工程重建/热加载，出 bug 会拖垮所有任务渲染；生产跑 LLM 现写代码有安全/稳定风险。现实折中：Agent 生成 → 暂存 composition → 自动试渲一条 → 人工确认 → 才升 ready（**半自动、有人工闸门**）。
- **路线 C（推荐，真正解决生产自助）：配置驱动的「万能模板」**。只写一个高度可配置的 Remotion 组件，布局槽位/配色/字体/动画预设/文字与素材位全由一份 JSON 配置决定。「新建模板」= 网页上填一份配置（或可视化表单），**不写代码、不重新部署，运营自助建**。代价是前期要把万能组件 + 配置 schema 做扎实；能力受 schema 边界限制，但对「文字动效 + 背景 + 素材位」类推广片覆盖面够。

**倾向建议**：短期走 A 保出片；投入做 C 作为二期正式方案；B 作为 C 之上的加速器（用 Agent 帮运营填配置 / 按参考视频自动生成配置），而非让 Agent 直接写代码。**待用户拍板。**

### 34.2 已建模板只传素材、一个 zip 全传（对应用户点 2）

- 已 ready 模板日常出片**不该再要求传参考视频分析**（分析只在设计新模板阶段用）。
- 素材分两类：**模板级素材**（logo/背景/BGM/字体，整套共用）适合 zip 传；**单视频级素材**（每条不同的录屏等）属于变量，走变量文件不走 zip。
- zip 自动化方案：约定 zip 内带一个 `manifest.json` 声明「文件 → asset key」映射（比纯文件名约定更灵活）。上传 → 解压 → 按 manifest 校验必需素材是否齐 → 落共享 media 卷。**待确认。**

### 34.3 理想的完整模板创建流程（对应用户点 3）

用户理想：给一个视频 → 系统分析 → 拆解 → 在后台与用户沟通「哪些不变 / 哪些变 / 哪些用户提供」→ 沟通后创建模板，**全程在生产后台完成，不在开发本地**。这本质要求路线 C（配置驱动）或路线 B（Agent 生成），A 做不到「生产后台自助」。

### 34.4 Flow 1 变量逻辑需澄清并重构（对应用户点 4）

- **澄清认知一致**：变量 = Remotion 模板里需要变、但**不能让 AI 编造**的元素（promo code、金额、链接等），由运营在建任务时提供。用户对「变量文件」的理解与系统设计一致，此前只是没讲清。
- **误解纠正**：promo code 输入框不是「变量写死到前端」，而是当前模板恰好声明了 promo_code 变量。换模板就不会有这个框。
- **待重构点（未改代码，待确认）**：
  1. 去掉 `ContentRun.promo_code` 专门字段，promo_code 只当 `variables_schema` 里普通变量，消除「被特殊对待」的观感。
  2. 「按数量」模式：模板声明了运营变量就填一组共享值；无声明则一个框都不出现；若变量本该每条不同则提示改用变量文件。
  3. 变量文件（CSV/xlsx）：表头 = 模板变量 key，每行 = 一条视频的一组值；做好模板与文件的列校验。
  - 目标：变量只有一个来源——**模板声明什么，任务就要什么**，无特例。

### 34.5 结论

用户遇到的不是 bug，是「模板画面只能靠代码」的天花板。要让运营在生产环境自助建模板，正道是**路线 C（配置驱动的万能模板）**，Agent（路线 B）用于加速填配置而非直接写代码。二期正式改造方案（万能模板配置 schema + 变量逻辑重构 + zip 素材规范）**待用户确认方向后再出**。
