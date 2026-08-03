# YouTube 自动化系统需求文档 1.0：关键词系统

版本：1.0  
整理日期：2026-07-31  
最近同步：2026-07-31  
实现进度更新：2026-08-03  
文档状态：草稿版  
当前范围：关键词系统为主；其他模块只记录 Notion 已写原文或占位  
同步原则：只整理 Notion 已写内容；未写需求保持空白或待补充；不补充推测需求。  
实现进度：关键词系统第一期核心功能（Suggest 拓展 → SerpApi 验证 → YouTube V3 补数 → 规则打分 → 后台列表/CSV）已全部完成并上线；AI 打分 Agent 仅保留配置未接入。详见第 12 节功能清单与 `CHANGELOG.md`。

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
| `youtube自动化系统` | 总体架构页 | 系统架构、系统难点、页面架构、技术架构、三方 AI API 接入、AI 接入逻辑说明子页面 |
| `1 关键词系统` | 关键词模块页 | 找词、关键词拓展、三方 API 验证、SerpApi 参考页面、打分逻辑、关键词打分 Agent |
| `YouTube系统` | 项目任务数据库 | 当前项目进度入口 |

---

## 3. 当前项目进度

| 任务名称 | 状态 | 优先级 | 截止日期 | 更新时间 | 说明 |
| --- | --- | --- | --- | --- | --- |
| youtube自动化系统 | 未开始 | 高 | 2026-07-31 | 2026-07-31T06:30:01.509Z | 总体架构页，已补充页面架构、技术架构、三方 AI API 接入 |
| 1 关键词系统 | 未开始 | 中 | 2026-07-31 | 2026-07-31T08:27:45.958Z | 已补充 SerpApi 参考页面、5 分制打分规则、关键词打分 Agent 目的 |
| 2 数据抓取系统 | 未开始 | 低 | 2026-07-31 | 2026-07-31T02:49:36.324Z | 本版本不展开 |

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

已写内容：

```text
内容生成：通过预设好的 agent，将关键词和清洗好的数据生成一份音频脚本。
音频生成：通过预设好的音频脚本，生成音频文件。
视频生成：不完全是 ai 生成视频，可以预设好多个视频模板；通过 api 抓取需要使用的元素、配合模板生成完整的视频。
元数据生成：生成视频标题、描述、封面。
```

本版本不展开需求。

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

## 9. 1.0 范围

### 9.1 本版本展开

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

### 9.2 本版本不展开

- 数据抓取系统
- 内容生成系统
- 音频生成
- 视频生成
- 元数据生成
- AdsPower 自动化系统
- AI 管理具体功能
- 任务自动化系统具体功能
- 全局设置具体功能
- 管理后台具体 UI 细节

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
| KW-015 | 将打分结果交给打分 Agent 再次分析 | Notion 已写 | ⏳ 待开发（本期仅保留 AI 配置，不发起调用） |
| KW-016 | 打分 Agent 判断搜索意图纯度 | Notion 已写 | ⏳ 待开发 |
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
