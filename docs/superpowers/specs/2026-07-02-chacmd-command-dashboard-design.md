# ChaCMD 指挥大屏（Command Dashboard）设计

- 产品：**ChaCMD（察CMD）** · 察元 · 智能体指挥平台
- 主题：ChaCMD SKU 全新主页 / 指挥大屏（对应总设计 §6.15 的深化与业界对齐重构）
- 日期：2026-07-02
- 状态：设计稿（待评审）
- 前置文档：`2026-06-30-chacmd-design.md`（总设计）、`2026-07-01-chacmd-requirements.md`（需求）、`2026-07-01-chacmd-p0-backend-skeleton.md`（P0 后端骨架，已实现）
- 作者：Claude（与用户 brainstorming 产出，含 4 路业界联网调研对齐）

---

## 0. 一句话定位

指挥大屏 = **数字员工指挥官的驾驶舱**：装在裸机主机上的原生客户端（`apps/chacmd` Tauri 壳），**开机自启全屏**，一屏统揽"主机 / 工位 / 数字员工 / 技能 / 状态 / 进度 / 实时反馈"，并直接下令。视觉上**炫酷、游戏化、3D**；工程上**信息全面、可下钻排障**——靠"3D 游戏化总览 + 2D 工程化下钻"双层兼得。

**运行形态（已钉死）**：
- 指挥系统装**裸机**，**不进 KasmVNC**。大屏在裸机本地 GPU 原生渲染，**不经 VNC 串流** → 3D/WebGL 满帧流畅，炫酷与流畅不矛盾。
- **KasmVNC 容器只是"某个专业数字员工"的工位**（子容器 agent 工作站），不承载大屏。
- 开机自启一个 kiosk 全屏客户端，像监控墙常驻。

---

## 1. 领域本体（对齐业界四层，最重要的地基）

> 本体错则后期返工代价最大。经 4 路联网调研（agent 框架 / 沙箱执行环境 / 编排任务 / 可视化），业界 2025-2026 已收敛出一套四层解耦模型，我们的直觉与之一致，此处采纳其命名以避免自造词返工。

### 1.1 四层解耦

| 我们的概念 | 业界层 | 业界命名 | 关键性质 |
|---|---|---|---|
| **数字员工 = 人** | 持久身份 Identity | Agent Identity / Workload Identity / **Digital Worker** | 持久、外置于容器、**机器挂了身份不丢**；唯一 ID |
| **容器 = 工位/电脑** | 短暂运行时 Runtime/Sandbox | Sandbox / Runtime / **"agent's computer"** | 短暂、可丢弃、**可重建、可迁移**（=天然容灾） |
| **引擎(openclaw/Hermes/codex)+技能** | 工具 Tools | Tools / MCP / Gateway + Skills | **装在环境里(能力池)**，"能不能用"由独立权限层(policy)决定；**引擎=能力不是身份** |
| **记忆** | 可插拔记忆 Memory | Memory / Checkpoint / event-sourcing | **外置、可插拔**；换容器身份+记忆都不丢——容灾闭环最后一块 |

**核心判断**：一个装了 openclaw+Hermes+codex 的 kasm 容器，**默认不是"三个人"，而是"一个会三种手艺的数字员工"**。引擎是可被不同角色取用的公共能力池，不是身份。

**业界印证**：CrewAI `Agent = role+goal+backstory`；MetaGPT/ChatDev 把软件公司拟人成 PM/架构师/工程师；Devin 被高盛称 "Employee #1"；Daytona "给每个 agent 一台电脑"；Cloudflare "Agents have their own computers"。→"一个员工 + 一台电脑(容器) + 一身手艺 + 外置记忆"是业界主流叙事。

### 1.2 对象关系：N:N 数据模型 + 一人一工位默认策略

```
主机 Host ─1:N─ 容器/工位 Container ─N:N─ 数字员工 Agent ─N:N─ 任务 Task
                          │(placement 映射)              │(assignment 映射)
        引擎池 + 技能池(装在容器) ──取用──┘              └── 一员工可接多任务, 一任务可多员工
```

- **数据层建成 N:N**：容器⇄员工（placement 映射）、员工⇄任务（assignment 映射）都走映射表。
- **策略/UI 层默认 1:1**：默认一人一工位、任务默认派给现成的人。
- **为什么这么定 = 防返工**：数据库写死 1:1 → 将来"一室多人"要改表迁移（大返工）；一开始建 N:N + 默认跑 1:1 → 放开策略开关即可，零迁移。业界 identity 与 runtime 从一开始就解耦为多对多，正为此。

**两个轴要分清**：
- **一工位多任务**：天生支持（任务不绑容器，靠 assignment 映射 + agent 复用）。
- **一工位多人**：技术支持但默认不建议（隔离/安全/故障域/审计/计费/大屏拟人化都会降级）。合理例外：紧耦合结对、一堆轻角色省资源、同引擎多开。仅按需放开，并标注"牺牲隔离"代价。

### 1.3 命名总账（对外亲和 / 对内严谨）

| 场景 | 用词 |
|---|---|
| 对用户/大屏 | **数字员工**、**工位/它的电脑**（容器）、**角色·目标·背景**（role/goal/backstory）、**技能栏** |
| 技术内部 | `identity / runtime(sandbox) / tools / memory` 四分；agent = stateless config + 外置记忆 |
| 总指挥 | **Supervisor**（业界最主流）/ lead agent；两档：**ROUTE 纯路由**(省 token) vs **ORCHESTRATE 拆解+并发+汇总** |
| 协作语义 | **handoff**(转交控制权=接力) vs **as_tool**(借用能力，不转交)——大屏上要区分画法 |
| 任务对象 | **Anthropic 四要素**：目标 objective / 输出格式 output_format / 工具与来源 tools&sources / 边界 boundaries + 依赖 + 状态 + 结果引用 |
| 多对多 | `Assignment(task_id, agent_id, role, status)` 映射表 + 共享状态（agent 无状态可复用） |
| 任务状态机 | created → queued → assigned → running →（input_required / retrying）→ completed / failed / canceled |

---

## 2. 大屏双层架构 + 三层下钻

### 2.1 双层架构（业界所有资料的交集共识）

- **总览氛围层 = 游戏化 / 3D**：直觉感知集群规模、谁活跃、消息在谁之间流。
- **下钻排障层 = 工程化 2D 高密度**：真正做决策和看数据的地方。
- **纪律：切勿只做炫的那层。** 3D 单独用会踩：遮挡藏信息、3D 里文字难读、深度歧义；NOC 实测盯 15-20 面板 MTTR +30%（告警疲劳）。→ 关键数据必须 2D 兜底，状态别用二元红绿灯，头顶用 emoji/图标气泡比塞文字耐读（斯坦福 Smallville 手法）。
- 大屏跑裸机本地 GPU → 3D 满帧流畅，"3D 总览 + 2D 下钻"分工兼得炫酷与可用。

### 2.2 三层下钻

| 层 | 形态（业界现成范式） | 对上的需求 |
|---|---|---|
| **L0 总览** | **3D 场景图**：节点=主机/工位/员工，连线=数据流（粒子流表 A2A 消息），bloom 辉光聚焦；**每个员工头顶 emoji 气泡显示"正在干嘛"**（Smallville） | 主机·工位·员工·技能·状态·进度全面 + "像游戏一样" |
| **L1 点进任务(Job)** | **编排扇出树/看板**（Supervisor 中心 + 并行分支）+ **活动时间线**（钉住"当前步"）+ **group-chat 消息流**（handoff 可见）；每个参与者一张**角色卡** | "点进任务有各个角色、实时反馈" |
| **L2 点进员工(Agent)** | **Devin 式多 Tab**（Progress/Shell/Browser/Editor）+ Manus 侧面板 + **一键免密开他的 KasmVNC 桌面(#8)** | "智能体本身/技能/当前进度/实时反馈" |

### 2.3 L0 主视觉：同一份数据两套皮肤（不硬选，防返工）

L0 底层是一张图（节点=主机/工位/员工，边=数据流/交接）。星群与城市只是渲染皮肤：
- **星群皮肤（v1 默认）**：`3d-force-graph`(Three.js) 力导向，科技深空感，节点多不乱，上手最快（粒子流/辉光/头顶气泡库现成）。
- **城市皮肤（后续）**：deck.gl + Cesium，楼宇/工位实体感、数字孪生政企大屏范，较重。
- 底层同一份 scene graph，换皮肤不动数据模型和下钻逻辑，零返工。L1/L2 与皮肤无关。

### 2.4 双模式（沿用总设计 §6.15）

- **驾驶舱模式（默认，可交互）**：指挥对话框为焦点，L0 态势环绕；对话即指挥（复用察元 chat composer，非自造 mini 版）。
- **投墙只读模式（kiosk）**：L0 铺满，对话收起，全屏深色、放大关键指标、多视图轮播。开机自启进此模式。

---

## 3. 关键 UI 组件字段与交互

### 3.1 数字员工卡（Agent Card，合并 CrewAI + 11x + 治理版 Ownership Card + 可观测）

| 类别 | 字段 |
|---|---|
| 身份 | 头像、昵称、角色/岗位、目标 goal、背景 backstory、所在工位/主机、owner |
| 状态 | 生命周期灯：thinking / using tool / waiting / **stuck** / done；钉住的当前步骤 |
| 能力 | 技能栏（引擎 + skills 图标）、绑定模型、知识域范围(#19) |
| 计划 | 当前/待办子任务 + status + 预期产物 |
| 观测 | token（in/out）、latency、累计耗时、成本；接近上限触发"请求继续授权"(circuit breaker) |
| 治理 | 权限、已知失败模式、审计入口 |
| 动作 | 免密开桌面(#8)、编辑角色契约(#18)、查日志 trace |

### 3.2 任务编排视图（L1）

- **顶层结构**：以 Supervisor 为中心的扇出树/看板（非线性对话），体现"中心编排 + 并行分支"；handoff 边与 as_tool 调用区分画法。DAG 复用 chayuan-client 已装的 **reactflow**。
- **活动时间线**（黄金组件）：时序展示操作，可折叠详略 + 钉住"当前步" + "跳到产物"链接；叠加带发言人标识的统一消息流（message passing / handoff）。
- **角色卡**：每个参与者一张（role/scope/tools/permissions/handoff rules + 当前是否 supervisor + 路由理由）。
- **任务对象字段**：Anthropic 四要素 + 依赖 + 状态机 + 结果引用（大产物走"存储+引用"，不塞进指挥上下文防截断）。

### 3.3 员工现场（L2）

- 学 Devin 多 Tab（Progress / Shell / Browser / Editor + 底部 Live 进度条 + timelapse 可回放/回滚）+ Manus "它的电脑"侧面板（实时看用什么工具、中间结果）。
- 一键免密开该员工的 KasmVNC 桌面（iframe，§6.5）。

---

## 4. 实时事件流 + 平滑动画

- **通道**：后端按 tick 推**增量事件流**（AG-UI 式事件类型：`TOOL_CALL_START` / `STATE_DELTA` / `THINKING` / 生命周期 / interrupt），复用 ChaCMD **统一事件总线脊柱**（心跳/进度/A2A/外部数据同一条总线）。**事件流而非轮询。**
- **平滑**：前端用 **AI Town 的"当前值 + 历史缓冲 + 插值"**把离散后端事件回放成连续动画（`useHistoricalValue` 手法），不是每帧拉数据 → 不卡。
- **降级**：无数据的 widget 优雅降级，不阻塞首屏。
- **聚合层**：Session/Thread 概念把多条 trace 串成一次多员工运行；大屏总览按 agent/任务过滤（AgentOps Agent Selector 手法）。

---

## 5. 人在环（HITL）+ 告警纪律

- **HITL**（S2 防空等场景刚需）：Intent Preview（"我准备做 X，可以吗"）+ **自主度调节钮**（Suggest → Draft → Execute 分级放权）+ 动作回执 / 可撤销（Action Receipts / Undo）+ 敏感步骤 interrupt 四选一（approve/edit/reject/respond）。
- **告警纪律**（防 NOC 告警疲劳）：优先级排序的告警队列、单一真源大图、"全员同一幅图"共享态势；状态别用二元红绿灯（隐藏因果因子），展示**提炼后的推理**而非 raw CoT（AG-UI "no raw CoT"），暴露不确定性(confidence)防自动化偏见。

---

## 6. 前端落点与技术栈

> 遵循总设计 §3.7「一套基座、双 SKU、不同主页、分开打包」+ §3.6 依赖单向硬约束。

### 6.1 代码组织

```
chayuan-client/
├─ packages/app            ← 察元基座（禁止 import chacmd 增量）
├─ packages/chacmd-features/ (@chayuan/chacmd-features)   ← ChaCMD 专属 UI（新增）
│     dashboard/CommandDashboard      L0 3D 总览（星群皮肤）
│     task/TaskOrchestrationView      L1 任务编排 + 角色卡
│     agent/AgentStageView            L2 员工现场多 tab
│     scene/                          scene graph 数据模型 + 皮肤渲染层
├─ apps/desktop  apps/web  ← 察元 SKU（主页不变）
└─ apps/chacmd/            ← ChaCMD SKU（新增：main.tsx + BrandConfig + src-tauri）
      import @chayuan/app(基座) + @chayuan/chacmd-features(增量)
```

- **注入 seam**（§3.7 注入点②）：`BrandConfig.homeComponent = CommandDashboard`；routeExtensions 新增 `/command`，landing 指 `/command`；察元 `/home` 及整套工作台始终可达（顶栏 `🏠 察元工作台` 一键进）。
- **依赖单向**：基座禁止 import chacmd；ESLint/CI 挡反向 import。

### 6.2 技术栈选型

| 用途 | 选型 | 理由 |
|---|---|---|
| L0 3D 场景（星群皮肤） | `3d-force-graph`(Three.js) 或 react-three-fiber | 力导向 + 粒子流 + bloom + 头顶气泡现成；跑裸机 GPU 流畅 |
| L0 城市皮肤（后续） | deck.gl + Cesium | 数字孪生底图，重，留后续 |
| L1 DAG / 编排图 | **reactflow**（chayuan-client 已装） | 复用现成依赖，零新增 |
| 对话框 | 复用察元 chat composer | 真复用，非自造 mini 版 |
| 实时 | 统一事件总线 SSE/WS（AG-UI 式增量）+ 前端历史插值 | 复用察元 SSE 基建 + packages/transport |
| 样式 | @chayuan/ui + design-tokens 的 ChaCMD 深色指挥风 theme | 经 BrandConfig 覆盖 |
| 状态 | zustand（chayuan-client 现状） | 现成 |

### 6.3 后端数据源

- L0/L1/L2 数据 = ChaCMD Orchestrator 聚合（已实现的 P0 骨架：注册表 + 事件总线 ingest + Job/Task 状态机 + workspace）+ 察元 `/api/v1/external-agents/{id}/status` + 察元 `/v1/providers`（网关健康）。
- 事件总线主题：心跳 / 任务进度 / A2A / 外部数据 / 越权审计 —— 同一条脊柱，大屏各 widget 订阅各自主题。

---

## 7. 分期落地

| 阶段 | 内容 | 依赖 |
|---|---|---|
| **v1（骨架 + 星群总览）** | apps/chacmd 壳 + BrandConfig 注入 seam；L0 星群皮肤（主机/工位/员工节点 + 状态灯 + 头顶 emoji 气泡）；事件总线接入 + 历史插值平滑；顶栏 KPI；驾驶舱/投墙双模式；开机 kiosk 自启 | P0 后端骨架（已实现）；察元前端三 seam（§3.7）待补 |
| **v2（任务下钻 L1）** | 任务编排视图（reactflow 扇出树 + 活动时间线 + 角色卡 + group-chat 消息流）；新建任务向导（§6.16）；HITL Intent Preview + 自主度钮 | 编排引擎（§6.7）落地 |
| **v3（员工现场 L2 + 治理）** | 员工多 tab 现场 + 免密开桌面 iframe；成本/告警队列；审计 | 免密网关(#8)、真 usage 计量 |
| **v4（城市皮肤 + 富化）** | L0 城市皮肤（deck.gl+Cesium）；timelapse 回放；投墙多视图轮播 | 稳定后增强 |

**v1 验收**：开机自启全屏，星群里能看到已注册工位/员工节点、状态灯随事件总线实时变、员工头顶 emoji 显示当前动作、点节点弹员工卡、顶栏 KPI 实时刷新，动画平滑不卡。

---

## 附：业界调研证据链接（精选）

- 本体/沙箱：E2B、Modal、Daytona（"给每个 agent 一台电脑"）、OpenHands（agent-as-stateless-config + event-sourcing）、Cloudflare Agents、AWS Bedrock AgentCore（Identity vs Runtime）、K8s Agent Sandbox。
- 框架本体：CrewAI（role/goal/backstory + Skill 一等 + Task 绑单 agent）、MetaGPT/ChatDev（软件公司拟人）、AutoGen、LangGraph、OpenAI Agents SDK（handoff vs as_tool）。
- 编排/任务：Anthropic multi-agent research（lead agent，任务四要素）、AWS Bedrock multi-agent（SUPERVISOR vs SUPERVISOR_ROUTER）、Google ADK（Sequential/Parallel/Loop、output_key、AgentTool）、LangGraph（supervisor / Command(goto)）。
- 可视化/数字员工：LangSmith/Langfuse/AgentOps（trace 树 + Session Waterfall + Agent Selector）、LangGraph Studio、斯坦福 Smallville（emoji 头顶气泡 + Phaser）、AI Town（PixiJS + tick 插值）、3d-force-graph、deck.gl+Cesium、11x/Artisan/Ema/Devin（数字员工叙事）、Relevance AI Workforce Canvas（org chart）、AG-UI 协议、Devin/Manus 下钻面板、Tufte chartjunk / NOC 告警疲劳（3D 坑）。
