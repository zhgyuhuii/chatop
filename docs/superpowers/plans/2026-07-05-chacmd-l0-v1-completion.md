# ChaCMD 指挥大屏 L0 v1 验收补全 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:executing-plans。Steps 用 checkbox。

**Goal:** 补全指挥大屏 L0 v1 验收（`command-dashboard-design §7`）尚缺项：顶栏 KPI、点节点弹员工卡（§3.1 Agent Card）、驾驶舱/投墙双模式（§2.4）、AI Town 插值平滑（§4）。落点 `packages/chacmd-features`。

**Architecture:** 纯派生逻辑（KPI、插值）走 TDD；员工卡/KPI 条/模式切换为组件（typecheck 验证，本仓约定不单测组件）。StarfieldL0 加 `onSelect` 回调；CommandDashboard 持 `selected`/`mode` 态编排。

**Tech Stack:** TS/React19 + 3d-force-graph（已装）+ vitest。

**环境边界**：可验证 = KPI/插值 vitest + typecheck。需用户机器 = 3D 节点点击视觉、kiosk 开机自启（Tauri）、ChatComposer 并入驾驶舱（v2）。

**工作目录:** `/work/chayuan-desktop/chayuan-client`（main，脏树——只路径限定 add 自己文件）。

---

## Task 1: KPI 派生（纯逻辑 TDD）

**Files:**
- Create: `packages/chacmd-features/src/dashboard/kpis.ts` + `kpis.test.ts`

- [ ] **Step 1: 写失败测试** `computeKpis(state)` → {total,running,waiting,succeeded,failed,interrupted,successRate}
- [ ] **Step 2: 跑测试确认失败**
- [ ] **Step 3: 实现 computeKpis**（successRate = succeeded/(succeeded+failed)，无则 0）
- [ ] **Step 4: 跑测试确认通过 + typecheck**
- [ ] **Step 5: 提交**

## Task 2: KpiBar 组件（顶栏）

**Files:**
- Create: `packages/chacmd-features/src/dashboard/KpiBar.tsx`

- [ ] KpiBar 接 DashboardKpis，渲染 6 指标 + 成功率；深色指挥风；typecheck。

## Task 3: AgentCard 员工卡（§3.1）

**Files:**
- Create: `packages/chacmd-features/src/dashboard/AgentCard.tsx`

- [ ] AgentCard 接 AgentState + onClose；渲染身份(昵称/工位)+状态灯+当前步+emoji+动作按钮(免密开桌面/编辑契约/查trace——v1 disabled 占位)。richer 字段(goal/owner/token/cost)标"待后端"。typecheck。

## Task 4: 节点点击选中 + 员工卡面板接线

**Files:**
- Modify: `packages/chacmd-features/src/dashboard/StarfieldL0.tsx`（加 `onSelect?:(id:string)=>void` → graph.onNodeClick）
- Modify: `packages/chacmd-features/src/dashboard/CommandDashboard.tsx`（selected 态 + AgentCard 侧板 + KpiBar 顶栏）

- [ ] StarfieldL0 onNodeClick → onSelect(node.id)；CommandDashboard 持 selected，渲染 KpiBar + 选中时 AgentCard 侧板；typecheck。

## Task 5: 双模式（驾驶舱/投墙 kiosk）

**Files:**
- Modify: `CommandDashboard.tsx`（mode: 'cockpit'|'kiosk'，默认 cockpit；kiosk 隐侧板、放大 KPI、L0 满屏；右上角切换钮；`?mode=kiosk` 初始）

- [ ] mode 态 + 布局分档 + 切换钮；typecheck。

## Task 6: AI Town 插值平滑（§4，纯逻辑 TDD）

**Files:**
- Create: `packages/chacmd-features/src/scene/interpolate.ts` + `interpolate.test.ts`

- [ ] `lerp(a,b,t)` + `sampleHistorical(buffer, now)`（当前值+历史缓冲+线性插值，AI Town useHistoricalValue 手法）；TDD 边界(空缓冲/单点/超范围 clamp)。为后续节点位置/指标平滑铺底。typecheck + vitest。

---

## Self-Review / 边界
- v1 验收覆盖：KPI(T1/2) + 员工卡点选(T3/4) + 双模式(T5) + 平滑地基(T6)；状态灯/emoji/节点已在上轮。
- 未覆盖（需用户机器/v2）：kiosk 开机自启(Tauri src-tauri)、3D 点击视觉、ChatComposer 驾驶舱并入、richer AgentCard 字段(需后端补事件字段)。
- 忠于设计：员工卡字段照 §3.1；双模式照 §2.4；插值照 §4；不臆造。
