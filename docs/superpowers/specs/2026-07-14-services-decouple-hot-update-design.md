# 配置/监控/任务调度 与容器镜像解耦 + 免重打热更新 · 设计

- 日期：2026-07-14
- 状态：设计已通过对话逐节评审，待用户审文档 → writing-plans
- 范围（用户明确收窄）：**配置 / 监控 / 任务调度**三块底层服务；不动 KasmVNC 桌面基座、app-manager、caddy 等无关件。

## 0. 背景与痛点

chatop 是 KasmVNC 云桌面 Docker 镜像。当前 **station（监控/大屏常驻服务）、agent-config（配置引擎）、dashboard-web（大屏前端）** 三本体在构建期被 `COPY` 进 `/opt` 只读镜像层，改一行就得重打镜像 + 重启容器；而重打又正撞本机 7.3G 内存的 buildkit 导出 OOM 墙。目标：让这三块**运行时解耦、免重打镜像热更新**，后期能跨 OS 安装、可视化系统配置/大屏、并与 `/work/chayuan-desktop` 指挥系统（ChaCMD）连接传数据。

## 1. 前期需求与计划分析（关键认知）

### 1.1 这三块活在"两侧"，别混为一谈

| | 指挥中心侧（`chayuan-desktop/chacmd`，独立进程 :8100/:8767） | 工位镜像侧（`chatop`，痛点所在） |
|---|---|---|
| 配置 | `orchestrator/config_center.py`（下发+热更事件）+ `nacos_registry.py` | `agent-config/agentconfig/` + `station/agentcfg_api.py` + `dashboard-web/config` |
| 监控 | `observability/`(OTel) + `api/stream.py`（SSE `/api/v1/stream`） | `station/probe/` + `station/heartbeat.py` + `dashboard-web` 六区大屏（SSE `/dashboard/api/events`） |
| 调度 | `orchestrator/{dispatcher,dag,router}` + `scheduler/`（工单/队列/熔断/路由/webhook） | `station/tasks/`（工位本地任务） |
| 与镜像解耦？ | ✅ 天生解耦（跑母体进程，不在 chatop 镜像） | ❌ 全部焊在 `/opt` 只读层 |

**结论**：用户要的"免重打热更"，中心侧早已是既定且已实现的架构；痛点全在工位侧。

### 1.2 逐块现状（文档计划 vs 代码现状）
- **配置**：用户填的值（key/通道/模型）写 `~/.openclaw/openclaw.json` 用户卷、已能热改；但配置能力本体（引擎、schema、27 通道教程、模型端点表、Token 字段表）焊在 `/opt/agent-config`、`/opt/openclaw-tool`、`/usr/share/chatop`。引擎纯 stdlib、schema/数据驱动，已有 `OPENCLAW_TOOL_DIR` env 覆盖 + catalog 三级降级（含可写缓存 `~/.cache/chatop`）——现成松耦合抓手。测试 38+9+52。
- **监控**：station 六区大屏 v1 + SSE + 派活 + 动作端点 + 双入口已落地；`heartbeat.py` 是向自家官网报活（非指挥系统）。全部焊 `/opt/station`，无解耦/热更计划。
- **调度**：工位本地 `station/tasks/`（焊镜像）；中心重型 `chacmd/scheduler/` 6 模块 33+ 测试通过但**未接入运行进程**（无周期 tick/webhook HTTP/Redis 锁、阈值硬编码），且**根本不在 chatop 镜像**。chacmd 已有热更通道 `config_center.py`（发总线事件→容器热加载无需重启），但 scheduler 未接。

### 1.3 可复用抓手 + 血泪教训
1. **配置即数据**（07-11 spec）：配置已按"磁盘文件单一真源、不进代码"设计——但只覆盖配置。
2. **拆-合镜像教训**（07-04 拆 base → 07-07 合回）：拆双镜像导致盘面 footprint 翻倍+悬空层，被推翻。结论直指本设计——**免重打热更要走运行时解耦（卷/播种），不是再拆构建层**。
3. **现成播种机制** `chatop-seed-home.sh`：`WANT` 版本哨兵 + `cp -an` 幂等播种到 `chatop-home` 卷；只是三服务本体没纳入播种范围。
4. **中心热更通道** `chacmd/config_center.py` + 反连网关 `bridge_gateway.py`；但 station 侧 `bridge.py` 是设计 v2、代码未落地（agent-bridge 独立仓、无鉴权、无重连）。

### 1.4 需新决策补齐的空白
- 工位侧三本体无运行时热替换机制（全在 `/opt`）。
- 监控/调度无"解耦热更"成文计划（仅配置有 config-as-data 结论）。
- station↔chayuan-desktop 数据回传通道未实现。
- 跨 OS 交付形态未定。

## 2. 目标与非目标

**目标**
- 工位侧 station / agent-config / dashboard-web 从 `/opt` 只读层 → 卷内可热替换，改它们零镜像构建。
- 服务版本化 bundle + 验签 + 原子切换 + 健康门 + 自动回滚，可视化更新/回滚。
- station 反连 chayuan-desktop 指挥系统：上行现场数据、下行配置/服务包（复用 chacmd 现成件）。
- 调度：工位本地任务走 A 热更；中心 chacmd 调度规则接 config_center 外部化热更（两者都要）。

**非目标（本轮不做）**
- 完整原生跨 OS（脱离容器、打包 Python 运行时、替 KasmVNC）——仅保留架构前置。
- 重走构建层拆分（已被 07-07 推翻）。
- 触碰 KasmVNC 桌面基座、app-manager、caddy 等无关件。

## 3. 已定决策
- **主架构：A 打底 + B 叠加**（A=卷播种本地自足热更；B=中心下发叠加）。
- **调度口径：两者都要**（工位本地 + 中心规则外部化）。
- **本地自治铁律**：中心不可达时 A 照常工作；B 仅叠加。
- **出厂副本兜底**：镜像仍留 `/opt` 出厂 bundle，首启播种、离线自足、开机必起。

## 4. 设计详情

### 4.1 解耦机制（A 地基）
卷上开服务区（`chatop-home` 卷持久）：
```
/home/<用户>/.chatop/services/
  station/ <ver>/…   current -> <ver>
  agent-config/ <ver>/agentconfig/…  current -> <ver>
  dashboard-web/ <ver>/dist/…  current -> <ver>
  openclaw-tool/ <ver>/…  current -> <ver>   # 已有 OPENCLAW_TOOL_DIR 可指
```
- 每服务按版本存目录，`current` 软链指生效版——原子切换=改软链，回滚=软链指回旧版。
- 镜像 `/opt` 留出厂 bundle 当兜底 + 首播种源；首启用 `WANT` 哨兵 + `cp -an` 幂等播种（扩展 `chatop-seed-home.sh` 范围到服务本体）。
- `start-station.sh` 把 `PYTHONPATH`/`OPENCLAW_TOOL_DIR`/station 源/StaticFiles 四个指向从 `/opt` 改为"卷内 `current`，缺失回退 `/opt`"。

### 4.2 更新通道（A）
- **Bundle**：每服务 `.tar.gz` + `manifest.json`（`name/version/sha256/sig/min_base/needs_venv`）；`build-bundle.sh` 从源出包，不走 Docker。
- **热更边界**：纯 stdlib Python + 静态资源 = 可自由热更（占绝大多数）；引入新 pip 依赖 = `needs_venv=true`，走 venv 增量或退回重打（少数）。
- **apply 流水线**：验签（复用 `/opt/chatop/license-keys.json` HMAC）→ 兼容校验 → 解包到 `<ver>.tmp` 原子改名 → 切 `current` 软链 → **健康门**（重启 station，轮询 `/dashboard/api/system` 就绪）→ 健康则留+清旧版；失败则**自动回滚**+上报。
- **热重启**：station 本体/引擎/探针换版→重启 station 进程（`custom_startup` 里包极简 supervisor）；前端 dist 换版→无需重启；配置值→本来就热。
- **来源（A 自助）**：卷内 `.chatop/inbox/` 投递监视 / app-manager `chatop-fetch.sh`+`mirrors.conf` 市场拉取 / `chatop-update apply|rollback` CLI。
- **可视化**：updater 版本状态/一键更新/回滚做成 station 端点 + 大屏面板。

### 4.3 反连中心（B 叠加）
- **station `bridge.py`**（重写 agent-bridge 进 station asyncio 后台任务）：反连 `wss://<chacmd>:8767/bridge`（NAT 友好）；**鉴权**用持久 `hid` + HMAC 签名注册、中心签发租约 token；**断线指数退避重连**（补当前空白）。
- **上行（工位→中心）= 传数据**：bridge 订阅 station `EventHub`，按对齐 schema `kind/agent/job_id/ts/payload/container` 原样转发；中心 `EventStreamHub` 摄入→驱动指挥大屏/调度。
- **下行（中心→工位）复用现成件**：配置下发接 `config_center.py`（热应用无需重启）；服务包下发走 4.2 同一条 apply 流水线（车队级更新=中心编排、A 机制执行）；派活走 dispatcher/scheduler → `station/tasks`。
- **安全边界**：下发一律验签；中心指令**类型化/白名单，绝不 eval 任意 shell**（记忆里 openclaw GUI 命令注入点未修，反连通道尤须守）；涉密任务 scheduler 强制不派 DMZ、走本地 vLLM。

### 4.4 监控与调度落地
- **监控**：探针（`station/probe/`）与大屏面板随 station / dashboard-web bundle 热更；上行经 bridge 汇入中心 OTel/大屏。加指标=发 bundle，不重打镜像。
- **调度（两侧）**：
  - 工位本地 `station/tasks` → 随 station bundle 热更（A 覆盖）。
  - 中心 `chacmd/scheduler` → ①接入运行进程（补周期 tick / webhook HTTP / 真锁）②阈值($8/$200/$5000)、路由表外部化到 `config_center`/Nacos，改规则发总线事件热加载、免重启 chacmd。独立于 chatop 镜像，属 chacmd 轨。

### 4.5 跨 OS 门（本轮只留前置）
- 立即可用：Mac/Win 跑 Docker Desktop 同一镜像。
- 前置红利：三服务已是卷内纯 Python+静态 bundle、不绑 KasmVNC，后期可复用 chacmd 的 Tauri/PyInstaller sidecar 路子打原生 SKU 在 Mac/Win 直跑。完整原生跨 OS 是另一条大轨，本轮不做。

## 5. 错误处理
- 更新：验签不过→拒绝留当前；健康门不过→自动回滚+上报；卷无包→回退 `/opt` 出厂。开机必起。
- 中心不可达：A 本地自治照常；bridge 退避重连；鉴权失败拒连。
- 配置冲突：磁盘文件单一真源为准，中心下发合并不覆盖用户显式改动。
- `needs_venv` 遇离线：优雅拒绝+提示，不假装成功。

## 6. 测试（守 TDD）
- A：updater 单测（验签/原子切换/健康门/回滚）、播种幂等测（复用 station/agent-config 测试骨架）。
- B：bridge 测（鉴权握手/退避重连/事件 schema 往返）、配置下发 apply 测。
- 中心轨：scheduler tick 守护 + config_center 阈值外部化集成测（复用 chacmd 238 测试体系）。
- 端到端冒烟：打包→投递→apply→健康→回滚；中心下推→apply。

## 7. 分期落地
| 期 | 内容 | 仓 | 价值 |
|---|---|---|---|
| P1 · A 地基 | 服务区+播种扩展+start-station 加载改造+updater(验签/原子/健康/回滚)+本地/市场来源+大屏 updater 面板 | chatop | 解痛点+绕 OOM |
| P2 · B 上行 | station `bridge.py`(鉴权+重连)+上行事件 | chatop | 对接指挥系统传数据 |
| P3 · B 下发 | 配置下发(接 config_center)+服务包下发(接 updater) | chatop+chacmd | 车队级热更 |
| P4 · 中心调度轨 | chacmd scheduler 接入运行进程+阈值路由外部化 | chayuan-desktop/chacmd | 调度规则免重启热更 |
| P5 · 跨 OS 门（可选后期） | 三 bundle 打原生 SKU(Tauri/PyInstaller) | chatop→新 SKU | 跨 OS |

推荐先 P1（独立见效、解痛点、绕 OOM），再 P2→P3→P4，P5 后期。

## 8. 风险与取舍
- 镜像体积基本不变（出厂副本还在）；换来服务与镜像生命周期彻底分离。
- 多一个 updater 组件 + 一把签名密钥 + 一条反连通道的运维税。
- `needs_venv` 类更新仍需重路径（少数），不是 100% 免重打——如实标注。
- 中心调度轨（P4）是 chacmd 仓的活，与 chatop 镜像解耦独立推进。

## 9. 关键文件指针
- 工位服务：`/work/chatop/station/station/`（`api.py`/`agentcfg_api.py`/`heartbeat.py`/`probe/`/`tasks/`）、`/work/chatop/station/start-station.sh`
- 配置引擎：`/work/chatop/agent-config/agentconfig/`、`/work/chatop/openclaw-tool/`
- 大屏前端：`/work/chatop/dashboard-web/src/`
- 反连（待重写进 station）：`/work/chatop/agent-bridge/agent_bridge/`
- 播种/镜像：`/work/chatop/app-manager/chatop-seed-home.sh`、`/work/chatop/Dockerfile`、`/work/chatop/VERSION`
- 中心件（chacmd 轨）：`/work/chayuan-desktop/chacmd/chacmd/orchestrator/config_center.py`、`gateway/bridge_gateway.py`、`scheduler/`、`interfaces/nacos_registry.py`
- 相关既有文档：`docs/superpowers/specs/2026-07-11-agent-smart-config-design.md`、`2026-07-06-chatop-station-dashboard-design.md`、`2026-07-07-merge-single-dockerfile-design.md`、`2026-07-05-chacmd-placement-and-requirements-master.md`、`2026-07-06-scheduler-placement-analysis.md`
