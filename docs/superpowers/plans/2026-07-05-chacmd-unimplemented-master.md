# ChaCMD 未实现需求 — 总实现计划（分优先级 + 可验证性）

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:executing-plans / test-driven-development。逐项 TDD，pytest 绿再提交。

**Goal:** 把 #1–#21 中未实现/半实现的产物按优先级 + 依赖顺序逐项落地。纯逻辑走 pytest TDD（本环境可验证）；需基建项用 Fake + 契约单测锁行为、留运行时冒烟。

**测试环境:** scratchpad py3.11 venv `…/scratchpad/cvenv/bin/python`，`cd /work/chayuan-desktop/chacmd && pytest -q`。基线 **106 passed**。新增测试落 `tests/test_*.py`（扁平 1:1），手写 Fake（无 unittest.mock），DI 经 `container.build_container(use_fakes=)`。

**工作目录:** `/work/chayuan-desktop/chacmd`（分支 worktree-chacmd-p0-backend；只 add chacmd 内文件）。

---

## A. 纯逻辑批（本环境 TDD 可完整验证）—— 按依赖排序优先做

### Task 1 · #11 DAG 编排引擎
**Files:** Create `chacmd/orchestrator/dag.py` + `tests/test_dag.py`
- DAG 模型（node=task, edge=依赖）+ 拓扑排序 + 就绪集计算；并行扇出/汇聚；条件路由（edge.condition）；有界回环（max_loops 防死循环）；sub-DAG 展开。
- 纯逻辑：给定 DAG + 各 node 结果，`next_ready(state)` 返回可跑集；`is_complete`/`is_failed`。
- 测试：串行链、并行扇出+汇聚 barrier、条件分支、回环达上限终止、菱形依赖。

### Task 2 · #14 资源级 RBAC 本地判定
**Files:** Create `chacmd/interfaces/rbac.py`（`RbacPolicy`：主体×资源(container/agent/view/kb)×动作(view/dispatch/open/config)）+ `tests/test_rbac.py`；`dispatcher` 接入本地 check（替 FakeChayuanClient 恒 allow 的盲区）
- 纯判定矩阵 + tenant_id(部门) 隔离过滤；deny 优先；通配符资源。
- 测试：无权资源拒、越权 dispatch 拒、跨部门拒、admin 全通。

### Task 3 · #18 角色契约 Charter + trigger + handoff
**Files:** Create `chacmd/domain/charter.py` + `tests/test_charter.py`
- Charter 声明式实体（identity/goal/system_prompt/skills/knowledge_scope/triggers/handoffs）。
- `render_system_prompt(charter)`；`match_triggers(charter, event)`→触发的动作；`resolve_handoff(charter, outcome)`→下一 nickname。
- 测试：prompt 注入含 goal/scope、trigger 命中/不命中、handoff 路由到指定角色、无 handoff 回 supervisor。

### Task 4 · #5 NL 路由 intent detection + 快慢双路
**Files:** Create `chacmd/orchestrator/router.py` + `tests/test_router.py`
- 快路：@昵称正则直取（已有，抽到 router）；规则分类（关键词→角色）；慢路 fallback：`chayuan.chat_completions` 冷启 NL 路由（mock 验证 prompt 构造 + 解析）。
- `route(text, registry)`→目标 nickname + 置信度 + 路径(fast/rule/llm)。
- 测试：@昵称走 fast、关键词命中 rule、未命中走 llm（mock）、多候选取最高置信。

### Task 5 · #19 知识源范围授权 scope filter
**Files:** Create `chacmd/orchestrator/kb_scope.py` + `tests/test_kb_scope.py`
- `filter_ku_ids(subject_grants, requested_ku_ids)`→过滤越界库；按类型(doc/src/office)+具体库粒度；返回准入集 + 被剔除集（诊断）。
- dispatcher 调 kb_query 前先过 scope。
- 测试：越界库剔除、类型级授权、空授权全剔、诊断含被剔理由。

### Task 6 · #20 Task-as-API 安全（HMAC/APIKey/幂等/OpenAPI）
**Files:** Create `chacmd/api/taskapi.py` + `tests/test_taskapi_security.py`
- per-caller API Key 校验（部门级）；webhook HMAC 签名/验签（复用 `crypto.StdCrypto`）；幂等键去重（存储层 seen-set）；`app.openapi()` 暴露任务契约；外部输入信任分级降权标记。
- 测试：错 Key 拒、HMAC 篡改验签失败、同幂等键第二次返首次结果、OpenAPI 含 code 端点。

### Task 7 · #13 容灾 reconcile 决策 + leader/lease 单活
**Files:** Create `chacmd/orchestrator/reconcile.py` + `tests/test_reconcile.py`（Fake 时钟）
- reconcile 决策：期望态 vs 实况 diff→重建/改派动作列表；死容器 Task→interrupted（承认至少一次+去重）；leader election via lease（防多实例双拉替身，NFR-S2）。
- 纯决策逻辑（真重建需 Docker，留冒烟）。
- 测试：死 nickname→重建动作、在途 Task→interrupted、非 leader 不动作、lease 过期换 leader。

### Task 8 · #21 Nacos provider 契约
**Files:** Create `chacmd/interfaces/nacos_registry.py` + `tests/test_nacos_registry.py`（mock httpx）
- `NacosServiceRegistry`/`NacosConfigSource` 实现 I4 SPI（register/deregister/discover/get_config）；后台开关（config 选 内置|nacos）。契约/映射逻辑单测（真注册需 Nacos，留冒烟）。
- 测试：register 构造正确 Nacos REST 调用、discover 解析实例列表、切回内置仍可用。

### Task 9 · #7 中心语义汇总
**Files:** Create `chacmd/orchestrator/synthesize.py` + `tests/test_synthesize.py`
- 汇总多 Task 产物（读卷 output）→ `chayuan.chat_completions` 生成回大屏摘要（mock）；跨 job 卷引用读（成果共享）。
- 测试：多产物拼装 prompt、mock 返回摘要、缺产物优雅降级。

## B. 供给/配置批（Fake 可验证，真起容器需基建）

### Task 10 · #2/#10 供给参数化 + 配置中心 CRUD
**Files:** Modify `chacmd/orchestrator/provisioner.py`；Create `chacmd/orchestrator/config_center.py` + tests
- 供给参数化：端口/用户名/密码/权限/装应用/工作目录 bind（`$HOME/<code>`→`/workspace/<job_id>`）；配置中心 CRUD（每 agent 模型/Key/BaseURL）+ 下发 env + 热更新事件。
- Fake sandbox 验证参数透传；真起容器留冒烟。

## C. 需基建批（本轮出接口/契约 + Fake 单测；端到端需用户机器）

- **#2 真起容器 / SEC1 socket 不可见真验证**（Docker rootless）
- **#13 跨机 reconcile / 替身真重建 / 在途重放**（多容器+网络）
- **#14 Postgres RLS policy 真过滤**（Postgres）
- **#6/#21 NATS JetStream 真投递 / Nacos 真注册 + Java OpenFeign**（NATS/Nacos/Java）
- **#8 免密 KasmVNC 反代**（凭据金库 I9 CredentialVault SPI——gap 分析发现 I9 未落地，先补 SPI 抽象）
- **#16 真调国内/本地模型**（察元实例）

## D. 前端批（chayuan-client SKU，另仓 pnpm/vitest）

- **L1 任务编排视图**（reactflow 扇出树 + 时间线 + 角色卡 + group-chat）
- **新建任务向导**（§6.16：goal 必填 + NL 草稿推断表单 + 创建 agent/派活分离）
- **员工视图**（状态/成果/工作记录）
- **richer AgentCard 字段**（需后端 Task 3/9 补事件字段后接）

## E. 大工程/信创（列入路线，不本轮实现）

- #12 A2A 直连(P3)、#15 外部数据接入(P3)、#9 装应用技能体系(P1 需供应链)、NFR-R2 Temporal(P2)、NFR-S1 active-active(P2)、NFR-S3 Nomad(P2)、跨机 K8s、GX1-6 国产化(达梦/麒麟/昇腾/国密/三员分立/内容安全)。

---

## 执行顺序 & 检查点
A 批（Task 1–9）纯逻辑最先、按序 TDD，每 Task pytest 绿即提交；每 3 个 Task 给用户看一次。B/C/D 视进度续。E 批仅路线不实现。

## Self-Review
- 覆盖 gap 分析 ③ 全部 ❌/🟡 逻辑缺口；#3/#4/#6/#16/#17 已✅不列。
- I9 CredentialVault SPI 缺口（gap 分析发现）纳入 C 批 #8 前置。
- 忠于需求编号 + 验收要点，不臆造范围。
