# ChaCMD 任务调度器 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:test-driven-development。逐项 pytest TDD，绿再提交。

**Goal:** 在 `chacmd/scheduler/` 实现 24×7 无人值守派单调度器：ready 队列+优先级取单+并发/互斥锁+九步工单状态机（核心）、三级成本熔断+回炉重试+连败隔离（护栏）、模型分层+涉密强制路由（路由）、对接反连网关/事件总线/CI webhook（对接层）。

**Architecture:** chacmd 后端新增 scheduler 决策层，复用现有 dispatcher/DAG/state/eventbus/bridge_gateway（见 `docs/superpowers/specs/2026-07-06-scheduler-placement-analysis.md`）。纯 Python，本环境 pytest TDD 可验；耐久工作流引擎抽 SPI 留 Temporal 口（P2）。

**测试环境:** scratchpad cvenv py3.11；`cd /work/chayuan-desktop/chacmd && pytest -q`。手写 Fake，无 unittest.mock。新增测试落 `tests/test_scheduler_*.py`。

**工作目录:** `/work/chayuan-desktop/chacmd`（只 add chacmd 内文件）。

---

## 组 1 · 调度核心

### Task 1 · 九步工单状态机
`chacmd/scheduler/workorder.py` + `tests/test_scheduler_workorder.py`
- WorkOrderState 九步（ready/assigned/in_progress/ci_passed/reviewed/merged/staging/canary/released）+ blocked/cancelled；转移表 + 回炉(→in_progress)/打回/等人。
- WorkOrder dataclass：id/code/priority(P0-P3)/repo/touches/classification/retries。

### Task 2 · ready 队列 + 优先级取单 + 并发/互斥锁
`chacmd/scheduler/queue.py` + test
- `next_dispatchable(orders, inflight)`：从 ready 单按 P0>P1>P2>P3 取，跳过违反并发（同仓≤2）/互斥（touches 交集在途）的单。

## 组 2 · 成本护栏

### Task 3 · 三级熔断 + 回炉 + 连败隔离
`chacmd/scheduler/guardrails.py` + test
- 三级：单任务 $8→挂起；单晚 $200→停派；月度触顶→暂停。`circuit_state(spend)`。
- 回炉：retries<3 → in_progress + 保留上下文；≥3 → blocked。
- 连败隔离：容器连败≥N → 隔离出可用池。

## 组 3 · 模型路由 + 涉密

### Task 4 · 分层路由 + classification 拦截
`chacmd/scheduler/routing.py` + test
- 模型档位：默认 Sonnet；连败 2 次升 Opus（带失败上下文）。
- 涉密：classification=secret → 不派 DMZ、强制本地 vLLM；否则走 LiteLLM 分层。

## 组 4 · 对接层

### Task 5 · CI/GitLab webhook 事件源 → 状态流转
`chacmd/scheduler/webhook.py` + test
- 归一化 GitLab/CI 事件（mr_opened/ci_passed/ci_failed/review_approved/review_rejected）→ 工单状态转移动作。

### Task 6 · 调度循环 + 任务卡↔Job 映射（对接 dispatcher/gateway/eventbus）
`chacmd/scheduler/loop.py` + test
- `SchedulerTick`：取 next_dispatchable → 过护栏/路由 → 经 dispatcher 派活（复用反连网关）→ 工单置 assigned；Fake dispatcher 验证编排，真派活留冒烟。

---

## Self-Review
- 覆盖用户四选组 + 对接层；耐久引擎抽 SPI 留 Temporal（P2）不本轮引入。
- 复用而非重造：dispatcher/DAG/state/eventbus/gateway 已有，scheduler 只加决策层。
- 忠于文档：九步/三级熔断阈值/回炉3轮/涉密红线/同仓≤2 均照 work-model 文档。
