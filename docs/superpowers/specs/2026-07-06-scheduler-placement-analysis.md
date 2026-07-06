# 任务调度器落点架构分析报告

- 日期：2026-07-06
- 触发：用户质疑"为什么把任务调度器放在 chacmd？chayuan-desktop 调用 chatop 接口、chatop 执行任务"——要求先深度分析落点（chayuan-desktop vs chatop）+ Temporal 引入优缺点，再动手。
- 依据：`/work/work-model` 三份文档（统御AI桌面建设方案/24×7 白皮书/网络隔离说明）+ 代码事实（chatop/agent-bridge、chayuan-desktop/chacmd）+ 既有需求 NFR-R2。

---

## 1. 三仓真实角色（代码事实，非臆测）

| 仓 | 角色 | 代码证据 |
|---|---|---|
| **`/work/chatop`** | **数字员工/工位容器镜像 = 执行侧（每容器）** | `agent-bridge/main.py` docstring：「子容器 resident service: **reverse-connect to gateway, register by nickname, heartbeat**」；`connect_and_register` → `websockets.connect(url/bridge)` + `register`。另有 app-manager/caddy/novnc/Dockerfile = KasmVNC 云桌面镜像组件。 |
| **`/work/chayuan-desktop/chacmd`** | **中央指挥后端 = 编排/调度侧（中央）** | `gateway/bridge_gateway.py`（agent-bridge 反连的**服务端**，nickname→ws 会话表）+ `orchestrator/dispatcher.py`（派活）+ `orchestrator/dag.py`（依赖编排）+ `domain/state.py`（Job-Task 状态机）+ `interfaces/eventbus.py`（事件回传）+ lease/reconcile/budget/rbac。 |
| 接缝 | **agent-bridge 反向 WS** | chatop 容器内的 agent-bridge **client** ⇄ chacmd 的 bridge_gateway **server**。容器主动反连（NAT/隔离友好），中央经既有隧道下推指令。 |

> 用户的框架"chayuan-desktop 调用 chatop 接口、chatop 执行"，机制上精确说是**反向 WS**（容器反连、中央下推），但语义完全正确：**chacmd 决策+派发，chatop 执行**。

---

## 2. 核心问题：调度器该落 chayuan-desktop 还是 chatop

### 2.1 调度本质是"全局协调"函数 → 必须中央

文档里调度器要做的每一件事都需要**跨容器全局视图**：

| 调度职责 | 为何需要全局 |
|---|---|
| ready 队列按优先级取单（P0-P3）| 队列是**所有**待办卡的单一真源 |
| 并发/互斥锁（同仓 ≤2、模块 touches 互斥）| 要看**所有**在途任务才能判冲突（Redis 全局锁）|
| 三级成本熔断（$200/晚全局、月度）| 预算是**全单位聚合**，非单容器可知 |
| 连败容器隔离、健康择优派单 | 要比较**所有**容器的心跳/磁盘/连败 |
| 模型分层 + 涉密强制路由 | 按卡/仓分级做**统一**拦截与出口收口 |

单个 chatop 容器**只知道自己**。若把调度器塞进工位镜像 → 每容器各跑一个调度器、互相看不见 → 全局队列/互斥/预算无从协调 → 必然超并发、超预算、抢同仓。**架构上不成立。**

### 2.2 为什么正好落 chacmd（而非 chatop、也非另起服务）

- chacmd 已具备调度器所需的**全部底座**：反连网关（接入所有容器）、派活、DAG、事件总线、Job-Task 状态机、lease 判死、reconcile 容灾、budget 预算、rbac。调度器 = 在这些之上加"**扫队列 + 优先级 + 互斥 + 熔断 + 路由**"的**决策层**，是最小增量、零重复。
- 文档自证：白皮书 §02「ChaCMD 指挥台设计中，**第 08 节调度机制即其落地形态**」——调度器本就是 ChaCMD 的落地件，不是外挂。
- 放 chatop：要把中央网关/事件总线/全局队列全搬进工位镜像，违背"工位镜像专职"，每容器重复一套且无法全局协调（见 2.1）。
- 另起第三个独立调度服务：可行，但会**重复造 chacmd 已有的反连网关 + 事件总线 + 状态机**，不划算；且文档明确调度器=ChaCMD 落地形态。

### 2.3 澄清一个易混边界

- **"调度器在 chacmd" ≠ "调度器 = 指挥大屏 SKU"。** chacmd 是**指挥系统后端**；指挥大屏只是它的一个**前端 SKU**（apps/chacmd）。调度器是 chacmd **后端**的新模块 `chacmd/scheduler/`，与大屏 UI 无关。之所以之前 Q1 写"放 chacmd"，指的是这个后端，不是大屏。
- **chatop 仍有"执行侧的容器内调度"**：容器内单任务的 `git clone`→run→report 生命周期、seed-home 重建等，是 chatop 的活。但那是**执行**，不是**派单调度**（谁做/何时做/做哪张卡）。派单调度是中央的。二者分层不冲突。

### 2.4 落点三方案对比

| 方案 | 全局协调 | 复用底座 | 部署/维护 | 判定 |
|---|---|---|---|---|
| **A. chacmd 后端新增 scheduler（推荐）** | ✅ 天然中央 | ✅ 复用网关/派活/DAG/状态机/总线 | 随 chacmd 一体 | **采纳** |
| B. chatop 每容器内 | ❌ 各自为政无法协调 | ❌ 要把中央件搬进镜像 | 每容器一套 | 不成立 |
| C. 独立第三方调度服务 | ✅ | ❌ 重复造网关/总线 | 多一个服务 | 不划算 |

---

## 3. chacmd 引入 Temporal 的优缺点

### 3.1 优点

1. **耐久执行/断点续跑**：九步工单跨小时甚至跨天（build→CI→评审→合并→灰度），中途崩溃/重启不丢进度。直击 NFR-R2（自研引擎崩溃=重跑整 Job）。
2. **内置重试/超时/退避**：回炉重试（上限 3 轮）、步骤超时免自研。
3. **human-in-loop signal**：晨审人工签批 = Temporal signal/wait，原生支持长等待。
4. **timer/cron**：夜间 18:00–08:00 派单、cron 巡检原生。
5. **历史/可见性**：每次 workflow 执行全程可审计——契合"审计实时外送、容器内不可删改"。
6. **自研代码大减**：文档称"自研只剩三五百行规则"。

### 3.2 缺点

1. **重基建**：Temporal server + 持久层（Cassandra/PG/MySQL）+ workers 集群。在 **air-gapped 涉密 DMZ**：必须自托管 + 离线安装 + 长期运维，负担显著。
2. **与 chacmd 现有编排重叠**：DAG 引擎 + Job-Task 状态机 + reconcile 已实现（本轮已 197 tests）。引入 Temporal 要么**弃用现有**（浪费已建资产）、要么**两套编排并存**（认知/维护混乱）。
3. **学习曲线 + 约束**：workflow 确定性规则、activity/worker/task-queue 概念、workflow 版本化管理，团队 ramp-up。
4. **信创张力**：涉密 + 国产化栈（达梦/麒麟/昇腾）上跑 Temporal 增加适配与保密测评负担；又一个需过审的外来依赖。
5. **不替代派活层**：Temporal 不替代 agent-bridge 网关/昵称派活/SSE——它**坐在派活层之上**，workflow 的每一步仍要调 chacmd dispatch。即 **Temporal + chacmd 派活并存**，不是替换。真正被 Temporal 取代的只是"自研工作流状态机/重试/定时/签批"这一小层。

### 3.3 建议（与既有 NFR-R2 完全一致）

需求 NFR-R2 **早已定调**：
> "P0/P1 自研引擎锁死无耐久（崩溃=重跑整 Job）；**P2 切 Temporal/Restate/DBOS** 拿续跑/定时/幂等/human-signal。"

故建议：

- **本轮原生实现 `chacmd/scheduler/`**（复用 DAG/状态机/派活，纯 Python，本环境 TDD 可验），当下可交付可验证。
- 把"**耐久工作流引擎**"抽成 SPI（仿 chacmd 既有 I1–I10 的可插拔风格），内置实现 = 自研；**P2 当耐久/签批规模真正需要时，再切 Temporal provider**，零重写业务规则。
- 既满足当下 air-gapped 可交付/可验证，又不锁死未来——**不现在引入 Temporal**，但留好口子。

---

## 4. 结论

1. **调度器落 `/work/chayuan-desktop/chacmd` 后端新增 `chacmd/scheduler/` 模块**——因为调度是全局协调函数（队列/优先级/互斥/预算/择优跨所有容器），必须在看得见全局的中央，而 chacmd 正是中央指挥后端且已备齐底座。**chatop 仍是执行侧**（agent-bridge 容器内执行），二者经反向 WS 分层协作，不冲突。
2. **本轮不引入 Temporal**，把耐久工作流引擎抽成 SPI 留口，P2 再评估——与 NFR-R2 既有决策一致。
3. 调度器 ≠ 指挥大屏；它是 chacmd **后端**模块，大屏只是消费其状态的前端 SKU 之一。

### 落地范围（用户已选四项全做）
调度核心（ready 队列+优先级+并发/互斥锁+九步工单状态机）· 成本护栏（三级熔断+回炉3轮+连败隔离）· 模型路由+涉密（分层升档+classification 强制拦截）· 对接层（复用反连网关/事件总线 + GitLab/CI webhook 事件源 + 任务卡↔Job-Task 映射）。
