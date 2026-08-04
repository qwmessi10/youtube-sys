# YouTube 真空长尾词系统 V2 技术方案

版本：2.0（设计稿）
整理日期：2026-08-03
来源：基于 ChatGPT 对话《YouTube关键词分析工具》整理，并与现有 V1 代码对齐
文档状态：设计稿，尚未实现
配套文档：`youtube_system_requirements_v1.0.md`（V1 已实现需求）、`CHANGELOG.md`

---

## 0. 文档说明

### 0.1 这份文档解决什么

你现在有一套 V1 打分模型，它已经上线：`YouTube Suggest 拓展 → SerpApi 验证 → YouTube V3 补数 → 规则打分（4 维）→ 后台列表/CSV`。这套模型能回答的问题是：

> **「这个关键词现在竞争激烈不激烈？」**

但它回答不了另一个更值钱的问题：

> **「这个关键词最近是不是突然开始有人搜索？」**

这份文档就是要把系统从**「竞争难度分析器（Keyword Analyzer）」**升级成**「机会发现引擎（Keyword Discovery Engine）」**，核心是引入**时间序列**和**需求/供给双向模型**。

### 0.2 本文档回答的 8 个问题

| # | 问题 | 对应章节 |
| --- | --- | --- |
| 1 | 每个字段为什么存在 | 第 4 章 |
| 2 | 每个分数为什么这么计算 | 第 9 章 |
| 3 | AI 在哪个环节参与 | 第 10 章 |
| 4 | 如何做时间序列分析 | 第 5 章 |
| 5 | 如何发现 Rising Keyword | 第 6 章 |
| 6 | 如何计算 View Velocity | 第 7 章 |
| 7 | 如何计算 Demand/Supply Gap | 第 8 章 |
| 8 | 如何发现真正的 Vacuum Keyword | 第 8.4 + 第 9 章 |

### 0.3 与 V1 的关系（重要）

对话里反复强调一句话：**不要推翻现有模型，而是在它前面加一层「实时需求发现层」。**

- V1 现有系统已经覆盖了 4 层架构里的**后 3/4**（拓展、供给分析、竞争评分）。
- 真正要新增的是**第 1 层：需求发现层（Demand Discovery）**。
- 现有的 4 维规则打分不是废弃，而是被降级成整个机会评分里的一个子项（Competition Score，占最终分 35%）。

### 0.4 一个贯穿全文的核心区别

| 维度 | V1（现在） | V2（目标） |
| --- | --- | --- |
| 系统起点 | 从已有关键词出发找长尾 | 先发现「需求正在变化」再反向生成关键词 |
| 时间观 | 一次性快照分析 | 持续监控时间序列 |
| 判断依据 | 竞争难度（静态） | 需求增速 × 供给缺口（动态） |
| 数据维度 | 播放/订阅/标题/时间 4 项 | Demand / Discovery / Supply / Competition / Opportunity 5 组 |
| 产品定位 | Keyword Analyzer | Keyword Discovery Engine |

---

## 1. 核心问题：缺一个「Trend Signal」

V1 缺的不是「更复杂的打分公式」，而是**需求变化信号（Trend Signal）**。举对话里的例子：

```text
关键词 A                          关键词 B
搜索量：1000                       搜索量：300
过去 30 天：1000→1000→1000         过去 30 天：10→20→50→100→300
竞争：低                           竞争：低
```

V1 旧模型很可能给出：`A = 80 分，B = 55 分`（因为 A 绝对搜索量更高、竞争也低）。

但实际上 **B 才是真正要抓的「真空词」**——它的需求正在爆发式增长，而供给还没跟上。V1 完全看不到 B 的增长曲线，因为它没有时间维度。

**结论：V2 的第一优先级不是接 AI，而是给系统装上「时间的眼睛」。**

---

## 2. V2 四层架构

```text
                 ┌────────────────────┐
                 │  Demand Discovery   │  ← 新增（V2 核心）
                 │   需求发现层         │
                 └─────────┬──────────┘
                           ↓
             ┌──────────────────────────┐
             │ Keyword Expansion Engine │  ← V1 已有（Suggest）
             │    长尾扩展引擎           │
             └────────────┬─────────────┘
                          ↓
             ┌──────────────────────────┐
             │ YouTube Supply Analysis  │  ← V1 已有（SerpApi+V3），需补字段
             │    内容供给分析           │
             └────────────┬─────────────┘
                          ↓
             ┌──────────────────────────┐
             │ Opportunity Scoring      │  ← V1 已有雏形，需重构公式
             │    真空机会评分           │
             └──────────────────────────┘
```

**四层里，V1 已经覆盖了后三层，真正要新增的只有第一层。**

---

## 3. 数据流：从「输入词」到「发现词」

### 3.1 V1 现在的数据流

```text
用户输入 Seed → YouTube Suggest → 长尾词 → SerpApi SERP → 竞争分析 → 打分
```

这是传统 Keyword Tool 的做法：**被动等用户输入**。

### 3.2 V2 目标数据流

```text
系统每天自动扫描
        ↓
Google Trends Rising Queries  +  vidIQ Rising Keywords（趋势源）
        ↓
发现 Rising Keyword（正在增长的词）
        ↓
把 Rising Keyword 当成新的 Seed，扔回 YouTube Suggest
        ↓
AI / 规则做 Query Expansion（意图扩展）
        ↓
Keyword Pool（关键词池）
        ↓
YouTube SERP（SerpApi 拿竞品数据）
        ↓
Supply / Competition 分析
        ↓
Vacuum Detection（真空检测）
        ↓
🔥 TOP 50 机会词
```

关键转变：**Seed 不再只来自用户输入，而是系统自动从趋势源里发现的 Rising Keyword。** 这就是 `Trend × Vacuum`——既在涨、又没人做的词。

### 3.3 印度市场的具体例子（对话原例）

Seed = `AI video generator`，Google Trends 可能发现这些相关上升词：

```text
AI video generator for youtube shorts
AI video generator free
AI video generator from text
AI video generator mobile
AI video generator hindi   ← 假设这个突然 +350%
```

**注意：不要因为它 +350% 就直接判定它是好词。** 正确做法是把这个 Rising Keyword 重新扔回 YouTube pipeline 再扩展一轮：

```text
ai video generator hindi
   ↓ （再次 Suggest + AI 扩展）
ai video generator hindi free
ai video generator hindi for mobile
ai video generator hindi for beginners
ai video generator hindi shorts
   ↓
SERP → 竞争分析 → 真空检测
```

只有走完这一整轮，才真正出现 `Trend（在涨） × Vacuum（没人做）` 的交集。

---

## 4. 数据库字段设计：每个字段为什么存在

### 4.1 设计原则：数据采集与算法解耦

对话里给了一个非常重要的设计原则：

> **「这样你未来就可以不断换算法，而不需要重新采集数据。」**

意思是——**先把原始维度都存下来（demand、supply 的原始时间序列），分数（demand_score、vacuum_score）作为"派生字段"随时可以重算。** 不要只存一个最终分数，因为一旦你想调公式，历史数据就废了。

所以字段分成两类：
- **原始采集字段**（raw）：直接从 API 拿到、随时间累积的事实数据，永不因改公式而失效。
- **派生计算字段**（derived）：由原始字段算出来的分数，改公式后可全量重算。

### 4.2 V1 现在存了什么（对照）

现有 [models.py](backend/keywords/models.py) 的 `KeywordResult` 只存了这些：

```text
keyword          长尾词
top5_video_data  前 5 视频的 JSON（标题/播放/订阅/点赞/评论/发布时间）
score_breakdown  4 维打分明细
rule_score       规则总分
final_decision   最终判断
```

问题：**全是"某一时刻的快照"，没有任何时间序列，也没有 demand 侧数据。** 这就是为什么 V1 看不到"需求在涨"。

### 4.3 V2 目标字段树（对话原设计）

```text
Keyword
│
├── Demand（需求侧 —— V2 全新增）
│   ├── trend_now        当前趋势指数（Google Trends 相对值）
│   ├── trend_7d         近 7 天趋势序列
│   ├── trend_30d        近 30 天趋势序列
│   ├── velocity_24h     24 小时需求变化速度
│   ├── velocity_7d      7 天需求变化速度
│   └── acceleration     加速度（velocity 的变化）
│
├── Discovery（来源侧 —— V2 全新增）
│   ├── youtube_suggest  是否来自 YouTube Suggest
│   ├── google_rising    是否来自 Google Trends Rising
│   ├── related_query    是否来自相关查询
│   └── external_signal  其他外部信号
│
├── Supply（供给侧 —— V1 部分有，需补时间维度）
│   ├── result_count     该词 YouTube 结果总数
│   ├── top10_views      Top10 视频播放量
│   ├── median_views     播放量中位数
│   ├── median_age       视频年龄中位数（发布距今）
│   ├── new_videos_7d    近 7 天新增视频数
│   └── new_videos_30d   近 30 天新增视频数
│
├── Competition（竞争侧 —— V1 已有，对应现有 4 维）
│   ├── title_match              标题匹配度
│   ├── exact_match_count        完全匹配数
│   ├── avg_channel_subscribers  平均频道订阅数
│   ├── avg_views_subscriber_ratio  播放/订阅比
│   └── top10_strength           Top10 综合强度
│
└── Opportunity（机会侧 —— 派生分数）
    ├── demand_score       需求分
    ├── supply_gap         供给缺口
    ├── competition_score  竞争分（≈ V1 现有 rule_score）
    └── vacuum_score       真空分（最终核心指标）
```

### 4.4 逐字段解释：为什么存在

#### Demand 组（需求侧，全新增）

| 字段 | 为什么存在 | 数据来源 |
| --- | --- | --- |
| `trend_now` | 当前需求水位。单独看意义不大，必须配合时间序列 | Google Trends |
| `trend_7d` / `trend_30d` | **存序列而不是存单值**，这样才能算增速；对话原话："不要只保存 Google Trends=80 这个数字意义不大，你应该保存时间序列" | Google Trends `now 7-d` / `today 1-m` |
| `velocity_24h` / `velocity_7d` | 需求变化速度，是"这个词在涨吗"的直接答案（算法见第 5 章） | 由 trend 序列计算 |
| `acceleration` | 加速度——"涨得越来越快还是在放缓"，比 velocity 更早捕捉爆发 | 由 velocity 计算 |

#### Discovery 组（来源侧，全新增）

| 字段 | 为什么存在 |
| --- | --- |
| `youtube_suggest` | 记录该词是否来自 Suggest。对话强调："Rising Keyword 本身就是一个独立的数据维度，不要把所有东西混成一个分数" |
| `google_rising` | 记录是否来自 Google Trends 上升查询——这是"自动发现"的关键来源 |
| `related_query` | 相关查询来源 |
| `external_signal` | 预留给未来其他趋势源（如新闻、赛事日历） |

**为什么来源要单独存字段**：因为一个词从"Rising 来源"发现，和从"用户手输"发现，价值完全不同。混成一个分数就丢失了这个信息。

#### Supply 组（供给侧，V1 需补齐）

| 字段 | 为什么存在 | V1 现状 |
| --- | --- | --- |
| `result_count` | 该词在 YouTube 一共有多少视频，供给总量 | ❌ 未存 |
| `top10_views` / `median_views` | 用中位数而非平均，避免个别爆款拉偏 | 🚧 V1 只有前 5 |
| `median_age` | 视频年龄中位数。**前排都是旧视频=内容空位**（V1 的"发布超 24h"维度是这个的粗糙版） | 🚧 V1 只判断 24h |
| `new_videos_7d` / `new_videos_30d` | **近期新增视频数——供给增长速度**，这是 Supply Gap 的核心输入（第 8 章） | ❌ 未存 |

#### Competition 组（竞争侧，对应 V1 现有 4 维）

| 字段 | 为什么存在 | 对应 V1 |
| --- | --- | --- |
| `title_match` / `exact_match_count` | 前排标题是否精确包含该词 | ✅ `title_mismatch` |
| `avg_channel_subscribers` | 竞对频道体量 | ✅ `low_subscriber` |
| `avg_views_subscriber_ratio` | 播放/订阅比——见第 7、12 章的 Breakout 信号 | ❌ 未存 |
| `top10_strength` | Top10 综合强度 | 🚧 分散在 V1 各维度 |

#### Opportunity 组（派生分数）

| 字段 | 为什么存在 |
| --- | --- |
| `demand_score` | 需求侧综合分（第 9.1） |
| `supply_gap` | 供给缺口（第 8 章）——V2 最核心的新指标 |
| `competition_score` | ≈ V1 现有 `rule_score`，降级为子项 |
| `vacuum_score` | 真空分，最终排序依据（第 9.3） |

### 4.5 SerpApi 视频字段也要扩

V1 只从每条视频拿了 `views / subscribers / title / published_date`。对话建议扩成：

```text
Video
├── views
├── likes
├── comments
├── channel_subscribers
├── published_at
├── title
├── description   ← V1 未存，AI 意图判断要用
├── duration      ← V1 未存，区分长视频/Shorts 要用
└── channel
```

> 注：`description` 和 `duration` SerpApi 的 YouTube 结果不一定直接给全，可能仍需 YouTube Data API V3 补（V1 已经在用 V3 补订阅数，加这两个字段成本很低）。

---

## 5. 如何做时间序列分析

### 5.1 数据源：SerpApi 的 Google Trends API

对话推荐的第一个要接入的工具就是 **SerpApi Google Trends API**。它能返回：

- Interest over time（随时间的兴趣度）
- Related queries（相关查询）
- Rising queries（上升查询）
- Related topics（相关主题）
- 地区维度
- 时间序列

它支持像 `now 7-d` 这样的时间窗口参数，直接返回时间序列，非常适合当作现有架构的"趋势数据层"。

### 5.2 关键：存序列，不要存单值

这是时间序列分析的地基。对话原话：

> 不要只保存 `Google Trends = 80`，这个数字其实意义不大。你应该保存**时间序列**。

举例，一个词近 7 天的趋势指数：

```text
Day 1    12
Day 2    15
Day 3    14
Day 4    21
Day 5    30
Day 6    48
Day 7    76
```

只有存下这条曲线，才能算出它"在加速上涨"。如果只存最后一个值 76，你根本不知道它是从 12 涨上来的，还是一直稳定在 76。

### 5.3 采集频率：持续监控而非一次性

对话强调的另一个升级点（第 20 节、第 2 阶段）：

> 你现在是**一次性分析关键词**，下一步应该变成**持续监控关键词**。

具体做法：**每天 / 每 6 小时保存一次**趋势快照，让每个关键词都积累出自己的时间序列。示例（对话原例）：

```text
今天：Trend=42  Top10 median=8,200  New videos 7D=4  Score=72
明天：Trend=51  Top10 median=9,000  New videos 7D=5  Score=78
后天：Trend=68  Top10 median=10,000 New videos 7D=6  Score=91 🔥
```

这时系统告诉你的不是"这个词不错"，而是**"这个词正在进入窗口期"**——这才是真正的实时真空词。

### 5.4 时间序列表结构建议

为了支撑上面的监控，需要一张**独立的时间序列快照表**（区别于关键词主表）：

```text
KeywordSnapshot（每次采集写一行）
├── keyword_id      关联关键词
├── captured_at     采集时间戳
├── trend_index     当时的 Google Trends 指数
├── result_count    当时 YouTube 结果总数
├── new_videos_7d   当时近 7 天新增视频
├── top10_median_views
└── ...
```

主表存"最新值 + 派生分数"，快照表存"历史每一次"。velocity / acceleration 都从快照表算。

> 说明：对话没有给出这张表的具体字段名，5.4 是为落地补的结构建议；字段以对话第 7 节的字段树为准。

---

## 6. 如何发现 Rising Keyword

「Rising Keyword」= 搜索需求正在明显增长的词。对话给了**两个独立来源**，建议都接，互相校准。

### 6.1 来源一：Google Trends Rising Queries（SerpApi）

SerpApi Google Trends 的 `RELATED_QUERIES` 返回结果里，`rising` 部分会带增长值：

```text
+250%          某个词最近涨了 250%
Breakout       "爆发"——增长超过 5000%，Google 不再给具体数字
```

**发现流程**：

```text
Seed（如 "AI video generator"）
   ↓ 请求 SerpApi Google Trends RELATED_QUERIES
Rising Queries 列表（带 +xxx% / Breakout 标记）
   ↓ 筛出增长显著的词
候选 Rising Keyword
```

### 6.2 来源二：vidIQ Rising Keywords

对话建议参考 **vidIQ 的 Rising Keywords** 功能，它可以按 **Today / This week / This month** 筛选，算法专门识别 **YouTube 搜索量**（注意：是 YouTube，不是 Google）正在明显增加的词。

用途定位：**辅助校准**。因为 Google Trends 是 Google 搜索兴趣，vidIQ 是 YouTube 搜索热度，两者结合更准。

### 6.3 为什么要两个来源分开记录

对话原则：

> **Rising Keyword 本身就是一个独立的数据维度。** 所以模型应该新增 `trend_source`，而不是把所有东西混成一个分数。

`trend_source` 可能的取值：

```text
Google Trends
vidIQ Rising
YouTube Suggest
YouTube search result changes
```

同一个词从不同来源被发现，说明信号强度不同（多个来源都指向它 = 更可信）。

### 6.4 发现之后做什么（关键：不要直接用）

**发现 Rising Keyword 只是起点，不是终点。** 对话明确警告：

> 不要直接判定它是好关键词。而应该把它扔回你现有的 YouTube pipeline。

正确流程见 [3.2](#32-v2-目标数据流) 和 [3.3](#33-印度市场的具体例子对话原例)：Rising Keyword → 当作新 Seed → YouTube Suggest → AI 扩展 → SERP → 竞争分析 → 真空检测。

---

## 7. 如何计算 View Velocity

### 7.1 为什么需要 View Velocity

对话第 8 章指出 V1 的"播放量越低越容易做"是错的。看两个词：

```text
Keyword A（Top10）        Keyword B（Top10）
2M / 1M / 800K / 500K...   50K / 30K / 20K / 10K / 8K...
```

A 明显竞争强。但**不能简单判断 B 是低竞争**——B 播放低可能只是因为这个词本身搜索需求就低。所以关键不是绝对播放量，而是：

> **Views / Demand —— 搜索需求相对于现有内容表现怎么样？**

而在单个视频层面，衡量"内容表现"最好的指标是 **View Velocity（播放速度）**，而不是总播放量。

### 7.2 View Velocity 公式

```text
View Velocity = views / days_since_publish
             = 播放量 / 视频发布至今的天数
```

对话原例：

```text
Video A：100,000 views，100 天前发布  →  1,000 views/day
Video B： 20,000 views，  2 天前发布  → 10,000 views/day
```

**结论：Video B 实际更强。** 虽然总播放量 A 是 B 的 5 倍，但 B 的日播放速度是 A 的 10 倍——它正在快速起量，说明这个词现在有活跃的观看需求。V1 只看 `view_count` 会把 B 误判成"播放低、好做"，完全看反了。

### 7.3 计算所需字段

```text
views              已有（V1 有 view_count）
published_at       已有（V1 有 published_at）
days_since_publish = now - published_at  ← 需新增计算
```

好消息：**V1 已经存了 `view_count` 和 `published_at`**（见 [services.py](backend/keywords/services.py) 的 `enrich_videos`），所以 View Velocity 基本是"免费"就能加上的——只需加一个除法。

### 7.4 Breakout Ratio（小频道破圈信号，配套指标）

对话第 12 章强调这个指标"以后一定要加"。它和 View Velocity 是一对，都是看"相对表现"：

```text
Breakout Ratio = Views / Subscribers
```

对话原例：

```text
词 X 的 Top 视频都是：10M views/2M subs、4M/800K、2M/500K
→ 大频道靠粉丝基本盘，小频道进不去，即使搜索量大也不适合你

另一个词的视频：12K views/1K subs、8K/700 subs、20K/2K subs
→ 12K/1K = 12x，小频道也能从这个词拿到流量
→ 这是非常强的机会信号（因为你的 AdsPower 矩阵账号都是小频道/新号）
```

这对你的博彩矩阵尤其重要：你的号都是新号小号，只有"小频道能破圈"的词才做得动。所需字段 `views`、`subscriber_count` V1 都已存。

---

## 8. 如何计算 Demand/Supply Gap，如何发现真正的 Vacuum Keyword

这是整个 V2 的**灵魂章节**。对话原话：这可能会成为系统里**最核心的指标之一**。

### 8.1 核心直觉：需求在涨，但没人做

真正的"真空词"不是"竞争低的词"，而是**需求在快速增长、但内容供给还没跟上的词**。用一个对话的例子：

```text
过去 30 天：关键词需求 ↑ 250%
但是：      过去 30 天只有 3 条新视频
→ 很强的真空信号（大家想看，但没人做）

反过来：
过去 30 天：需求 ↑ 250%
但是：      过去 30 天出现 800 条新视频
→ 这个热点已经被创作者发现了，不是真空
```

### 8.2 Freshness Gap（供给新鲜度缺口）

最朴素的表达：

```text
Vacuum = Demand Growth − Content Growth
       = 需求增长      − 内容增长
```

需求涨得比内容快 → 缺口为正 → 有机会。内容涨得比需求快 → 缺口为负 → 已饱和。

### 8.3 Demand / Supply Ratio（供需比，更精确）

用比值比用差值更能体现"倍数级"的机会。对话原例：

```text
Keyword A：
  Demand Growth（Google Trends）= +300%
  Supply Growth（YouTube 新视频）= +20%
  Gap = 300 / 20 = 15x   ← 非常好，需求增速是供给的 15 倍

Keyword B：
  Demand Growth = +300%
  Supply Growth = +450%
  → ❌ 不是真空。内容生产速度已经超过需求增长
```

**公式：**

```text
Supply Gap Ratio = Demand Growth Rate / Supply Growth Rate
```

- Ratio ≫ 1：需求远快于供给 → **真空词**
- Ratio ≈ 1：需求供给同步 → 正常竞争
- Ratio < 1：供给反超需求 → 已饱和，放弃

其中：
- **Demand Growth** 来自第 5 章的 Trend Velocity（Google Trends 时间序列）
- **Supply Growth** 来自 Supply 组的 `new_videos_7d` / `new_videos_30d`（第 4.4）

### 8.4 什么是"真正的" Vacuum Keyword

对话第 13 章给出真空词的三条件同时成立：

```text
        需求 ↑↑↑   （Demand 高速增长）
        供给  ↑    （Supply 增长缓慢）
        竞争  ↓    （Competition 弱）
              ↓
        Vacuum Score（真空分）
```

三者的数据来源：

| 维度 | 判断依据 | 来自章节 |
| --- | --- | --- |
| 需求 ↑↑↑ | Trend Velocity + Acceleration | 第 5 章 |
| 供给 ↑（慢） | new_videos_7d/30d、median_age | 第 4.4 |
| 竞争 ↓ | title_match、频道体量、Breakout Ratio | 第 7.4 + V1 4 维 |

**注意**：只有需求增长（第 6 章的 Rising Keyword）**不等于**真空词。Rising 只满足"需求↑"一个条件；必须再叠加"供给慢 + 竞争弱"，才是真正能吃到流量的真空词。这就是为什么第 6.4 强调 Rising Keyword 要扔回 pipeline 走完供给和竞争分析。

### 8.5 一个重要的坑：Google Trends ≠ YouTube 搜索量

对话第 19 章专门警告，落地时**必须避开**：

> **不要把 Google Trends = YouTube Search Volume。**

原因：
1. Google Trends 是 **Google 搜索兴趣**，不是 YouTube 精确搜索量。
2. Google Trends 的数值是**相对指数**（0-100），不是绝对搜索量。
3. 低搜索量的词在 Google Trends 里还可能出现**数据缺失 / 噪声**。

**正确用法**：Google Trends 只能作为 **Demand Signal（需求信号）**，不能当搜索量用。真正可靠的判断要**四个信号融合**：

```text
Google Trends（需求趋势）
      +
YouTube Suggest（YouTube 真实下拉）
      +
YouTube SERP（竞品供给实况）
      +
你自己的历史数据（时间序列积累）
```

---

## 9. 评分模型：每个分数为什么这么计算

对话第 14 章给出 V2 第一版评分公式。**注意：这些权重是对话给的"第一版拍脑袋值"，明确说了"先别追求复杂，不要一开始就上机器学习"，落地时应做成可配置。**

### 9.1 Demand Score（需求分）

```text
Demand Score =
  30% × Trend Velocity      需求变化速度（第 5 章）
+ 25% × Trend Acceleration  加速度，越早爆发权重越高
+ 20% × Rising Signal       是否来自 Rising 来源（第 6 章）
+ 15% × Suggest Signal      YouTube Suggest 信号
+ 10% × Baseline Demand     基础需求水位
```

**为什么这么配**：Velocity + Acceleration 合计 55%，说明**"变化"比"绝对水位"重要得多**——这正是对整个 V1 缺陷的纠正。Baseline（绝对需求）只占 10%。

### 9.2 Supply Score（供给分）

```text
Supply Score =
  30% × New Videos 7D          近 7 天新增视频（供给增速，最重要）
+ 25% × New Videos 30D         近 30 天新增视频
+ 20% × Top10 Median Views     Top10 播放中位数
+ 15% × Exact Title Match      精确标题匹配
+ 10% × Top10 Channel Strength Top10 频道强度
```

**为什么这么配**：New Videos 7D+30D 合计 55%，因为 Supply Gap 的核心是"供给增长速度"（第 8.3），而不是供给存量。

> 说明：这里的 Supply Score 数值越高代表供给越充足（越不利）。进入 Vacuum 公式时它以"缺口"形式参与——供给越低，缺口越大。落地时注意方向，避免符号写反。

### 9.3 Vacuum Score（真空分，核心）

```text
Vacuum Score =
  Demand Score × 0.55
+ Supply Gap   × 0.45
```

需求增长和供给缺口几乎平分权重（55/45），对应第 8.4 的"需求↑↑↑ + 供给↑（慢）"两个条件。

### 9.4 Opportunity Score（最终排序分）

```text
Opportunity Score =
  Vacuum Score      × 0.65
+ Competition Score × 0.35
```

**这里就是 V1 现有模型的位置**：`Competition Score` ≈ V1 现在的 `rule_score`（4 维打分），在 V2 里被降级为最终分的 35% 权重的一个子项。**V1 没白做，它变成了竞争侧的评估器。**

### 9.5 完整评分链路

```text
              Keyword
                 │
   ┌─────────────┼─────────────┐
   ↓             ↓             ↓
 Demand        Supply     Competition
   │             │             │
   ↓             ↓             ↓
Trend         Freshness      Top10
Velocity        Gap         Strength
   │             │             │
   └─────────────┼─────────────┘
                 ↓
           Vacuum Score
                 ↓
         Opportunity Score
                 ↓
          🔥 TOP 50 Keywords
```

### 9.6 评分设计的三条铁律（对话反复强调）

1. **先别追求复杂**——这只是第一版公式，不要一开始就搞机器学习。
2. **权重和阈值必须可配置**——不要写死在代码里（和 V1 文档第 21 章"规则引擎+可配置"一致）。
3. **原始数据和分数分离存储**——改公式时能全量重算历史数据（第 4.1）。

---

## 10. AI 在哪个环节参与

### 10.1 一句话结论：AI 只做"扩展"和"理解"，不做"打分"

对话第 13、16 章立场非常明确，甚至用了"先忍住"：

> 不要现在就把所有数据扔给 GPT 说"帮我判断这个关键词好不好"。因为你现在缺的是**数据维度**，而不是**判断能力**。

### 10.2 AI 该做什么

| AI 负责 ✅ | AI 不负责 ❌ |
| --- | --- |
| "这个词可能有哪些真实搜索意图？" | "这个关键词 87 分。" |
| Seed / Rising Keyword 的意图扩展 | 基础数据计算（播放、订阅、时间） |
| 长尾词生成 | 关键词最终评分排序 |
| 主题聚类（Topic Clustering） | 替代规则引擎 |
| 搜索意图分类 | |

具体例子（对话原例）：系统发现 `ai video generator for shorts`，AI 负责生成：

```text
ai video generator for shorts free
ai video generator for youtube shorts
ai video generator for shorts mobile
ai video generator for shorts hindi
ai video generator for shorts without watermark
ai video generator for shorts from text
```

然后交给 API（SerpApi / YouTube）去验证真实供给。**AI 出"可能性"，数据出"事实"。**

### 10.3 为什么不让 AI 打分（对话理由 + V1 文档理由）

- AI 输出不稳定，不利于批量排序（V1 文档 21.1 已确认这一点）。
- 播放量、粉丝、时间、标题匹配是确定数据，用规则算又快又可解释。
- 规则写进提示词后，调分、复盘、解释淘汰原因都会变难。

### 10.4 AI 参与的位置（在数据流里）

```text
Rising Keyword / Seed
        ↓
   YouTube Suggest
        ↓
【AI Query Expansion】← AI 唯一的主战场：意图扩展、长尾生成
        ↓
   Keyword Pool
        ↓
   YouTube SERP（数据）→ 规则评分（不碰 AI）
```

### 10.5 AI 的接入时机（Phase 5，靠后）

按对话的落地顺序，AI 扩展排在**第 5 阶段**，在时间序列、Supply Velocity、Vacuum Score 都做完之后。这与 V1 现状一致——V1 目前 AI 打分 Agent「仅保留配置未接入」，方向吻合，不用急着接。

### 10.6 机器学习（Phase 6，最后）

对话把 ML 放在最后。只有当你积累了这批数据后才值得做：

```text
关键词 → Score → 实际发布 → 7/14/30 天真实表现
```

有了这批"预测分 vs 实际表现"的历史，才能训练：

```text
Keyword Features → ML Model → Ranking 概率 / Breakout 概率
```

对话原话：这会比现在让 GPT 打分**强得多**。这也呼应了你的转化路径——铺量博彩长尾词、吃自然搜索流量、导 Telegram，只有真实发布回收数据才能训练出真正的预测模型。

---

## 11. 工具选型

对话第 18 章给的实际组合：

| 功能 | 第一选择 | 用途 | V1 现状 |
| --- | --- | --- | --- |
| YouTube Suggest | 你现有方案 | 长尾扩展 | ✅ 已用 |
| YouTube SERP | SerpApi | 竞品数据 | ✅ 已用 |
| Google Trends | **SerpApi Google Trends API** | 趋势 / 上升速度 | ❌ 待接 |
| Rising Queries | **SerpApi Related Queries** | 自动发现增长词 | ❌ 待接 |
| YouTube Rising | vidIQ | 辅助校准 | ❌ 待接 |
| AI Expansion | GPT / Claude / Gemini | 搜索意图扩展 | 🚧 仅配置 |
| 数据库 | PostgreSQL / Supabase | 保存时间序列 | ✅ 已用 PostgreSQL |
| 定时任务 | n8n / cron | 每小时 / 每天刷新 | ✅ 已有 Celery+Redis |
| 最终评分 | **你自己模型** | 不要交给 AI | ✅ 已有规则引擎 |

**好消息**：数据库（PostgreSQL）、定时任务（V1 已有 Celery+Redis，可替代 n8n/cron）、规则评分引擎，V1 都已就位。V2 主要是**加数据源（Google Trends / vidIQ）+ 加字段 + 重构评分公式**，基础设施不用重搭。

---

## 12. 落地路线（对话第 21 章的 6 个 Phase）

对话给了非常明确的推进顺序，**核心原则：不要推翻旧模型，逐层叠加。**

| Phase | 做什么 | 与 V1 关系 | 交付物 |
| --- | --- | --- | --- |
| **Phase 1** | 保留现有 Suggest → SerpApi → Competition Score | ✅ V1 已完成 | 现有系统 |
| **Phase 2** | 加时间序列：接 Google Trends，每天/每 6 小时存快照，算 Trend Velocity + Acceleration | 新增 Demand 层 + 快照表 | 需求增速 |
| **Phase 3** | 加 Supply Velocity：new_videos 24H/7D/30D，算 Demand Growth / Content Growth | 扩 Supply 字段 | 供给增速 |
| **Phase 4** | 做 Vacuum Score：需求↑↑↑ + 供给↑ + 竞争↓ | 新增派生分数 | 真空分 |
| **Phase 5** | 接 AI：意图扩展、长尾生成、主题聚类、意图分类（不打分） | 激活 V1 已配置的 AI | 自动发现扩展 |
| **Phase 6** | 机器学习：用"预测分 vs 实际发布表现"训练模型 | 需先积累历史数据 | 排名/破圈概率预测 |

**对话给你的最终建议原话**：

> 你这个项目下一步最值得做的，不是继续堆工具，而是把现有模型改成**「时间序列 + Demand/Supply 双向模型」**。

即：**优先做 Phase 2 和 Phase 3**（时间序列 + 供给增速），这是性价比最高的两步，做完 Vacuum Score（Phase 4）就自然成立了。

---

## 13. V1 → V2 映射总表（给 AI Coding 改代码用）

| 能力 | V1 现状 | V2 目标 | 改动量 |
| --- | --- | --- | --- |
| Seed 来源 | 用户手输 | + Google Trends / vidIQ Rising 自动发现 | 大（新数据源） |
| 时间维度 | 无（快照） | 时间序列快照表 + 定时采集 | 大（新表 + Celery beat） |
| Demand 数据 | 无 | trend_now/7d/30d、velocity、acceleration | 大（全新层） |
| Supply 数据 | 前 5 视频快照 | + result_count、median_age、new_videos_7d/30d | 中 |
| View Velocity | 无（只有 view_count） | views / days_since_publish | 小（已有字段） |
| Breakout Ratio | 无 | views / subscribers | 小（已有字段） |
| 视频字段 | 9 项 | + description、duration | 小（V3 补） |
| 评分公式 | 4 维 rule_score | Demand/Supply/Vacuum/Opportunity 多层 | 中（rule_score 降级为 Competition Score） |
| AI | 仅配置未接入 | 意图扩展（Phase 5，不打分） | 中 |

### 13.1 现有 4 维打分在 V2 里的归属

V1 [services.py](backend/keywords/services.py) `calculate_score` 的 4 个维度，在 V2 里全部归入 **Competition Score**（Opportunity Score 的 35%）：

| V1 维度 | V1 含义 | V2 归属 |
| --- | --- | --- |
| `title_mismatch` 标题不匹配 | 前排没精确覆盖该词 | Competition → title_match / exact_match_count |
| `low_subscriber` 订阅<2000 | 竞对是小频道 | Competition → avg_channel_subscribers + Breakout Ratio |
| `low_view` 播放<5000 | 没有爆款压制 | Competition → top10_strength（建议升级为 View Velocity） |
| `published_over_24h` 发布超24h | 前排内容旧 | Supply → median_age（升级为供给新鲜度） |

**这四个维度都保留、都还有用**，只是从"最终分"变成"竞争侧子项"，并且部分升级成更精确的指标（如播放量 → View Velocity、24h → median_age）。

---

## 14. 与 V1 文档的衔接说明

- 本文档是 V1 需求文档（`youtube_system_requirements_v1.0.md`）的**演进版**，不替代它。
- V1 文档记录的是"已实现的第一期"，本文档记录的是"下一步 V2 升级设计"。
- 本文档所有技术观点均来自 ChatGPT 对话《YouTube关键词分析工具》，未加入对话之外的推测；凡对话未明确、由我补充的落地结构（如 5.4 快照表、9.2 符号方向说明），均已在正文标注。
- 落地时建议：先按第 12 章 Phase 2/3 做时间序列和供给增速，其余按优先级排期。

---

## 15. 待确认问题

以下是对话里没讲透、落地前需要你拍板的点：

1. **趋势采集频率**：每天一次还是每 6 小时一次？频率越高数据越细但 SerpApi 额度消耗越大。
2. **vidIQ 是否第一版就接**：对话定位它为"辅助校准"，可以 Phase 2 只接 Google Trends，vidIQ 往后放。
3. **评分权重**：第 9 章的权重是对话的初版拍脑袋值，是否直接用还是先做成可配置再调。
4. **监控范围**：是所有关键词都持续监控，还是只监控进入 TOP 50 的候选词（省额度）？
5. **Supply Growth 数据获取**：new_videos_7d/30d 需要按发布时间过滤统计，SerpApi 是否能高效拿到还需验证。

