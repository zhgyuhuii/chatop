# ChaCMD 指挥大屏 SKU（apps/chacmd + packages/chacmd-features）Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:executing-plans。Steps 用 checkbox。

**Goal:** 在 chayuan-client 建 ChaCMD SKU：`packages/chacmd-features`（大屏 UI + SSE 流消费 + /command 路由）+ `apps/chacmd`（Tauri 壳，注入 brand，复用察元基座与首启门），大屏 L0 消费后端 `/api/v1/stream`。

**Architecture:** 经已建的 3 注入 seam（brand.routeExtensions + landing）注入 `/command` 大屏为 ChaCMD 主页；基座零改、首启 DB 门天然复用（§3.7 + 首启调研）。大屏数据 = `useCommandStream`(EventSource `/api/v1/stream`) → 纯 reducer `applyStreamEvent` 累积员工/节点态 → 渲染。

**Tech Stack:** TypeScript/React19 + TanStack Router（基座）+ EventSource(SSE) + 3d-force-graph(three) L0；vitest。

**环境边界（诚实标注）**：本 headless 环境**可验证** = reducer/route/brand 的 vitest 单测 + typecheck；**不可验证（需用户机器）** = Tauri 构建(需 Rust)、3D GPU 渲染、运行时首启/SSE 联调。

**工作目录:** `/work/chayuan-desktop/chayuan-client`（分支 main，脏工作树——只路径限定 add 自己的新文件）。

---

## Task 1: packages/chacmd-features 包骨架 + SSE 流 reducer（可验证核心）

**Files:**
- Create: `packages/chacmd-features/package.json`, `tsconfig.json`, `src/index.ts`
- Create: `packages/chacmd-features/src/stream/streamReducer.ts` + `.test.ts`

- [ ] **Step 1: 建包 + 纯 reducer 失败测试**（reducer 累积 SSE 事件为员工态）
- [ ] **Step 2: pnpm install 链接工作区 + 跑测试确认失败**
- [ ] **Step 3: 实现 `applyStreamEvent(state, event)`**（started→员工上线/running，succeeded/failed→终态，进度累积）
- [ ] **Step 4: 跑测试确认通过**
- [ ] **Step 5: 提交**

## Task 2: /command 路由 + chacmdBrand（seam 注入，可验证）

**Files:**
- Create: `packages/chacmd-features/src/route.tsx`（`commandRoute: RouteEntry` + `chacmdBrand: BrandConfig`）
- Test: 在基座 `page-registry.test.ts` 加"注入 chacmdBrand 后 /command 命中"

- [ ] TDD：setActiveBrand(chacmdBrand) 后 resolveRoute('/command') 命中；landing='/command'。

## Task 3: useCommandStream 钩子 + CommandDashboard 组件（jsdom 轻测 + smoke）

**Files:**
- Create: `packages/chacmd-features/src/stream/useCommandStream.ts`
- Create: `packages/chacmd-features/src/dashboard/CommandDashboard.tsx`（L0：先 2D 节点栅格，状态灯 + emoji 气泡；3D 星群作增强层，见 Task 5）

- [ ] TDD：hook 用 reducer；组件渲染 smoke（jsdom）。

## Task 4: apps/chacmd Tauri 壳（脚手架，Tauri 构建需用户机器）

**Files:**
- Create: `apps/chacmd/{package.json, index.html, vite.config.ts, tsconfig.json, src/main.tsx, src-tauri/*}`（照抄 apps/desktop，改 productName=ChaCMD 指挥台、identifier、注入 `brand: chacmdBrand`，保持 `thinClient=false`+sidecar→单机 sqlite）

- [ ] 脚手架文件齐；`pnpm --filter @chayuan/chacmd typecheck` 过（Tauri build 需用户机器）。

## Task 5: L0 3D 星群增强（3d-force-graph，需 GPU/用户机器渲染）

**Files:**
- Modify: `packages/chacmd-features` 加 `dashboard/StarfieldL0.tsx`（3d-force-graph）+ 装 three/3d-force-graph
- CommandDashboard 用 3D 皮肤（2D 作降级/测试）

- [ ] 装依赖 + typecheck 过；视觉验证需用户机器。

---

## Self-Review / 边界
- 可验证核心（Task 1/2 + Task 3 逻辑）走 vitest；Tauri/3D/运行时（Task 4/5 渲染 + 首启联调）需用户机器，已标注。
- 首启门复用：apps/chacmd 保持 thinClient=false+sidecar（单机 sqlite），/command 经 brand.routeExtensions 可达，不绕首启门。
