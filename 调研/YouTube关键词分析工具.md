---
created: 2026-08-03T18:14:23 (UTC +08:00)
tags: []
source: https://chatgpt.com/share/6a706767-c594-83ee-9149-e9db29bf7361
author: 
---

# YouTube关键词分析工具

> ## Excerpt
> 对，你现在这套初版其实方向是对的。问题不在于“打分公式不够复杂”，而在于你现在的系统本质上是：

---
对，你现在这套初版其实**方向是对的**。问题不在于“打分公式不够复杂”，而在于你现在的系统本质上是：

> **从已有关键词出发 → 找长尾 → 判断竞争难度**

而你真正想要的是：

> **先发现“需求正在发生变化” → 再反向生成关键词 → 最后判断 YouTube 供给是否跟得上。**

这两者是完全不同的系统。

我刚查了目前的工具和 API 能力后，我建议你**不要推翻现有模型，而是在前面加一层「实时需求发现层」**。

___

## 一、你现在的系统，缺的其实是一个“Trend Signal”

你现在：

这个模型可以很好地回答：

> **“这个关键词现在竞争激烈不激烈？”**

但是无法回答：

> **“这个关键词最近是不是突然开始有人搜索？”**

所以你会遇到一个问题：

### A

keyword A
搜索量：1000
过去 30 天：1000 → 1000 → 1000
竞争：低

### B

keyword B
搜索量：300
过去 30 天：10 → 20 → 50 → 100 → 300
竞争：低

你的旧模型很可能：

A = 80分
B = 55分

但实际上：

**B 才是你真正想抓的“真空词”。**

___

## 二、我建议你改成 4 层架构

我会把你的系统升级成：

                 ┌────────────────────┐
                 │  Demand Discovery   │
                 │   需求发现层         │
                 └─────────┬──────────┘
                           ↓
             ┌──────────────────────────┐
             │ Keyword Expansion Engine │
             │    长尾扩展引擎           │
             └────────────┬─────────────┘
                          ↓
             ┌──────────────────────────┐
             │ YouTube Supply Analysis  │
             │    内容供给分析           │
             └────────────┬─────────────┘
                          ↓
             ┌──────────────────────────┐
             │ Opportunity Scoring      │
             │    真空机会评分           │
             └──────────────────────────┘
你的现有系统实际上已经覆盖了后面 **3/4**。

真正需要新增的是第一层。

___

## 三、第一步：增加 Google Trends

这是我认为你**现在就应该接入的第一个工具**。

不是因为 Google Trends 能告诉你 YouTube 精确搜索量。

它不能。

而是因为它可以给你：

> **Demand Velocity（需求变化速度）**

SerpApi 现在直接提供 Google Trends API，可以获取：

-   Interest over time
    
-   Related queries
    
-   Rising queries
    
-   Related topics
    
-   地区
    
-   时间序列
    

而且 `RELATED_QUERIES` 返回的 rising queries 里可以得到增长值，例如 `+250%` 或 `Breakout`。[![](https://www.google.com/s2/favicons?domain=https://us-west.serpapi.com&sz=128)SerpApi+1](https://us-west.serpapi.com/google-trends-api?utm_source=chatgpt.com)

所以你的系统可以变成：

Seed
 ↓
Google Trends
 ↓
发现 Rising Query
 ↓
YouTube Suggest
 ↓
长尾扩展
 ↓
YouTube SERP
 ↓
竞争分析

___

## 四、而且你做印度市场，这个东西特别有价值

比如你的 seed：

AI video generator

Google Trends 可能发现最近：

AI video generator for youtube shorts
AI video generator free
AI video generator from text
AI video generator mobile
AI video generator hindi

其中某个词突然：

+350%

这时候不要直接判定它是好关键词。

而应该把它扔回你现有的 YouTube pipeline：

Rising keyword
       ↓
YouTube Suggest
       ↓
生成：
xxxx free
xxxx for mobile
xxxx for beginners
xxxx hindi
xxxx india
xxxx shorts
       ↓
SERP
       ↓
竞争分析

这样才开始真正出现：

> **Trend × Vacuum**

___

## 五、第二个非常重要的东西：Trend Velocity

不要只保存：

Google Trends = 80

这个数字其实意义不大。

你应该保存**时间序列**。

比如：

7 days

Day 1    12
Day 2    15
Day 3    14
Day 4    21
Day 5    30
Day 6    48
Day 7    76

然后计算：

velocity = (recent_avg - old_avg) / old_avg

### Trend Velocity

velocity = (recent_avg - old_avg) / old_avg

更进一步，可以计算：

### Acceleration

velocity(t) - velocity(t-1)

你真正想找的是：

Demand
   ↑
   │                   ●
   │               ●
   │           ●
   │       ●
   │   ●
   └────────────────────→ Time

而不是：

Demand
   ↑
   │  ● ● ● ● ● ● ●
   │
   └────────────────────→ Time

___

## 六、第三层：Google Trends 不够，要加入“趋势发现器”

这里我反而建议你参考 **vidIQ 的 Rising Keywords** 思路。

vidIQ 目前已经提供 Rising Keywords，可以按：

-   Today
    
-   This week
    
-   This month
    

筛选，而且它的算法就是专门识别 YouTube 搜索量正在明显增加的关键词。[![](https://www.google.com/s2/favicons?domain=https://support.vidiq.com&sz=128)vidIQ Help Center](https://support.vidiq.com/en/articles/9421214-keywords-research?utm_source=chatgpt.com)

这说明市场上已经验证：

> **Rising Keyword 本身就是一个独立的数据维度。**

所以你的模型应该新增：

trend_source

Google Trends
vidIQ Rising
YouTube Suggest
YouTube search result changes

而不是把所有东西混成一个分数。

___

## 七、我建议你的关键词数据库以后长这样

不要只存：

keyword
views
subscribers
title_match
published_date
score

扩成：

Keyword
│
├── Demand
│   ├── trend_now
│   ├── trend_7d
│   ├── trend_30d
│   ├── velocity_24h
│   ├── velocity_7d
│   └── acceleration
│
├── Discovery
│   ├── youtube_suggest
│   ├── google_rising
│   ├── related_query
│   └── external_signal
│
├── Supply
│   ├── result_count
│   ├── top10_views
│   ├── median_views
│   ├── median_age
│   ├── new_videos_7d
│   └── new_videos_30d
│
├── Competition
│   ├── title_match
│   ├── exact_match_count
│   ├── avg_channel_subscribers
│   ├── avg_views_subscriber_ratio
│   └── top10_strength
│
└── Opportunity
    ├── demand_score
    ├── supply_gap
    ├── competition_score
    └── vacuum_score

这样你未来就可以不断换算法，而不需要重新采集数据。

___

## 八、你现有的“播放量”指标，我建议改掉一个思路

你现在可能类似：

播放量越低
→ 越容易做

这个逻辑不够准确。

比如：

### Keyword A

Top 10：

2M
1M
800K
500K
300K
...

显然竞争强。

但：

### Keyword B

Top 10：

50K
30K
20K
10K
8K
...

不能简单判断它是低竞争。

因为可能：关键词搜索量很低

所以真正重要的是：

## **Views / Demand**

也就是：

> **搜索需求相对于现有内容表现怎么样？**

___

## 九、我建议加入一个非常关键的指标

## Freshness Gap

比如：

过去 30 天：
关键词需求 ↑ 250%

但是：
过去 30 天只有 3 条新视频

这就是很强的信号。

反过来：

需求 ↑ 250%

过去 30 天出现 800 条新视频

那么：

**这个热点已经被创作者发现了。**

所以：

Vacuum =
Demand Growth
-
Content Growth

这可能会成为你系统里**最核心的指标之一**。

___

## 十、进一步升级：做“Demand / Supply Ratio”

例如：

### Keyword A

Google Trends
+300%

YouTube 新视频
+20%

那么：

Demand Growth = 300
Supply Growth = 20

Gap = 15x

非常好。

___

### Keyword B

Demand Growth = +300%

Supply Growth = +450%

那就：

❌ 不是真空。

因为内容生产速度已经超过需求增长。

___

## 十一、你现在 SerpAPI 这一层也可以升级

你现在应该不是只拿：

views
subscribers
title
published date

而应该进一步记录：

Video
│
├── views
├── likes
├── comments
├── channel_subscribers
├── published_at
├── title
├── description
├── duration
└── channel

SerpApi 的 YouTube Video Results 当前可以直接结构化返回视频的：

-   title
    
-   channel
    
-   published date
    
-   views
    
-   length
    
-   thumbnail
    
-   position
    

等字段。[![](https://www.google.com/s2/favicons?domain=https://serpapi.com&sz=128)SerpApi](https://serpapi.com/youtube-video-results?utm_source=chatgpt.com)

然后你真正需要计算的是：

### View Velocity

views / days_since_publish

例如：

Video A
100,000 views
100 days old

= 1,000 views/day

VS

Video B
20,000 views
2 days old

= 10,000 views/day

第二个实际上更强。

___

## 十二、再加一个非常重要的：Small Channel Breakout

这是我认为你的模型以后**一定要加**的。

假设：

Keyword X

Top videos:

10M views / 2M subs
4M views / 800K subs
2M views / 500K subs

这种词即使搜索量很大，也不一定适合小频道。

但是：

Video A
12K views / 1K subs

Video B
8K views / 700 subs

Video C
20K views / 2K subs

这说明：

> **小频道也可以从这个关键词获得流量。**

这是非常强的机会信号。

可以做：

Breakout Ratio
=
Views / Subscribers

例如：

12K / 1K = 12x

___

## 十三、所以你的新评分模型，我建议暂时不要上 AI

这点我反而建议你**先忍住**。

不要现在就：

> 把所有数据扔给 GPT → “帮我判断这个关键词好不好”。

因为你现在缺的是：

**数据维度**

而不是：

**判断能力。**

第一阶段应该先变成：

                   Keyword
                       │
          ┌────────────┼────────────┐
          ↓            ↓            ↓
       Demand        Supply      Competition
          │            │            │
          ↓            ↓            ↓
       Trend         Freshness    Top10
       Velocity       Gap         Strength
          │            │            │
          └────────────┼────────────┘
                       ↓
                 Vacuum Score
___

## 十四、我会这样重新设计你的 Score

先别追求复杂。

### Demand Score

Demand Score =
30% Trend Velocity
25% Trend Acceleration
20% Rising Signal
15% Suggest Signal
10% Baseline Demand

### Supply Score

Supply Score =
30% New Videos 7D
25% New Videos 30D
20% Top10 Median Views
15% Exact Title Match
10% Top10 Channel Strength

然后：

Vacuum Score =
Demand Score × 0.55
+
Supply Gap × 0.45

最后再加入你现在的竞争分：

Opportunity Score =
Vacuum Score × 0.65
+
Competition Score × 0.35

**这只是第一版。**

不要一开始就搞机器学习。

___

## 十五、真正重要的是：从“输入关键词”变成“自动发现关键词”

这是你整个项目最应该改变的地方。

现在：

用户：
AI video

系统：
↓
AI video generator
AI video maker
AI video editor
...

这是传统 Keyword Tool。

你真正应该做到：

系统每天自动扫描
        ↓
Google Trending / Rising
        ↓
Google Trends Rising Queries
        ↓
YouTube Rising Keywords
        ↓
YouTube Suggest
        ↓
你的 Seed Keyword
        ↓
AI/规则做 Query Expansion
        ↓
YouTube SERP
        ↓
Vacuum Detection
        ↓
TOP 50

这样你的产品从：

> **Keyword Analyzer**

变成：

> **Keyword Discovery Engine**

这两者产品价值完全不同。

___

## 十六、AI 应该放在哪里？

我建议 AI **只放在“扩展”和“理解”上**。

而不是放在基础数据计算上。

例如系统发现：

"ai video generator for shorts"

AI 负责生成：

ai video generator for shorts free
ai video generator for youtube shorts
ai video generator for shorts mobile
ai video generator for shorts hindi
ai video generator for shorts without watermark
ai video generator for shorts from text

然后你的 API 再验证。

AI 不负责：

> “这个关键词 87 分。”

而是：

> **“这个词可能有哪些真实搜索意图？”**

___

## 十七、最终系统，我会设计成这样

                    ┌───────────────┐
                    │  Trend Sources │
                    └───────┬───────┘
                            │
          ┌─────────────────┼─────────────────┐
          ↓                 ↓                 ↓
    Google Trends       YouTube Rising    External Trends
    Rising Queries        Keywords
          │                 │                 │
          └─────────────────┼─────────────────┘
                            ↓
                  ┌──────────────────┐
                  │ Discovery Engine │
                  └────────┬─────────┘
                           ↓
                   YouTube Suggest
                           ↓
                   AI Query Expansion
                           ↓
                    Keyword Pool
                           ↓
                  ┌──────────────────┐
                  │ YouTube SERP     │
                  │ SerpAPI / API    │
                  └────────┬─────────┘
                           ↓
              ┌─────────────────────────┐
              │ Supply / Competition    │
              ├─────────────────────────┤
              │ Views                   │
              │ View Velocity           │
              │ Subscribers             │
              │ Views/Subs              │
              │ Title Match             │
              │ Freshness               │
              │ New Videos 7D/30D       │
              └────────────┬────────────┘
                           ↓
                    Vacuum Engine
                           ↓
                    Opportunity Score
                           ↓
                  🔥 TOP 50 Keywords
___

## 十八、工具怎么选，我给你一个很实际的组合

|功能|第一选择|用途|
|---|---|---|
|YouTube Suggest|**你现有方案**|长尾扩展|
|YouTube SERP|**SerpApi**|竞品数据|
|Google Trends|**SerpApi Google Trends API**|趋势/上升速度|
|Rising Queries|**SerpApi Related Queries**|自动发现增长词|
|YouTube Rising|**vidIQ**|辅助校准|
|AI Expansion|GPT/Claude/Gemini|搜索意图扩展|
|数据库|PostgreSQL/Supabase|保存时间序列|
|定时任务|n8n / cron|每小时/每天刷新|
|最终评分|**你自己模型**|不要交给 AI|

SerpApi 的 Google Trends 接口甚至可以直接请求 `now 7-d` 这种时间窗口，并返回时间序列；所以它很适合成为你现有架构的一个“趋势数据层”。[![](https://www.google.com/s2/favicons?domain=https://serpapi.com&sz=128)SerpApi+1](https://serpapi.com/google-trends-api?utm_source=chatgpt.com)

___

## 十九、但是有一个非常重要的坑

**不要把 Google Trends = YouTube Search Volume。**

Google Trends 是 Google 搜索兴趣，不是 YouTube 精确搜索量。

所以：

Google Trends
        ↓
只能作为 Demand Signal

不能：

这是错误的。

甚至 Google Trends 自身的数值是相对指数，并不是绝对搜索量；低量词还可能出现数据缺失/噪声问题。[![](https://www.google.com/s2/favicons?domain=https://arxiv.org&sz=128)arXiv+1](https://arxiv.org/abs/2504.07032?utm_source=chatgpt.com)

所以你要做的是：

Google Trends
      +
YouTube Suggest
      +
YouTube SERP
      +
你自己的历史数据

**四个信号融合。**

___

## 二十、还有一个我认为比接 AI 更重要的升级

你现在是：

> **一次性分析关键词。**

下一步应该变成：

> **持续监控关键词。**

比如今天：

keyword = AI video generator for shorts

Trend = 42
Top10 median = 8,200
New videos 7D = 4
Score = 72

明天：

Trend = 51
Top10 median = 9,000
New videos 7D = 5
Score = 78

后天：

Trend = 68
Top10 median = 10,000
New videos 7D = 6
Score = 91 🔥

这时候系统不是在告诉你：

> “这个词不错。”

而是在告诉你：

> **“这个词正在进入窗口期。”**

这才是你真正要的**实时真空词**。

___

## 我建议你下一阶段按这个顺序做

### Phase 1 —— 先不要改旧模型

保留你现在：Suggest → SerpApi → Competition Score

### Phase 2 —— 加时间序列

增加：

Google Trends
↓
每天/每6小时保存一次
↓
Trend Velocity
Trend Acceleration

### Phase 3 —— 加 Supply Velocity

增加：

New videos 24H
New videos 7D
New videos 30D

然后计算：

Demand Growth / Content Growth

### Phase 4 —— 做 Vacuum Score

重点判断：

需求 ↑↑↑
供给 ↑
竞争 ↓

### Phase 5 —— 再接 AI

AI 负责：

Seed
 ↓
Intent Expansion
 ↓
Long-tail Generation
 ↓
Topic Clustering
 ↓
Search Intent Classification

**不要让 AI 替代你的数据评分。**

### Phase 6 —— 最后才考虑机器学习

等你积累了：

> **关键词 → Score → 实际发布 → 7/14/30 天表现**

这批历史数据以后才是真正值钱的。

届时可以训练：

Keyword Features
        ↓
ML Model
        ↓
Probability of Ranking
        ↓
Probability of Breakout

这会比现在让 GPT 给关键词打分强得多。

___

**我认为你这个项目下一步最值得做的，不是继续堆工具，而是把你现有模型改成“时间序列 + Demand/Supply 双向模型”。**

如果你愿意，我下一步可以直接按你现在的程序思路，给你设计一份\*\*「YouTube 真空长尾词 V2 技术方案」\*\*：包括 **数据库字段、SerpApi/Google Trends API 接入、每小时数据采集、Trend Velocity/Acceleration 算法、Supply Gap、Vacuum Score 公式，以及 n8n/代码的具体工作流**。这样你可以直接拿给 AI Coding 去改现有程序。
