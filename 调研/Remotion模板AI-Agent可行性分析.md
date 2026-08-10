# Remotion 模板 AI Agent 可行性分析

整理日期：2026-08-07
背景：在系统后台做一个 AI 自动化 agent（效果类似 Claude Code），在聊天窗口用自然语言描述需求，agent 帮忙分析并生成/修改 Remotion 视频模板。
文档状态：可行性评估，未开发。

---

## 一、结论先行

**可行，但建议把目标从「做一个像 Claude Code 的通用 agent」收窄成「做一个专门写 Remotion 模板的窄域 agent」。**

- 通用 Claude Code 克隆是大工程（工具框架、循环控制、上下文管理、安全沙箱，长期投入）。
- 窄域 agent 因为**领域很窄、验证方式明确**，v1 大概 1~2 周能做出真正可用的东西。

**关键洞察**：Claude Code 难在「任意仓库、任意任务、任意工具」。而本场景是：

1. **单一文件类型**（`render/src/PromoVideo.tsx` 一个模板文件）；
2. **已知数据契约**（`promoSchema` / inputProps 字段固定，见 `render/Remotion操作文档.md` 第 3 节）；
3. **明确的验证手段**（TypeScript 类型检查 + 渲染一帧看效果）。

这三点让它比通用 agent 简单一个量级。

---

## 二、Claude Code 由什么构成

拆开看，「像 Claude Code」= 四件事，缺一不可：

| 要素 | Claude Code | 本系统窄域版怎么落地 |
| --- | --- | --- |
| 强编码模型 | Claude 原生 | 用 moretokens 里的 claude/gpt；**不能**用现在打分/元数据的 gemini-flash 文本模型硬扛复杂 React |
| 工具循环（读/写文件、跑命令、看输出） | 原生 tool-use | 需自建：读模板、写草稿、类型检查、渲一帧 |
| 错误反馈闭环（看到结果再改） | 有 | **价值核心，必须做** |
| 运行环境（能跑代码） | 本地全文件系统 | 现有 `render` Node 容器已具备 |

### 现有可复用基础（底子不差）

- `keywords/services.py` 的 `_call_ai_stream()`：moretokens SSE 流式对话，已验证。
- `_extract_json()`：容错解析 AI 返回的 JSON。
- Django ↔ `render` 容器的 HTTP 桥（`render_video()` 已在用）。
- `render` 容器能跑 Remotion（bundle + renderMedia 已实现）。

---

## 三、架构草图（窄域 agent）

```
前端聊天窗（复用现有 SSE 流式 UI）
   │  例：「我要一个标题从左滑入、promo code 脉冲高亮的模板」
   ▼
Django agent 循环（新 app 或挂 content_gen）
   │  system prompt = Remotion 知识 + 当前模板源码 + inputProps schema
   │  ┌─────────── agent loop（最多 N 轮）───────────┐
   │  │ 1. 模型产出 动作(JSON) 或 tool call          │
   │  │ 2. 执行工具 → 拿结果 → 回喂模型               │
   │  └───────────────────────────────────────────┘
   ▼  （工具通过 HTTP 调 render 容器）
render 容器新增端点：
   - read_template        读当前 .tsx 源码
   - write_draft          写到草稿文件（不动生产模板 PromoVideo.tsx）
   - typecheck            tsc 类型检查 → 返回编译报错
   - render_preview_frame renderStill 渲一帧 png → 返回图
```

### 反馈闭环两档

- **文字档（便宜、必做）**：`typecheck` 返回的编译错误回喂模型，让它自纠。
- **视觉档（更像 Claude Code，但更贵）**：`render_preview_frame` 渲一帧图，用**多模态模型**看图自评「布局对不对」，需要视觉模型 + 更多 token。

---

## 四、必须先探明的未知项（决定难度）

以下没定，工作量估不准，建议开工前先验证：

1. **moretokens 是否支持 function calling（`tools` 参数）？**
   - 支持 → 用原生 tool-use，最稳。
   - 不支持（很可能，因为它强制 `stream:true`）→ 退回 **ReAct 风格**：模型输出固定 JSON 动作，后端解析后执行。已有 `_extract_json`，这条路走得通，只是不如原生稳。
   - **验证方式**：`GET /v1/models` + 发一个带 `tools` 字段的测试请求探一下。

2. **用哪个模型写代码？** 复杂 React / 动画代码质量 = 模型能力决定。建议 agent 这块**单独配强编码模型**（claude / gpt），别用 gemini-flash。

3. **要不要视觉反馈？** 要的话得接多模态模型，成本和延迟都上去。v1 可先只做类型检查 + 人预览。

4. **上线机制（体验关键）**：现在改模板要 `docker compose build render` 才生效。若 agent 要「即改即预览」，建议把 `render/src` 挂成卷（热更新），否则每轮迭代都要 rebuild，循环体验很差。

---

## 五、主要风险与缓解

| 风险 | 说明 | 缓解 |
| --- | --- | --- |
| 代码执行安全 | agent 写的代码在 render 容器里跑 Chromium，等于任意代码执行 | 写**草稿文件**、人审通过才 promote 到生产模板；容器限制外网/写权限 |
| 覆盖生产模板 | 直接改 `PromoVideo.tsx` 可能弄坏正在跑的批量渲染 | 草稿隔离 + 每次改动备份 + 一键回滚 |
| 循环失控 / 烧 token | agent 反复改改不对 | 限制最大轮数、设 token 预算、超限交人工 |
| 质量天花板 | = 模型能力 + 反馈质量，复杂视觉效果未必一次到位 | 保留「agent 出方案 → 人在 Studio 预览 → 继续调」的人机闭环 |

---

## 六、分阶段建议

| 阶段 | 内容 | 工作量 | 价值 |
| --- | --- | --- | --- |
| **P0 · 副驾** | 聊天里 agent 生成/修改模板代码，给出 diff，一键写入**草稿文件**，人点开 Studio 预览。无自动循环 | 几天 | 已经很高，非程序员也能用大白话调模板 |
| **P1 · 自校验循环** | 每次写完自动跑 typecheck + 渲一帧，编译错自纠，稳定后再交人 | 1~2 周 | 真正「像 Claude Code」的核心体验 |
| **P2 · 视觉自评** | 接多模态模型看渲染帧，自评布局并微调 | 额外几天 + 成本 | 锦上添花 |
| **P3 · 通用 agent** | 多文件、任意任务的完整 Claude Code 克隆 | 大工程 | ❌ 不建议，性价比低 |

**推荐路线：P0 → P1 打住。P3 不追。**

---

## 七、一个要摆在桌面上的替代方案

如果操作这个功能的是懂点技术的人，**最快、质量最高、零构建成本的做法其实是：直接用 Claude Code / Cursor 打开 `render/` 目录改模板**（见 `render/Remotion操作文档.md` 第 6 节 Remotion Skills 思路）。

系统内自建 agent 的真正价值在于：

- 给**非程序员**用；
- 在一个**后台里闭环**；
- 带**护栏**（草稿隔离、自动校验、一键回滚）。

**决策点**：如果没有「非程序员操作」这个刚需，自建 agent 的投入产出比不如直接用现成工具。要不要投，取决于这个刚需是否成立。

---

## 八、下一步

若决定推进，建议先做 **P0 副驾原型**：

1. 探明 moretokens 是否支持 function calling（决定 tool-use vs ReAct）。
2. render 容器新增三个接口：`read_template` / `write_draft` / `typecheck`。
3. Django 新增一个 agent 端点（system prompt 注入当前模板源码 + inputProps schema，复用 `_call_ai_stream`）。
4. 前端一个聊天框（复用现有流式 UI）。
5. 打通链路：描述 → 出模板代码 → 写草稿 → Studio 预览。

跑通后再评估是否进入 P1 自校验循环。

---

## 参考

| 资源 | 位置 |
| --- | --- |
| Remotion 操作文档（本系统） | `render/Remotion操作文档.md` |
| 模板本体 | `render/src/PromoVideo.tsx` |
| inputProps 数据契约 | `render/src/PromoVideo.tsx` 的 `promoSchema` |
| 渲染服务 | `render/server.mjs` |
| AI 流式调用能力 | `backend/keywords/services.py` 的 `_call_ai_stream` / `_extract_json` |
| 需求文档 | `调研/youtube_system_requirements_v2.0.md`（流程一见第 27~30 节） |
