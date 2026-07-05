# ChaCMD 落点与需求总纲（修订版·单一真源）

- 日期：2026-07-05
- 状态：**待用户确认**（确认后据此设计→计划→实现）
- 目的：纠正此前的落点误解，按 §3.5–3.9 已定架构，把"每个组件在哪个仓、现状如何、还差什么"一次性理清，作为后续所有 ChaCMD 工作的落点真源。
- 前置真源：`2026-06-30-chacmd-design.md`（§3.5–3.9 母体/双 SKU/前端/命令/形态）、`2026-07-01-chacmd-requirements.md`（需求 SRS）、`2026-07-02-chacmd-command-dashboard-design.md`（大屏设计）。

---

## 0. 架构真相（一句话）

**ChaCMD = 察元（chayuan-desktop 母体）+ 一层"跨容器横向调度"增量，作为 chayuan-desktop monorepo 内的一个 SKU。** 察元 SKU 与 ChaCMD SKU 同一份代码、两档构建，**只差**：构建/开发命令、构建产出物、docker 镜像名、主页/进入模式（大屏）。**chatop 仓只负责 KasmVNC 子容器镜像（工位/agent 工作站）**，不承载指挥系统。

## 1. 三仓职责边界（钉死）

| 仓 | 职责 | 含什么 |
|---|---|---|
| **`/work/chayuan-desktop`**（母体 monorepo，git main） | **指挥系统全部功能** | `chayuan-server/`（服务端：模型网关/RBAC/kb-query/agent 框架）+ `chayuan-client/`（客户端：察元 UI 基座 + 新增 ChaCMD SKU）+ **新增 `chacmd/`**（后端横向调度增量）+ 两档构建 |
| **`/work/chatop`**（本仓，git main） | **KasmVNC 子容器镜像** | Dockerfile.base/app-manager/agent-bridge/**chacmd 后端骨架(暂居，待迁)** —— 工位镜像 + agent 反连客户端 |
| 子容器运行时 | agent 工作站 | chatop-ai 镜像实例，覆盖网反连母体 |

> **依赖单向**：`chacmd/` → 察元；察元核心（chayuan-server/client）**永不** import chacmd。构建隔离 + `CHACMD_ENABLED` 默认关，保证察元 SKU 逐字节纯净可独立部署（§3.6 三条硬约束）。

## 2. 全局落点地图（每个组件的正确家）

| 组件 | 正确落点 | 现状 | 处置 |
|---|---|---|---|
| **ChaCMD 后端 Orchestrator**（薄实时派活核心，`python -m chacmd.cli start`，端口 8100） | `/work/chayuan-desktop/chacmd/`（§3.6/§3.8/§10.2） | ❌ **误建在 `/work/chatop/chacmd`**（P0 已实现 97 tests） | **决策点 D1：迁到 chayuan-desktop/chacmd/**（代码几乎不用改——本就按 `ChayuanClient` 全 HTTP 抽象写，§3.9 形态 B/C 都靠换 URL） |
| **anthropic `/v1/messages` shim** | `chacmd/anthropic-shim/`（§3.6 拓扑） | ✅ 已实现（在 chatop/chacmd 内 shim/） | 随后端一起迁 |
| **connectors**（claude-code/codex adapter，上游进 chayuan-server，flag 关） | `chayuan-server` agent_connector（上游化+flag，§3.6.C/§3.5.C） | ❌ 未做（P0 用 FakeAgentAdapter + 独立 OpenHandsAdapter） | P1：按 §3.6 Phase0 上游加 adapter（~90 行/个 + flag 关） |
| **指挥大屏前端**（大屏 L0/L1/L2 + BrandConfig 主页） | `chayuan-desktop/chayuan-client`：新增 `apps/chacmd` + `packages/chacmd-features`（§3.7） | ❌ 未建（绿地） | **本轮目标**（F 切片）：先补 3 注入 seam + apps/chacmd 壳 + L0 星群 |
| **员工视图 / 新建任务** | 同上，chacmd-features 内 | ❌ 未建 | F 切片后续（v2） |
| **模型网关/RBAC/kb-query/知识库** | 察元 chayuan-server **现成** | ✅ 母体已有 | 复用（经 ChayuanClient 防腐层），不重建 |
| **构建 flavor**（build-chacmd / --chacmd） | chayuan-desktop `build-desktop.sh` 加档（§3.6） | ❌ 未做 | 打包阶段做 |

## 3. P0 现状盘点（已实现，但在 chatop/chacmd）

已实现并合入 `/work/chatop` main（97 tests，见 `chacmd/docs/chacmd-m4-acceptance.md`）：
- 10 接口抽象 I1–I10（防腐层，含 `ChayuanClient` 全 HTTP）、反向 WS 网关、租约存活、@昵称派活、事件摄取、Job/Task 状态机（含 pending_approval）、per-job 卷原子 done-marker、Task-as-API code 端点。
- M3/M4：NatsEventBus、Anthropic shim、审批门、per-job 预算 kill、DockerSandbox 加固、OpenHandsAdapter、OTel、Provisioner。
- 察元契约（实证）：whoami `/openapi/v1/whoami`、网关 `/v1/chat/completions`；察元无资源级 authz 端点（scope-based）→ container-dispatch RBAC 归 ChaCMD 本地域。

**问题**：落点是 chatop 而非 chayuan-desktop。因全按 `ChayuanClient` HTTP 抽象写，**迁仓成本低**（移目录 + 改 import 根 + 构建接线），不涉及重写。

## 4. 需求全量重列（按落点 + 状态 + 优先级）

> 编号沿用 SRS。状态：✅已实现 / 🟡骨架-待增强 / ❌未做。落点：母体后端(BE)=chayuan-desktop/chacmd 或 chayuan-server；前端(FE)=chayuan-client SKU；复用=察元现成。

### 后端 / 调度核心（chayuan-desktop/chacmd）
| # | 需求 | 状态 | 优先级 |
|---|---|---|---|
| #5 统一调度对话框（@昵称直派 / NL 路由） | 🟡 直派✅ / NL 路由❌ | P0→P1 |
| #11 多智能体串并行编排（复杂 DAG/回环/子编排） | 🟡 线性✅ / 复杂 DAG❌ | P0→P1 |
| #2/#3 容器供给 + 昵称寻址 | 🟡 Provisioner✅ / 真起容器❌ | P1 |
| #13 容灾自愈（挂了重建/改派 + reconcile 单活） | ❌ | P1→P2 |
| #12 A2A 直连（卷直传 + 总线旁路审计） | ❌ | P3 |
| #18 角色契约 Charter（触发/交接） | 🟡 system_prompt 注入✅ / trigger·handoff❌ | P0→P1 |
| #15 外部数据接入/感知 | ❌ | P3 |
| #20 Task-as-API 完整（API Key/HMAC/OpenAPI 生成） | 🟡 code 端点✅ / 完整契约❌ | P1 |
| #21 服务发现+配置中心（Nacos 可插拔 SPI） | 🟡 SPI 抽象✅ / Nacos❌ | P1 |
| #16 模型网关（Anthropic shim 缺口） | ✅ shim / 网关复用察元 | P0 |
| 无 IP 寻址 | ✅ | P0 |
| NFR-S1 Postgres 状态外置 / NFR-T1 RLS | 🟡 方言无关✅ / 真 Postgres+RLS❌ | P1 |
| NFR-P3 NATS / NFR-C1 预算 / NFR-SEC 沙箱 / NFR-O1 OTel | ✅ | P0 |

### 上游察元改动（chayuan-server，上游化+flag）
| # | 需求 | 状态 | 优先级 |
|---|---|---|---|
| connectors 补 claude-code/codex | ❌（Phase0 唯一需上游改码项，~90 行/个） | P1 |
| #14 RBAC 资源维度扩到容器/agent/视图 | ❌（察元有 kb grant，需扩资源类型） | P1 |
| #19 知识源范围授权（按 ku_ids 下发 scope） | ❌ | P1 |

### 前端 SKU（chayuan-desktop/chayuan-client：apps/chacmd + packages/chacmd-features）
| # | 需求 | 状态 | 优先级 |
|---|---|---|---|
| 3 注入 seam（BrandConfig/homeComponent+routeExtensions/按 SKU 构建） | ❌（Explore 确认基座无此 seam，待补） | **本轮** |
| 指挥大屏 L0 星群总览（3D + 状态灯 + emoji 气泡 + KPI + 双模式 + kiosk） | ❌ | **本轮 v1** |
| L1 任务编排（reactflow 扇出树 + 时间线 + 角色卡）| ❌ | v2 |
| L2 员工现场（Devin 多 tab + 免密开桌面 iframe #8） | ❌ | v3 |
| 员工视图 / 新建任务向导 | ❌ | v2 |
| 城市皮肤（deck.gl+Cesium） | ❌ | v4 |

### 复用察元现成（不重建）
模型网关 25+ 厂商 + 本地 · kb-query 五类源 · RBAC/org/审计底座 · chat/graph supervisor · 本地+网络双部署。

## 5. 本轮目标：指挥大屏 v1（落点已纠正）

**落点**：`/work/chayuan-desktop/chayuan-client` 新增 `apps/chacmd`（Tauri SKU 壳）+ `packages/chacmd-features`（大屏 UI），复用 `@chayuan/app`(基座) + `@chayuan/ui` + `@chayuan/transport`(SSE) + ChatComposer + reactflow。

**v1 三个前置依赖（Explore + 后端核实，均需先补）**：
1. **察元基座 3 注入 seam**（§3.7）：BrandConfig / homeComponent+routeExtensions / 按 SKU 构建 —— 基座现无，需在 `packages/app` 补（仿 registerToolCard 注册器模式）+ 3 项小重构。
2. **3D 依赖**：three + 3d-force-graph（chayuan-client 未装，reactflow/zustand 已装）。
3. **后端浏览器向事件流**：ChaCMD 需新增 SSE 端点（`net.sse` 消费，察元实时通道是 SSE 无 WS），把 EventBus 桥接到浏览器。现有 BridgeGateway 仅 agent 反连用。

**v1 验收（§7）**：apps/chacmd 开机自启全屏，星群里见已注册工位/员工节点，状态灯随事件总线实时变，员工头顶 emoji 显当前动作，点节点弹员工卡，顶栏 KPI 实时刷新，动画平滑不卡。

## 6. 待用户确认的决策

- **D1 · P0 后端迁仓**：把 `/work/chatop/chacmd`（97 tests）迁到 `/work/chayuan-desktop/chacmd/`？（推荐**是**，对齐 §3.6；迁移成本低。或暂缓、先做大屏、后端稍后迁。）
- **D2 · 前端目标仓确认**：大屏建在 `/work/chayuan-desktop/chayuan-client`（母体那份），非独立 `/work/chayuan-client`。（默认按此。）
- **D3 · 文档落点**：ChaCMD 设计/需求文档现在 chatop/docs，是否随后端一并迁到 chayuan-desktop/docs？（默认暂留，后续统一迁。）
- **D4 · 大屏 v1 起点**：先补察元 3 注入 seam（正规、后续视图受益）还是先 fork 薄壳快速出画面？（依 §3.7 推荐**补 seam**，因这是双 SKU 的正规地基，员工视图/新建任务都要用。）

## 7. 下一步（确认后）

① 据 D1–D4 定案 → ② 对"指挥大屏 v1"走设计细化（补齐 seam 契约 + 后端 SSE 契约 + 大屏组件分解）→ ③ writing-plans 出逐项 TDD 计划 → ④ 逐项实现。
