# ChaCMD（察CMD）智能体指挥系统 —— 技术选型与架构设计

- 产品名：**ChaCMD（察CMD）** · 察元 · 智能体指挥平台
- codename / CLI：`chacmd`（如 `chacmd dispatch @小查 "整理报告"`）
- 日期：2026-06-30
- 状态：设计稿（待评审）
- 适用项目：`chatop-ai`（KasmVNC AI 智能体桌面）
- 作者：Claude（与用户共同 brainstorming 产出）

---

## 0. 一句话定位

在现有 `chatop-ai` **单容器智能体桌面**之上，加一层**控制平面（control plane）**：
把"克隆容器 → 分配角色 → 统一配模型/Key → 统一对话框派活 → 各容器无头 agent 干活并实时回传 → 结果与文件统一共享 → 免密远程开任意容器界面"串成一个端到端的指挥系统。

---

## 1. 背景与现状基线（已实地核实，非印象）

当前 `chatop-ai` 是**单个** KasmVNC 桌面容器，构成：

- **桌面**：`kasmweb/core-ubuntu-jammy:1.19.0`（XFCE）+ 中文化 + 品牌壁纸。
- **单端口收口**：Caddy(7443) 反代 KasmVNC(6901) 与 filebrowser(8585)，对外仅一个端口。
- **文件传输**：filebrowser（KasmVNC 开源版无文件传输能力，旁挂补齐）。
- **应用市场**：`app-manager/app_manager.py`（Python `http.server`，560 行），管理 CLI / GUI(AppImage) / proot-apps / VSCode 扩展 的安装、启动、分组。
- **预装智能体（两类跑法）**：
  - **CLI Agent**（装在 `~/.npm-global`，桌面终端交互 TUI）：`openclaw`、`@openai/codex`、`@anthropic-ai/claude-code`、`tokscale`、`rtk`、（一键装）`hermes`。
  - **Web/GUI Agent**（Chrome 或 AppImage 载体）：OpenHuman、openclaw 配置器、Chrome 内 Web 智能体。
- **身份/端口/权限现状**：单容器，靠 `.env` + `docker-compose` 管（`LOGIN_USER` / `PASSWORD` / `PORT` / `FILES_*` / `CLIPBOARD_*`）。
- **跨界共享现状**：只有 filebrowser + 剪贴板，**没有容器间共享机制**。

> 结论：现有项目是"**单个 agent 工作站**"。指挥系统要做的是把它**横向复制成集群 + 纵向加控制平面**。

---

## 2. 需求清单（20 条）与拆解

用户原始 9 条 + brainstorming 中陆续追加 7 条（#10 统一配置、#11 串并行编排、#12 A2A 直连、#13 容灾、#14 资源级授权、#15 外部数据接入、#16 统一模型网关/国内·本地模型接入）：

| # | 需求 | 本质 | 归属子系统 |
|---|---|---|---|
| 1 | 全套角色分配 | 给每个 agent 定角色（能力画像 + system prompt + 绑定技能） | 角色与权限中枢 |
| 2 | 复制本容器：配端口/文件/用户名/密码/权限/动态装应用/启动 | 容器生命周期编排 | 容器编排服务 |
| 3 | 为每个容器命名/昵称 | 注册表 `nickname → container` 映射 | Agent 注册表 |
| 4 | 统一工作空间地址（同一任务同一文件夹） | 容器内固定 `$HOME/<code>` 挂共享卷 `/workspace/<job_id>/` | 共享工作区 |
| 5 | 统一调度对话框（说事/喊昵称 → 调对应容器 agent 干活） | NL 路由 + 派活 | 调度编排（Orchestrator） |
| 6 | 各容器 agent 执行任务实时反馈到指挥系统 | 流式事件总线 | 实时回传 |
| 7 | 任务结果回对话框 + 容器间数据/成果物/参考文件共享 | 结果聚合 + 共享卷 | 共享工作区 + 编排 |
| 8 | 指挥系统免密打开任意容器 OS 界面 | 凭据金库 + 预认证反代 | 凭据金库 + 接入网关 |
| 9 | 统一装应用/agent/skill + 定/调角色（参考 Hermes 固定角色） | 下发安装 + 角色配置 | 控制台 + 编排 |
| 10 | 统一设置每个 agent 的模型、API Key、Base URL 等 | 配置中心 + 密钥金库 | 统一配置中心 |
| 11 | 多智能体串行/并行编排（任务可串可并，agent 间可串可并） | 工作流引擎（串行链 + 并行扇出/汇聚） | 编排引擎（Orchestrator 内） |
| 12 | 智能体间直连通讯（A 的结果不经指挥系统直传 B） | 数据走共享卷直传 + 消息走总线 pub/sub（指挥台旁路审计） | A2A 通讯层 |
| 13 | 容灾/高可用（某角色容器挂了立即起一个相同职责的替身） | 期望态声明 + 心跳探活 + 协调环重建/改派 + 在途任务重放 | 容灾与自愈（Orchestrator 内） |
| 14 | 把"操作某容器界面 / 查看某系统"按用户或角色授权 | 资源级 RBAC：主体(用户\|角色) × 资源(容器/系统视图) × 动作(查看/开界面/派活/配) | 角色与权限中枢（jeecg）|
| 15 | 某容器可接外部数据：拉数据 / 接数据 / 感知外部数据 | 数据接入层：拉(轮询)+接(webhook/MQ)+感知(事件触发编排) | 外部数据接入层 |
| 16 | agent 能接国内/本地模型（避免 Claude Code/Codex 锁死原厂 API） | agent 与模型间插**统一模型网关**做协议转换 + 路由 + 凭据收口 | 统一模型网关（控制面，#10 的执行后端）|
| 17 | 指挥系统"三位一体"：自带智能体 + 知识库 + 指挥系统，再指挥别的容器 | **以察元 `/work/chayuan-desktop` 为母体内核**（自带智能体/知识库/模型网关/RBAC），ChaCMD 只补"跨容器横向调度"增量 | 母体内核（察元）+ ChaCMD 增量层（见 §3.5） |
| 18 | 每个角色可定义系统提示词 + 用 Hermes 等技能 + 明确自己的目标 + 数据来了就知道做啥 + 知道下一步传给谁 | **声明式"角色契约"**：身份/目标/系统提示词/技能/触发(trigger)/交接(handoff)，派活时注入各 agent | 角色与权限中枢 + 编排（注入）|
| 19 | 给智能体分配知识库查询范围（文档类/数据库类/向量库类等）+ 制定知识库查询权限 | **知识源查询范围授权**：主体(agent/角色) × 知识源(类型粒度 + 具体库粒度) × 动作(查询)；检索时按范围过滤 | 知识源授权（复用察元 kb_subject_grant + kb-query authz） |
| 20 | 每个任务有任务代号，**外部凭代号即可调用**（中心或智能体接口）：执行任务、对接数据（拉/接）、提交数据（同步/webhook/回写） | **Task-as-API**：`code` 升级为对外调用契约 + 任务模板标识；per-caller API Key + RBAC + 幂等 + OpenAPI；与 #15 互补（主动调用 vs 被动感知） | 对外调用契约层（见 §6.21）|

> ⚠️ 这是一个**多子系统工程**，不是单点功能。下面按"先证伪核心、再扩集群"的方式分阶段落地（见 §10）。
>
> 用户追加需求 #10（统一配模型/Key）、#11（串行/并行编排）、#12（A2A 直连）、#13（容灾）、#14（资源级授权）、#15（外部数据接入）、#16（统一模型网关）、#17（三位一体母体）、#18（角色契约：系统提示词/技能/目标/触发/交接）、#19（知识源查询范围与权限）、#20（Task-as-API 对外调用契约）于 brainstorming 过程中并入。
>
> **⚠️ #17 是架构反转点**：经核实 `/work/chayuan-desktop`=察元产品 monorepo，已生产级具备模型网关/RBAC/知识库/agent 框架/服务编排底座。**ChaCMD 改为"以察元为母体内核 + 补一层跨容器横向调度"**，多处原计划组件（jeecg、LiteLLM 主网关）让位于母体能力。详见 **§3.5**。
>
> **深度架构观（#13/#14/#15 引入后定型）**：ChaCMD 收敛为**三个面 + 一条总线脊柱**——
> ① **控制面**：jeecg 资源级 RBAC（#1/#9/#14）+ Orchestrator **协调环**（从"派活器"升级为"控制器"：声明期望态、比对实际态、自愈，#13）+ 配置中心/凭据金库（#10）+ **统一模型网关**（#16，让 agent 接国内/本地模型，#10 的执行后端）。
> ② **数据面**：共享工作区（#4/#7）+ A2A 直传（#12）+ 外部数据接入（#15）。
> ③ **事件/观测面**：一条**统一事件总线**承载心跳（→#13 探活）、任务进度（#6）、A2A 消息（#12）、外部数据事件（#15 感知）。总线是脊柱——探活、派活回传、直连、外部感知**复用同一条总线**，不要各搭一套。

---

## 2.5 目标应用场景（用户用例，需求真源 2026-07-01）

用户给出 7 个真实场景。**共同点：单一 agent 或纯指挥系统都做不了，必须"分容器 / 分技能 / 容器隔离 / 自动化"**——这正面回答了"母体 vs 子容器边界"：**子容器 = 一个专业角色 + 隔离环境 + 特定技能；母体 = 指挥 / 研判 / 汇总**。

| # | 场景 | 协作拓扑 | 时序 | 关键能力 | 暴露的修正/新需求 |
|---|---|---|---|---|---|
| **S1** | **软件开发流水线**（开发"世界大小排名 APP"）：需求分析师→PM→美工→**多轮审核回环**→项目经理→架构师(选型/架构/详设/设计文档)→数据分析师(建库/爬或造数据)→开发→测试→改；各角色向 PM 汇报，PM 报中心 | 长链多角色 + **审核回环** + 分层汇报(角色→PM→中心) | 一次性 | #1/#18 角色、#11 编排、#12 交接、#7 分层汇总、#4 共享文档 | **①编排需支持循环/多轮审核 ②分层指挥：PM=子协调者角色** |
| **S2** | **防空拦截**：雷达容器接实时目标→自析→传"防空指挥中心容器"→**挂知识库研判**(距离/最近防空点/该点拦截武器/能否拦截，不能则换下一点)→防空点容器发射/模拟飞行/实时反馈；可人工介入 | 分层指挥 + 实时执行 + **条件重路由** | **实时流(秒级)** | #15 雷达数据、#12 直传、#17 知识库研判、#5 智能路由、#6 实时、#13 多实例、**人工介入** | **①秒级低延迟总线 ②条件决策/动态重路由 ③长时仿真+持续状态流 ④人工介入是刚需** |
| **S3** | **棋牌**（象棋/五子棋/麻将） | 对局/对抗 | 回合交互 | 多 agent 对抗 | 回合制交互（轻量验证场景） |
| **S4** | **个人秘书**：每日新闻/天气/邮件收发 | 单角色 + 工具密集 | **定时** | #15 定时触发、母体工具 | 常驻个人助理（轻量） |
| **S5** | **软件成本度量**：需求规格书→拆功能点→算规模→规模审计→核对多记/少记 | 单/少角色垂直 | 一次性(文档入) | #18 专业角色、#19 规则知识库 | 垂直专业 skill；**可接 S1 产物（场景串联）** |
| **S6** | **短视频加工工厂** | 流水线多工序 | 一次性 | #11 流水线、桌面 GUI agent、**母体文生/图生视频** | 富媒体 + 可能 GUI 自动化；复用察元视频能力 |
| **S7** | **员工云桌面**：每人一账户→登录容器云桌面办公→数据留容器→**agent 学会员工技能→自动进化**→以员工方式工作 | **人机共生** + 从操作学习 | 常驻 | #8 桌面(chatop-ai 本体)、#2 容器、#14 每人授权、**Hermes 自进化** | **①人机共容器(人用+agent 学) ②操作录制→技能提炼→写回角色契约→进化** |

**场景对架构的关键修正（重要——推翻/加强既有判断）**：
1. **编排必须支持"审核回环 + 条件分支"**——S1(多轮审核回退)、S2(不能拦截换下一点)都是刚需。**修正 §6.7"循环/条件后置"的判断**：review-loop + conditional-route 要提前，不能只做串并行。
2. **分层指挥 / 协调者角色**——S1(PM 子协调)、S2(防空指挥中心容器)。角色契约(#18)要支持"**管理者角色**"(能派活/汇总下级)，编排支持 **sub-DAG**；中心→协调者→执行的**树状指挥**，非扁平。
3. **实时 / 长时任务**——S2 秒级 + 持续仿真反馈。任务模型要支持 **long-running / streaming task** + 低延迟总线，非只"派活→完成"。
4. **人机共生 + 技能进化**——S7 全新模式：同一容器人用 + agent 学，Hermes 自进化，操作→技能→契约闭环。
5. **人工介入是刚需**(S2 明确)——印证 §10.0 遗漏项升为一等能力。
6. **场景可串联**(S1 产规格书 → S5 度量)——产物/知识跨 Job 沉淀复用。

**P0 首用例建议**：取 **S1 的最小切片**——"需求分析师 → 产品经理"两角色、一次交接、产物落共享目录、汇总回大屏（**不含审核回环**，回环留 P1）。它最能证伪核心闭环("母体派活给 2 个子容器角色 + 串行交接 + 汇总")，又足够小。S3/S4 可作轻量旁证。

---

## 3. 关键技术事实核实（决定 5/6/7 能否成立）

需求 5/6/7 整套押在"**这些 agent 到底能不能被非交互式驱动、并把进度流式吐出来**"。核实结论：

### 3.1 Agent 能力矩阵

| 智能体 | 形态 | 无头/编程驱动 | 派活方式 | 进度回传 |
|---|---|---|---|---|
| **Claude Code** | npm CLI | ✅ **最强** | `claude -p "<task>" --output-format stream-json --verbose`；逐 token 需 `--include-partial-messages`；双向走 `--input-format stream-json`；另有 **Claude Agent SDK（Python/TS）**同引擎封装 | stream-json NDJSON 事件流，天然实时 |
| **Codex** | npm CLI | ✅ | `codex exec "<task>" --sandbox workspace-write` | 进度走 stderr、最终结果走 stdout |
| **OpenClaw** | **常驻 headless 网关** | ✅✅ 自带控制平面 | 常驻 Node 守护进程，暴露 **WebSocket API**（默认 `127.0.0.1:18789`，JSON-Schema 校验帧；请求 health/status/send/agent/system-presence） | **服务端推送事件**（tick/agent/presence/shutdown）+ headless Node 暴露 `system.run`/`system.which` |
| **Hermes** (Nous Research) | PyPI `hermes-agent`，自进化（学习循环/技能） | ✅ **可无头自动派活（已核实其 CLI 文档，修正早期误判）** | `hermes -z "<task>"`（纯脚本：一句进/最终文本出，stdout/stderr 不掺杂物）；`hermes chat -q "<task>"`（一次性非交互）；`hermes serve`（无头后端）/`hermes dashboard --port 9119`（JSON-RPC 后端）；`hermes gateway start`（常驻服务）；**MCP server 模式**（暴露会话给其它 agent）；`-m` 换模型 / `-s` 预加载技能 | `-z` 取最终文本；`serve`/MCP 走 JSON-RPC；可当一等派活对象 + "固定演进角色" |
| **OpenHuman** (tinyhumans) | **Rust/Tauri 桌面 App**（吉祥物/记忆树/100+ OAuth/MCP/Skills） | ❌ **官方无任何无头接口**（核实：无 CLI / 无 HTTP·WS API / 无 server·daemon / 无 MCP server；它是 MCP **客户端**不是服务端；文档明确"no terminal required"） | **不可无人值守派活**。只能：①GUI 自动化硬驱（无头桌面容器拉起窗口 + computer-use/视觉点击，脆弱）②改 Rust 源码开本地端口（成本高/冲突上游）。**定位为人工桌面型**，ChaCMD 只负责"免密开界面"(需求8) | 不走批量编排 |
| **OpenHands**（开发型，开源） | PyPI/Docker，MIT(68k★) | ✅ **开源 + 自主开发部署** | `--headless --json` 输出 **JSONL 事件流**（Message/Action/Observation）；**model-agnostic 经 LiteLLM** 接 DeepSeek/Qwen/**Ollama/vLLM**/SGLang/llama.cpp（国内+本地+离线）；**自带 Docker 沙箱运行时**（terminal/editor/browser/fs）能写码+跑+构建+部署 | JSONL 事件流天然实时；见 §6.17 Dev Agent |
| tokscale / rtk / reasonix | CLI 辅助工具 | — | token/成本监控、终端 agent 等，按需 | — |

> **设计含义**：编排服务的**一等派活对象**是 Claude Code、Codex、OpenClaw、**Hermes**、**OpenHands**（均能无头自动派活）。其中 **OpenHands 是唯一"开源 + 离线可跑 + 自带沙箱能自主开发部署"** 的，作**实时开发部署智能体（Dev Agent，§6.17）**首选。**唯独 OpenHuman 无官方无头接口**，定位为"人工桌面型 + 免密开界面"，不做无人值守派活。印证用户选的"**桌面 + 无头混合**"。

### 3.2 平台工具核实

| 工具 | 形态 / 协议 | License | 角色 |
|---|---|---|---|
| ~~1Panel~~（**已去掉**，D6） | Go(Gin)+Vue3，Docker SDK 管容器 + Token API | GPL-3.0 | ~~每节点运维面板~~ → **改由主机 agent-bridge 本地驱动 Docker**（去 1Panel：省一进程 + 无 GPL 传染 + 不裸暴露 Docker API） |
| **Docker Engine（直管）** | 各主机本地 Docker socket / SDK，由**覆盖网 agent-bridge** 本地调用 | Apache-2.0 | 容器创建/启动/装应用的执行器（指挥中心经 bridge 反连通道下发） |
| **jeecg-boot** | Java SpringBoot + Shiro + JWT + RBAC + 低代码代码生成 + 在线表单/工作流；前端 AntDesign+Vue3 | Apache-2.0（含 JEECG 版权署名条款） | 管理控制台 + 角色权限/用户/审计中枢 |
| **K8s** | 多机容器编排 | Apache-2.0 | **可选增强**（自动扩缩容/自愈），非默认；集群由覆盖网实现 |
| **KasmVNC + Caddy** | 现有桌面 + 单端口反代 | 现有 | 桌面型容器接入 |

---

## 3.5 以察元（/work/chayuan-desktop）为母体的重构分析（核心反转）

> 用户新指令：**指挥系统本身要部署 `/work/chayuan-desktop` 知识库，"集智能体 + 指挥系统 + 知识库于一体"，再去指挥调度别的容器**。经核实，`/work/chayuan-desktop` 不是单纯知识库，而是**整个察元（Chayuan）产品的桌面版 monorepo**（Tauri 2 + React 19 + Python 3.12/FastAPI，AGPL-3.0，用户自有产品），定位「一套引擎、本地单机 + Docker 网络版双形态」。它**生产级地已具备 ChaCMD 原计划要新建的大半组件**。

**架构反转**：ChaCMD 不再是"从零搭控制平面"，而是 **"以察元 chayuan-server 为母体内核，补一层它缺的『跨容器横向调度』"**。母体 = 三位一体的"指挥官"（自带智能体 + 知识库 + 模型网关 + RBAC + 服务编排底座）；ChaCMD 增量 = 把任务横向分发/复制到子容器 agent，并做覆盖网/A2A/容灾。

### A. 察元母体已覆盖 → 直接复用，原计划组件让位（含文件证据）
| 需求 | 察元现成能力（文件，相对 `/work/chayuan-desktop`） | 成熟度 | 处置（对原计划的修订） |
|---|---|---|---|
| **#16 模型网关** | `chayuan-server/libs/chayuan-gateway/`（OpenAI 兼容全套端点）+ `.../config_panel/model_config.py` 的 `PROVIDER_CATALOG`（**25+ 厂商**：DeepSeek/通义/GLM/Kimi/豆包/混元/MiniMax… + 本地 **Ollama/vLLM/llamacpp** + Anthropic/OpenAI/Gemini）+ `provider_routes.py` + `libs/chayuan-runtime/adapters/` | 高 | **改用察元网关当统一模型出口**（本地+网络本就双支持，正好命中"本地和网络都要支持"）。**LiteLLM 从"主力"降为"补位"**——只补察元对外缺的 **Anthropic `/v1/messages`** 端（给 Claude Code），或用 claude-code-router 补 |
| **#14 资源级授权** | `.../db/models/{org,dept,role,user_role,role_scope_dept,kb_subject_grant,audit_log}_model.py` + `.../auth/` + `.../api_server/{orgs,roles,kb_acl,admin_users}_routes.py` + alembic `0024~0031`（**组织/部门/角色/用户 + data_scope 数据权限 + 主体可为用户/角色/部门含子树的资源级 grant + 审计日志 + Postgres RLS**） | 高（活跃迭代） | **砍掉 jeecg**，改用察元自有 RBAC——同 Python 栈、已有资源级 grant 概念、省掉一整个 Java 栈与桥接。这是最大的一处优化 |
| **知识库（新，三位一体的"库"）** | `.../kb_query/`（统一查询 `POST /api/v1/kb-query/search` + 异步任务 + NDJSON 流 + citation + 数据级授权）+ `.../retrieval/`（文档/图像/向量/结构化 text2sql 五类适配器）+ `.../knowledge_base/`（SQLite-vec 单机 / Milvus 集群） | 高 | **复用察元 RAG 当母体知识层**；母体智能体与各容器 agent 都查同一 `kb-query` API |
| **指挥系统"自带智能体"** | `.../chat/graph/`（**supervisor 多 agent 协作**：调研/写作/审校 + `runner/nodes/state`）+ `.../agent/tools_factory/`（**30+ 工具**：text2sql/shell/python_repl/http_request/openapi_call/各类搜索）+ MCP server/client | 中高 | **母体即"指挥官 agent"**：能自己用知识库+工具直接干活，也能把任务智能分派给子容器。`chat/graph` supervisor 可升级为"智能路由大脑"（替代原计划另起的 Claude Agent SDK 规划器） |
| **#2 容器/服务编排底座、#13 容灾原语** | `chayuan-server/libs/chayuan-supervisor/`（声明式 YAML→进程图 + **端口分配 + 重启策略 + 健康探针 + 自动凭据**）+ `libs/chayuan-discovery/`（服务发现）+ `libs/chayuan-registry/` + `deploy/k8s/` Helm + `profiles/cluster.yaml` | 中高（基础设施侧） | **复用其 端口/健康/重启/凭据 原语**做容灾；但它编排的是"本地推理引擎子进程"，**跨容器/远程节点的任务分发仍需自建**（见 B） |
| **本地 + 网络双部署** | 根 `docker/`（compose 单机/拆分/dev + nginx）+ PyInstaller 桌面 sidecar（端口 127.0.0.1:62581）+ K8s Helm | 高 | **原生满足"本地和网络都要支持"**：母体既可单机装、也可 Docker/K8s 起网络版 |

### B. 察元缺口 → 这才是 ChaCMD 真正要新建的本体增量
| 增量 | 为何察元没有/不够 | 对应需求 |
|---|---|---|
| **跨容器多实例 agent 分发** | `agent_connector/manager.py` 的 per-user / 多实例分发是 **v4 占位（`NotImplementedError`）** | #2/#3/#5 核心 |
| **覆盖网 agent-bridge 反连** | 察元只用 supervisor 拉**本地子进程**或 K8s，无"远程容器反连指挥中心"的覆盖网 | 集群（§6.3b） |
| **统一调度对话框 + 智能路由** | 察元 supervisor 是**固定**三 agent，无"按能力/负载/知识把任意任务智能分配到容器"的路由 | #5 |
| **用户可编排串/并行 DAG** | 察元 `chat/graph` 是写死的调研→写作→审校，不是用户可编排的 DAG | #11 |
| **A2A 直连总线** | 有 MCP/agent_connector，但无"A 结果不经中心直传 B"的事件总线 | #12 |
| **容灾期望态协调环（跨节点起替身）** | supervisor 只对本地子进程做 restart，无"角色容器挂→跨节点起同职责替身"的 reconcile | #13 |
| **免密开 KasmVNC 容器桌面** | 察元自身是 server/desktop，无"开别的容器桌面" | #8 |
| **Anthropic `/v1/messages` 兼容端** | 察元网关**对外只吐 OpenAI 兼容**，Claude Code 要 Anthropic 协议 | #16 缺口 |
| **外部数据接入/感知入站数据面** | 有 http_request/openapi_call/外部知识源，但无"拉/接/感知→触发编排"的入站事件面 | #15 |

### C. 察元有但需"加强"的点
- **RBAC 资源维度要扩**：现有 grant 主要是"知识库授权(`kb_subject_grant`)"，需扩到"**容器 / agent / 系统视图**"资源类型，才能满足 #14"把开界面/查系统授给用户或角色"。
- **token 估算 → 真实计费**：`admin/users_analytics.py` 是**按字符估算**；但 `observability/llm_callback.py` 已采集**真实 usage**，可在此接真实计量/配额。
- **agent_connector 白名单要补**：现仅接 **openclaw、hermes**，需补 **Claude Code、Codex** 两个一等派活 agent。
- **supervisor 编排域要扩**：从"本地子进程"扩到"**Docker 容器 / 远程节点**"（直接用 Docker SDK，经各主机 agent-bridge 本地执行；不引 1Panel）。

### D. 因母体而修订的关键选型（覆盖 §4/§8 的旧结论）
| 组件 | 旧结论 | **修订后** | 理由 |
|---|---|---|---|
| RBAC/控制台 | jeecg-boot(Java) | **察元自有 RBAC/org/审计** | 同栈、已有资源级 grant、省一个 Java 栈 |
| 模型网关 | LiteLLM 主力 | **察元 chayuan-gateway 主力**；LiteLLM/CCR 仅补 Anthropic `/v1/messages` | 察元已含 25+ 厂商 + 本地，本地/网络双支持 |
| 编排大脑 | 另起 Claude Agent SDK 做 NL→DAG | **复用察元 `chat/graph` supervisor** 做智能路由 + 拆解；Claude Agent SDK 仅在需要时驱动 Claude 任务 | 更一体化，少一套并行框架 |
| 知识库 | （原无） | **察元 kb-query 五类源** | 三位一体的"库"现成 |
| 容器管理 | ~~1Panel API 旁挂~~ → **主机 agent-bridge 直管 Docker（用户 2026-07-01 去掉 1Panel，D6）** | 与覆盖网同通道、无 GPL、不裸暴露 Docker API；可视化由指挥大屏自建 | 察元 supervisor 只管本地子进程，不管 Docker 容器生命周期 |
| 集群 | 覆盖网（不用 K8s） | **覆盖网为主**；察元已带 K8s Helm 可作大规模可选 | 二者并存，按规模选 |

### E. 三位一体 + 指挥别的容器的部署形态（回答"本地和网络都要支持"）
```
        ┌─────────────────── 母体：察元 chayuan-server（本地单机 或 Docker/K8s 网络版）──────────────────┐
        │  指挥官智能体(chat/graph supervisor + 30+工具 + MCP)  ·  知识库(kb-query 五类源)              │
        │  模型网关(25+厂商 + 本地 Ollama/vLLM ＋ 新增 Anthropic /v1/messages shim)  ·  RBAC/org/审计  │
        │            ▲ 自己干活            │ 智能分配/横向派活(ChaCMD 增量)            ▲ A2A/回传        │
        └────────────┼───────────────────┼──────────────────────────────────────────┼────────────────┘
                     （母体即一等智能体）  ▼                                          │（覆盖网 agent-bridge 反连）
                                 ┌─────────────┐   ┌─────────────┐   ┌─────────────┐
                                 │ KasmVNC 容器 │   │ KasmVNC 容器 │   │ 无头容器     │   ← 子容器 agent
                                 │ Claude Code │   │ OpenClaw    │   │ Codex/Hermes│
                                 └─────────────┘   └─────────────┘   └─────────────┘
        子容器内 agent 统一指向母体：模型网关(经 shim) + 知识库(kb-query) + MCP；任务结果回母体/直传同侪(A2A)
```

---

## 3.6 集成与解耦治理：基于察元开发，又要独立部署 / 可同步 / 不耦合

> 用户关切：`chayuan-desktop` 可独立部署，ChaCMD 基于它开发——**如何同时保证 ①察元仍能独立部署 ②能跟上游察元代码同步 ③两者不耦合**。这三个目标有内在张力（既要深度复用母体内部能力，又不能改它改到无法独立/无法同步），是本架构最关键的工程治理决策。

### 核心张力
ChaCMD 要复用察元的网关/RBAC/知识库/agent 框架，但察元要继续作为独立产品演进（自有发版/SKU）。直接改察元源码 → 察元被污染（纯净部署带上 ChaCMD 的东西）+ 上游同步变 merge 地狱 + 强耦合。可 §3.5.C 又有几个**必须扩察元内部**的加强点（RBAC 资源维度、agent_connector 补 Claude Code、supervisor 扩 Docker），与"不改源码"直接冲突。

### 两个核心洞察（化解张力）
1. **察元天然适合被"旁挂"**：它有 60+ REST 路由、OpenAI 兼容端、MCP server、独立 `libs/chayuan-*` 包。ChaCMD **默认零侵入**——作为独立服务部署在察元旁，只调其**公开 API**（进程隔离 + 契约式集成的同一哲学）。
2. **察元是用户自有产品 → "改察元" ≠ "耦合"**：对必须改内部的加强点，**不维护下游私有 fork**，而是把改动**通用化 + feature-flag 化、合进察元上游主线**。纯净部署 flag 关（行为不变，仍可独立部署）；ChaCMD 部署 flag 开。既扩能力、又零分叉、上游同步零冲突。

### 五条治理原则
1. **依赖单向**：ChaCMD → 察元。察元**永不** import / 依赖 ChaCMD。
2. **默认零侵入**：ChaCMD 能力优先 100% 放 ChaCMD 仓库，经察元公开 API/MCP 集成。
3. **必须改察元时，改动上游化 + flag 化**：作为察元标准特性合主线，默认关，ChaCMD 部署开启。**绝不维护下游私有补丁**。
4. **防腐层（ACL）**：ChaCMD 内用一个适配层封装**所有**对察元的调用；察元 API 若变，只改这一层。
5. **版本锁定**：pin 察元镜像 tag / 包版本（如察元 2.0.348）；上游升级走测试再升。

### 集成模式谱系与选型
| 模式 | 做法 | 耦合度 | 处置 |
|---|---|---|---|
| A 改源码(fork-and-modify) | ChaCMD 功能直接写进察元核心，无隔离 | 最高 | **否决**（污染+无法独立部署） |
| **B Monorepo 双 SKU（用户定）** | ChaCMD 增量作察元 monorepo **内独立目录/包**，单向依赖 + **两档构建 flavor** + flag 隔离 | 中（受控） | **主选**：同仓库共享察元源码 → **代码同步天然**（无跨仓库 pin/升级）；贴察元现有多 flavor 构建范式 |
| C1 API/服务依赖 | ChaCMD 把察元当**运行中的服务**，只走 HTTP API/MCP | 最低 | 备选/互补：纯远程、多机、或子容器 agent 访问母体时走此 |
| C2 包依赖 | 直接依赖察元已拆好的 `libs/chayuan-*`（已核实可独立 pip） | 低 | monorepo 内直接 import 稳定 libs |
| D 插件/扩展点 | ChaCMD 作察元插件加载 | 低 | 察元有 `chayuan.runtime_adapters` entry_points，但 agent_connector 不走此（§3.6 Phase0） |

> **主选 B（monorepo 双 SKU，用户定）**：ChaCMD 增量进察元同仓库的独立目录，用**两档构建 flavor** 产出「纯察元」和「察元+ChaCMD」两个产物；同仓库共享源码使代码同步天然。**混合依赖**：稳定 libs（gateway/supervisor/runtime/registry）monorepo 内**直接 import**（C2）；业务能力（知识库/RBAC/agent）走 **HTTP API + 防腐层**（C1）——同仓库不等于放弃边界。

### 集成契约（ChaCMD 调用察元的公开面，均为察元**已有** REST）
- 模型网关：`/v1/chat`、`/v1/models`、`/v1/providers`（OpenAI 兼容）
- 知识库：`/api/v1/kb-query/search`（+ 异步/流式）
- 认证/RBAC：`/auth`、`/orgs`、`/roles`、`/kb_acl`、`admin_users`
- 外部 agent 连接：`/api/v1/external-agents/*`
- MCP：察元 `mcp_server`（能力互通）
- admin/metrics：用量/资源看板

### 仓库与部署拓扑（monorepo 双 SKU，用户定）
```
chayuan-desktop/                         ← 同一仓库，两档构建产两个 SKU
├─ chayuan-server/  chayuan-client/      ← 察元核心（不动；禁止 import chacmd/）
├─ chacmd/                               ← ChaCMD 增量（新增，独立目录/包，单向依赖察元）
│    ├─ control/       覆盖网/调度/A2A/容灾/对话框/角色契约引擎/编排
│    ├─ connectors/    agent_connector 的 claude-code / codex adapter（上游进 chayuan-server，flag 关）
│    └─ anthropic-shim/  对外 /v1/messages（给 Claude Code 接母体网关）
├─ build-desktop.{sh,ps1}                ← 现有：产「纯察元」SKU（不含 chacmd/，flag 全关）
└─ build-chacmd.{sh,ps1} 或 flavor       ← 新增档：产「察元 + ChaCMD」SKU（含 chacmd/，开 CHACMD_ENABLED）
chatop-ai   (本仓库, KasmVNC 子容器镜像)  ← 子容器 agent 工作站形态（覆盖网反连母体）
```
两种部署形态：
- **形态1 纯察元**：`build-desktop`（现有）产出——不含 ChaCMD、flag 全关 = 普通产品，独立可部署。
- **形态2 ChaCMD 指挥平台**：`build-chacmd` 产出——察元 + `chacmd/` 增量、flag 开 + N 个 KasmVNC 子容器。

### 构建策略（"一个仓库、两档构建"是否可行 → 可行，且是察元现成范式）
> 已核实：察元 `build-desktop.sh` **本就是"一个脚本打多档 flavor（lite/standard/full）"的多 SKU 构建器**（`--lite-only/--standard-only/--full-only` 互斥档 + `CHAYUAN_LITE_BUILD` env 控制差异）。**再加一档 `chacmd` flavor 是这套机制的自然延伸**，不是新发明。

**两种落法（推荐 a）**：
- **(a) 加一档 flavor（推荐）**：给 `build-desktop.sh` 增 `--chacmd-only`（或 `FLAVORS` 增 `chacmd`），该档 = 编译 `chacmd/` + 打包进产物 + 构建期开 `CHACMD_ENABLED`。**贴现有 flavor 机制，一处维护**。
- **(b) 平行脚本**：独立 `build-chacmd.sh` 复用 `build-desktop.sh` 的公共步骤（前端/后端/PyInstaller），仅追加 chacmd 编译与 flag。逻辑清晰但有重复。

**三条硬约束（守住"察元仍能独立部署"，缺一则污染）**：
1. **依赖单向**：`chayuan-server/` `chayuan-client/` **禁止 import `chacmd/`**；只允许 `chacmd/` → 察元（libs 直依赖 / HTTP API）。可加 CI 静态检查（禁止反向 import）。
2. **构建隔离**：纯察元 SKU 的打包清单**不含 `chacmd/`**；即便误含，所有 ChaCMD 行为挂在**默认关的 `CHACMD_ENABLED`（+ 各子特性 `*_ENABLED`）flag** 后（照搬察元 `EXTERNAL_AGENTS_ENABLED` 惯例）。
3. **核心改动 flag 化**：那两类必须改察元核心的改动（agent_connector 加 claude-code/codex adapter、知识库授权三扩展 §6.14）**进 chayuan-server 但默认关**——纯察元 SKU 行为与现在**逐字节一致**，ChaCMD SKU 才开。

> 结论：**可行**。用户方案把"跨仓库同步"简化为"同仓库共享"，代价是靠上述三条纪律（构建/flag/单向依赖）守住察元的独立部署与纯净——而这三条察元现有机制都已支持。原"独立仓库 ChaCMD-control"方案降为备选（仅当未来要把 ChaCMD 完全脱离察元独立发行时再拆）。

### §3.5.C 加强点的归属（逐条对照三目标）
| 加强点 | 处置 | 是否影响察元独立部署 |
|---|---|---|
| RBAC 资源维度扩到"容器/agent/视图" | 优先察元配置式资源登记；必须改码则**上游化+flag** | 否（flag 关即纯净） |
| agent_connector 补 Claude Code/Codex | 若 registry 是配置式白名单→**加配置**；否则上游 PR | 否 |
| supervisor 扩到 Docker 容器/远程节点 | 优先 ChaCMD 侧自建容器编排，**不改 supervisor**；或上游加可选 driver | 否 |
| Anthropic `/v1/messages` shim | **放 ChaCMD 侧**（独立 shim 服务），零侵入察元 | 否 |

### Phase 0 前置假设——已查证（2026-07-01，文件级证据）
> 结论：**§3.6 治理方案成立，只需 1 项上游改造**（agent_connector 加 claude-code/codex adapter，包在默认关 flag 后）。

| # | 核实项 | 结论 | 证据 |
|---|---|---|---|
| 1 | 公开 API 是否够全 | **可行**：模型网关 `/v1/chat/completions`+`/v1/models`、知识库 `/api/v1/kb-query/search`(带 citation)、厂商 `/v1/providers/*`、外部 agent `/api/v1/external-agents/{system_id}/{status,start,stop,restart,install,config,logs}` + `/skills/*` 齐备；鉴权统一 `require_auth_enabled`(单机放行/多租户强制) | `api_server/{openai,kb_query,provider,external_agent}_routes.py` |
| 2 | agent_connector 注册=配置还是改码 | **需上游改码**(非配置)：硬编码 `if system_id=="openclaw"/"hermes"`，`SUPPORTED_SYSTEMS` 是模块常量，刻意不用 entry_points。新增 claude-code/codex = 各写 1 个 `Adapter(ExternalAgentConnector)` 类(~90 行) + registry 改 3 处 | `agent_connector/{registry,base,openclaw}.py` |
| 3 | 有无 feature-flag / 插件机制 | **可行且成熟**：`settings.py::BasicSettings` 大量 `*_ENABLED=False` 默认关(`EXTERNAL_AGENTS_ENABLED`/`USE_CHAT_GRAPH`/`RLS_ENABLED`…)，env/yaml 可开；范例 `shims.py::use_chat_graph()`(异常默认旧路径+灰度)。照搬即可，**无需新建 flag 框架** | `settings.py`、`chat/graph/shims.py` |
| 4 | `libs/chayuan-*` 能否独立 pip 装 | **可行**：gateway/supervisor/runtime/registry 均有 `pyproject.toml`(hatchling)，只依赖 `chayuan-core` 及彼此，**无一依赖主包 chayuan-server** | `libs/*/pyproject.toml` |

**两个必须纳入设计的发现**：
- **external-agents 的 `shared-multitenant`(多租户/远程)路径是 `NotImplementedError`(仅 trusted-local 同主机可用)** → 印证 §3.5.B：跨容器/多实例分发正是 ChaCMD 要新建的本体，**不能指望察元现成**。
- **kb-query 选源参数是 `ku_ids`**(统一 ID `doc:name`/`src:42`，非 `kb_names`)→ §6.14 的 `knowledge_scope` 下发须按 `ku_ids`；`synthesize` 默认 True 会额外调 LLM，只取原始命中要显式传 `false`。
- **`/v1/chat/completions` 与 `/v1/models` 裸开放无 auth** → ChaCMD/子容器接母体网关时，网络模式下要在网关前自行加接入控制（别裸暴露）。

---

## 3.7 前端架构：一套基座、双 SKU、不同主页、分开打包

> 用户诉求：**原有基座代码同步 + 新代码分块 + 打包分开 + 首页不同**（察元 SKU 仍以现主页为主，ChaCMD SKU 是全新主页）。这是 §3.6 monorepo 双 SKU 在**前端**的落地。已核实 chayuan-client 真实结构，结论：**天然支持骨架，只需补 3 个注入点 + 3 项小重构，无根本阻碍**。

### 已核实的有利前提（chayuan-client 真实结构）
- **pnpm workspace monorepo**，`pnpm-workspace.yaml` globs = `apps/* + packages/*`——**新增 `apps/chacmd/` 自动入包**，不改 workspace 配置。TanStack Router；Vite；每 app 独立 `vite.config.ts` + 独立 `src-tauri/tauri.conf.json`。
- **全部 UI/路由/业务已下沉 `packages/app`**（`Shell.tsx` 根、`router/index.tsx` 路由树、`features/` ~40 模块含 home/chat/kb/settings/admin、`store/`、`features/shell/page-registry.tsx`）；**`apps/desktop` 只剩 ~40-130 行引导 main.tsx**（建 platform + 挂 Shell）。→ **新 app 靠 import `@chayuan/app` 即复用整套基座**，本仓最大红利。
- Tauri：每 app 一份 `tauri.conf.json`（`frontendDist`→自己的 dist，`productName/identifier/icon/title` 各自独立）；`thin.conf.json` 变体已证明"同基座、不同品牌产物"可行。chayuan-server 走 `bundle.resources`（非 externalBin）。
- 缺口：**首页/路由写死**（`/home`→`HomePage.tsx`，无按 SKU 切换 seam）；品牌"察元"硬编码散落 ~30 文件；`build:desktop` 固定 `--filter @chayuan/desktop`，flavor(lite/standard/full) 只影响后端不影响前端。→ 这三处即要补的注入点。

### 核心原则：基座 SKU 无关，差异从 app 入口注入（控制反转/依赖注入）
`packages/app` **不认识任何具体 SKU**；每个 app 的 main.tsx 把"品牌 + 首页 + 路由扩展"作为配置**注入**基座。察元基座零改动即可承载 N 个 SKU，察元 SKU 行为逐字节不变。

**三个注入点（seam）**：
1. **品牌注入 `BrandConfig`**（复用现有 `ShellEnv` 通道）：
   ```ts
   interface BrandConfig {
     appName: string          // "察元 AI" | "ChaCMD 指挥台"
     logo: string; theme?: ThemeTokens
     homeComponent: React.ComponentType    // ← 决定首页
     routeExtensions?: RouteDef[]          // ← 该 SKU 额外路由
     navItems?: NavItem[]                  // ← 侧边栏覆盖/扩展
   }
   ```
   由 `Shell(env)` 下传 `router/Chrome`；i18n 已用 `labelKey`，对新品牌友好。
2. **首页/路由注入**：`createAppRouter(queryClient, brand)` 支持"可配 landing 路径 + `brand.routeExtensions` 新增路由"，**不覆盖察元原有路由树**。
   - **察元 SKU**：landing=`/home`（现有 HomePage 不动，现主页为主）。
   - **ChaCMD SKU**：routeExtensions **新增 `/command`（指挥大屏）**，landing 改指 `/command`（`/`→`/command`）；**察元原 `/home` 及整套工作台路由（chat/kb/settings/admin…）保持不动、始终可达**——这正是"从大屏一键进入察元现主页"的基础（见 §6.15）。
3. **构建按 SKU 分档**（与 flavor 正交）：新增 `build:chacmd = pnpm -r --filter './packages/*' build && pnpm --filter @chayuan/chacmd build`；`build-desktop.sh` 增 `--sku chayuan|chacmd`（默认 chayuan）维度，选 app + 选 tauri.conf；lite/standard/full 仍正交（任一 SKU 可任一 flavor）。

### 代码组织（前端增量分块，镜像 §3.6 三条硬约束）
```
chayuan-client/
├─ packages/app  ui  api  transport  i18n  design-tokens …   ← 察元基座（禁止 import chacmd 增量）
├─ packages/chacmd-features/  (@chayuan/chacmd-features)      ← ChaCMD 专属 UI（新增，分块）
│     指挥台 Dashboard 主页 / 容器拓扑视图 / 调度对话框 / DAG 进度树 / 角色契约编辑器 / A2A·事件视图
├─ apps/desktop  apps/web         ← 察元 SKU（现有，主页不变）
└─ apps/chacmd/                   ← ChaCMD SKU（新增：引导 main.tsx + BrandConfig + src-tauri/tauri.conf.json）
      import @chayuan/app(基座) + @chayuan/chacmd-features(增量)
```
- **原有基座代码同步**：`apps/chacmd` 与 `apps/desktop` **import 同一份 `packages/*`**——察元基座演进，ChaCMD **自动同步**（同仓库共享源码，无 pin/copy/fork）。
- **新代码分块**：ChaCMD 专属 UI 全在 `packages/chacmd-features` + `apps/chacmd`，**不散进 `packages/app`**。
- **依赖单向（硬约束）**：基座包 **禁止 import** `chacmd-features`/`apps/chacmd`；只允许 chacmd → 基座。ESLint/CI 规则挡反向 import（对齐 §3.6）。
- **分开打包**：每 app 各自 vite build → 各自 dist → 各自 tauri bundle，`productName/identifier/icon` 独立 → **两个完全独立的安装包**。

### 3 项小重构（为"不同主页 + 品牌"服务，一次性）
1. **首页/路由 seam**：`createAppRouter`/`Shell` 接受注入的 `homeComponent + routeExtensions`（当前写死）。
2. **品牌集中化**：把散落的 "察元"/`appName`/logo/二维码 抽成 `BrandConfig`，经 `ShellEnv` 注入。
3. **引导层下沉**：`apps/desktop/src` 里可复用的 `splash.ts`/`runtimeSync.ts`/thin 判定 下沉为 `packages/desktop-bootstrap`，让两个 app 的 main.tsx 都变成"传 BrandConfig + 调 bootstrap"几行。

### 否决的替代方案
- **单 app + 构建期 env flag 切首页**（`VITE_SKU`）：两 SKU 代码耦合在同一 app 判断点，难保察元纯净，**产物不分开**——违背"分开打包 + 全新主页"。否决为主选。
- **运行期 flag 切换**：直接违背"打包分开"。否决。
- **Module Federation / 微前端**：Tauri 桌面场景过度设计；仅当未来 ChaCMD 前端需**独立于察元运行时热更新/独立部署**（网络版）才考虑，非本期。

> **结论（架构师判断）**：采用 **"共享库包 + 薄 app 壳 + 依赖注入变体"** 这一 monorepo 前端最佳实践（等价 Nx/Turborepo 的 app+lib 分层，此处即 pnpm workspace 现状）。察元已把 UI 全下沉 packages，使该模式几乎零成本落地：**新增 `apps/chacmd` + `packages/chacmd-features` + 三个注入 seam**，即得"基座同步、增量分块、分开打包、双主页"。网络版(apps/web) 可同法加 `apps/chacmd-web` 保持对称。

### 3.8 双 SKU 开发态运行命令（dev 分开启动，2026-07-01，基于实测结构）

> 用户诉求：开发时察元前端/后端各有独立启动命令，**新项目 ChaCMD 也要能分开启动**（前后端各自独立、可并存、互不干扰）。

**察元现状（实测，保持零改）**：
- 前端（`chayuan-client`，pnpm workspace，UI 全在 `packages/app`，`apps/*` 是薄壳）：
  - `pnpm dev` = `pnpm --filter @chayuan/web dev`（网络版，vite，端口 5173）
  - `pnpm dev:desktop` = `pnpm --filter @chayuan/desktop dev`（= `tauri dev`）
- 后端（`chayuan-server`）：`cd libs/chayuan-server/chayuan && python cli.py start -a`

**ChaCMD 新增（与察元并存、分开启动）**：
- **前端**：新增薄壳 `apps/chacmd`（+ `apps/chacmd-web` 对称，依赖 `@chayuan/app` + `@chacmd/features`，§3.7）。root `package.json` 加脚本，**端口错开**避免冲突、可同时跑对比：
  ```jsonc
  "dev:chacmd":         "pnpm --filter @chacmd/web dev",        // 网络版, vite --port 5174
  "dev:chacmd:desktop": "pnpm --filter @chacmd/desktop dev"     // = tauri dev (独立 tauri.conf)
  ```
- **后端**：ChaCMD 后端 = **薄实时派活核心 Orchestrator**（§10.2，FastAPI，独立薄层，**不塞进察元 cli**）。独立入口、独立端口：
  ```bash
  # 独立入口（推荐，符合 §10.2 实时核心独立不经察元重 monorepo）
  cd <chacmd 增量根> && python -m chacmd.cli start        # Orchestrator, 端口 8100
  ```

**双 SKU 进程模型与端口规划**：
| SKU | 前端命令 | 后端命令 | 端口(建议) |
|---|---|---|---|
| **察元**（现状零改） | `pnpm dev` / `pnpm dev:desktop` | `python cli.py start -a` | 前 5173 / 后 8000 |
| **ChaCMD**（新增） | `pnpm dev:chacmd` / `pnpm dev:chacmd:desktop` | `python -m chacmd.cli start` | 前 5174 / 后 8100 |

**开发态依赖关系（关键）**：ChaCMD 后端依赖察元能力——**稳定 libs 直 import**（网关/registry，§3.6-C2）、**业务能力走 HTTP**（kb-query/RBAC，§3.6-C1）。因此:
- **纯 Orchestrator 逻辑开发**：只起 ChaCMD 前后端（察元 HTTP 依赖可 mock）。
- **联调**：**同时起察元后端 + ChaCMD Orchestrator**，ChaCMD 配置 `CHAYUAN_BASE_URL=http://127.0.0.1:8000` 指向察元后端。两后端进程并存、端口分开、互不干扰。

**一键起（可选，降心智负担）**：用 Procfile/concurrently/`make` 各 SKU 一条命令拉起该 SKU 全栈：
```
make dev-chayuan   # = 察元前(5173) + 察元后(8000)
make dev-chacmd    # = ChaCMD前(5174) + ChaCMD后(8100) + 按需察元后(8000, 联调)
```

**原则**：①**察元命令零改**（不破坏现有开发流）；②ChaCMD 命令**完全独立并存**，端口错开，可单跑也可与察元同时跑（对比开发）；③前端**复用同一 workspace + `packages/*`**（改 `packages/app` 两 SKU 同步生效 = "基座同步"），仅 app 壳与启动入口分开（= "新代码分块、分开启动、双主页"）；④后端 ChaCMD 是**独立薄核心进程**（§10.2），非察元 cli 的 flag。

### 3.9 三种部署/打包形态（含"轻量挂载已部署察元"，2026-07-01）

> 用户澄清：启动 **ChaCMD = 启动全部**（察元全量 + 指挥系统，仅主页/侧重界面不同）；启动 **察元 = 现状**（不启动指挥系统，界面就是现在的样子）；打包同理（察元只打现有、ChaCMD 打全量）。**并新增第三形态**：**不打包察元，挂载已独立部署的察元服务（用其接口 + 界面直接跳转），非常轻量**——问能否快速实现。

**三形态对比**：
| 形态 | 前端 | 后端 | 察元 | 主页 | 打包体积 |
|---|---|---|---|---|---|
| **A · 察元纯净**（现状） | `@chayuan/web` 只 bundle 察元 | 察元 cli | 就是自己 | 察元现状 | 只现有功能 |
| **B · ChaCMD 全量** | `apps/chacmd` bundle 察元 app + 指挥 UI | ChaCMD Orchestrator + **同机起察元后端** | **内嵌打包** | 指挥大屏 | 全量（含察元 ~3GB） |
| **C · ChaCMD 轻量挂载**（新） | `apps/chacmd` **只 bundle 指挥 UI**；察元界面**跳转/iframe** | ChaCMD Orchestrator，**全 HTTP 对接**已部署察元 | **挂载外部已部署实例** | 指挥大屏 | 极轻（仅指挥增量，几~几十 MB） |

**统一三形态的关键设计（一套代码 + 配置切换）**：
1. **后端优先"全 HTTP 对接察元"**（修订 §3.6 的混合依赖倾向）：ChaCMD 对察元的依赖统一走 `ChayuanClient` 抽象（封装网关调用 / kb-query / authz / 身份 / 跳转 URL）。
   - 察元大多数能力**本来就是 HTTP**（网关 OpenAI 兼容 `/v1`、kb-query API、authz）——所以全 HTTP 很自然，ChaCMD 需直 import 察元 Python libs 的场景其实很少。
   - **形态 B**：`CHAYUAN_BASE_URL=http://127.0.0.1:8000`（同机、同包）；**形态 C**：`CHAYUAN_BASE_URL=https://已部署察元`（远程、不打包）。**B/C 后端代码完全一致**，只是察元"随包同启"还是"外部已部署"。直 import libs 仅在确有低延迟必要时保留（且会绑定形态 B）。
2. **前端"察元界面来源"可切换**（BrandConfig 注入，§3.7 seam）：`chayuanUiMode: 'embedded' | 'mounted'` + `chayuanWebUrl`。
   - `embedded`（B）：察元界面走本 bundle 内 `@chayuan/app` 路由（`/home` 等）。
   - `mounted`（C）：指挥大屏"进入察元工作台"→ **新窗/iframe 打开 `chayuanWebUrl`**（已部署察元），带 SSO token 免登。§6.15 的"大屏↔察元工作台双向入口"在 C 下变为跨实例跳转。
3. **ChaCMD 后台配置**：`察元接入模式 = 内嵌(全量) | 挂载(填已部署实例 URL)`——直接呼应用户"后台能配置"（与 §10.4-B9 Nacos 可插拔同一思路）。

**形态 C 能否快速实现？—— 能，核心很轻；工作量集中在两个前提**：
- **轻的部分（快）**：HTTP 挂载 + URL 跳转/iframe 本身简单，ChaCMD 只是个指挥控制台（不重复打包 3GB 察元）。
- **前提 1 · 察元 HTTP 接口覆盖度**：网关 `/v1`、kb-query **已有 HTTP**（Phase 0 已核实部分裸端点）；**authz / 身份 / registry 若缺 HTTP 需补齐**（待核实）。凡 ChaCMD 用到但察元只有 Python 库没 HTTP 的能力，C 形态用不了或要补接口。
- **前提 2 · 跨实例 SSO 免登（主要难点）**：ChaCMD 与已部署察元是两个部署，用户在 ChaCMD 登录后跳转察元要免登。简单版=跳转带**一次性 token**（复用 #8 免密思路，察元验证放行）；标准版=**统一身份 OIDC SSO**（呼应 §10.4-B1 / NFR-GX6）。
- **结论**：**MVP 可快速做出**（接受简单 token 或同机部署）；**生产级需补齐察元 HTTP 接口 + 对接统一身份 SSO**。

**形态 C 的价值（最契合定位）**：极轻、复用已部署察元、ChaCMD 独立发版不受察元打包拖累、**控制平面 / 数据平面彻底分离**——这正是"ChaCMD = 察元之上的控制平面增量"（§3.5 母体反转）的最纯粹落地：**既能内嵌母体（B），也能挂载已部署母体（C）**。企业若已部署察元，ChaCMD 直接挂上去做指挥层，不动察元。

**风险/前提**：察元 HTTP 覆盖度（可能补接口）；跨实例 SSO；界面过渡断层（深色指挥→浅色察元，iframe 嵌入 vs 新窗跳转的体验，§10.1-D）；**版本兼容**（挂载的察元版本须在集成契约版本内，§3.6 契约版本化）。

**落地**：形态 A/B 已在双 SKU 设计内（§3.6/3.7/3.8）；**形态 C（轻量挂载）= 后端全 HTTP + 前端 `mounted` 模式 + 后台接入配置**，建议 **P1** 提供（P0 先用全量 B 证明价值，C 挂载随后）。为不返工，**P0 后端即按 `ChayuanClient` 全 HTTP 抽象写**（默认 localhost），这样 C 只是换 URL + 补 SSO。

---

## 4. 核心架构决策（含选型理由与已确认结论）

> 以下决策均经 brainstorming 与用户逐项确认。

### D1. 容器形态：**桌面 + 无头 混合**（用户已选）
- **桌面型容器** = 本镜像全量克隆（KasmVNC 全桌面），跑 OpenHuman / Hermes / Web 智能体，**可被指挥台远程开界面**。~3GB+/个，按需起。
- **无头型容器** = 精简镜像（仅 agent CLI + 共享卷，无 XFCE/KasmVNC），跑 Claude Code / Codex 批量任务，省资源、易横向扩。
- 两种都挂统一 `/workspace` 共享卷、都向 Orchestrator 注册。

### D2. 集群方式：**应用层覆盖网（常驻 agent-bridge 反连），不依赖 K8s**（用户确认）
- **关键洞察（用户提出）**：每个工作容器**已常驻一个服务**，能统一接收指挥中心命令、回传、执行任务。那么"集群"由**应用层覆盖网**实现：每个容器内的 agent-bridge **主动反向连回**指挥中心（持久 WebSocket）+ 心跳注册，指挥中心维护在线 agent 表并下发任务。
- **因此 K8s 不是必需品**：容器跑在哪台主机都行，只要能拨号回指挥中心即可形成集群（与 OpenClaw 的 node 模型同构）。多机 = 多台主机各跑 Docker + 各自的容器 agent-bridge 反连同一个指挥中心，**无需 K8s 做跨机调度**。
- K8s 降级为**可选**（仅当需要自动扩缩容/故障自愈/调度策略时再考虑），不进 MVP，不进默认架构。
- 容器的"创建/启动/装应用"由各主机的 Docker（**经 agent-bridge 本地 Docker SDK**，不用 1Panel）完成；"调度/通信/集群成员管理"由覆盖网负责。两者解耦。

### D3. 任务对接：**走各 agent 的无头/编程模式**（用户已选）
- Claude Code 走 stream-json / Agent SDK；Codex 走 `codex exec`；OpenClaw 走 WS API。**不驱动桌面 TUI**（脆弱、难结构化）。

### D4. 控制台后端：**jeecg-boot（Java 低代码）**（用户已选）—— 但**职责边界收紧**
- jeecg **只负责**：角色权限（RBAC）、用户/租户、审计、后台表单与配置 UI、角色-技能绑定（打需求 1、9、10 的管理面）。
- jeecg **不负责**：容器编排、agent 进程调度、流式回传。这些交给独立的 Orchestrator 微服务。
- jeecg 通过 REST 调 Orchestrator；Orchestrator 反向用 jeecg 的 RBAC 做鉴权。

### D5. 调度编排服务（Orchestrator，系统大脑）：**Python FastAPI**（用户已选）
- 与现有 `app_manager.py`（Python）一脉相承；贴 **Claude Agent SDK(Python)**、Docker SDK（经主机 bridge）、agent CLI、SSE/WS 流式最顺（如后续引入 K8s，Python k8s client 亦成熟）。

### D6. 容器管理：主机 agent-bridge 直管 Docker（**去掉 1Panel**，用户 2026-07-01 定）
- **决策变更**：原 D6「1Panel API 旁挂」**取消**。改为：每台装了 Docker 的主机跑一个**覆盖网常驻 agent-bridge**（§6.3b，本就反连指挥中心），由它**本地驱动 Docker（Docker SDK / unix socket）**执行"创建/启动/停止/装应用/删除"；指挥中心通过**反连通道下发指令**，bridge 本地执行并回传。
- **为什么更优**：① 与覆盖网/自愈协调环（§6.9）同一套控制通道，不再多引入一个面板进程；② **不远程裸暴露 Docker API**（socket 只被本机 bridge 访问，跨网只有 bridge↔中心的 mTLS 反连），攻击面更小；③ **彻底消除 1Panel 的 GPL-3.0 传染顾虑**；④ 容器/镜像/卷的**可视化改由 ChaCMD 指挥大屏（§6.15）+ Orchestrator 聚合**（bridge 上报）提供，取代 1Panel UI。
- **纳管新主机** = 装 Docker + 装 agent-bridge（一条 bootstrap 脚本），bridge 反连即入集群。
- **诚实代价**：失去 1Panel 现成的运维面板 UI 与"一键部署 OpenClaw/Ollama"便利——但 Ollama/vLLM 等由察元 `chayuan-supervisor` 已覆盖（§3.5），容器可视化由指挥大屏自建，净损失可接受。

### D7. 角色范式：参考 **Hermes 固定角色**
- 角色 = `{ 能力画像, system prompt 模板, 默认模型, 绑定技能集, 可用工具, 权限范围 }`。
- 既支持"固定角色"（如 Hermes 那种钉死人设），也支持运行时调整（jeecg 控制台改 → Orchestrator 热更新到容器）。

---

## 5. 总体架构

```
┌──────────────────────────────────────────────────────────────────────┐
│  指挥台前端 (Web SPA)                                                    │
│  · 统一对话框(派活/收结果)  · 容器墙(昵称/状态/角色)  · 嵌入式桌面 iframe  │
└───────────────┬──────────────────────────────────────┬────────────────┘
        WS/SSE  │ (实时进度/结果回传)            REST    │
   ┌────────────▼────────────────┐         ┌────────────▼─────────────────┐
   │  Orchestrator 编排服务         │  REST   │  jeecg-boot 控制台 (Java)      │
   │  (Python FastAPI, 新写)        │◄───────►│  · RBAC 角色/权限/用户/租户     │
   │  ─────────────────────────    │  RBAC   │  · 审计日志  · 后台配置表单      │
   │  · Agent 注册表(昵称↔容器↔能力) │  鉴权    │  · 角色↔技能↔模型 绑定 UI        │
   │  · NL 路由(Claude 分诊→选目标)  │         └────────────┬─────────────────┘
   │  · 派活: claude -p/codex exec/  │                      │ Token API
   │    openclaw WS/hermes CLI       │         ┌────────────▼─────────────────┐
   │  · 事件总线(进度/结果聚合)       │         │  agent-bridge 直管 Docker(每主机)│
   │  · 调 配置中心 注入 模型/Key     │         │  容器/镜像/卷 可视化 + Token API │
   └───┬───────────┬──────────┬─────┘         └────────────┬─────────────────┘
       │配置注入     │ 读注入    │挂卷                        │ Docker SDK(创建/启动/装应用)
       │            │          │                ┌───────────▼─────────────────┐
   ┌───▼────────┐ ┌─▼──────────┐│                │  各节点 Docker Engine          │
   │ 配置中心 +  │ │ 共享工作区  ││                │  (主机A / 主机B / 主机C ...)   │
   │ 凭据金库     │ │/workspace/ ││                └───────────┬─────────────────┘
   │(模型/Key/   │ │ <task-id>/ ││                            │ 起容器
   │ BaseURL/账密)│ │(本地卷/NFS)││                            ▼
   └─────────────┘ └─────┬──────┘│       ┌────────────────────────────────────┐
       ▲                 │挂卷    │       │  Agent 容器群 (本镜像克隆, 两种规格)    │
       │                 └────────┼──────►│  每个都挂 /workspace                  │
       │  ┌──────────────────────┐│       │  ┌──────────────┐ ┌───────────────┐ │
       │  │ 集群覆盖网(无需 K8s)   ││       │  │桌面型:KasmVNC  │ │无头型:agent CLI│ │
       └──┤ 各容器 agent-bridge   │◄───────┤  │OpenHuman/Web   │ │Claude/Codex/  │ │
   持久WS │ **反向连回**指挥中心   ││ 反连   │  │(纯GUI,人工)    │ │Hermes/OpenClaw│ │
   +心跳  │ +心跳注册+派活+回传     ││ 注册   │  │→远程开界面(8)  │ │→流式回传(6)    │ │
          └──────────────────────┘│       │  └──────────────┘ └───────────────┘ │
                                   │       │  每容器常驻 agent-bridge:               │
                                   │       │  接派活/起无头agent/转发事件/读注入配置   │
                                   │       └────────────────────────────────────┘
```

---

## 6. 子系统详解

### 6.1 Orchestrator 编排服务（Python FastAPI）—— 系统大脑
职责：
- **Agent 注册表**：`{ nickname, container_id/pod, kind(desktop/headless), role, capabilities, model, status, endpoint }`，SQLite/Postgres 持久化。
- **NL 路由（需求 5）**：对话框输入 → 用 Claude 做"分诊"（参考 chayuan 的 router 模式）→ 解析是"喊昵称"还是"按能力派"→ 选定目标容器与 agent。
- **派活适配器（按 §3.1）**：
  - Claude Code：`subprocess`/Agent SDK，`-p --output-format stream-json`
  - Codex：`codex exec`，读 stderr 进度
  - OpenClaw：WebSocket client 连容器内 gateway，发 `agent` 请求、订阅推送
- **事件总线（需求 6/7）**：聚合各 agent 的 NDJSON/stderr/WS 事件 → 统一 `TaskEvent` 模型 → 经 SSE/WS 推到前端对话框。
- **结果回填（需求 7）**：任务终态写回对话框 + 落 `/workspace/<task-id>/result/`。
- 路由层只做协议适配，业务分发独立成模块（`registry / router / dispatch / adapters / events`），避免单文件膨胀。

### 6.2 统一配置中心 + 凭据金库（需求 8、10）
- **配置中心**：集中维护"每个 agent / 每个角色"的 **模型、API Key、Base URL（代理，应对国内 API）、温度等参数**。
- **凭据金库**：集中维护"每个容器"的 **用户名 / 密码 / VNC 凭据**（打需求 8 免密开界面的根基）。
- **注入方式**：容器启动时由 Orchestrator 把对应配置注入为**环境变量 / 挂载只读 config**（如 `ANTHROPIC_API_KEY`、`ANTHROPIC_BASE_URL`、`OPENAI_API_KEY`、各 agent 的 `~/.config`）。
- **存储**：密钥不落明文卷；用加密文件 + 主密钥（或外部 Vault；引入 K8s 时可选 K8s Secret）。jeecg 提供录入/编辑 UI，金库本体由 Orchestrator 持有。

### 6.3 容器生命周期编排（需求 2、3）
- **克隆**：以本镜像为模板，参数化 `LOGIN_USER / PASSWORD / PORT / FILES_* / CLIPBOARD_*`（现有 compose 已参数化，直接复用）+ 新增"角色/昵称/装哪些 app"。
- **动态装应用**：直接复用现有 `app_manager.py` 的 catalog + 安装逻辑（容器内 agent-bridge 调用），无需重写。
- **昵称**：注册表 `nickname → container`，前端可"喊昵称"。
- **执行器**：各主机的 **agent-bridge 本地 Docker SDK** 创建/启动容器（不用 1Panel、不引入 K8s）。多机时每台主机各自一个 Docker + 一个 bridge，容器起来后由 agent-bridge 反连入网。

### 6.3b 集群覆盖网与常驻 agent-bridge（用户关键洞察）
- 每个容器**常驻一个 agent-bridge 服务**（复用/扩展现有常驻服务，如 `app_manager` 一类；与 OpenClaw 的 node 模型同构）。
- bridge 启动即**主动反向连回指挥中心**（持久 WebSocket），完成：①心跳与能力注册（昵称/角色/模型/在线态）②接收派活 ③起本地无头 agent（`claude -p` / `codex exec` / 本地 openclaw）④把 stream-json/stderr/事件转发回指挥中心 ⑤读取注入的模型/Key/角色配置。
- **集群 = 一堆 bridge 反连同一指挥中心**。容器在哪台主机无所谓，只要能拨号回家即入集群。故**不需要 K8s 做跨机调度**；K8s 仅在需要自动扩缩容/自愈时作为可选增强。
- 反连方向（容器→中心）还顺带绕开了"中心主动连容器"的网络/防火墙/NAT 难题。

### 6.4 共享工作区（需求 4、7）—— 容器内固定路径 + 挂载到共享卷（双视角）

> 用户明确机制：**新任务发到容器后，在容器内固定位置建一个同名文件夹（如 `/home/<user>/<工作目录名>`），该容器这次任务生成的所有文件都放这里**。这是"容器内视角"；再叠加"共享视角"实现跨容器统一（#4）。

**容器内视角（agent 只认这一个路径，简单一致）**：
- 任务派到容器时，在容器内**固定位置**建工作目录：**`$HOME/<code>`**（即 `/home/<容器登录用户>/<工作目录名>`，`<工作目录名> = 任务代号 code`，§6.16）。
- 所有参与同一任务的容器**用同一个文件夹名（code）**，位置对每个容器都固定在其 `$HOME` 下 → agent（claude-code/codex…）无脑读写 `~/<code>/`，跨容器路径习惯一致。
- 该容器这次任务的**全部产出**落此目录；agent 的默认工作目录（cwd）即指向它。
- 建立时机：agent-bridge 在派活前 `mkdir -p $HOME/<code>`（或挂载，见下），按 #14 授权设权限。

**共享视角（跨容器统一 + A2A 直传，#4/#7/#12）**：
- 容器内的 `$HOME/<code>` **不是各自孤立的本地目录，而是 bind-mount / 挂载到共享卷**的该任务目录 `/workspace/<job_id>/`（宿主/中心侧稳定用 job_id，`<code>` 建软链方便人读）。
- 于是：一个容器写 `~/<code>/output/x`，其它被授权容器**立即可见**（#4 同一任务同一文件夹）；A2A 文件交接天然点对点、指挥系统不在路径上（#12）；结果回收 = 读该目录 `output/`（#7）。
- 目录结构（挂载后端）：`input/ output/ refs/ steps/<stage>/<task>/ logs/`，供串行 Stage 传产物、并行 Task 各写子目录（§6.7）。
- **多机**：单机 = Docker named volume / bind mount；多机 = NFS / CephFS 挂到各主机同一 `/workspace`，容器再挂 `$HOME/<code>` → 跨主机同一任务仍同一文件夹。
- **退路**（无共享卷或强隔离场景）：容器各写本地 `$HOME/<code>`，由 agent-bridge 把产物同步回中心 `/workspace/<job_id>/`（弱实时，但保底）。默认走挂载，退路可配。

**指挥中心汇总（需求 7 强化，用户强调）**：各容器产出都落在同一 `/workspace/<job_id>/`（容器视角 `$HOME/<code>`），指挥中心（Orchestrator）天然能读全部 → 在各 Stage/Task 完成后做**汇总**：
- **产物汇总**：收集各 `steps/<stage>/<task>/output/` → 归并成 Job 级最终结果 `/workspace/<job_id>/result/`（去重/排序/合并按需）。
- **结果汇总回对话框 + 大屏**：多 agent 的分散结果**聚合成一份**呈现（#7），并在指挥大屏任务流节点显示各自贡献。
- **智能综合**：汇总这步可由**母体智能体**（察元 `chat/graph` 的汇总/审校节点）做语义综合（如"把三份体检报告合成一份总报告"），或编排引擎 join 屏障后指派一个"汇总"Task（常派给母体或"汇总员"角色）。
- **元数据汇总**：状态（各 Task 完成/失败）、指标（token/耗时，接真实计费 §3.5.C）、事件/审计（#9）一并汇总，形成 Job 级总览。

### 6.5 免密开任意容器界面（需求 8）
- 桌面型容器仍是 KasmVNC + Caddy 单端口。
- 指挥台点"打开界面" → Orchestrator 从**凭据金库**取该容器账密 → 生成**一次性签名 token** → 经统一**接入网关（Caddy/反代）**做预认证（注入 BasicAuth 或会话）→ 前端 `iframe` 直接打开该容器 KasmVNC，用户无感免密。
- 网关按 RBAC（jeecg）校验"该用户能否开该容器"。

### 6.6 角色与技能管理（需求 1、9）
- 角色模型见 D7。jeecg 控制台维护"角色库"+"技能库"+"角色↔技能↔模型"绑定。
- 下发：jeecg 存配置 → Orchestrator 拉取 → 注入容器（system prompt / skill 文件 / 模型参数）。
- 统一装 agent/skill：复用 `app_manager.py` catalog；skill 走各 agent 自身机制（Claude skills、Hermes skills、MCP server）。

### 6.7 多智能体工作流编排引擎（需求 11）—— 串行 + 并行
> 这是 Orchestrator 的核心调度逻辑：让多个 agent 之间能串行、能并行、能混合。

**概念分层**：
- **Task** = 派给一个 agent 的一个工作单元。
- **Job/Workflow** = 一张任务图。基础复杂度 = **串行链 + 并行扇出/汇聚**（串行多个 Stage，Stage 内并行扇出 N 个 Task，Stage 末 join 屏障汇聚）。
- **⚠️ 修正（§2.5 场景 S1/S2 推翻"循环/条件后置"）**：真实场景需要 **① 审核回环（review-loop：产品经理↔美工多轮、审核不通过回退上一步）② 条件路由（conditional：S2"不能拦截则换下一个防空点"）③ 子编排/分层（sub-DAG：PM/防空指挥中心作为协调者角色，派活+汇总下级）**。故引擎从"仅串并行"升级为 **串并行 + 有界回环 + 条件分支 + 子编排**（仍自研 asyncio，有界回环设最大轮次防死循环）。**仍暂不做**通用图灵完备工作流 / 重型持久化（届时再评估 Temporal/Prefect）。
- **串行**：Stage N 依赖 Stage N-1，后者产物落 `/workspace/<job_id>/steps/<stage>/` 后，前者读其产物为输入。
- **并行**：同一 Stage 内多个 Task 并发派给不同容器/agent；**失败隔离**（一个并行分支挂不连累兄弟，记录后继续）；可配 fail-fast。
- **并发上限**：扇出并发受"在线容器数 + 资源配额"限制（见 §11 资源风险），超出排队。

**引擎选型**：**FastAPI + asyncio 自研轻量引擎**（与 §6.1 派活适配器、§6.4 共享工作区直接咬合；模型同 pipeline/parallel-barrier）。**否决** Temporal/Prefect/Airflow（本期串并行用不上其重型持久化/调度，徒增运维）。

#### 6.7a 编排引擎："用 Claude Code 源码搭" vs "自研"——决策（已与用户确认）
> 用户提出："任务编排是否用 Claude Code 开源源码搭建更靠谱/更智能？" 核实后的结论与取舍：

- **事实纠正**：**Claude Code 不是开源可 fork 的源码框架**（npm 包分发，无开放源码仓库）。官方可作底座的是三样：**Claude Agent SDK（Python/TS，同引擎封装）**、**headless `claude -p` CLI**、**Managed Agents（Anthropic 托管 agent loop + 每会话容器，自带多 agent coordinator/串并行/SSE/outcome）**。
- **⚠️ 关于"泄露源码 fork"（2026-03-31 事件，红线，见 §9）**：Claude Code 源码曾于 2026-03-31 因 npm 漏 `*.map` 意外泄露（~513K 行 TS），社区出现 `claude-code-fork/*`、重建可跑 fork、clean-room 重写等。**但这属 Anthropic 专有代码，泄露≠授权（官方已 DMCA 下架 8000+ 仓库），且泄露 fork 已被证实用于传播恶意软件。绝对禁止用于本产品**——法律(侵权/污染商用产品)+ 安全(供应链投毒，而 agent 直接碰代码与 API key)双重禁用。要开源用 OpenHands(§6.17)，要 Claude Code 能力用官方闭源 CLI 经 shim(§6.12)。
- **拆开两件事**：①「编排引擎」= DAG 调度器（谁先跑/谁并行/谁等谁/产物怎么传）=**传动机构**；②「节点上的智能」= NL→DAG 拆解 + 每个 agent 任务内部推理 =**大脑**。"确保智能"属于②，"编排"属于①，二者用不同东西。
- **否决"全建在 Claude 之上"当主调度器**：Claude 的 subagent / Managed Agents coordinator **只调度 Claude 子 agent**，不认识 Codex/Hermes/OpenClaw 容器、覆盖网、jeecg RBAC。把调度器做成 Claude 专属直接违背需求 #11「多智能体」与多厂商前提。Managed Agents 还是云端托管 + Claude-only，与"复制 KasmVNC 桌面容器 + 多厂商 + 免密开桌面"不兼容。
- **采纳：混合方案（C）**——
  - **传动机构**：FastAPI + asyncio **薄**自研 DAG 引擎（厂商中立的派活/心跳/屏障/流式聚合；代码量小）。
  - **大脑**：**Claude Agent SDK（Python，`claude-opus-4-8`）** 干两件最吃智能的事——① 把自然语言**拆成 DAG 草稿**（§6.7 的"两者结合"那步）；② 驱动 Claude 类 agent 任务本身。其它厂商由引擎用各自无头接口拉起。
- **为什么这才是成熟做法**：业界（含 Claude Code 自身的 subagent/工作流编排）都是"**确定性控制流 + LLM 只在节点与规划处**"，而非让 LLM 直接当调度器。混合 = 照成熟范式搭 + 把"智能"外包给官方 SDK；纯 LLM 当调度器反而更不可控、更贵、更难复现。
- **一句话**：调度器自研但**薄且确定**；智能（拆 DAG + Claude 执行）压在 **Claude Agent SDK** 上——既靠谱成熟，又不被锁死在单厂商。

**NL → DAG（用户确认"两者结合"）**：
1. 用户在对话框说自然语言（"把这三个库各自体检一遍再汇总成一份报告"）。
2. **Claude 分诊 + 规划**：拆成 Stage/Task 草稿（每个 Task 标注派给哪个昵称/角色、依赖关系）。
3. **用户可视化审/改**：指挥台渲染 DAG 草稿，用户微调（改派谁、加/删并行分支、调串并行）后确认。
4. 引擎执行。

**执行与回传**：
- 引擎维护任务状态机（pending→dispatched→running→done/failed）+ Stage join 屏障 + Job 终态。
- 每个 Task 的 stream-json/stderr/WS 事件经**事件总线**（§6.1）汇聚 → 指挥台渲染成**实时 DAG 进度树**（哪个节点跑着/done/挂了），直接打需求 6/7 的可视化。
- 产物经共享工作区跨 Stage/跨容器流转（串行传产物、并行各写子目录）。

### 6.8 智能体间直连通讯 A2A（需求 12）—— 数据直传，事件旁路上报
> A 处理完结果**不经指挥系统中转**直接交给 B。原则：**数据/消息直走 A→B，指挥系统不在路由路径上；但广播一份事件拷贝给指挥台，保住可观测+审计+DAG 可见性**（与需求 6/7 不冲突）。

**两条直传通道，分工明确**：
- **文件/成果物** → 走**共享工作区**（§6.4），A 写 B 读，**指挥系统完全不在路径上**。这本就是点对点，零新增。
- **消息/交接信号**（"我干完了，结果在 X，你接着干"）→ 走**消息总线 pub/sub**（用户确认）。

**消息总线选型**：**Redis Streams 或 NATS**。理由与拓扑适配——
- 容器 bridge 在覆盖网里只能**对外拨号**（§6.3b），容器间未必能直接 TCP 互连（尤其跨主机）。故"直连"工程上落成**各 bridge 都拨号连总线**：A `XADD`/publish 到 topic，B 订阅直接消费。**消息不经过 Orchestrator 的路由逻辑**（满足"不经过指挥系统传"），但靠总线送达、NAT 友好、可水平扩。
- 总线是**独立组件**（非 Orchestrator 进程），所以消息确实"不经过指挥系统"。

**旁路观测+审计（用户确认）**：指挥台**也订阅同一总线**（消费者组旁路），只读不转发——
- 实时把 A2A 消息映射成 DAG 进度树上的"A→B 交接"边，需求 6/7 可见性不丢；
- 全量 A2A 消息落审计（jeecg 审计表），出事可排查。

**通讯通道的权限治理（防止 A2A 失控）**：
- 在**通道授权层**做 RBAC（jeecg）：A 能不能给 B 发，在**建立通道/授权时**校验一次，**而非每条消息**（性能+解耦）。未授权的 topic 拒绝订阅/发布。
- 防环/防风暴：消息带 `job_id` + `hop` 计数 + TTL，超 hop 或超时丢弃并告警（见 §11）。

**与编排引擎（§6.7）的关系——两种交接并存**：
- **编排式交接**：DAG 引擎按依赖排好 A→B（B 在 A 的 Stage 完成后启动）——计划内、指挥台驱动。
- **直连式交接（本节）**：A 运行时**自主**决定把结果甩给 B，引擎不预先编排——动态、emergent 协作。
- 二者通过同一**事件总线 + 共享卷**统一观测；OpenClaw 自带的 node↔node WS 总线、Hermes 的 MCP server 模式可作为支持该模式的现成 A2A 子通道（按 agent 能力择优，不强求统一）。

### 6.9 容灾与自愈（需求 13）—— Orchestrator 从"派活器"升级为"控制器"

> 用户要求：某角色的 docker 挂了，**立即起一个相同职责的替身**。本质不是"重启进程"，而是"**让某角色始终有 N 个健康实例**"——这是**期望态协调（desired-state reconcile）**，正是 Orchestrator 该承担的控制器职责。

**期望态声明（在 jeecg/配置中心定义，存 Orchestrator DB）**：
```
role: 文档体检员
  image: chatop-headless:latest
  desired_replicas: 1          # 该角色期望几个健康实例
  nickname: docchk            # 单例角色昵称固定；多副本则 docchk-1/2…
  env/model/key: <引用配置中心 + 凭据金库>   # 复用 §6.2，替身配置一字不差
  restart_policy: always
  placement: {node: any | 指定节点}
```

**三层探活 → 三层恢复（从快到慢，能在低层解决就不惊动高层）**：
| 层级 | 探活手段 | 失败场景 | 恢复动作 |
|---|---|---|---|
| L0 进程级 | Docker `restart: unless-stopped` + healthcheck | agent 进程崩了但容器/主机还在 | Docker 原地拉起容器，**最廉价**，秒级 |
| L1 容器级 | **agent-bridge 心跳**（§6.3b，覆盖网现成）超时 | 容器死/卡死/bridge 断且 Docker 没救活 | Orchestrator 协调环判死 → **按期望态在同节点重建**一个同角色容器 → 复用 §6.3 生命周期 + §6.2 配置注入 → 重新注册昵称 |
| L2 节点级 | 节点级心跳/**主机 agent-bridge 失联** | 整台主机宕 | 协调环在**其它健康节点**重建该角色（需多机 + 共享卷 NFS/Ceph 落产物，§6.4） |

**协调环（reconcile loop，核心）**：
- Orchestrator 常驻一个循环：周期性比对**每个角色的"期望副本数" vs "总线上活着的实例数"**。
- 缺则补（按上表择层重建/改派），多则回收（僵尸容器清理）。
- 这是**幂等收敛**逻辑，与 K8s controller 同思想，但**轻量自研、跑在覆盖网上、不需要 K8s**（K8s 仍是 §8 的可选增强：规模大到需要调度策略时才上）。

**昵称/身份接管**：单例角色，替身**沿用同一昵称**；注册表把 `昵称 → 容器id` **重映射**到新实例，对话框/A2A 的寻址透明无感（喊 `docchk` 永远命中当前活实例）。

**在途任务重放（别丢活）**：
- 任务状态在 Orchestrator DB（§6.7 状态机）：跑在死容器上的 Task 标 `interrupted` → **重新入队**派给替身。
- 产物落**共享工作区**（§6.4，卷的生命周期长于容器），替身能看到死者已完成的中间产物，**断点续跑**而非从零。
- 要求 Task **幂等/可重入**（派活契约里带 `job_id+step_id`，重复执行不产生副作用）。

**冷备 vs 热备（按角色重要度选）**：
- **冷备（默认）**：挂了才拉替身（省资源，秒~十秒级恢复）。
- **热备（关键角色）**：`desired_replicas≥2` 常驻多实例 + 派活做负载/故障转移（零恢复时延，费资源）。
- 现状磁盘/内存紧张（§11.1），**默认冷备**；关键角色按需开热备。

**指挥中心自身的单点**：Orchestrator/总线/jeecg 本身别成 SPOF——本期单点 + 状态落盘（重启可恢复期望态），目标态做**主备（Raft/keepalived）**，列入 §11。

### 6.10 资源级访问授权（需求 14）—— 把"开界面/查系统"按用户或角色发

> 用户要求：把"**操作某容器的界面**"或"**查看某个系统**"分配给**某个用户**或**某个角色**。这是把 ChaCMD 做成**多租户控制台**——不同用户/角色登录只看得见、只动得了**被授权的那部分**。落在 jeecg RBAC 上扩一个"资源维度"。

**授权模型（三元组，复用 jeecg RBAC + 数据权限）**：
```
主体 Subject   = 用户  或  角色            （jeecg 已有 user/role）
资源 Resource  = 容器/agent  |  系统视图     （新增资源登记表）
动作 Action    = 查看(view-only) | 开界面操作(operate) | 派活(dispatch) | 改配(config)
授权 Grant     = (Subject) × (Resource) × (Action)
```
- **资源类型**：① 容器/agent 实例（按昵称/角色）；② "系统视图"——如某监控页、某容器只读桌面、某 DAG 看板、指挥大屏投墙。
- **查看 vs 操作分级**：`view-only` = KasmVNC **只读/共享会话不给控制权**（看得到画面、动不了鼠标）；`operate` = 完整控制权。"查看某系统"通常发 view-only，"操作容器界面"发 operate。

**与免密开界面（§6.5）的咬合——授权是开界面的前置闸**：
- §6.5 的预认证网关签发一次性 token **之前**，先查 §6.10 的 Grant：
  `当前登录用户 / 其角色  对  目标容器  有没有 (operate|view) 权限？`
- 无权 → 拒发 token，连桌面 iframe 都加载不了。**前端永远不直连容器**（红线 §9），授权判定只在服务端。

**与派活（§6.5/§6.7）的咬合**：对话框喊昵称派活前，同样校验该用户/角色对该 agent 有无 `dispatch` 权。无权的 agent 在用户的可选列表里**根本不出现**。

**落地复用**：jeecg 自带 RBAC（用户/角色/权限）+ **数据权限规则（数据规则）**，资源登记 + Grant 表用其低代码建模即可，**不自研一套权限引擎**。Orchestrator 与网关只做"问 jeecg 要判定结果"。

### 6.11 外部数据接入与感知（需求 15）—— 给容器装上"对外的眼睛和手"

> 用户要求：某容器可以**接外部的数据，拉数据或接数据，感知外部数据**。三个动词对应三种接入模式，统一汇入**数据面 + 事件总线**，让外部世界既能喂数据、也能**触发编排**。

**三种接入模式**：
| 模式 | 语义 | 实现 | 典型源 |
|---|---|---|---|
| **拉 Pull** | 主动去取 | 定时连接器（cron 轮询）：连 DB/HTTP API/对象存储/文件/RSS，取回→落共享工作区→发事件 | 业务库、第三方 API、网盘、Feed |
| **接 Push** | 被动收 | 常驻订阅端：webhook 接收器 / MQ·MQTT 消费者，收到即落工作区 + 发事件 | 上游 webhook、消息队列、IoT 上报 |
| **感知 Sense** | 数据变化触发动作 | 接入产生的**事件进事件总线** → 触发规则 → **拉起编排（§6.7）/通知 agent** | "新订单到了就分析"、"文件夹有新文件就处理" |

**架构落点——外部数据是入站数据面 + 事件源**：
- **运行位置**：接入能力做成**连接器（connector）**，既可作为**某容器内的一种 agent 能力**（用户说的"某个容器可接外部数据"），也可作为控制面的**共享数据接入网关**（多容器共用一类源时收口，避免每容器各连各的）。两种形态共存，按源是否专属选。
- **归一化落地**：拉/接回来的数据**归一化后写共享工作区**（§6.4），于是**任何被授权的容器/agent 都能消费**（天然打通 #4/#7 的容器间共享）。
- **感知 = 事件驱动编排**：外部数据事件进**统一事件总线**（与 #6 心跳/进度、#12 A2A 同一条总线，脊柱复用），Orchestrator 订阅后按**触发规则**（"匹配到 X 就跑工作流 Y / 派活给昵称 Z"）发起编排——这让 ChaCMD 除了"人在对话框派活"外，多出**"外部事件自动派活"**这条驱动路径。
- **凭据**：连外部源的 key/token/连接串走**凭据金库（§6.2）**，不落明文。

**安全（入站是攻击面，必须收紧，见 §9）**：
- webhook/API 拉取要防 **SSRF / 注入 / 投毒**：源白名单、出站目标白名单、速率限制、载荷大小/类型校验、对不可信数据做隔离沙箱解析。
- 外部数据触发编排前要过**信任分级**：低信任源只能触发只读/受限工作流，不能直接驱动高权限 agent。

### 6.12 统一模型网关（需求 16）—— 让 agent 接国内/本地模型，而不被锁死原厂 API

> 用户诉求：把"开源 claude code 部署到本地"以避免 **Codex / Claude Code 接不了国内模型**。先纠正前提，再给真正能达成目标的架构。

**前提纠正（已查证，§12 来源）**：
- **Claude Code 不是开源软件，没有"开源版"可 fork 部署**（§6.7a 已结论）。但**接国内模型根本不需要它开源**——它本就是本地运行的 CLI，只是默认连 Anthropic 云；认 `ANTHROPIC_BASE_URL` 环境变量，指向一个能转协议的网关即可接任意模型（含本地离线）。
- 用户口中的"开源 claude code"大概率指 **claude-code-router**（`musistudio/claude-code-router`，开源）——它专门把 Claude Code 路由到任意 provider。它是方案的一种，但不是唯一也不是最优（只服务 Claude Code）。

**真问题重定义**：不是"换一个 agent"，而是**在 agent 与模型之间统一插一层"模型网关"**，做①协议转换 ②路由/负载/fallback ③凭据收口。这正是需求 #10 配置中心缺的后半段——#10 管"谁用哪个逻辑模型"，模型网关管"逻辑模型 → 真实后端的协议转换与路由"。

**架构（网关挂控制面，作 #10 的执行后端）**：
```
agent CLI (Claude Code / Codex / Hermes / OpenClaw)
   │  只跟网关说话；配置中心给 agent 注入的是"网关 BaseURL + 网关签发的虚拟 Key"
   ▼
统一模型网关 (LiteLLM 主力)
   │  对上双协议端点 + 对下多后端适配；协议转换 + 路由 + 限流/计费/审计/fallback
   │  真实国内模型 Key 收口在网关 + 凭据金库(§6.2)，不下发到 agent/共享卷
   ▼
后端模型  ├─ 国内云: DeepSeek / 通义Qwen / 智谱GLM / Kimi / 豆包 / MiniMax
          ├─ 本地离线: Ollama / vLLM (开源权重，推理不出境)
          └─ 国外: Anthropic / OpenAI (可达时)
```

**网关对上暴露双协议**（关键——一个网关喂所有 agent）：
- **Anthropic `/v1/messages`** → 喂 **Claude Code**（`ANTHROPIC_BASE_URL`+`ANTHROPIC_AUTH_TOKEN` 指过来）。
- **OpenAI `/v1/chat/completions`** → 喂 **Codex / Hermes / OpenClaw** 等 OpenAI 格式 agent。

**各 agent 接入现状核实（含坑，§12 来源）**：
| agent | 接国内/自定义模型方式 | 坑 / 备注 |
|---|---|---|
| Claude Code | `ANTHROPIC_BASE_URL`+`ANTHROPIC_AUTH_TOKEN` → 网关 | ✅ 成熟；网关需出 Anthropic `/v1/messages` 协议 |
| Codex | `~/.codex/config.toml` 配 `[model_providers.x]` base_url | ⚠️ 默认走 OpenAI **Responses API**，国内模型多只会 **Chat Completions**，须显式 `wire_api="chat"`+`requires_openai_auth=false`；**直连不可靠 → 走网关更稳**（网关屏蔽协议差异） |
| Hermes | `-m` 换模型 + OpenAI 兼容 base_url | PyPI/Python，可配 |
| OpenClaw | OpenAI 兼容 provider 配置 | 自带网关，也可指到我们的统一网关 |

> 结论：四个一等派活 agent **都能经统一网关接国内/本地模型**；网关把每家 agent 的协议怪癖（尤其 Codex 的 Responses-vs-Chat）统一收口。

**选型（§8 有总表）**：
- **LiteLLM（Python，主力）**：同时吐 Anthropic + OpenAI 双协议，一个网关喂全部 agent；与 Orchestrator 同栈；100+ 模型 + key 管理/成本/限流/fallback。⚠️ **安全**：PyPI `1.82.7/1.82.8` 出过窃取凭据的投毒版本，**必须 pin 干净版 + Key 走金库不落明文**。
- **claude-code-router（Node，专用）**：只服务 Claude Code，但能"按请求类型分级路由"（日常用便宜模型、`think` 用强模型）省钱。可在 Claude Code 侧叠加。
- **new-api / one-api（Go，国内流行）**：国内模型聚合 + 计费管理强、有 Web 台，OpenAI 协议为主；可当二级后端。

**完全离线 / 数据不出境路径**（若有此诉求）：
- 网关后端挂 **Ollama / vLLM 跑开源权重**（DeepSeek-V3 / Qwen / GLM 开源版）。此时 agent CLI 本地运行 + 推理走"本地网关 → 本地模型"，**数据不出境**。
- 但 **Claude Code / Codex 的 CLI 二进制本身闭源**——若要求"连 agent 也开源可审计"，备选**真开源 coding agent**：OpenHands / Aider / Goose(Block) / Cline，可本地部署 + 接任意模型。**这是方案分叉点，待用户确认离线程度与是否要开源 agent**（见 §11）。

**与现有架构咬合**：网关是 #10 配置中心的执行后端；真实 Key 进凭据金库（§6.2）；调用日志进审计 + 计费（§9）；网关本身别成 SPOF，多实例 + 健康检查纳入容灾（§6.9）。

### 6.13 角色契约 Agent Charter（需求 18）—— 让每个角色"知道我是谁、要干啥、谁接力"

> 用户诉求：能定义每个角色的**系统提示词**、能用 **Hermes 等的技能**、**数据来了就知道自己要做啥**、**明确自己的目标**、**知道下一步把数据传给谁**。这五点统一收口为一份**声明式"角色契约"**——把"角色"从单纯能力标签升级成可执行的 Agent 定义，是 #1（角色）+ #9（技能/固定角色）+ #11（编排）+ #12（A2A 交接）+ #15（数据感知）的交汇。

**角色契约（声明式，存母体察元 RBAC/persona + 配置中心 #10）**：
```yaml
role: 数据清洗员
  identity:        { nickname: cleaner, 绑定容器/镜像 }          # 我是谁（#3 昵称）
  goal: "把原始数据清洗成结构化表，供分析员使用"                  # ← 明确自己的目标
  system_prompt: |                                              # ← 定义每个角色的系统提示词
    你是数据清洗员，只做清洗，不做分析。产出落 output/clean.csv …
  skills:                                                       # ← 用 Hermes 等的技能（复用，不自造）
    - hermes:data-clean            # 复用 Hermes 技能体系（§3.1：hermes -s 预加载）
    - mcp:<server>/<tool>          # 复用母体 MCP 工具（§3.5 chayuan mcp_server）
    - skillpack:<name>             # 统一装的 skill（#9）
  model_binding:   { via: 模型网关(#16), model: <逻辑模型名> }    # 关联 #10/#16
  knowledge_scope:                                              # ← 可查的知识源范围（#19，详见 §6.14）
    allow_types: [document, structured]    # 类型粒度：只给文档+数据库，不给向量
    allow_refs:  [doc:合同库, src:订单数据库]  # 具体库粒度
    default_action: search                 # 只读检索
  triggers:                                                     # ← 数据来了就知道要做啥
    - on: "workspace/<job>/raw/*.csv 出现"   then: 自启执行
    - on: "事件总线 topic=new-data 命中规则"  then: 自启执行     # 复用 #15 感知 / 脊柱总线
  handoff:                                                      # ← 知道下一步把数据传给谁
    - when: "清洗完成"   to: 分析员(昵称)   via: A2A总线+共享卷(#12)
    - on_error:          to: 指挥官         action: 上报/重试(#13)
```

**五点逐一对应实现**：
| 用户诉求 | 契约字段 | 落点 |
|---|---|---|
| 定义系统提示词 | `system_prompt` | 派活时注入各 agent（见下"注入"） |
| 用 Hermes 等技能 | `skills`（引用，不复制） | 复用 Hermes `-s` 技能 / 母体 MCP 工具 / 统一 skillpack（#9） |
| 明确自己的目标 | `goal` | 渲染进 system prompt + 任务上下文头部 |
| 数据来了就知道做啥 | `triggers` | 共享卷 watch / 事件总线规则（#15 感知 + 脊柱总线）触发自启 |
| 知道下一步传给谁 | `handoff` | 静态声明 next-hop → A2A 总线/共享卷（#12）；可附动态决策 |

**契约 → 各 agent 的"注入"（关键实现点，各 agent 机制不同，派活适配器负责翻译）**：
- **Claude Code**：`--system-prompt`（或 CLAUDE.md/settings）注入 prompt；skills 经其 skill 机制；模型经 Anthropic-shim 指母体网关。
- **Codex**：`AGENTS.md` / config 注入；OpenAI 协议指母体网关。
- **Hermes**：`-s` 预加载技能 + `-m` 选模型 + prompt 注入（§3.1 核实，天然契合"角色+技能"）。
- **OpenClaw**：agent 定义 + provider 配置注入。
> 即：**一份统一契约，N 种注入翻译**。这与"真复用"原则一致——技能引用 Hermes/MCP 现成体系，不自造一套技能运行时。

**两种交接并存（呼应 §6.8）**：
- **静态声明式 handoff**：契约里写死 `to: 分析员`——可预测、可审计，编排式（#11 DAG 的边可由各角色 handoff 自动拼出）。
- **动态自主 handoff**：agent 运行时按产出内容**自主决定**传给谁（LLM 决策，emergent），仍经 A2A 总线送达 + 旁路审计（#12）。

**数据驱动闭环（"数据来了就知道做啥"的完整链路）**：
```
外部数据接入(#15) 或 上游 agent 产出
   → 落共享卷 / 发事件总线(脊柱)
   → 命中某角色 trigger
   → 该角色据 goal + system_prompt + skills 自主执行
   → 按 handoff 把结果传给下一个角色(A2A #12)
   → … 直至 Job 终态，结果回对话框(#7)
```
这让系统从"**人在对话框逐个派活**"升级为"**角色按契约自驱动的流水线**"——指挥官（母体智能体）只需下发目标与初始数据，角色们各自感知、执行、接力。

**复用母体**：角色契约的存储/管理优先复用察元 **persona（`admin/persona.py`）+ RBAC 角色 + chat/graph 的 agent 定义**（具体复用点 Phase 实现时核实，避免重复造角色体系）；契约里的"资源/技能可见性"受 #14 资源级授权约束。

### 6.14 知识源查询范围与权限（需求 19）—— 给每个智能体划定"能查哪些库"

> 用户诉求：**知识库能向智能体分配查询范围（文档类 / 数据库类 / 向量库类等），并制定知识库查询权限**。本质是把"知识源"作为一种**受控资源**，按主体（智能体/角色）授权。这是 #14（资源级授权）+ #17（母体知识库）+ #18（角色契约）的交汇。
>
> **核实结论（2026-07-01，文件级查证）**：察元授权**骨架可复用，但需三处扩展（中等工作量）**，并非"零新造"。可复用：类型枚举 1:1 对得上、泛化主体表骨架、检索期 authz 管线（主体由传入 user dict 驱动是关键复用点）。需扩展：① 主体加 `agent`；② 结构化/向量**源侧授权**当前只认 user_id，要泛化到 agent；③ **类型级授权数据模型缺失**，必须新建或在授权服务里展开成多条具体 grant。详见下文与 §3.6 Phase 0 结论。

**授权模型（三元组）**：
```
主体 = 智能体/角色（角色契约 #18）   ← 察元 kb_subject_grant 已是 subject_type+subject_id 泛化，加 'agent' 即可
资源 = 知识源，两级粒度：
   · 类型粒度：document(文档) | structured(数据库) | vector(向量库) | image(图像) | office(办公)
   · 具体库粒度：doc:<kb> | src:<structured_id> | src:<vector_collection> | office:<owner>
动作 = 查询(reader)；察元当前仅 reader/editor，细分 read/aggregate 需另扩
```

**两级粒度对应察元统一知识源体系（已核实，`knowledge_source/types.py::SourceKind` + `retrieval/query/refs.py::normalize_kind`）**：
| 用户说的"类" | 察元 SourceKind / 寻址 | normalize_kind → | adapter |
|---|---|---|---|
| 文档类 | 平台托管 KB / `doc:<name>` | `document` | `adapters/document.py` |
| 数据库类（结构化） | `SQL/MONGO/ES` / `src:<id>` | `structured` | `adapters/structured.py`（text2sql） |
| 向量库类 | `VECTOR/VS` / `src:<id>` | `vector` | `adapters/vector.py` |
| 图像类 | （图像源） | `image` | `adapters/image.py` |
| 办公类 | `office:<owner>[:<group>]` | office | office 检索 |
> ⚠️ 陷阱（已核实）：**文档类（平台托管 KB，`doc:`）与向量库类（外部向量集合 VS，`src:`）是两套存储 + 两套授权表**，别把二者混为一类，否则授权会分裂。

**检索时如何生效（已核实察元真实机制，非"静默过滤全集"）**：
- 察元检索是**"调用方显式传 `ku_ids`，服务端 `orchestrator` 逐个 `assert_readable(subject, ref)`，无权即 403"**的硬门禁（`retrieval/query/{orchestrator,authz}.py`）；`GET /knowledge-bases`（`kb_query/authz.py::list_readable_items`）才是"列举主体可读集合"。
- 故 `knowledge_scope` 落地分两步：① ChaCMD 先用 `/knowledge-bases` 拿该 agent **可读集合**（或按 `knowledge_scope` 解析）→ 作为可选 `ku_ids` 池；② 检索时只传池内 `ku_ids`，由 `assert_readable` 兜底把关。引用（citation）只来自授权源，可溯源到具体库。
- **主体注入（关键）**：察元授权完全由"传入的 user dict"驱动，`SearchRequest` 当前**不暴露**授权主体字段，但有现成先例——`openapi_routes.py::_spec_to_user(app)` 合成 `{"id":"app:<id>","role":"app"}`，`access.py::kb_access_for` 检测 `is_app_user` 即短路到 `app_acl`。**注入 `{"id":"agent:<id>"}` 主体架构上可行**，要么复用 app 账号合成路径，要么给 kb-query 加**受信主体上下文**（只能服务端可信注入，不可外部冒充）。

**与现有约束咬合**：
- `ku_ids` 是知识源真源（已核实 `SearchRequest` 选源参数确为 `ku_ids`，非 `kb_names`）；`knowledge_scope` 本质是**限定一个 agent 能用哪些 `ku_ids`**。
- `synthesize` 默认 True 会额外调 LLM 综合，只取原始命中要显式传 `false`。
- 红线（§9）：**无授权不得访问任何 KB/source**；`src:*` 不当普通文档 KB；查询阶段不接受外部 embedding 模型（跟随库索引配置）。

**三处必须扩展（已核实，工作量中等；走 §3.6 上游化+flag）**：
1. **主体加 agent（小）**：`kb_grant_repository._SUBJECT_TYPES=("user","role","dept")` 写死，加 `"agent"`；`access.py` 增 agent 解析分支（仿 `is_app_user` 短路）。
2. **源侧授权泛化（中）**：结构化/向量源走 `source_access.py` + `SourceAccessGrantModel`，**当前只认 `user_id`**（无 role/dept/app/agent）。不扩则 **agent 只能管"文档类"，管不了"数据库类/向量库类"**——这条对本需求是硬伤，必须补。
3. **类型级授权（中）**：察元授权**只能按具体 `kb_id/source_id`**，无"按类型/分类"字段。实现"给某 agent 授文档类全部"要么新建类型级授权表/规则，要么在授权服务里把"类型"**展开成多条 per-resource grant**（ChaCMD 侧展开是低风险起步路径）。

### 6.15 指挥大屏（ChaCMD 主页 / homeComponent）设计

> ChaCMD SKU 的全新主页（§3.7 注入点②的 `homeComponent`）。**定位：指挥官（人 + 母体智能体 #17）的驾驶舱（Command Cockpit）**——一屏统揽"态势 / 任务 / 数据 / 资源"，并**直接下令**。不是欢迎页，是作战指挥中心。它是 #5/#6/#11/#12/#13/#15/#18/#19 等能力的 **UI 汇聚投影**。

**五条设计原则**：
1. **态势感知优先**：一眼看清全局健康 + 在办任务（谁在、在干嘛、干得怎样）。
2. **对话即指挥**：自然语言 / @昵称派活是核心入口，常驻可达（#5）。**复用察元 chat composer 组件**（真复用，不自造 mini 版）。
3. **全实时**：所有 widget 走**统一事件总线**（脊柱）SSE/WS 流式刷新（#6），复用察元 SSE 基建 + `packages/transport`。
4. **可下钻（三层信息密度）**：L0 一眼（顶栏 KPI + 告警红点）→ L1 扫视（三栏态势卡片）→ L2 下钻（点开详情/日志/免密开桌面 #8）。
5. **双模式**：交互驾驶舱（默认）/ 投墙只读大屏（全屏、深色、放大关键指标、自动轮播）。

**布局（已定形态：中央默认集群拓扑 + 对话优先 + 投墙双模式）**——两种模式共用同一套 widget，仅焦点重排：

**模式 A — 驾驶舱（默认，可交互，对话优先）**：指挥对话框居中为焦点；态势（拓扑默认，可切任务流）与情报环绕四周。
```
┌────────────────────────────────────────────────────────────────────────┐
│ 顶栏 ChaCMD | KPI:容器N·任务M·告警K·网关OK | [🏠察元工作台] | 时间 | 用户 │ #3/#6/#13/#14/#16
├──────────────┬───────────────────────────────────┬───────────────────────┤
│ 左 智能体编队 │        ★中央焦点 = 指挥对话框★       │ 右 实时事件流(脊柱投影)│
│ · 昵称+头像   │   ┌─────────────────────────────┐   │ · A2A 交接            │
│ · 角色+状态   │   │  [说个任务 或 @昵称…]   [发送]│   │ · 心跳/容灾告警(挂→替身)│
│ · 健康/负载   │   └─────────────────────────────┘   │ · 外部数据事件到达     │
│ 点开→免密开桌 │   近期回执/结果流(#7)               │ · 越权拦截 / 审计流    │
│ 面/契约/知识域│   ┌─────────────────────────────┐   │  (分类可过滤)         │
│ (拓扑缩略,可 │   │ 态势主视觉: 集群拓扑(默认)   │   │                       │
│  切任务流)    │   │  ↔ 任务流 DAG (切换)         │   │                       │
│ #1/#3/#13/#18 │   └─────────────────────────────┘   │ #9/#12/#13/#14/#15    │
├──────────────┴───────────────────────────────────┴───────────────────────┤
│                          #5/#7/#17 对话即指挥                              │
└────────────────────────────────────────────────────────────────────────┘
```

**模式 B — 投墙只读大屏（一键切换，挂墙监控）**：**集群拓扑（默认）铺满**，对话框收起；全屏深色、放大关键指标、多视图自动轮播。
```
┌────────────────────────────────────────────────────────────────────────┐
│  ChaCMD 指挥中心   容器 12/12 在线 · 3 任务在办 · 0 告警 · 网关 OK   14:22 │
├────────────────────────────────────────────────────────────────────────┤
│                    ★集群拓扑铺满(默认) ↺ 轮播 任务流/事件★                 │
│              【母体智能体】                                                │
│          ╱      │      ╲                        右上角滚动: A2A/告警/数据 │
│  [cleaner]  [analyst]  [writer] …                                         │
│    ●健康      ●忙       ⚠挂→已起替身(#13)                                  │
└────────────────────────────────────────────────────────────────────────┘
```
> 两模式天然分工：驾驶舱=指挥官坐着**对话下令**（对话居中）；投墙=无人值守**只读监控**（拓扑铺满）。"集群拓扑为默认"贯穿两模式的态势主视觉；"对话优先"只作用于驾驶舱。

**各分区 × 需求 × 数据源**：
| 分区 | 内容 | 需求 | 数据源（复用） |
|---|---|---|---|
| 顶栏 KPI | 容器在线/在办任务/告警/网关健康 | #6/#13/#16 | Orchestrator 聚合 + 事件总线 + 察元 `/v1/providers` |
| 左 智能体编队 | 每 agent 卡：昵称+角色+在线/忙/挂+当前任务+负载；点开下钻 | #1/#3/#13/#18 | 注册表 + 心跳(§6.3b) + 察元 `/api/v1/external-agents/{id}/status` |
| 中央 任务流视图 | 在办编排 DAG 实时进度树（节点=Task/角色，A2A 交接边） | #5/#6/#11/#12 | 编排引擎(§6.7) + 事件总线 |
| 中央 拓扑视图 | 节点=容器/母体，连线=数据流/A2A，色=健康（可切换） | #12/#13 | 覆盖网(§6.3b) + A2A 总线(§6.8) |
| 右 事件流 | A2A 交接 / 容灾告警 / 外部数据到达 / 越权 / 审计 | #9/#12/#13/#14/#15 | **统一事件总线**（脊柱，四类事件同一条） |
| 中央焦点 指挥对话框（驾驶舱模式） | NL 派活 + @昵称定向 + 母体智能体自答/自干 | #5/#7/#17 | 复用察元 chat composer + Orchestrator 派活 |
| 中央 态势主视觉 | **集群拓扑（默认）↔ 任务流 DAG（可切）**；投墙模式铺满 | #5/#6/#11/#12/#13 | 覆盖网(§6.3b)+编排(§6.7)+A2A(§6.8)+事件总线 |
| （浮层）数据感知 | 外部源接入状态 + 触发规则命中 | #15 | 数据接入层(§6.11) |

**下钻动作（L2）**：容器卡 → **免密开 KasmVNC 桌面**（iframe，§6.5）；任务节点 → DAG 详情 + 流式日志；角色 → **角色契约编辑器**（#18）；知识域 → 知识源范围（#19）。

**大屏 ↔ 察元工作台 双向入口（用户诉求：大屏放个菜单/按钮进入察元现主页）**：
- 母体即察元，**察元原有整套工作台（HomePage/chat/kb/settings/admin…）在基座里始终可达**（§3.7 注入点②：ChaCMD 只新增 `/command` 大屏，不动察元 `/home`）。
- **大屏 → 察元**：指挥大屏顶栏放一个 **`🏠 察元工作台`** 菜单/按钮，点击 `navigate('/home')` 进入察元现主页（整套原界面原样可用）。
- **察元 → 大屏**：察元工作台侧边栏（Chrome/Sidebar）加一个 **`指挥大屏`** 入口（仅 ChaCMD SKU 显示，经 `BrandConfig.navItems` 注入），点击回 `/command`。
- 两个入口都是**同一前端 app 内的路由跳转**（非跨应用/非新窗口），零额外进程、状态无缝；纯察元 SKU 不出现"指挥大屏"入口（navItems 未注入）。

**技术实现（结合 §3.7）**：
- 位置：`packages/chacmd-features/dashboard/CommandDashboard`，作 ChaCMD SKU 的 `homeComponent`（注入 seam ②）。
- UI：`@chayuan/ui` 组件 + design-tokens 的 **ChaCMD 深色指挥风 theme**（经 BrandConfig 覆盖）。
- 图可视化：DAG / 拓扑用成熟库（React Flow / `@xyflow/react`）。
- 对话框：**直接复用察元 chat composer / 会话组件**（配置成"指挥"语境），杜绝自造 mini 版。
- 实时：每个 widget 订阅事件总线主题；无数据时优雅降级，不阻塞首屏。

> **一句话**：指挥大屏把"分散在 #5/#6/#11/#12/#13/#15/#18 的能力"收敛成**一块驾驶舱玻璃**——左看编队、中看战况、右看情报、下达命令，点哪下钻哪。

### 6.16 新建任务（Job 创建）：数据模型与流程

> 用户诉求：新建任务要**全面**——任务名称、任务代号、工作任务目录、智能体选择与创建等。"新建任务"= 创建一个 **Job**（一次完整工作，可单 agent 单步、也可多 agent 串并行）。它是 #2/#3/#4/#5/#11/#15/#18/#19 的汇流点，是指挥大屏最高频的动作。

**三级标识（分清"显示名 / 人友好别名 / 系统主键"，最佳实践）**：
| 字段 | 例 | 用途 | 生成 |
|---|---|---|---|
| **任务名称 name** | "Q3 财报分析" | 人读、列表展示 | 用户填 |
| **任务代号 code**（slug） | `q3-fin-report` | 工作目录名、事件总线 topic、A2A 寻址、URL、日志前缀 | 从 name 自动生成（拼音/翻译，可改）+ **唯一性校验** |
| **job_id** | `job_01H…`（雪花/UUID） | 系统主键、跨表引用、状态机 | 系统生成 |

**Job 完整字段（分组，覆盖"等等"）**：
| 组 | 字段 | 说明 / 关联 |
|---|---|---|
| 标识 | name / code / job_id | 见上 |
| 目标 | **goal 描述（必填）** + 输入 | goal 叠加在角色 system_prompt(#18) 之上；输入=上传附件→`input/`、引用知识库 `ku_ids`(#19)、绑定外部数据源(#15) |
| **工作目录** | `workspace`（名=code） | **容器内固定 `$HOME/<code>`**（即 `/home/<user>/<工作目录名>`），所有参与容器同名、任务开始时建、agent 产出全落此；**挂载到共享卷 `/workspace/<job_id>/`** → 跨容器统一(#4)+A2A 直传(#12)+结果回收(#7)；结构 `input/ output/ refs/ steps/ logs/`（§6.4）；新建即 mkdir/mount + 授权(#14) |
| **智能体** | assign_mode + 编排 | 见下"智能体选择四档" + 多 agent→DAG(#11) |
| 资源 | model / knowledge_scope / 预算 | model 经网关(#16) 默认跟契约；knowledge_scope(#19) 默认跟契约、可临时收窄；token 预算 / 超时 / 重试次数 |
| 触发 | trigger | 立即 / 定时 cron / 事件触发（外部数据到达 #15 或上游 Job 完成） |
| 交接 | handoff | 多 agent 时 Task 完成后交给谁（DAG 边 或 角色契约 handoff #12/#18） |
| 治理 | owner / 可见性 / 优先级 | owner + 授权哪些用户/角色可见可管(#14)；调度优先级；自动审计(#9) |
| 状态 | status | draft→queued→running→done/failed/cancelled（§6.7 状态机） |

**智能体选择——四档（从省心到精确）**：
1. **智能调度（默认）**：不指定，**母体智能体按 goal + 能力画像 + 负载/健康 智能路由**到合适 agent（#5，复用察元 `chat/graph` supervisor）。
2. **指定角色**：选一个角色契约(#18)，系统按容灾/负载挑一个该角色的健康实例（无则起一个）。
3. **指定昵称**：直接点编队里某个在线 agent（@昵称）。
4. **即时新建**：没有合适的 → **内联创建新智能体**（下）。

**内联"创建智能体"子流程（#2/#3/§6.3，新建任务里可直接拉起）**：
形态（桌面型 KasmVNC / 无头型）→ 基镜像 + 装哪些 agent CLI(claude-code/codex/openclaw/hermes)/应用 → 昵称 → 绑角色契约(system_prompt/skills/goal/knowledge_scope/model) → 端口/用户名/密码/权限(#2) → placement 放哪台主机（经主机 agent-bridge 本地 Docker，D6）→ 起容器 → bridge 反连 → 注册入编队。也可"仅创建不派活"（独立入口），任务里再选。

**多 agent 编排（#11）**：单 agent 任务选一个即可；多 agent 任务定义 Stage(串行)+Stage 内 Task(并行)+依赖，每 Task 指派 agent/角色。DAG 可**手工搭**，也可 **NL→DAG 自动拆**（母体 supervisor 生成草稿→用户可视化审改，§6.7"两者结合"）。

**两种入口（呼应指挥大屏"对话优先"）**：
- **对话式（快）**：大屏中央对话框直接说"让 cleaner 清洗这批数据再让 analyst 分析" → 母体智能体解析出 **Job 草稿**（自动填 name/code/agent/DAG）→ 用户确认/微调 → 执行。
- **表单式（全）**：点 `+ 新建任务` → 结构化向导（标识/目标/目录/智能体/编排/资源/触发/治理）。适合复杂、可复用、需精确控制的任务。
- **两者结合**：对话式生成草稿 → 落表单补全审改 → 执行（同 §6.7 NL→DAG）。

**字段自动化（降填写负担）**：code 从 name 自动生成、目录自动按 job_id 建、agent 不选则智能调度、model/knowledge_scope 默认跟角色契约——**只有 goal 必填**，其余皆有默认。

**创建后**：Job 进指挥大屏任务流 DAG，实时反馈(#6)；各容器产出落各自 `$HOME/<code>`（挂共享卷）；**指挥中心汇总**各容器/各 Stage 产出成 Job 级结果 `result/`，聚合回对话框 + 大屏(#7，§6.4"指挥中心汇总")；全程审计(#9)。

**复用落点**：NL 拆解=察元 `chat/graph` supervisor；容器创建=Docker SDK 经主机 bridge(D6)+复用 `app_manager`；知识域=kb-query(#19)；模型=网关(#16)；Job/状态机/DAG=ChaCMD 编排引擎(§6.7)；表单/向导 UI=`packages/chacmd-features`。

> **工作目录（用户已定机制）**：容器内固定 **`$HOME/<code>`**（`/home/<user>/<工作目录名>`），同名、任务起时建、产出全落此；挂载到共享卷 `/workspace/<job_id>/` 实现跨容器统一（§6.4）。故 `code` 即工作目录名（人可读、唯一），job_id 仅用于共享卷后端寻址。
>
> **一个我已做主推、你可推翻的决策点**："创建智能体"**既是独立入口、也可在新建任务里内联**——也可强制分开。

### 6.17 实时开发部署智能体（Dev Agent）—— 开源、接国内/本地、离线可跑

> 用户诉求：要一个能**实时开发+部署应用、把过程反馈给指挥中心**的智能体，能接 DeepSeek/千问/本地 Ollama/vLLM、**离线可跑**；并再问"开源的 claude code 是哪个"。

**先澄清（第三次）**：**没有"开源版 Claude Code"，Claude Code 闭源不可 fork**（§6.7a）。要"开源 + 接国内/本地/离线 + 自主开发部署"的编码 agent，**首选 OpenHands**（已核实，§12 来源）。

**选型对比（已核实）**：
| agent | 开源 | 接国内/本地/离线 | 自主开发+部署 | 无头事件流 | 定位 |
|---|---|---|---|---|---|
| **OpenHands（首选）** | ✅ MIT(68k★) | ✅ LiteLLM 接 DeepSeek/Qwen/**Ollama/vLLM**/SGLang/llama.cpp，本地即离线 | ✅ **自带 Docker 沙箱运行时**能写码+跑+构建+部署 | ✅ `--headless --json` JSONL(Message/Action/Observation) | 全自主"AI 软件工程师"，最匹配"实时开发部署" |
| **OpenCode**（纯代码备选） | ✅ MIT(178k★) | ✅ 75+ providers(含本地) | ⚠️ 纯代码编辑，**无自带沙箱/浏览器/部署**；LSP 诊断反馈 | ✅ **`opencode serve` OpenAPI 3.1 server**(接口最规整) | 纯编码/审查/重构；"起界面看预览"要外部拼装 |
| **Hermes**（协调者，非执行器） | ✅ | — | ❌ 自己不直接开发 | 无头模式 | **上层自主壳**：经 skill **委托** OpenHands/OpenCode/Claude Code 当子 agent；当 S1 项目经理/协调者角色(#18 管理者角色) |
| Claude Code（备选，闭源） | ❌ | ✅ 经 Anthropic-shim 指母体网关(§6.12) | ✅ | ✅ stream-json | 体验强但闭源；要开源则不选 |
| Aider / Goose | ✅ | ✅ 接 Ollama | 偏结对改码，沙箱/部署/事件流弱于 OpenHands | 部分 | 轻量备选 |

**针对"自动开发界面 + 调整 + 部署 + 指挥中心看预览"——OpenHands 执行器 + Hermes 协调者**：
- **调整界面（需 agent 看渲染结果）**：OpenHands **自带浏览器自动化 + 能起 web app**，可访问自己做的界面；**诚实标注**：交互式浏览器(#4389)、截图分享(#8372) 仍是 open issue，"全自动视觉迭代"随 OpenHands 演进，近期更稳为"起服务→人在大屏预览→反馈"半自动。OpenCode 只有 LSP 文本诊断、无视觉。
- **部署 + 预览**：OpenHands **自带 Docker 沙箱**起服务 → 经 Caddy/网关 **iframe 指挥大屏免密预览**(#8/§6.5)；OpenCode 无 runtime，需外部配合。
- **反馈指挥中心**：两者皆有编程接口（OpenHands JSONL 事件流 / OpenCode OpenAPI server），都好接事件总线。
- **分层组合（呼应 §2.5 分层指挥修正）**：**Hermes/项目经理协调者** 委托 **OpenHands**(界面开发+部署+预览) 与/或 **OpenCode**(纯代码任务)——即 S1"项目经理→开发工程师"的落地。

**Dev Agent 容器设计**：
- **形态**：无头开发容器 = OpenHands + 其 Docker 沙箱运行时（构建/运行/部署代码）；容器内 Docker 用 DinD 或经主机 agent-bridge 的 sibling-docker（D6）。
- **接模型（统一走母体网关，不各配 key）**：OpenHands 经 LiteLLM 指向**母体模型网关（#16 察元 gateway，OpenAI 兼容）** → DeepSeek/Qwen/Ollama/vLLM；**离线** = 网关后端挂本地 Ollama/vLLM（§6.12 离线路径），全链路不出网。
- **实时开发-部署-反馈闭环**：OpenHands `--headless --json` 的 JSONL 事件 → agent-bridge 转发**统一事件总线** → 指挥大屏任务流节点 + 实时日志流（#6）；部署产物（预览 URL / 服务端口）→ 指挥大屏**免密打开**（#8 iframe）看运行效果。产物落 `$HOME/<code>`（§6.4）汇总回中心（#7）。
- **角色**：即 S1 的"开发工程师"、S6 的加工 agent；角色契约(#18) 绑 OpenHands + 逻辑模型 + skill/knowledge_scope。

**与 P0 的关系**：P0 的"开发工程师"角色即用此 Dev Agent；先证伪"母体派开发任务 → Dev Agent(OpenHands) 接国内/本地模型写码+跑 → JSONL 事件流实时回大屏 → 产物汇总"。

### 6.18 子容器（Agent 工作站 = 本 chatop-ai 容器）内置能力清单与实现子任务

> 把全部需求/场景**投影到子容器侧**：作为一个功能完整的"容器内智能体节点"，**本容器（chatop-ai KasmVNC 镜像）镜像里必须内置什么**。职责边界：**母体（察元）= 指挥/网关/知识库/RBAC/汇总；本容器 = 被派活、执行、回传的 agent 工作站**。以"桌面型 agent 工作站"为完整基线（无头型是其裁剪子集，去掉 G 桌面组）。

**内置能力清单（能力 → 为什么/需求 → 现状 → 优先级）**：
| 域 | 能力 | 对应需求/场景 | chatop-ai 现状 | 级 |
|---|---|---|---|---|
| **A 接入控制** | **A1 agent-bridge 常驻服务**：反向 WS 连回中心 + 心跳注册 + 收派活指令 + 回传事件/结果 | 集群/#5/#6/#13 | ❌ **缺（核心）** | P0 |
| | A2 健康探活 + 断线重连 + 僵尸回收 | #13 | ❌ 缺 | P0/P1 |
| | A3 配置/契约注入通道：bridge 拉中心配置写 env/文件（网关 BaseURL+虚拟 Key、角色契约、knowledge_scope） | #10/#16/#18/#19 | ❌ 缺 | P0 |
| **B Agent 运行时** | B1 一等 agent 运行时：**OpenHands(Dev)** + Claude Code/Codex/OpenClaw/Hermes | #5/§6.17/S1·S6 | ⚠️ CLI 已预装(openclaw/codex/claude-code/hermes)，**缺 OpenHands** | P0 |
| | B2 输出→事件流适配：OpenHands JSONL / claude stream-json / codex stderr → 统一事件 | #6 | ❌ 缺 | P0 |
| | B3 角色契约→各 agent 注入翻译（--system-prompt / AGENTS.md / hermes -s） | #18 | ❌ 缺 | P0/P1 |
| **C 工作空间** | C1 工作目录：任务起时建 `$HOME/<code>` + 挂载共享卷 | #4/#7 | ❌ 缺 | P0 |
| | C2 共享卷 client（NFS/CephFS，多机） | #4 Phase2 | ❌ 缺 | P2 |
| | C3 成果物回收/汇总上报（bridge 报 output/） | #7 | ❌ 缺 | P0/P1 |
| **D 模型接入** | D1 模型网关对接：agent base_url/key 指母体网关（A3 注入） | #16 | ❌ 缺 | P0 |
| **E 知识/技能** | E1 kb-query / MCP client：agent 查母体知识库（带 scope） | #19 | ❌ 缺 | P1 |
| | E2 技能运行时：Hermes skills / MCP client 连母体 mcp_server | #9/#18 | ⚠️ Hermes 有，MCP client 待接 | P1 |
| **F 协作 A2A** | F1 消息总线 client（Redis Streams/NATS 收发信令） | #12 | ❌ 缺 | P1/P3 |
| | F2 文件直传（共享卷，已由 C1 解决） | #12 | ✅（随 C1） | P0 |
| **G 桌面界面**（桌面型） | G1 KasmVNC + Caddy 单端口 | #8 | ✅ **已有** | — |
| | G2 一次性 token 预认证接入（中心签发免密开） | #8/§6.5 | ❌ 缺 | P2 |
| | G3 Dev 起服务预览：web app 端口 → Caddy 暴露 → 中心 iframe | §6.17 | ⚠️ Caddy 有，暴露规则待加 | P2 |
| | **G4 员工视图服务**：容器常驻自省工作台（我的状态/成果/所有任务工作记录），本地实时 + 反查中心历史 | §10.3 | ❌ 缺 | P1 |
| **H 部署**（Dev） | H1 容器内 Docker（DinD 或经主机 bridge sibling-docker） | §6.17/S1 | ❌ 缺 | P2 |
| | H2 构建/运行工具链（node/python/git…） | §6.17 | ⚠️ 部分（视镜像） | P0/P1 |
| **I 人机学习**（S7） | I1 操作录制 → 技能提炼 → Hermes 自进化写回契约 | S7 | ❌ 缺 | P3 |
| **J 安全** | J1 最小权限沙箱 / 凭据不落明文 / Docker socket 不暴露 / bridge 白名单 | #9 | ⚠️ 部分 | 贯穿 |

**实现子任务分解（容器内智能体内置，按 P0→P3 排序）**：
- **P0 — 最小 agent 节点（能被派活+执行+回传）**
  - **T1 agent-bridge 常驻服务**（A1/A2）：反连 WS + 心跳 + 收指令 + 回传；以 systemd/supervisor 内置镜像、随首启启动。
  - **T2 配置/契约注入**（A3/D1/B3 最简）：bridge 拉中心配置 → 写 `ANTHROPIC_BASE_URL`/`OPENAI_BASE_URL`+虚拟 Key + 落角色 system_prompt。
  - **T3 工作目录机制**（C1）：派活时 `mkdir $HOME/<code>` + bind/挂载共享卷。
  - **T4 内置 OpenHands**（B1/H2）：镜像装 OpenHands + 其 Docker 运行时依赖 + node/python/git；bridge 能拉起 `openhands --headless --json`。
  - **T5 事件流适配**（B2/C3）：OpenHands JSONL / claude stream-json → 统一事件 → bridge 回传 + output/ 上报。
  - ✅ **P0 验收**：中心派开发任务 → 容器 OpenHands 接国内/本地模型干活 → JSONL 实时回中心 → 产物落 `$HOME/<code>` 汇总。
- **P1 — 多 agent 协作 + 知识 + 技能**
  - T6 kb-query/MCP client（E1）；T7 技能运行时 + MCP 连母体（E2）；T8 A2A 总线 client（F1）；T9 契约完整注入 + 多 agent 齐全（B3）；T10 健康/重连/僵尸回收完善（A2）。
- **P2 — 界面预览 + 部署 + 授权 + 多机**
  - T11 一次性 token 预认证接入（G2）；T12 Dev 起服务预览 → Caddy 暴露 → 中心 iframe（G3）；T13 容器内 Docker DinD/sibling（H1）；T14 共享卷 NFS/CephFS client（C2）。
- **P3 — 高级**
  - T15 操作录制→技能提炼（人机学习 I1/S7）；T16 安全加固收口（J1 全面）。

**功能完整性自检**：A~J 覆盖 19 需求在容器侧的全部投影 + 7 场景所需（S1 开发=B1 OpenHands、S2 实时=A1 bridge 低延迟+F1、S4 定时=中心触发+B、S5 度量=B+E1、S6 视频=B+H、S7 云桌面=G+I1）。**唯一不在本容器的**：模型网关/知识库/RBAC/汇总（在母体，本容器只做 client/被汇总）。

### 6.19 主机纳管与部署编排（主机接入 → 自动部署 → 通讯 → 在线检测 → 装应用/技能）

> 用户诉求：主机接入后自动把基础容器 + 智能体容器部署上，容器与指挥平台通讯打通，指挥中心检测在线，并给容器装应用/技能。

**两层 bridge（理清 D6/§6.18 的 bridge）**：
- **host-bridge（主机级）**：每台纳管主机一个，反连指挥中心，**本地驱动 Docker**（部署/启停容器，即 D6）+ 上报主机健康。
- **agent-bridge（容器级）**：每个容器内一个（§6.18 T1），反连指挥中心，管该容器 agent 执行/回传。
- 两级心跳 → 在线检测。

**纳管 + 部署流程**：
1. **主机纳管**：新主机跑 bootstrap 脚本（装 Docker + host-bridge）→ host-bridge 反连中心 → 主机上线（大屏可见）。
2. **自动部署容器**：中心经 host-bridge 下发 → 主机本地 Docker 拉起 **基础容器**（chatop-ai KasmVNC 基座镜像）+ 按需 **智能体容器**（绑角色/agent，§6.3 生命周期 + §6.2 配置注入）。
3. **通讯打通**：容器内 agent-bridge 反连中心 → 注册入编队（§6.3b 覆盖网）。
4. **在线检测**：主机（host-bridge）+ 容器（agent-bridge）两级心跳 → 指挥大屏在线/健康（#6/#13）；超时 → 容灾协调环（§6.9）。
5. **装应用/技能下发**：中心 → agent-bridge → 容器内装 app（app-manager）/ 装技能（SKILL.md）/ 装 MCP 插件（§6.20）。
6. **镜像分发**：基础镜像预置或经 registry 拉；首启播种（复用 chatop-ai 现有 preinstall 机制）。

### 6.20 技能与插件体系（通用 SKILL.md + chatop-ai 技能安装窗口）

> 用户问：openclaw / Hermes / OpenHuman 技能通用吗？并要 chatop-ai 应用管理窗口能点详情装 openclaw/Hermes 技能、打开技能安装页搜索装技能 + 插件。

**技能通用性（已核实，§12 来源）**：
- **通用**：**OpenClaw / Hermes / Claude Code / Codex / OpenCode / OpenHands 都遵循 agentskills.io 的 `SKILL.md` 开放标准**（YAML frontmatter: name/description/compatibility/allowed-tools + Markdown body + scripts/references/assets），**一个技能可跨这些 agent 用（几乎零改）**。**MCP 是共同底座**（OpenClaw 65% 新技能是 MCP 封装；Hermes v0.7 支持 MCP stdio/HTTP）。
- 市场：**OpenClaw ClawHub（44,000+ 技能，一键装/版本/依赖）** + **Hermes Skills Hub（652 + `hermes skills` CLI）** + agentskills.io。
- **差异**：ClawHub 静态包（手动更新）；**Hermes 技能自进化**（skill_manage，复杂任务成功后自动捕获成技能）——正是 S7 学习进化机制；Hermes 技能**可按角色**加载（`hermes -s`）。
- **OpenHuman 例外**：MCP **客户端** + OAuth 集成（桌面 GUI），消费 MCP 但非 SKILL.md 标准生产者，**不完全通用**（且无无头接口，§3.1）。

**设计含义**：装技能 = 装**通用 SKILL.md**，**一次装，容器内 OpenClaw/Hermes/Claude Code/OpenHands 共用**——不必为每家各装一套（重大简化）。技能绑角色契约（#18 skills 字段）可按角色分配。

**chatop-ai 应用管理窗口的技能安装（本项目侧，扩展现有 app-manager）**：
- app 详情页 → **"安装技能"入口** → **技能安装页**：搜索技能/插件 → 一键装（SKILL.md）/ 装 MCP 插件。
- **数据源**：优先**察元 `/api/v1/external-agents/skills`**（`search` / `install` / `uninstall` / `translate`，已核实存在）统一市场 + ClawHub + Hermes Hub。
- **落地**：技能装到容器内标准技能目录（供各 agent 读）；MCP 插件注册到 MCP client（§6.18 E）。
- **前端**：chatop-ai `ui.js` 加技能页（npm 打包需重建）；后端 `app_manager.py` 加技能 API 代理（转发察元 /skills）。
- **按角色**：装的技能挂到角色契约（#18），或经 `translate` 适配到目标 agent。

### 6.21 任务代号即对外调用契约（Task-as-API，需求 #20）

> 用户诉求：每个任务都有任务代号，**外部系统凭任务编码就能调用**——通过中心或智能体的接口，传入 code 即可执行任务、对接数据、提交数据。

**定位（关键概念升级）**：把 §6.16 的 `code`（任务代号）从"人看的标识"升级为**对外可编程调用契约 + 任务模板标识**，一举统一两个需求:**给人复用 = 任务模板；给机器调用 = 稳定 API 入口**（合并 §10.1 产品视角的"任务模板/工作流库"）。因此:
- **`code` 绑定到"任务定义/模板"（可复用、声明 input/output schema），不是一次性实例**。外部传 `code` 调用 → 用该模板 spawn 一个**新任务实例 `job_id`**。
- **`code` 是对外契约 = 一经发布不可随意改**（改了破坏外部集成）；部门内唯一（私有化 License），或全局唯一。

**三种调用语义**：
1. **执行任务(invoke)**：`POST /api/v1/tasks/{code}/runs`（body=inputs）→ **异步优先**返回 `{job_id, status}`；短任务可选 `?wait=…` 同步返回结果。
2. **对接数据(input)** —— 双向×双模式矩阵:
   | 方向 | pull（平台主动） | push（外部主动） |
   |---|---|---|
   | 入(input) | 任务从外部源**拉**数据(**复用 #15 连接器**+金库凭据) | 外部调 API **传**数据进来(payload/文件/引用) |
   | 出(output) | 外部 `GET /runs/{job_id}` **查/拉**结果 | 平台 **webhook 回调** / **回写**外部系统(需外部 endpoint+凭据) |
3. **提交数据(output)**：同步返回 / 轮询 `GET /runs/{job_id}` / **webhook 回调(HMAC 签名)** / 主动回写外部系统。外部也可 `POST /runs/{job_id}/data` 中途补充数据(呼应人工/外部介入)。

**两个入口(中心 vs 智能体)**：
- **中心接口(主入口,推荐)**：外部调中心 → 按 code 找模板 → **鉴权(#14)** → 编排派活到容器 → 聚合结果。统一、可控、可审计。
- **智能体直连(快路径)**：外部经**统一接入网关**直调某容器 agent-bridge 暴露的接口(低延迟/点对点),**仍走网关鉴权,绝不裸暴露容器端口**(安全红线:外部/前端永不直连容器)。默认走中心;直连仅对已授权快路场景开放。

**契约设计(现代最佳实践)**：REST + **异步优先**(agent 任务耗时不定)+ **每个 code 自动生成 OpenAPI 文档**(外部好集成)+ **幂等键**(`Idempotency-Key` 防重复触发,呼应 C9)+ **input/output schema**(模板声明,参数化)。

**鉴权与安全(平台安全视角必守)**：
- **per-caller API Key**(私有化=**部门级 Key**)+ RBAC(#14:该外部身份能否调这个 code)+ **per-caller 配额/限流** + **每次调用审计**。
- **外部输入=不可信**:防注入/投毒,套 #15 **信任分级**(低信任源只触发只读工作流);外部数据进 agent prompt/执行的**间接 prompt 注入在工具/网关层强制降权**(不靠提示词自觉)。
- **webhook HMAC 签名**防伪造;**幂等键防重放**;**code 不可枚举**(不可猜 + 鉴权)。

**数据流(落到工作目录)**：外部 push 的 input → 落 per-job 卷 `input/` → agent 执行 → 产物 `output/` → 按提交语义回传(同步/webhook/回写)。

**与已有设计的关系**：`code`↔§6.16 三级标识 / 任务模板↔§10.3 产品缺失面"任务模板库" / pull 入↔#15 连接器 / 回写↔§10.3"交付面回写" / 数据落卷↔§6.4 / 鉴权↔#14 / 凭据↔金库。**与 #15 互补**:#15=外部数据**被动**感知触发,#20=外部**主动**按 code 调用。

**落地阶段**：**P1**(与任务模板库一起做:code=模板标识 + 对外 invoke API + webhook)；**P0 先把 code 作为标识存好**(§6.16 已有),对外 API/OpenAPI/回写留 P1,同步模式/复杂 schema/直连快路留 P1→P2。

### 6.22 容器通讯与寻址：逻辑标识而非 IP（2026-07-01）

> 用户诉求：容器间(及容器与中心)通讯要能实现，**不是非要 IP**。

**硬原则**：**系统内一切寻址用逻辑标识**——容器昵称(#3)/`job_id`/总线 subject/共享卷路径；**IP 仅是覆盖网/总线的内部实现细节，应用层与用户永不填 IP，任何模块不得硬编码容器 IP**。容器动态重建/迁移/替身接管后逻辑标识不变，寻址自动重解析，无需改配置。

**为什么必须无 IP**：①容器动态(重启/销毁/重建，IP 会变)；②跨 NAT/防火墙 IP 不可达(反连已解决方向问题)；③万级/跨主机 IP 规划不可行(§10.4)；④容灾替身 IP 不同但昵称同，寻址不变(#13)。

**分层寻址机制(全部逻辑标识，零 IP)**：
| 通讯类型 | 寻址方式(无 IP) | 承载 |
|---|---|---|
| 中心 → 容器(派活/指令) | 容器昵称/ID → 注册表查当前反连会话 | 反连 WS(容器主动拨号，中心无需知容器 IP) |
| 容器 → 中心(心跳/事件/回传) | 中心固定**逻辑端点**(服务名/域名，非 IP) | 反连 WS |
| 容器 ↔ 容器 A2A 信令(#12) | 目标昵称 → 总线 subject `agent.<昵称>.inbox` | 消息总线 pub/sub(I6，subject 寻址) |
| 容器 ↔ 容器 A2A 数据/成果物(#12) | 共享卷路径 `/workspace/<job_id>/` | 共享卷(**不走网络**，路径寻址) |
| (可选)点对点低延迟直连 | 覆盖网逻辑名(MagicDNS/mesh 名) | 覆盖网(WireGuard/NATS leaf)：逻辑名→隧道，应用不碰 IP |

**与既有设计的一致性**：#3 昵称注册表本就"喊昵称"、覆盖网反连本就不需中心知容器 IP、#12 总线 subject + 共享卷本就无 IP、I4 Registry + I6 EventBus 承载逻辑寻址。本节把"无 IP 寻址"**从隐含提升为显式硬原则**，并统一到接口：寻址解析经 **I4**(昵称→逻辑路由句柄，非 IP)+ **I6**(subject)+ 新增 **I10 传输/寻址抽象**(逻辑名→传输，屏蔽 IP，反连 WS/总线/覆盖网可换)。

**落地(P0)**：中心中转 + 总线 subject + 共享卷(三者都无 IP)即满足；点对点覆盖网直连留 P1+(与 #12 A2A 同步，A2A 本 P3)。**P0 硬性验收：全链路寻址无任何容器 IP 硬编码**(用昵称/subject/卷路径)。

### 6.23 与 Spring Cloud / OpenFeign 生态互操作（2026-07-01）

> 用户问：接口要支持 OpenFeign 调用，Python 是否支持？

**结论：支持。OpenFeign 是 Java 的客户端技术、与服务端语言无关**——本质是"按服务名从注册中心发现 + 发标准 HTTP/REST + 负载均衡"。**被调用方是 Python 还是 Java 无所谓**。已核实(§12 来源)Python 侧生态成熟。

**Java 端用 OpenFeign 调用 ChaCMD(Python FastAPI)的三前提(全部已有或易补)**：
1. **标准 REST**：FastAPI 天然满足。
2. **注册到 Nacos**：ChaCMD 与 Java Feign 用同一注册中心，Feign 按**服务名**(如 `chacmd-orchestrator`)发现调用——**正好命中 §6.22 无 IP 寻址 + I4 Nacos 接入**。Python 用官方 **`nacos-serving-python`**(async v2 SDK，专为 FastAPI/Flask 自动注册+发现)或 **`nacos-sdk-python` v2**(`add_naming_instance` + 心跳)。
3. **OpenAPI 契约**：ChaCMD 暴露 OpenAPI(#20 已要求)，Java 端用 openapi-generator 生成 Feign client 或手写 `@FeignClient` 对齐；契约版本化(§3.6)。

**反向(ChaCMD Python 调 Java 服务)**：Python 无 OpenFeign 但等价——`nacos-serving-python`/`nacos-sdk-python` 服务发现 + `httpx`/`aiohttp` 按 `http://<service-name>/path` 调用；需声明式可用 `uplink`(类 Feign)。**I1 `ChayuanClient` 即这种封装 HTTP 客户端**，可扩展"按服务名发现调用"。

**与既有设计契合**：①按服务名寻址 = §6.22 无 IP + I10 Transport；②Nacos = I4(后台可配置接入)；③OpenAPI = #20；④异构互通靠 **Nacos + REST + OpenAPI**，ChaCMD Python 作 Spring Cloud 生态一等公民。

**边界(否决)**：不为"纯 Java 生态一致"用 Java 重写 Orchestrator(违背复用察元 Python/FastAPI + Claude Agent SDK 的核心决策)。**语言异构由 Nacos + REST + OpenAPI 打通，不靠同语言**。企业若有 Spring Cloud IT 体系，它作"外围集成/IT 层"，ChaCMD Python 核心经 Nacos 与之互操作。

**落地**：**P0 就绪 REST + OpenAPI**(Java 端即使不经 Nacos，也能按 URL + OpenAPI 生成 Feign client 直接调用)；**Nacos 注册 + 按服务名发现随 I4 = P1**。

---

## 7. 需求 → 落点对照表（验收口径）

| # | 需求 | 落点 | 验收 |
|---|---|---|---|
| 1 | 角色分配 | jeecg 角色库 + Orchestrator 注册表 | 能新建角色并绑到容器 |
| 2 | 复制容器/配参/装应用/启动 | 编排服务 + 主机 agent-bridge 本地 Docker SDK + 复用 app_manager | 一键起出带指定角色/应用的新容器 |
| 3 | 命名/昵称 | 注册表映射 | 对话框喊昵称命中正确容器 |
| 4 | 统一工作空间 | 容器内 `$HOME/<code>`（同名）挂共享卷 `/workspace/<job_id>/` | 各容器同名目录、产出落此、跨容器读写同一份 |
| 5 | 统一调度对话框 | NL 路由 + 派活适配器 | 自然语言/昵称 → 正确 agent 执行 |
| 6 | 实时反馈 | stream-json/stderr/WS → 事件总线 → SSE | 对话框逐步显示执行进度 |
| 7 | 结果回传 + 共享 | 结果聚合 + 共享卷 | 结果进对话框；产物跨容器可见 |
| 8 | 免密开界面 | 凭据金库 + 预认证网关 + iframe | 点击直接进容器桌面，无需输密码 |
| 9 | 统一装/调角色 | jeecg 控制台 + 编排下发 | 后台改角色/技能即时生效 |
| 10 | 统一配模型/Key | 配置中心 + 注入 | 后台改模型/Key → 容器内 agent 生效 |
| 11 | 串行/并行多 agent 编排 | 编排引擎(Stage 串行 + Stage 内并行 join) + NL 拆 DAG | 多 agent 先并行后汇总能跑通；指挥台显示实时 DAG 进度树 |
| 12 | 智能体间直连通讯 | 文件走共享卷 + 消息走总线 pub/sub；指挥台旁路订阅审计 | A 干完直接触发 B 且不经 Orchestrator 路由；指挥台仍能看到/审计这次交接 |
| 13 | 容灾/高可用 | Orchestrator 协调环（期望态）+ 心跳探活 + 重建/改派 + 在途任务重放 | kill 掉某角色容器，秒~十秒级自动起一个同角色/同昵称/同配置替身，在途任务断点续跑 |
| 14 | 资源级授权 | jeecg RBAC + 资源登记 + Grant 表；网关/派活前置校验 | 给用户/角色授某容器 view/operate/dispatch；无权者开不了界面、列表里看不到该 agent |
| 15 | 外部数据接入/感知 | 连接器(拉/接)→共享工作区 + 事件总线→触发编排 | 外部源数据能拉/接进工作区供跨容器消费；外部事件能自动触发一条工作流 |
| 16 | 统一模型网关/国内·本地模型 | LiteLLM 双协议网关 + 配置中心注入虚拟Key + 金库收口真实Key | Claude Code/Codex 经网关跑通 DeepSeek/Qwen 等；离线时经 Ollama/vLLM 推理不出境；换模型 agent 无感 |
| 17 | 三位一体母体 | 部署察元为母体内核 + ChaCMD 跨容器调度增量 | 母体自带智能体/知识库/网关/RBAC 跑起来，并能向子容器派活 |
| 18 | 角色契约（提示词/技能/目标/触发/交接）| 声明式契约 → 派活适配器注入各 agent；trigger 接 #15/总线，handoff 接 #12 | 定义一个角色含 system_prompt+skills+goal+trigger+handoff；数据到达自启执行并自动交接给下一角色 |
| 19 | 知识源查询范围与权限 | 角色契约 `knowledge_scope`（类型+具体库）→ 复用察元 kb_subject_grant + kb-query authz 过滤 | 给某 agent 只授文档+某库；它检索只召回授权范围内，越权源不可见；引用可溯源 |

---

## 8. 技术选型总表与取舍

> **注**：下表为引入察元母体（§3.5）**之前**的选型；§3.5.D 已对「控制台/RBAC」「模型网关」「编排大脑」「知识库」做出修订，**以 §3.5.D 为准**。下表保留以记录取舍推演。

| 关注点 | 选型 | 理由 | 否决的替代 |
|---|---|---|---|
| 控制台 + RBAC | ~~jeecg-boot~~ → **察元自有 RBAC（§3.5.D 修订）** | 母体已含 org/部门/角色/data_scope/资源级 grant/审计，同 Python 栈 | jeecg（引入后与母体 RBAC 重复，砍）；纯自研 |
| 编排大脑 | **Python FastAPI** | 贴现有 Python app_manager + Claude SDK + agent CLI + 流式 | 全塞进 jeecg(Java)：调 CLI/流式桥接重 |
| 工作流引擎(串并行+回环+条件+子编排) | **FastAPI + asyncio 自研轻量** | 串并行 + 有界审核回环 + 条件路由 + sub-DAG（§2.5 场景 S1/S2 需要），与派活适配器/共享卷咬合 | Temporal/Prefect/Airflow（本期用不上重型持久化，徒增运维）；纯串并行（覆盖不了审核回环/条件重路由） |
| NL→DAG 规划 + Claude 执行的"大脑" | **Claude Agent SDK(Python, claude-opus-4-8)** | 同 Claude Code 引擎的官方封装，智能/流式开箱即用 | 官方无开放源码可 fork；**泄露源码 fork(2026-03-31)法律+安全双重禁用(§9/§6.7a)** |
| 编排"大脑"放哪 | **薄自研引擎调度 + Agent SDK 仅做规划/Claude执行** | 厂商中立、确定、可复现；业界(含Claude Code自身)成熟范式 | 让 Claude subagent/Managed Agents 当主调度器（Claude-only，违背多厂商需求11） |
| A2A 消息通道 | **消息总线 Redis Streams / NATS** | bridge 对外拨号即可,NAT 友好;不经 Orchestrator 路由;指挥台可旁路订阅审计 | 容器间直连 TCP(覆盖网下跨主机不可达)、指挥系统中转(违背"不经过指挥系统") |
| A2A 数据/成果物 | **共享工作区直传(复用§6.4)** | A 写 B 读,本就点对点,零新增 | 走消息总线传大文件(总线只适合信令/小消息) |
| 容灾/自愈 | **Orchestrator 自研协调环（期望态 reconcile）** | 跑在覆盖网现成心跳上,轻量,与 §6.3 生命周期/§6.2 注入直接复用;不需 K8s | 默认上 K8s 做自愈(重、对本场景过度);仅靠 Docker restart(救不了整机宕/跨节点改派) |
| 资源级授权 | ~~jeecg RBAC~~ → **察元 RBAC + 数据权限（§3.5.D 修订）** | 母体已有 org/角色/data_scope/资源级 grant/审计;只需把资源维度扩到"容器/agent/系统视图"(§3.5.C 加强点) | 自研权限引擎(重复造轮子);前端自行判权(越权风险,红线否决) |
| 外部数据接入 | **连接器(拉:cron 轮询 / 接:webhook·MQ) + 事件总线触发** | 复用脊柱事件总线;归一化落共享卷直接打通跨容器消费;感知=事件驱动编排 | 每容器各搭一套接入(重复、难审计);外部源直连高权 agent(投毒/SSRF 风险) |
| 统一模型网关(#16) | ~~LiteLLM 主力~~ → **察元 chayuan-gateway 主力（§3.5.D 修订）**；LiteLLM/CCR 仅补 Anthropic `/v1/messages` shim 给 Claude Code | 母体网关已含 25+ 厂商 + 本地 Ollama/vLLM，本地/网络双支持；只缺对外 Anthropic 协议端，补一个 shim 即可 | 每 agent 各配 base_url(Codex 协议坑/Key 散落);"部署开源 claude code"(不存在,Claude Code 闭源) |
| 模型网关补充 | claude-code-router(Claude Code 分级路由省钱) / new-api(国内模型计费聚合) | 按需叠加:CCR 给 Claude Code 按任务分档省钱;new-api 当国内模型二级后端+计费台 | — |
| 完全离线后端 | **Ollama / vLLM 跑开源权重(DeepSeek-V3/Qwen/GLM)** | 推理不出境;agent 本地 CLI+本地网关+本地模型 | — |
| **实时开发部署 agent(#S1/S6, §6.17)** | **OpenHands(首选,开源MIT)** | 开源+经LiteLLM接DeepSeek/Qwen/Ollama/vLLM(离线可跑)+自带Docker沙箱能开发部署+`--headless --json`事件流实时回中心 | Claude Code(闭源,要开源则不选);Aider/Goose(沙箱/部署/事件流弱) |
| 容器管理/运维 | ~~1Panel~~ → **主机 agent-bridge 本地驱动 Docker（用户 2026-07-01 定，D6）** | 与覆盖网同控制通道；不远程裸暴露 Docker API；无 GPL 顾虑；可视化由指挥大屏自建 | 1Panel（多一个面板进程 + GPL-3.0 传染，去掉）；远程裸暴露 Docker TCP（攻击面大） |
| 多机集群 | **应用层覆盖网（agent-bridge 反连）** | 容器已常驻服务，反连+心跳即成集群；不依赖 K8s，绕开 NAT/防火墙 | K8s 当调度器（重、对本场景过度） |
| 容器创建/启动 | **Docker SDK（各主机 agent-bridge 本地执行）** | 复用现有 compose 参数化；多机=各主机各一个 Docker + 一个 bridge | 远程 Docker API / 1Panel（已去掉） |
| 自动扩缩容/自愈（可选） | **K8s（仅按需，非默认）** | 仅当规模大到需要调度策略时引入 | 默认就上 K8s（过早复杂化） |
| 共享存储 | 本地卷→**NFS/CephFS** | 单机够用，多机需共享读写 | 对象存储（不适合 POSIX 文件协作） |
| 桌面接入 | **KasmVNC + Caddy（现有）** | 复用现成单端口方案 | 重写远程桌面 |
| 一等派活 agent | **Claude Code / Codex / OpenClaw / Hermes** | 四者均有真无头接口 + 流式（§3.1 核实）；OpenHuman 无无头接口仅作人工桌面型 | GUI 自动化硬驱纯桌面 agent（脆弱，否决作主力） |
| 角色契约(#18) | **声明式 charter(身份/目标/系统提示词/技能/触发/交接) + 派活适配器按 agent 翻译注入** | 一份契约 N 种注入;技能引用 Hermes/MCP 现成体系不自造;复用察元 persona/角色 | 给每个 agent 各写一套硬编码角色(难维护、难复用、无法自驱) |
| 知识源查询范围(#19) | **角色契约 knowledge_scope + 复用察元 kb-query authz 骨架 + 3 处上游扩展** | 类型枚举/检索 authz 管线/泛化主体表骨架可复用;**扩展(已核实)**:主体加 agent(小)+源侧授权泛化(中,否则只能管文档类)+类型级授权(中) | 自造一套知识授权(与母体重复);前端/agent 自行裁剪范围(越权风险);仅靠静默过滤(察元实为 assert 403 硬门禁) |

### 关于 jeecg 与 1Panel 的诚实提醒（两者均已去掉）
- **jeecg 已在 §3.5.D 被砍**：引入察元母体后，RBAC/org/角色/审计 改用母体自有能力（同 Python 栈），不再引入 jeecg(Java)，省掉一整套 Java↔Python 桥接。
- **1Panel 已在 D6 被去掉**（用户 2026-07-01 定）：改由主机 agent-bridge 本地驱动 Docker——与覆盖网同控制通道、不裸暴露 Docker API、无 GPL-3.0 传染顾虑，容器可视化由指挥大屏自建。

---

## 9. 安全与权限红线

- 所有"开容器界面 / 派活 / 改配置"必须过**察元 RBAC**（§3.5.D，jeecg 已砍）校验，不许前端直连容器。
- **供应链/合规红线（禁用泄露专有代码）**：**绝对禁止使用 2026-03-31 泄露的 Claude Code 源码及其任何 fork/镜像/重建版**（`claude-code-fork/*`、重建可跑 fork、"unlocked"版等）。泄露≠授权（Anthropic 已 DMCA 下架 8000+ 仓库），且泄露 fork 已被证实投毒传播恶意软件——法律侵权 + 供应链投毒双重风险。要开源 agent 用 **OpenHands**(§6.17)；要 Claude Code 能力用**官方闭源 CLI 经 Anthropic-shim**(§6.12)。同理，任何来源不明的 agent/依赖须来源可信 + 版本锁定（对齐 LiteLLM 投毒版本教训）。
- **资源级授权（§6.10）**：开界面/派活/查系统前先查 Grant(主体×资源×动作)，无权即拒；查看与操作分级（view-only KasmVNC 不给控制权）。
- 密钥不落明文共享卷；走 Secret / 加密金库 + 主密钥；连**外部数据源**的凭据同样进金库。
- agent 执行默认最小权限沙箱（如 `codex exec --sandbox workspace-write`），危险全权限需显式授权 + 审计。
- **外部数据入站（§6.11）是攻击面**：源白名单 + 出站目标白名单防 SSRF；信任分级——低信任外部事件**不得直接驱动高权限 agent**；载荷大小/类型校验、速率限制、不可信数据隔离沙箱解析。
- **A2A 通道（§6.8）** 建链时做一次通道 RBAC；消息带 hop+TTL 防环防风暴。
- 审计：派活、开界面、改模型/Key、**A2A 交接、外部数据触发的编排**全部留痕（察元审计表）。
- **Docker 管理安全（去 1Panel 后）**：主机 Docker socket **不对外开 TCP**，仅本机 agent-bridge 访问；跨网只有 bridge↔指挥中心的 **mTLS 反连通道**；bridge 可执行的 Docker 操作走**白名单**（禁止任意 shell），并全量审计。

---

## 10. 分阶段实施路线（对"多机/集群"的负责任答复）

### 10.0 需求合理性评审与优化建议（2026-07-01 复盘，先读）

> 通盘 red-team 一次 19 条需求 + §3.5~§3.7、§6.15/§6.16。**结论：愿景成立，母体复用(#17)是明智杠杆且已文件级核实；但当前最大风险不是技术，而是范围——需求平铺、缺 MVP 边界、核心闭环尚未端到端证伪。**

**扎实（保留）**：#17 母体 / #16 网关 / #4·#7 工作目录+汇总 / #5·#6 对话+实时 / monorepo 双 SKU——均有察元现成能力或已核实支撑。

**张力与重叠（需收敛）**：
- **母体自带 agent(#17) vs 子容器多 agent(#2/#5/#11) 分工边界未定**——若母体本身已是强多 agent 系统，"再横向起一堆容器"的边际价值须讲清。**建议明确规则**：子容器只用于 ① 沙箱执行代码/装东西、② 特定 agent 能力（如 claude-code 编码）、③ 桌面 GUI agent、④ 并行扩容；**母体能直接干的不起容器**。否则是功能重叠+过度设计。
- **编排式交接(#11 DAG) vs 直连 A2A(#12) 重叠**，且直连 A2A 不成熟——**建议 MVP 只用 DAG，直连 A2A 后置**。

**过度设计嫌疑（后置，非"证明可用"必需）**：直连 A2A(#12)、外部感知触发(#15)、容灾脑裂 fencing(#13)、投墙模式。

**遗漏（须补，优化建议）**：
1. **成本/token 治理**——N 容器 × 多 agent × LLM，成本会爆；察元 token 仅估算无计费(§3.5.C)。**补预算/限流/护栏**。
2. **失败处理与人工介入**——agent 跑歪 / DAG 卡住 / 结果错 → **补熔断 + 人工审批门 + 中断/回滚**。越自动(#18 触发/交接)越需要。
3. **端到端可观测**——多容器异步，**补 Job 级分布式 trace**（复用事件总线的 job_id 串联）。
4. **状态一致性**——Job 状态(DB)/产物(卷)/容器(实况)三者一致性边界须明确（容器挂了但 DB 说 running 等）。
5. **容量规划**——并发 Job/容器上限（§11.1 磁盘已紧）。

**头号技术风险**：**"NL→DAG→多 agent 串并行→无头执行→流式回传→汇总"全链路从未端到端验证**，却是系统成立的核心假设。**Phase 0 必须先证伪这条最小链路**。

**优先级重排（P0–P3，落地纪律）**：
| 级 | 内容 | 目的 |
|---|---|---|
| **P0 核心闭环** | #17+#16+#5+#6+#4+#7 + #2 起 1 个子容器 + #18 最简角色 | **"母体把一个任务派给一个子容器 agent，用指定(国内)模型干活，产出汇总回大屏"**——证伪心脏 |
| **P1 多 agent 价值** | #11 串并行 + #3 昵称 + #9 角色/技能 + #19 知识域 | 证明"多 agent 协作"比"母体单干"更值 |
| **P2 规模化治理** | #13 容灾 + #14 资源授权 + #10 完整配置 + **成本治理(补)** + **失败/人工介入(补)** | 能放心多人/多机用 |
| **P3 高级协作** | #12 直连 A2A + #15 外部感知 + 投墙 + 多机覆盖网 | 完整愿景 |

**两个必须先回答的问题**（决定能砍掉多少 MVP）：① **第一个真实用例场景是什么？**（有它才能砍 P2/P3）② 母体 vs 子容器的**分工边界**（决定 #2/#5 的形态）。

---

> 核心难点是 **5/6/7 的 agent 编排与流式回传**，不是容器多机调度。先证伪核心，再扩集群。

- **Phase 0 — 骨架**：Orchestrator(FastAPI) + Agent 注册表 + 容器内 agent-bridge；单机 Docker 起 1 个无头容器，跑通 `claude -p` 流式回传到一个最简对话框。
- **Phase 1 — 核心链路（单机）**：
  - 统一对话框 NL 路由 → 派 Claude/Codex/OpenClaw/Hermes；实时进度 SSE；结果回填。
  - 共享工作区 `/workspace/<task-id>/`；配置中心注入模型/Key；主机 agent-bridge 本地 Docker SDK 管容器（不用 1Panel）。
  - **统一模型网关（#16）：LiteLLM 起一个，Claude Code 经 `/v1/messages`、Codex 经 `/v1/chat` 各跑通一个国内模型（如 DeepSeek）；真实 Key 进金库。这是「接国内模型」的核心证伪，应放在 Phase 0/1 最早做。**
  - jeecg 接入：RBAC + 角色库 + 容器列表 + **资源级 Grant（#14，开界面/派活前置校验）**。
  - **统一事件总线**立起来（脊柱）：先承载心跳 + 任务进度。
- **Phase 1.5 — 编排 + 直连 + 自愈（单机即可验证）**：
  - 串/并行编排引擎（#11）+ NL→DAG；A2A 消息总线 + 旁路审计（#12）。
  - **容灾协调环（#13）**：声明期望副本 → kill 容器 → 自动重建同角色/昵称替身 + 在途任务重放（单机即可证伪）。
- **Phase 2 — 多机集群（用户目标态，覆盖网方案）**：
  - 加第二台主机，各跑 Docker；容器 agent-bridge 反连同一指挥中心即入集群（**不引入 K8s**）。
  - 共享卷上 NFS/CephFS（多机共享读写）；凭据走加密金库（如需 K8s Secret 仅在引入 K8s 时）。
  - 免密开界面经统一接入网关 + 一次性 token（绑 #14 Grant）；**容灾扩到跨节点改派（整机宕→他节点重建）**。
- **Phase 3 — 外部感知 + 角色/技能/混合桌面增强**：
  - **外部数据接入（#15）**：连接器（拉/接）→ 归一化落共享卷 → 事件触发编排；信任分级。
  - 桌面型容器（OpenHuman/Hermes）远程开界面；角色↔技能↔模型可视化编排；Hermes 式固定角色。
  - 指挥中心主备（消除 SPOF）。

每个 Phase 结束给用户验收，不堆多个里程碑才汇报。

### 10.1 全方位深度评审（架构 / 产品 / 设计UE / 平台性能安全 四视角交叉综合，2026-07-01）

> 方法：四个独立专家视角背靠背通读全稿。**凡是 ≥2 视角互不通气却独立点名的，视为高置信硬阻塞，必须在计划定稿前拍板**；仅 1 视角提出的按其严重度收录。

**四视角一句话总判**：
- **架构师**：愿景与复用杠杆成立；三处会翻车——① 执行模型(subprocess-per-task + 每次派活 LLM 路由)撑不起 S2 实时；② 自研耐久编排引擎与自己列的 #13/S2/S4 需求正面相撞；③ Orchestrator 有状态单点 + 三者一致性无解 = 扩展天花板。
- **产品经理**：工程严谨、产品严谨偏低；病根是**没选定买家/beachhead/定位**——19 需求多为"系统能力"非用户 JTBD，7 场景是 7 个市场。护城河("能操作整机桌面的异构 agent 舰队")被埋没成一个特性；MVP 只证明管道不证明价值。
- **设计UE**：架构成熟但界面只有"分区示意"没有"操作流设计"；三大 UX 债——① 指挥大屏双焦点致态势视图被挤小；② 人工介入/失败处置无操作面；③ 技能管理与 S7 员工侧界面缺位。
- **平台性能安全**：达"高并发/低延迟/多租户/安全"生产标准前,5 个硬阻塞不能后置——沙箱逃逸、S2 热路径、多租户隔离、总线分流、单例+reconciler。

**A. 跨视角共识必改项（≥2 视角撞车 = P0 阻塞，计划定稿前必须解决）**：
| # | 必改项 | 谁点名 | 结论/方案 |
|---|---|---|---|
| C1 | **执行模型改常驻会话** | 架构+安全 | subprocess-per-task 冷启数百 ms~秒，撑不起 S2 实时/长时/流式。派活适配器必须同时支持"one-shot 批量"与"**persistent-session 流式**"(Claude Agent SDK 长会话 / OpenHands server / OpenClaw 常驻网关 / Hermes serve)。 |
| C2 | **热路径禁 LLM，实时/规划双路径分离** | 架构+安全 | 每次派活用 LLM 分诊 = 延迟+成本毒药；kb-query `synthesize=true` 更是把 LLM 放进 S2 决策热路径。**实时路径走确定性规则+缓存结构化数据(`synthesize=false`)，硬 SLO(如<200ms)；LLM 只做冷启 NL 路由/离线策略**。派活分快慢路(@昵称/规则/缓存=快)。 |
| C3 | **事件总线定 NATS JetStream + 心跳与判死解耦** | 架构+安全 | 三合一命中本架构:leaf node 承载反连、**Accounts 原生多租户 subject 隔离**、headers 载 traceparent。**一条总线扛心跳+进度+A2A+审计是反模式**——心跳洪峰污染 retention 会致容灾误判→脑裂。心跳走反连 WS/NATS core + **独立 lease 判死**;进度/A2A/审计分 stream 分 retention。Redis Streams 仅 MVP，Kafka 作外部数据/审计二级 sink。 |
| C4 | **Orchestrator 拆无状态 + reconcile 单活选举** | 架构+安全 | 现设计有状态单例(WS+内存DAG+SQLite)=SPOF+吞吐天花板。**连接层拆独立无状态 bridge-gateway**(终结WS+鉴权+发总线);Job/DAG 状态外置 **Postgres(第一天就上,弃 SQLite)**;按 job_id 分区 active-active;**reconcile 环必须 leader election/lease 单活**(否则多实例双拉替身)。 |
| C5 | **多租户隔离(全链路)** | 安全+产品 | 目标写"多租户"但隔离几乎空白。**ChaCMD 新表全加 `tenant_id`+Postgres RLS;共享卷改 per-job 子目录 bind(禁整卷挂载,现设计=跨租户数据泄露);NATS Accounts 隔离总线;网关签 per-tenant 虚拟 Key+硬预算+限流;一次性 token 绑租户**。产品层:租户模型(=公司?部门?)须先定义。 |
| C6 | **人工介入/失败处理前置为一等** | 产品+设计+安全 | 三方独立点名(最强共识)。#18 自驱/#15 自动派活拉满自动化却把 human-in-loop 当脚注,与企业管控正面冲突。**任务状态机第一天加 `pending_approval` 一等状态**;大屏事件流顶部"需要你处理"区带[批准]/[打回]/[暂停]/[改派]/[回滚]动作;**#8 免密开桌面接成"接管"载体**(现设计浪费了这张牌)。 |
| C7 | **成本/token 护栏** | 产品+安全 | N容器×多agent×LLM循环(OpenHands 单任务可循环几十步狂烧)。**per-job 硬预算(超则kill)+per-tenant 月预算+per-role 上限+实时计量(接察元 `llm_callback` 真实 usage)+runaway 熔断+agent 最大迭代数**;护栏放**网关层**(天然收口)。跑前预估+燃尽+成本归因。 |
| C8 | **自研耐久引擎焦油坑** | 架构+安全 | 回环+条件+sub-DAG+续跑+审批门+cron = Temporal 全集。**自研引擎明确锁死在无耐久 P0/P1;P2 #13 续跑落地前切换 Temporal/Restate/DBOS**,薄 asyncio 只留流式派活+fan-in。别手搓 saga/fencing/resume。 |
| C9 | **三者一致性(Job态/产物/容器实况)** | 架构+安全 | 每事实单一真源(存活=心跳/reconcile;Job态=DB但周期对账;产物=卷+原子完成标记 write-then-rename)。**reconcile 必须兼收 Job 态(死容器 Task→interrupted),现设计只对账副本数**。承认至少一次+去重,别假设 code-exec agent 幂等("断点续跑"对不 checkpoint 的 LLM agent 是空头支票)。 |

**B. 单视角高严重度必改（虽 1 视角提出但等级=严重/高）**：
| # | 项 | 视角 | 结论 |
|---|---|---|---|
| S1 | **沙箱逃逸(全文最严重矛盾)** | 安全 | §6.17/§6.18 用 **DinD --privileged / 挂 docker.sock** 给会跑不可信代码的 agent = 平凡宿主逃逸,**直接违背 §9"socket 不入容器"**。必改:**gVisor / Kata / Sysbox / rootless Docker**,socket 绝不入不可信容器。+ 容器加固基线(cap-drop ALL / no-new-privileges / seccomp / userns-remap / read-only rootfs / cgroup 硬限)。 |
| S2 | **技能/MCP 一键装 = 未设防 RCE + 间接注入** | 安全 | §6.20 从 ClawHub 44k 一键装到 code-exec agent;一个恶意 SKILL.md/MCP = agent 权限任意执行。**allowlist+签名校验+沙箱执行;生产禁自动装;私有 registry 镜像;pin 版本**。外部数据+KB 进 prompt 的**间接 prompt 注入必须在工具/网关层强制降权**(不靠提示词自觉)。 |
| S3 | **可插拔是 fork-based(名不副实)** | 架构 | 加 agent 要改察元 registry 三处(硬编码 if system_id)。ChaCMD 侧**自建 `AgentAdapter`/`Connector` ABC + 注册表**(spawn/stream/inject-charter/health/cancel + capability manifest),使加 agent/connector/skill **零改察元核心**,顺带卸掉"上游化+flag"负担。 |
| S4 | **出站流量管控缺失** | 安全 | 只防入站 SSRF,没管 agent 主动出站(curl 外发/DNS 外泄)。默认拒绝出站+per-role 白名单。 |
| S5 | **可观测性只有一句 job_id** | 安全 | 上 **OpenTelemetry** W3C traceparent 全链路(注入总线 header)+ **Prometheus metrics(重点 bus consumer lag=误判死前兆)**+ 结构化日志(tenant/trace/job/task id)+ SLO 告警。 |
| S6 | **多机 reconcile 在重造 K8s(漏了 Nomad)** | 架构 | split-brain/fencing/lease/leader 选举正是 K8s 花多年做对的。跨节点 placement/health/reconcile **先评估 Nomad**(单二进制/无 etcd/原生跨主机 Docker/贴"不用 K8s")再决定是否自研。 |

**C. 战略层必答题(产品,决定后续所有设计)**：
1. **选定 1 个 beachhead 场景 + 买家(ICP)**:砍 S2/S3 作架构驱动。推荐 beachhead = 桌面容器"必要"的场景(S1 开发+沙箱+预览,或 S7 云桌面),单 agent 明显做不到——这样 MVP 才**证明价值而非只证明管道**。
2. **重定位到护城河**:"统一指挥、可操作整机桌面的异构 agent 舰队",而非"又一个多 agent 编排器"(那是 Dify/Coze/百炼红海)。
3. **先定商业模式**(重塑租户/成本/网关):私有化 License(租户=部门,成本=分摊) vs 多租户 SaaS(用量计费)。按国内/离线/RBAC 侧重,大概率前者。
4. **补缺失产品面**:成本预算子系统、人工介入控制面、任务模板/工作流库(留存杠杆)、通知(完成/失败/待审批→邮件/IM/webhook)、交付面(下载/导出/发布/回写)、角色/agent 市场、**按角色分设产品视图**。

**D. 界面层必改(设计UE)**：
1. **指挥大屏重构为"全幅态势画布 + 悬浮指挥条(⌘K式) + 可折叠抽屉"**——消双焦点、态势拿最大版面、**投墙=画布减命令条(省一半构建)**。这是开发前最该定死的布局。
2. **技能管理中央化**(从子容器 app-manager 提到大屏中央能力库:搜索→下发→绑角色;容器内降级为本地兜底)。
3. **事件流按严重度分层**(顶"需处理"带动作/中"活动流"摘要聚合/底"审计"收起)。
4. **DAG 默认泳道/时间轴 + sub-DAG 折叠 + 回环计数徽章**,图/列表切换。
5. **多角色视图分离**:管理员作战大屏 vs **员工云桌面(现完全缺)是两套壳**,靠 RBAC+BrandConfig 决定;S7 补**员工侧最小 UI + 学习知情同意/"正在学习"指示/回看批准**(隐私红线)。
6. **新建任务**:拆出"创建智能体"(基础设施供给≠快速派活)、隐藏 job_id、slug 冲突才打扰、NL 草稿原地渲染成带"推断"标记的表单;守住"仅 goal 必填"。
7. **深色控制台设计系统**:察元浅色办公组件气质不匹配,把状态徽章/密集表/指标卡/图节点沉为 chacmd 子组件,深色单独做对比度/色觉校验。
8. **补 onboarding + 空状态**(全文无);**进 writing-plans 前先补一轮以操作流为主线的界面 brainstorming**(对照 CLAUDE.md"大功能强制先 brainstorming")。

**E. 核心冲突与调和**：
- **"以察元为母体(#17)" vs "S2 亚秒实时"**:架构师说 supervisor 是伪复用、平台安全说重母体拖累亚秒路径。**调和**:察元做**规划/知识/网关/RBAC(非热路径)**;**实时派活核心独立为薄层**(不经察元重 monorepo),经 C1 常驻会话 + C2 规则热路径达 SLO。修订 #17 的"一切压察元"为"察元做大脑与能力底座,实时调度另起薄核心"。
- **自研 vs Temporal**:两视角一致=渐进(P0/P1 自研无耐久,P2 切 Temporal),非冲突。
- **AGPL 合规**:察元 AGPL-3.0,合并 SKU 即 AGPL;用户自有产品可 relicense,但**对外分发/SaaS/嵌第三方 AGPL 会触发源码义务**,须显式记为决策点。

**F. 修订后的现代化技术主线(选型汇总)**:常驻会话执行 + 快慢路由 / 实时规划双路径(热路径禁LLM,`synthesize=false`+规则) / NATS JetStream(心跳解耦、Accounts 多租户) / Orchestrator 无状态化 + Postgres + reconcile leader lease + 独立 bridge-gateway 连接层 / P2 Temporal 耐久层 / gVisor|Kata 沙箱 + 容器加固基线 / OTel+Prometheus 可观测 / ChaCMD 侧 AgentAdapter/Connector ABC 真插件 / 多机先评 Nomad。

**G. 对 Phase 路线的修正**:P0 不再只跑"需求分析师→PM 管道"(只证机制)。**P0 收窄为"单 agent 明显做不到的价值切片"**(如 S1:开发+沙箱跑+桌面预览),并从第一天内建:Postgres 状态、`pending_approval` 状态机、per-job 预算护栏、per-job 卷隔离、常驻会话执行的一种、gVisor/rootless 沙箱。**C1~C9 + S1 沙箱不是 P2/P3 后置项,是 P0 的地基**。

### 10.2 修订版 P0 方案细化（beachhead=S1 开发流水线 / 商业=私有化 License，2026-07-01 用户拍板）

> 用户已定:**beachhead=S1 开发流水线**、**商业=私有化 License(租户=部门,成本=部门分摊)**、下一步=先细化 P0。本节把 §10.1 的 C1~C9 + S1 沙箱落实成一个可评审、可证明价值的 P0 切片。**本节是 design 细化,不是实现 plan**;审过后再决定走界面 brainstorming 还是 writing-plans。

**0. 私有化 License 对设计的减负(与 SaaS 相比锁死)**:
- 租户=部门,**隔离务实降级**:Postgres **RLS(行级 tenant_id=部门)** + **per-job 卷隔离** 即够;**NATS Accounts 部门级隔离降到 P1**,P0 单 account + subject 前缀带部门即可。
- **无计费系统**:成本=**部门分摊报表**(计量即可),不做账单/套餐/用量计费。
- 网关配额=**per-部门预算护栏**,不是 per-tenant 商用限流。
- 部署形态=**服务端/网络部署为主**(§一.B 坑2:桌面单机 SKU 实质=纯察元,不硬撑本地指挥平台)。

**1. P0 价值假设与验收口径(必须证明"单 agent 做不到")**:
- **价值切片**:在指挥平台建一个开发任务(如"做个世界大小排名的小 web app")→ **Dev Agent(OpenHands 常驻会话)接国内/本地模型** → 在 **gVisor/rootless 沙箱容器**里写码 + **真跑起来** → **指挥中心 iframe 看到渲染预览** → 部署动作前 **`pending_approval` 人工审批门** → 产物落 **per-job 卷** → 汇总回大屏。
- **为什么证明价值(非管道)**:需真运行时 + GUI 预览 + 沙箱 + 审批门——**单个聊天 agent 一段对话无法完成**(这是对 §10.1 产品视角"MVP 只证管道"的直接回应)。
- **验收**:①端到端跑通上述链路;②沙箱内不可逃逸(socket 不入容器);③超 per-job token 预算自动 kill;④审批门能[批准]/[打回];⑤大屏实时看到进度事件流 + 预览。

**2. P0 范围(做什么 / 锁死不做)**:
- **做**:薄实时派活核心(Orchestrator P0 单实例但按无状态设计)+ Postgres 状态 + NATS JetStream(进度/事件)+ 心跳走 bridge WS + 独立 lease 判死 + 独立 bridge-gateway 连接层(P0 可与 Orchestrator 同进程但代码分层)+ OpenHands 常驻 server 执行 + gVisor/rootless 沙箱 + per-job 卷 bind + `pending_approval` 状态机 + per-job 预算护栏(接察元 `llm_callback`)+ OTel traceparent 最小链路 + 大屏最小集(见 6)。
- **锁死不做(明确后置)**:多机 reconcile/Nomad(P2)、Temporal 耐久层(P2,P0 引擎无耐久)、A2A 自主编舞(P3)、外部数据接入#15(P3)、投墙模式(P3)、复杂多 agent DAG(P0 就"1 Dev Agent + 1 审批门",线性)、LLM 分诊路由(P0 只 @昵称直派/规则快路)、NATS Accounts 部门硬隔离(P1)、SaaS 计费(不做)。

**3. P0 架构(薄实时核心 + 察元底座 + 子容器,落实 §10.1 冲突调和)**:
```
[大屏/新建任务]──HTTP──▶ Orchestrator(薄实时核心, 无状态化设计/P0单实例)
                             │  状态→ Postgres(Job/DAG/注册表, 弃SQLite)
                             │  进度/事件→ NATS JetStream(subject: job.<dept>.<id>.*)
                             ▼
                        bridge-gateway(终结反连WS+鉴权+发总线; 代码独立分层)
                             ▲ 反连WS(心跳+lease)
                    ┌────────┴─────────┐
              子容器 chatop-ai (gVisor/rootless 沙箱, 加固基线)
                    │ agent-bridge(常驻: 反连+收派活+事件流适配+lease心跳)
                    │ OpenHands server(常驻会话, 非subprocess-per-task)
                    │ per-job 卷 bind: $HOME/<code> ⇄ /workspace/<job_id>(仅该job子目录)
                    │ 起 web app 端口 → 网关暴露 → 大屏 iframe 预览
                    └ 出站默认拒绝 + 白名单(仅模型网关+批准端点)
             察元母体(能力底座, 不在热路径):
                    模型网关(国内/本地 + Anthropic shim, per-dept 预算护栏)
                    RBAC(部门=租户, RLS) · kb-query(P0 可选) · llm_callback(真实usage计量)
```
- **调和落地**:察元只做网关/RBAC/知识(非热路径);**实时派活核心独立薄层**,不经察元重 monorepo(回应 §10.1-E)。

**4. P0 技术选型(把 C1~C9+S1 逐条落到 P0)**:
| 地基项 | P0 落法 |
|---|---|
| C1 常驻会话 | OpenHands server 常驻(Dev Agent 一等);派活喂已热起的 session |
| C2 热路径禁LLM | P0 无实时决策场景(S1 非秒级),派活走 @昵称直派;kb-query 若用则 `synthesize=false` |
| C3 总线 | NATS JetStream(进度/事件);心跳走 bridge WS;**独立 lease 判死**(不靠总线有无心跳) |
| C4 无状态+选举 | Postgres 状态外置;bridge-gateway 连接层独立;P0 单 Orchestrator 但 reconcile 逻辑走 lease(为 P1 多活铺路) |
| C5 多租户 | 私有化降级:RLS(dept) + per-job 卷 bind;Accounts 延后 P1 |
| C6 人工介入 | `pending_approval` 一等状态 + 大屏审批门(部署前) |
| C7 成本护栏 | per-job token 预算,接 `llm_callback` 实时计量,超则 kill;per-dept 分摊报表 |
| C8 耐久引擎 | P0 自研 asyncio 引擎**锁死无耐久**(崩溃=重跑整 Job,先接受);Temporal 留 P2 |
| C9 一致性 | 产物 write-then-atomic-rename + `output/.done` 标记;reconcile 兼收 Job 态(死容器 Task→interrupted) |
| S1 沙箱 | **P0 定 rootless Docker 或 gVisor(二选一先做一个)**;容器加固基线 cap-drop ALL/no-new-privileges/seccomp/cgroup 硬限;**docker.sock 绝不入容器** |
| S2 技能供应链 | P0 不开放一键装(禁自动装);Dev Agent 用预置/pin 版本工具链 |
| S3 可插拔 | P0 先只 OpenHands 一个 adapter,但**按 `AgentAdapter` ABC 写**(spawn/stream/inject-charter/health/cancel),为加 agent 零改铺路 |
| S5 可观测 | OTel traceparent 全链路(注入 NATS header)+ 最小 metrics(派活延迟、bus lag) |

**5. P0 任务状态机(含人工介入)**:
`queued → dispatching → running → (pending_approval ⇄ running) → succeeded / failed / interrupted / cancelled`
- `pending_approval`:Dev Agent 触发部署/高危动作前置态,大屏[批准]→running、[打回]→带反馈回 running、[取消]→cancelled。
- `interrupted`:reconcile 发现承载容器死 → 该 Task 置此态(不谎报 running)。

**6. P0 界面最小集(完整界面留 brainstorming,P0 只做够验收的)**:
- **大屏**:全幅态势画布(P0 节点少:母体+1~N 子容器)+ 悬浮指挥条 + **事件流分层**(顶"需处理"含审批按钮)。
- **新建任务(最小)**:仅 goal 必填 + 选 Dev Agent(P0 就一个);job_id 隐藏,code 自动+冲突才提示。
- **进度**:P0 线性时间轴(Dev Agent 步骤 + 审批节点),暂不做复杂 DAG 图。
- **预览**:iframe 分级——先只读缩略帧,"进入操作"再拉全 VNC。
- 深色控制台原语(状态徽章/事件条)沉 `packages/chacmd-features`。

**7. P0 里程碑(供后续 writing-plans 展开,非最终 plan)**:
- **M1 骨架**:Orchestrator + Postgres + NATS + bridge-gateway;agent-bridge 反连注册 + lease 心跳;大屏看到"1 容器在线"。
- **M2 派活+执行**:@昵称派活 → OpenHands 常驻会话执行 → 事件流适配 → JetStream → 大屏实时进度;产物落 per-job 卷。
- **M3 沙箱+预览+审批+护栏**:rootless/gVisor 沙箱加固;起 web app → iframe 预览;`pending_approval` 审批门;per-job 预算 kill;OTel 链路。
- **M4 端到端验收**:跑通"建开发任务→沙箱开发+跑→预览→审批→汇总",过第 1 节 5 条验收。

**8. 明确留到 P1+(不在 P0)**:多机 Nomad reconcile、Temporal、A2A、外部数据#15、投墙、NATS Accounts 部门硬隔离、复杂 DAG、LLM 分诊、技能一键装市场、多 agent 齐全、S7 员工侧 UI 全套。

### 10.3 员工视图 + 各视角问题的系统解决方案（2026-07-01 用户确认产品视角，补员工视图）

> 用户确认产品经理的判断成立:**要有员工视图——每个容器常驻的服务能站在员工角度看自己的状态、成果、所有任务的工作记录**;并要求把各视角问题系统性给出"如何解决"。

**一、员工视图（Employee / Agent Self-View）—— 修订 §6.15 为"双壳三视图"**

原设计只有"指挥大屏(管理员上帝视角)"。现确立**两套壳、三种视图**:
| 视图 | 谁用 | 看到 | 由谁提供 |
|---|---|---|---|
| **指挥大屏** | 管理员/指挥官 | **全局**:所有主机/容器/任务/态势/成本 | 指挥中心 |
| **员工视图** | 普通员工(S7 云桌面) / agent 自省 / 非管理员默认落地 | **自己这一个容器**:我的状态/成果/工作记录 | **容器常驻服务(agent-bridge 扩展)** |
| **访客视图** | 访客 | 被分享的**单个任务结果**只读 | 指挥中心(分享链接) |

**员工视图看什么(对应用户原话三项)**:
1. **我的状态**:容器/agent 在线健康、忙闲、**当前正在执行的任务**、资源占用、连着哪个模型、**我的角色契约**(system_prompt/skills/goal/knowledge_scope,#18)。
2. **我的成果**:当前 + 历史任务的**产物**(output/ 文件、预览链接、交付物),可预览/下载。
3. **所有任务的工作记录**:我承接过的**全部任务履历时间线**——每个任务的目标、步骤日志、**事件流回放**、耗时、token 花费、状态、A2A 交接(给谁/从谁)、审批记录。即"个人工作履历 + 工作日志"。

**关键:由容器常驻服务提供 + 数据两级**:
- agent-bridge 扩出一个**本地员工视图服务**(轻量 HTTP/UI,经 Caddy 单端口暴露,或作为 KasmVNC 桌面里 app-manager 的"我的工作台" app)。
- **数据两级**:容器本地缓存(实时/当前会话)+ **中心 Postgres(历史真源)**。因容器会重启/销毁(§C9 一致性),**工作记录真源必须在中心**,员工视图查历史走中心 API(带该 subject 的 RBAC token,#14);实时态读本地。

**与指挥大屏的关系**:同一份底层数据(Job/事件/产物),按 RBAC(#14/§6.10"无权不出现")裁剪——员工只见自己的;**管理员从大屏下钻某容器 = 以管理员身份看该容器的员工视图**(视图复用,权限不同)。登录路由:员工登录默认落**员工视图**(非大屏),管理员默认落大屏(呼应 §10.1-D5"多角色视图分离,两套壳靠 RBAC+BrandConfig 决定")。

**隐私/信任(S7)**:员工视图内含"**agent 正在学习我什么**"透明区 + 知情同意开关 + 学到技能的**回看/批准**入口(呼应 §10.1-D5 隐私红线)。

**技术实现 + 落地**:agent-bridge 员工视图模块(本地缓存 + 反查中心)+ 前端复用 `packages/chacmd-features` 组件(任务卡/事件流/产物列表/契约卡)组装成个人工作台。**数据面 P0 已具备**(Job/事件/产物已在中心 Postgres);**员工视图 UI 落 P1**(M3 大屏之后);S7 学习透明落 P3。**更新 §6.18 容器内置清单**:新增能力 **G4 员工视图服务**(容器常驻,提供自省工作台)。

**二、各视角问题 → 解决方案 → 落地阶段(系统收口)**

*(技术地基 C1~C9/S1~S6 的 P0 落法见 §10.2 表,此处给完整跨阶段解法)*

**技术地基(架构 + 平台安全)**:
| 问题 | 解决方案(完整) | 阶段 |
|---|---|---|
| C1 执行模型 | P0 OpenHands 常驻会话;P1 扩 Hermes serve/OpenClaw 常驻;适配器双模式(one-shot + persistent) | P0→P1 |
| C2 热路径 LLM | P0 无实时场景直派;P1 快慢路(规则/缓存路由);实时场景(若做 S2)规则引擎+`synthesize=false` | P0→P2 |
| C3 总线/心跳 | P0 JetStream + WS 心跳 + lease;P1 分 stream 分 retention;心跳与判死永久解耦 | P0→P1 |
| C4 无状态+选举 | P0 Postgres 外置 + 单实例;P1 bridge-gateway 独进程 + reconcile lease;P2 active-active 分区 | P0→P2 |
| C5 多租户 | P0 RLS(dept)+per-job 卷;P1 NATS Accounts 部门隔离;网关 per-dept 预算 | P0→P1 |
| C6 人工介入 | P0 pending_approval + 审批门;P1 回滚(工作区快照)+步骤级介入+接管(接 #8 桌面) | P0→P1 |
| C7 成本护栏 | P0 per-job 预算 kill + 计量;P1 预估+燃尽+归因+部门分摊报表 | P0→P1 |
| C8 耐久引擎 | P0/P1 自研无耐久(崩溃重跑);P2 切 Temporal/Restate 拿续跑/定时/幂等 | P0→P2 |
| C9 一致性 | P0 原子产物标记 + reconcile 收 Job 态;P2 随 Temporal 强化续跑 | P0→P2 |
| S1 沙箱 | **P0 rootless Docker + 加固基线**(socket 不入容器);P1 gVisor/Kata 加强 | P0→P1 |
| S2 技能供应链 | P0 禁自动装 + pin;P1 allowlist+签名+沙箱执行;间接注入在工具/网关层降权 | P0→P1 |
| S3 可插拔 | P0 OpenHands 单 adapter 但按 AgentAdapter ABC;P1 加 Codex/Hermes 零改验证;Connector ABC | P0→P1 |
| S4 出站管控 | P0 默认拒绝出站 + 白名单(网关+批准端点) | P0 |
| S5 可观测 | P0 OTel traceparent + 最小 metrics;P1 Prometheus/Grafana 全套 + bus lag 告警 + SLO | P0→P1 |
| S6 多机调度 | P1 评估 Nomad;P2 落多机 placement/health/reconcile | P1→P2 |

**产品层**:
| 问题 | 解决方案 | 阶段 |
|---|---|---|
| 定位/beachhead | **已解:S1 开发流水线**,护城河=可操作整机桌面的异构 agent 舰队 | 已定 |
| 商业模式 | **已解:私有化 License(部门分摊)** | 已定 |
| 多角色产品形态 | **本节:双壳三视图(管理员大屏/员工视图/访客)** | P0数据/P1 UI |
| 缺失:成本预算 | 见 C7:护栏+预估+燃尽+分摊报表 | P0→P1 |
| 缺失:人工介入 | 见 C6:审批门+回滚+接管+步骤介入 | P0→P1 |
| 缺失:任务模板/工作流库 | 存为模板/克隆/参数化("每周财报"一键跑)——留存杠杆 | P1 |
| 缺失:通知 | 完成/失败/待审批 → 邮件/IM/webhook | P1 |
| 缺失:交付面 | 下载/导出/发布/回写业务系统 + 用户→系统迭代精修回路 | P0(下载)→P1 |
| 缺失:角色/agent 市场 | 角色契约分享/导入导出/市场(扩 §6.20 技能市场) | P2 |
| 缺失:合规呈现 | 审计导出 + 数据不出境证明(离线模型作卖点) + 知识访问报告 | P2 |
| MVP 证价值 | **已解:S1 切片(沙箱+运行时+预览,单 agent 做不到)** | P0 |

**界面 / UE 层**:
| 问题 | 解决方案 | 阶段 |
|---|---|---|
| 大屏双焦点 | 全幅态势画布 + 悬浮指挥条(⌘K) + 可折叠抽屉;投墙=画布减命令条 | P0 最小(M3)→完整P1 |
| 员工视图缺失 | **本节:容器常驻员工视图(状态/成果/工作记录)** | P1 |
| 技能管理散在容器 | 提到大屏中央能力库(搜索→下发→绑角色);容器内降本地兜底 | P1 |
| 事件流五类挤一管 | 按严重度分层(顶"需处理"带动作/中活动摘要/底审计收起) | P0 顶区(M3)→完整P1 |
| DAG 可读性 | P0 线性时间轴 + 审批节点;P1 泳道/sub-DAG 折叠/回环计数徽章/图列表切换 | P0→P1 |
| 深色控制台设计系统 | 状态徽章/密集表/指标卡/图节点沉 `chacmd-features`,深色单独校对比度/色觉 | P0 起沉淀 |
| onboarding/空状态 | 首启引导(纳管→起容器→建角色→派首任务)+ 各面板空状态 CTA | P1 |
| S7 学习透明 | 员工视图内知情同意 + "正在学习"指示 + 回看批准 | P3 |
| 进 plan 前 UI 设计 | **M1~M2 后端直接 writing-plans;M3+ 界面(大屏/员工视图/审批/预览)走界面 brainstorming** | 流程 |

### 10.4 超大规模 / 党政军 / 分布式集群的架构冲击评估（2026-07-01，含 Nacos 接入）

> 用户追问:企业 1 万人 / 1 万容器工作站、党政军、分布式集群下有没有遗漏、有没有**会推翻架构**的地方;并要求**可接入 Nacos(可配置开关,ChaCMD 后台配置)**。

**结论先行**:当前设计对**中小私有化(数百~千级容器、普通企业)成立**;放大到**万级 / 党政军涉密 / 多机房分布式**时——**4 处会推翻或重塑架构、9 处重大遗漏、若干分期须提前**。核心判断:**架构骨架方向(覆盖网反连、母体复用、事件驱动、可插拔)在大规模下仍成立,但"P0 单中心 + 自研协调环 + 每 agent 一重桌面 + 锁 x86/Postgres/标准密码"这些隐含假设在万级/信创下会碎。**

**A. 会推翻/重塑架构(必须现在决策,否则后期大改)**：
- **A1 信创国产化栈(若含党政军/国企,最大推翻点)**：CPU 鲲鹏/飞腾/龙芯(ARM/LoongArch 非 x86)、OS 麒麟/UOS、**DB 达梦/人大金仓/GaussDB(非 Postgres!)**、推理 NPU 昇腾/寒武纪(非 CUDA,vLLM 要昇腾 MindIE)、通信/存储**国密 SM2/3/4 + TLCP(非标准 TLS)**。**冲击**:①DB 层必须抽象(ORM/方言),不能锁 Postgres;②所有镜像**多架构构建**(x86+ARM+LoongArch),Tauri/PyInstaller/依赖要能在国产架构编译;③沙箱 gVisor/Kata 在国产 CPU/内核可用性存疑,可能只能用国产安全容器;④密码学要可换国密。**现设计完全没考虑信创**——这是最需要现在拍板的岔路。
- **A2 "不用 K8s"在万级 + 跨机房站不住**：自研覆盖网 + 轻量 reconcile 适合中小规模;**万级 + 多机房时网络分区是常态,自研 lease/fencing/quorum 不现实**,必须成熟分布式协调(etcd/K8s/Nomad,信创场景=国产 K8s 如华为 CCE/青云/KubeSphere)。**重定位**:覆盖网负责"应用层 agent 调度"(反连、派活、事件),**底层容器编排与协调在大规模时委托 K8s**(而非自研跨机 reconcile)。§6.9/§11 的"轻量自研 reconcile"仅限中小规模。
- **A3 单中心 → 分层/联邦指挥(战区制)**：万级跨地域(总部+分支)不能单 Orchestrator（哪怕 active-active）。改**分层树/联邦**:全局指挥中心 + **区域指挥节点(战区)** + 容器;区域自治 + 向上汇聚(正好契合 S1 分层指挥与军事战区隐喻)。架构从"星型"改"分层联邦"。
- **A4 默认容器形态:无头轻量 vs 桌面重容器**：1 万 × 3GB 桌面 = 30TB 内存,不可行。**默认无头轻量 agent 容器,重桌面容器(chatop-ai)按需起 + 用完回收**(冷/热池、空闲回收、按需唤醒)。修正"每 agent 一常驻桌面"的隐含假设——**桌面舰队是护城河特性,但规模化时是按需资源不是常态**。

**B. 重大遗漏(加,一般不推翻骨架)**：
- **B1 企业统一身份**：对接 LDAP/AD/OIDC/SSO + 国产身份(麒麟信安/宁盾),不能只靠察元内置账号(1 万人 + 组织树)。
- **B2 三员分立 / 职责分离(SoD) / 双人复核**：党政军涉密"系统管理员/安全保密员/审计员"权力制衡,RBAC 要从"资源级"扩到"三员 + SoD + 双人操作复核"。
- **B3 国密算法**：SM2(签名)/SM3(摘要)/SM4(加密)/TLCP(国密 TLS),密码学层可替换(见 A1)。
- **B4 内容安全 / 生成式 AI 合规**：agent 输出过内容安全网关(生成式 AI 管理办法、备案、涉政涉密过滤)。
- **B5 完全离线 + 国产 NPU 推理**：涉密网物理隔离→**离线唯一**(国内云 API 也不能用),模型后端必须支持昇腾 MindIE/寒武纪(非 CUDA);#20 对外调用限内网。
- **B6 分布式存储 + DB 扩展**：共享卷单 NFS 在万级并发会崩→Ceph/国产分布式存储 + 分租户分区;Postgres 单库不够→分库分表/读写分离(或分布式国产库)。
- **B7 多架构镜像流水线**：x86 + ARM + LoongArch 构建、私有 registry、SBOM。
- **B8 大规模运维**：批量升级/灰度、容器池化(冷热池/按需唤醒/空闲回收)、准入控制 + 队列深度上限 + 背压反馈。
- **B9 服务注册发现 + 配置中心可插拔(整合用户 Nacos 需求)**：万级下 host-bridge/agent-bridge/Orchestrator/gateway 多实例需**服务注册与发现** + **统一配置动态下发/热更新**。**设计为可插拔 provider**:定义 `ServiceRegistry` / `ConfigSource` SPI 抽象——**内置实现(Postgres/自研注册表)为默认;可选接入 Nacos(服务发现 + 配置中心,国产友好);预留 Consul/etcd/Eureka**。**ChaCMD 后台可配置"服务发现/配置源 = 内置 | Nacos | …",开关接入或不接入**(小规模用内置零依赖,大规模/已有 Nacos 的企业接入 Nacos)。Nacos 正好减轻 A2 的服务发现与 #10 配置中心自研负担。配置项:Nacos 地址/命名空间(按租户/部门)/分组/鉴权/开关。

**C. 分期必须提前(万级不能后置到 P2/P3)**：连接层水平分片(独立 bridge-gateway 集群 + 一致性哈希路由)、Orchestrator active-active、成熟协调(K8s/etcd)、可观测全套(万级排障刚需)、DB/存储分片。这些在中小规模可后置,**万级/党政军目标下须列入早期**。

**D. 决定架构的岔路(必须用户拍板,否则无法定 P0 边界)**：
1. **目标客户是否含党政军 / 涉密 / 国企信创?** → 决定 A1(信创栈)/B2(三员)/B3(国密)/B4(内容安全)/B5(离线+国产 NPU) 是否为硬约束。若是,DB 抽象/多架构/国密/离线要**从 P0 预留接口**(不必 P0 实现,但不能锁死)。
2. **规模形态:单体万级 vs 多个千级部署?** → 决定 A2(K8s)/A3(联邦战区)/连接层分片 是否早期投入。若是"多个千级独立私有化部署",当前中小架构 × N 即可,不必联邦;若"单体万级/跨地域",须联邦 + K8s。
3. **是否要求完全离线?** → 决定模型后端(国产 NPU 本地权重 vs 国内云 API)。

**对 P0 的影响(务实)**:P0 仍是 S1 价值切片(中小规模),**但为避免大改,P0 须预留三个抽象接口**:①DB 访问层(不硬编码 Postgres 方言);②密码学层(不硬编码 TLS/AES/HMAC,可换国密);③`ServiceRegistry`/`ConfigSource` SPI(内置默认,可接 Nacos)。**其余信创/联邦/K8s 按岔路结论决定是否进 P1/P2**,不进 P0 实现。

### 10.5 P0 必须预留的抽象接口清单（不返工的地基，M1 硬约束）

> 收口 §3.9 / §10.2 / §10.4 散落的"P0 预留接口"。**原则：P0 只做"接口 + 一个默认实现"，不实现所有 provider**——这是"预留可换接口"，不是"功能全做"。判据：**若 P0 不预留、后期加会渗透大量调用点导致重构，则必须 P0 预留**；局部新增的留到 P1。这张表是 M1 后端骨架 writing-plans 的硬前置。

| # | 接口 | 抽象什么 | P0 不预留的返工代价 | P0 默认实现 | 未来可换 | 来源 |
|---|---|---|---|---|---|---|
| **I1** | `ChayuanClient`（全 HTTP） | ChaCMD 对察元的**全部**依赖：网关 `/v1` / kb-query / authz / 身份 / 察元界面跳转 URL | 察元调用散落各处；**形态 C 轻量挂载无法实现**，要重构 | HTTP → `localhost:8000` | 远程挂载（形态 C）；少量低延迟直 import 优化 | §3.9 |
| **I2** | DB 访问层（Repository + 方言隔离） | 持久化：Job/DAG 状态、注册表、审计 | 锁 Postgres 方言，国产库（达梦/金仓/GaussDB）要改所有 SQL | PostgreSQL | 国产库方言 | §10.4-A1/R8 |
| **I3** | 密码学层 `Crypto` | 加密/签名/摘要/传输安全 | 硬编码 AES/HMAC/SHA/TLS，国密（SM2/3/4·TLCP）要改所有点 | 标准 TLS/AES/HMAC/SHA | 国密 SM + TLCP | §10.4-B3/R8 |
| **I4** | `ServiceRegistry` + `ConfigSource` SPI | 服务注册发现 + 统一配置源 | 散落各组件，接 Nacos/Consul/etcd 要重构 | 内置（自研/PG） | **Nacos（可选，后台配置）** / Consul / etcd | §10.4-B9 / #21 |
| **I5** | `AgentAdapter` ABC | 派活执行：spawn / stream / inject-charter / health / cancel + capability manifest | 硬编码 `if system_id`，加 agent 要改核心 | OpenHands adapter | Codex / Hermes / OpenClaw / Claude Code | §10.1-S3 / NFR-M1 |
| **I6** | `EventBus` 抽象 | 事件 / 进度 / A2A 收发 | MVP→生产→信创 切换要改所有收发点 | Redis Streams（MVP）或直接 NATS | NATS JetStream / 国产 MQ | §10.1-C3 |
| **I7** | 沙箱运行时 `Sandbox` provider | 容器起法 / 隔离后端 | rootless→gVisor/Kata/国产安全容器 切换改容器供给 | rootless Docker | gVisor / Kata / 国产安全容器 | §10.4-A1 / NFR-SEC1 |
| **I8** | 身份认证 `AuthProvider` | 登录 / 鉴权 / token 签发校验 | 锁察元内置账号；**形态 C 跨实例 SSO + 企业 SSO + 三员分立**无法接 | 察元内置（经 I1） | OIDC/LDAP/AD/SSO + 一次性 token（形态 C）+ 三员扩展 | §10.4-B1/B2 / §3.9 |
| **I9** | 前端 SKU 注入 seam | BrandConfig(homeComponent) / createAppRouter / build-by-SKU / **chayuanUiMode(embedded｜mounted)** | 单 app 耦合，双 SKU 与形态 C 无法分离 | ChaCMD BrandConfig | embedded↔mounted 切换 | §3.7 / §3.9 |
| **I10** | 传输/寻址抽象 `Transport` | **逻辑名→传输**（昵称/subject/卷路径，**屏蔽 IP**） | 硬编码容器 IP，动态重建/跨主机/容灾/万级全崩 | 反连 WS + 总线 subject + 共享卷 | 覆盖网点对点(MagicDNS/mesh) / 国产网络 | §6.22 |

**说明**：
- **模型后端不单列**：ChaCMD 不自建模型抽象，经 **I1 → 察元网关**调用；国产 NPU（昇腾 MindIE）是察元网关后端能力（ChaCMD 依赖、不实现）。
- **留到 P1（非 P0 预留）**：`Connector` ABC（#15 外部数据接入，P3 实现，接口 P1 定）；三员分立/SoD 完整（P2，但 I8 已留口）。
- **验收**：M1 完成时，上述 I1~I9 各有**接口定义 + 默认实现 + 至少一处替换点注释/桩**，可通过"换一个实现不改调用方"的冒烟验证（如 I4 从内置切 Nacos 桩、I6 从 Redis 切 NATS 桩）。

---

## 11. 风险与开放问题

1. **资源**：桌面型容器 ~3GB+/个，10 个就 30G+ 内存压力（现状磁盘已紧张，preinstall 已因磁盘把 Hermes/OpenHuman 改成一键装）。多机/集群下需明确节点规格与配额；**热备（§6.9）会成倍吃资源，默认冷备**。
2. **OpenHuman 无法无人值守派活**：核实其无任何官方无头接口（无 CLI/API/server/MCP-server），纯 Tauri 桌面 GUI。**定位为人工桌面型**，ChaCMD 只"免密开界面"(需求8)，不当无头派活对象；若确需自动驱动，只能 GUI 自动化硬驱（脆弱）或改其 Rust 源码（成本高）。**Hermes 反之**：经核实有 `hermes -z` / `serve` / MCP 等多档无头模式，已升级为一等派活对象（见 §3.1）。
3. **OpenClaw 双重身份**：它本身就是"网关 + 多 agent + node 反连"控制平面，与我们的"agent-bridge 反连覆盖网"高度同构。待定：是把 OpenClaw 当"被编排的一个 agent"，还是**直接借它的 WS 网关 + node 协议当覆盖网底座**（省自研 bridge）？建议先评估 OpenClaw node 协议能否承载我们的派活/回传契约，能则复用、不能则自研轻量 bridge。
4. **集群成员管理**：覆盖网下需处理 bridge 断线重连、僵尸容器回收、心跳超时摘除。
5. **jeecg 与 Orchestrator 的边界**：鉴权 token 流转、用户态同步需定契约（jeecg 签发 JWT，Orchestrator 校验）；§6.10 资源级授权的判定结果如何高效暴露给网关/Orchestrator（缓存 vs 每次问）待定。
6. **共享卷并发写**：多容器写同一 `task-id` 目录需约定子目录隔离 + 锁或"单写多读"。
7. **免密开界面的安全面**：一次性 token 的有效期/作用域/审计要严，避免越权开他人容器；与 §6.10 Grant 强绑定。
8. **国内 API 代理**：catalog 已注明"国内 API 需代理"，配置中心的 Base URL 必须支持每 agent 独立代理。
9. **A2A 失控（需求 12）**：防环/防风暴靠 `job_id`+`hop` 计数+TTL，阈值待压测定；消息总线本身是单点，需主备；通道授权在建链时做一次 RBAC，授权变更后已建通道的回收策略待定。
10. **容灾边界（需求 13）**：① **指挥中心自身 SPOF**——Orchestrator/总线/jeecg 挂了谁来自愈？本期单点+状态落盘，目标态需主备（Raft/keepalived）。② **脑裂**——网络分区下心跳误判为死，可能重复拉替身；需要 fencing/租约（lease）防双活。③ 任务**幂等性**是断点续跑的前提，派活契约必须保证重复执行无副作用。④ 整机宕机的跨节点改派依赖共享卷（NFS/Ceph）就绪，否则产物丢失。
11. **资源级授权粒度（需求 14）**：是否需要到"按容器内单个 app/单个 skill"授权，还是"按容器/角色"够用？过细会爆炸 Grant 表；建议起步按容器/角色，按需下沉。
12. **外部数据接入安全（需求 15）**：入站是主要攻击面——SSRF、数据投毒触发恶意编排、webhook 伪造。必须源白名单 + 信任分级（低信任源只触发只读工作流）+ 速率限制；外部事件**默认不得直接驱动高权限 agent**，需经审批或降权。
13. **模型网关安全与依赖（需求 16）**：① LiteLLM PyPI **`1.82.7/1.82.8` 出过窃取凭据的投毒版本**，必须 pin 已知干净版 + 锁依赖 + Key 走金库（绝不明文）。② 网关是所有 agent 的咽喉，**不能成 SPOF**：多实例 + 健康检查纳入容灾（§6.9）。③ Codex 的 **Responses-vs-Chat 协议**坑需在网关侧确认能正确转换（Phase 0 实测）。
14. **"完全离线 / 是否要开源 agent"分叉未定（需求 16）**：方案随两点分叉——(a) 是否要求推理**数据不出境**（→ 网关后端挂 Ollama/vLLM 本地权重）；(b) 是否要求**连 agent CLI 也开源可审计**（→ 用 OpenHands/Aider/Goose 替代闭源 Claude Code/Codex）。**待用户确认**后再定主线，默认：网关接国内云模型 + 保留 Claude Code/Codex 闭源 CLI（体验最强）。

---

## 12. 参考来源

- Claude Code Headless：<https://code.claude.com/docs/en/headless>
- Codex 非交互模式：<https://developers.openai.com/codex/noninteractive> ；exec 文档 <https://github.com/openai/codex/blob/main/docs/exec.md>
- OpenClaw 架构/网关：<https://docs.openclaw.ai/concepts/architecture> ；<https://docs.openclaw.ai/cli/gateway>
- Hermes Agent（Nous Research）：<https://github.com/nousresearch/hermes-agent> ；<https://hermes-agent.nousresearch.com/docs/>
- OpenHuman（tinyhumans）：<https://github.com/tinyhumansai/openhuman>
- 1Panel（曾评估，**已否决**，见 D6）：<https://github.com/1Panel-dev/1Panel>
- Docker Engine API / SDK（直管所选）：<https://docs.docker.com/engine/api/> ；Python SDK <https://docker-py.readthedocs.io/>
- jeecg-boot：<https://github.com/jeecgboot/JeecgBoot>
- claude-code-router：<https://github.com/musistudio/claude-code-router>
- LiteLLM（AI 网关，100+ 模型，双协议）：<https://github.com/BerriAI/litellm> ；Anthropic `/v1/messages` 统一端点 <https://docs.litellm.ai/docs/anthropic_unified/> ；接非 Anthropic 模型 <https://docs.litellm.ai/docs/tutorials/claude_non_anthropic_models>
- Codex 自定义 provider（config.toml / wire_api）：<https://developers.openai.com/codex/config-advanced>
- new-api / one-api（国内模型聚合网关）：<https://github.com/Calcium-Ion/new-api>
- 开源 coding agent（**OpenHands 首选做 Dev Agent §6.17**）：OpenHands <https://github.com/OpenHands/OpenHands> ；本地/离线模型（Ollama/vLLM）<https://docs.openhands.dev/openhands/usage/llms/local-llms> ；无头 `--headless --json` 事件流；Aider <https://github.com/Aider-AI/aider> ；Goose <https://github.com/block/goose>
- OpenCode（纯代码备选，`opencode serve` OpenAPI）：<https://github.com/sst/opencode> ；server 文档 <https://opencode.ai/docs/server/>
- Hermes 委托编码子 agent（协调者）：<https://hermes-agent.nousresearch.com/docs/user-guide/skills/optional/autonomous-ai-agents/>

---

## 13. 下一步

本设计稿评审通过后，用 `writing-plans` 拆 **Phase 0 + Phase 1** 的实施计划（先把"NL 派活 → 无头 agent → 流式回传 → 共享卷 → 配置注入"这条命脉跑通），再分阶段推进。
