# ChaCMD 需求全方位分析报告（2026-07-05）

- 主题：需求剩余清单 · 与母体察元关系实证 · 产品/架构/用户/美工四视角评估 · 可行性逐项判定 · 业界同类项目对标
- 证据来源：① 本地文档与代码实证（需求 SRS、总设计、大屏设计、P0 骨架 58 测试实跑、`/work/chayuan-desktop` 全仓探查）；② 联网深度调研（5 路检索 + 对抗验证；8 条主张 3/3 票通过，另约 20 条已取证但验证轮次因会话限额未走完，文中以「高置信/中置信」区分）
- 结论先行：**愿景成立、本体正确、母体杠杆真实；但存在 2 处文档级事实错误需立即修正（License、集成契约），P0 价值切片尚未闭环（M3/M4 未做），且"完整组合无业界对标"意味着护城河与工程量是同一枚硬币的两面。**

---

## 一、核心概念本体解读（数字员工 / 工位 / 引擎 / 技能 / 记忆）

ChaCMD 的领域模型是"四层解耦"，每层含义与业界印证：

| 概念 | 本质 | 业界独立证据（本次联网核实） |
|---|---|---|
| **数字员工** | 持久**身份**，外置于容器——机器挂了身份不丢，唯一 ID | Okta for AI Agents（agent 注册为一等身份、绑 owner、短期凭据，2026-03 EA）；Microsoft Entra Agent ID（agent 作为非人类身份纳入企业 IAM）→ 「身份外置」已是主流 IAM 厂商产品方向【中置信：已取证未走完验证】 |
| **容器 = 工位** | 短暂**运行时**，可丢弃/可重建/可迁移 = 天然容灾；KasmVNC 桌面容器即"员工的电脑" | TClone（UCSD, 2026-05）把"活的 GUI 工作区"做成可快照/fork/回滚的系统原语【高置信 3/3】；E2B Desktop（VNC 可视桌面沙箱）、Daytona（agent 无关沙箱、100 并行副本用完即销）、Kasm Workspaces（商业级容器桌面流式交付）【中置信】 |
| **引擎 + 技能** | openclaw/Hermes/codex/Claude Code/OpenHands 是**能力不是身份**——装在工位里的公共能力池；一个装三引擎的容器是"一个会三种手艺的员工"，不是三个人 | Cua（trycua）用统一 API 抽象任意 VM/容器沙箱并适配异构 CLI agent【高置信 3/3（沙箱抽象部分）】；SKILL.md 已从 Claude Code 单家扩展为 26+ 工具支持的开放标准，OpenAI Codex 官方采纳【中置信】 |
| **记忆** | 外置、可插拔——换容器身份+记忆都不丢 | Mem0/Zep/Letta 已成独立商用"记忆基础设施"品类；"externalize state 是第一架构原则"成为共识【中置信】 |

**判定：本体设计是对的，且不是自造词**——四层每一层都有独立的业界产品/学术印证。但要注意：**没有任何一家把四层完整组合成"桌面工位舰队 + 指挥驾驶舱"**（见第六节），这是差异化，也是无人验证过的组合风险。

数据模型上「N:N 建表 + 1:1 默认策略」（容器⇄员工 placement、员工⇄任务 assignment 走映射表）是正确的防返工决策——业界 identity 与 runtime 从第一天就是多对多解耦。

---

## 二、与 /work/chayuan-desktop（察元母体）的关系——实证结论

### 2.1 关系模型（设计意图）

- **察元 = 母体内核**：提供模型网关、RBAC/组织/审计、知识库 kb-query、agent 框架——做"大脑与能力底座"（非实时热路径）。
- **ChaCMD = 横向调度增量**：补察元没有的"跨容器多实例分发、覆盖网反连、统一调度、DAG 编排、容灾 reconcile"——实时派活核心独立为薄层。
- **chatop-ai（本仓库）= 工位镜像**：KasmVNC 子容器，数字员工的"电脑"。
- 治理：monorepo 双 SKU + 依赖单向（察元永不 import ChaCMD）+ feature-flag + 防腐层 + 全 HTTP `ChayuanClient` 抽象（形态 B localhost / 形态 C 远程同一套代码）。

### 2.2 本次全仓实证（含两处文档错误修正）

| 核实项 | 结论 | 影响 |
|---|---|---|
| 项目真实性/活跃度 | ✅ 真实且活跃：Tauri 2 + React 19 + FastAPI monorepo，后端 ≈26.6 万行 Python（1442 文件），前端 ≈11.9 万行，最近提交 2026-06-30（v2.0.348），近期主题正是 org/RBAC | 母体杠杆真实可靠 |
| 模型网关 | ✅ 超预期：`PROVIDER_CATALOG` 实测 **75 个 provider**（文档说 25+），两套 OpenAI 兼容端点（独立 gateway 微服务 + 内嵌 `/v1/*`），Ollama/vLLM 本地模型一键装 | #16 复用成立 |
| Anthropic `/v1/messages` | ❌ 不存在（符合设计预期，需 ChaCMD 自建 shim） | Claude Code 接入前置项 |
| RBAC/组织/审计 | ✅ 真实成熟：org/dept/role/user/kb_acl 全套模型 + 路由 + e2e 测试 | #14 复用成立 |
| **集成契约** | ❌ **错配**：ChaCMD `HttpChayuanClient` 硬编码的 `POST /api/v1/authz/check` 与 `GET /api/v1/whoami` **在察元均不存在**（whoami 真实路径是 `/openapi/v1/whoami`；authz/check 全仓零命中） | **P0 集成一连就 404，必须先修** |
| kb-query | ✅ `POST /api/v1/kb-query/search` 完全对齐 | 知识层复用成立 |
| agent 框架 | ✅ 双层：LangChain 派生框架 + `agent_connector/`（已有 hermes/openclaw adapter，claude-code adapter 落点现成） | #17 复用成立 |
| **License** | ❌ **文档错误**：实际 **Apache-2.0**（LICENSE 文件），非设计文档声称的 AGPL-3.0 | **合规顾虑基本解除**，发行策略重大利好；需求 §1.5/R3 需修订 |
| headless 部署 | ✅ 标准 FastAPI + 完整 docker compose 矩阵（单机/拆分/dev） | 形态 B/C 可行 |
| 与 chatop 主干耦合 | 目前仅设计文档 + worktree 代码层面；主干只有品牌资产引用，无运行时依赖 | 部署编排尚未打通 |

**结论**：母体关系的架构判断（复用四大能力 + 补横向调度）经实证**成立且比文档预想更有利**（provider 更多、license 更宽松），但暴露了一个流程问题——**骨架是"对着文档写的"，没做过一次真实集成冒烟**，两个 404 端点就是证据。

---

## 三、需求剩余内容（逐项清单）

### 3.1 当前基线

P0 计划 M1+M2（后端骨架）已完成：10 个接口抽象（I1–I10）、反连注册、@昵称派活、事件流、per-job 卷、状态机（含 pending_approval）、Task-as-API code 端点、58/58 测试绿（实跑验证）。**M3/M4 未开始，P0 五条验收 0 条完整通过。**

### 3.2 P0 剩余（闭合价值切片的硬缺口，按依赖排序）

| # | 剩余项 | 需求来源 | 现状 |
|---|---|---|---|
| 0 | **修集成契约**（authz/check、whoami 404）+ 首次真实察元冒烟 | #17/#14 | 新发现，最优先 |
| 1 | 真 OpenHandsAdapter（替换 FakeAgentAdapter 非 fake 路径） | #5/#6/S1 | ABC 已就位 |
| 2 | 真 rootless Docker 沙箱 + 加固基线（cap-drop/seccomp/userns/read-only）+ 实机验证 socket 不入容器 | NFR-SEC1/#2 | 仅代码级 guard |
| 3 | Anthropic `/v1/messages` shim（LiteLLM 或 claude-code-router） | #16 | 未建 |
| 4 | 审批门 API（批准/打回端点；状态机已埋 pending_approval） | NFR-H1 | 半成 |
| 5 | per-job token 预算 kill（网关层护栏，接察元 `llm_callback` 真实 usage） | NFR-C1 | 未做 |
| 6 | NATS JetStream 替 InMemoryEventBus；Postgres+RLS 替 SQLite | NFR-P3/S1/T1 | 抽象已留 |
| 7 | OTel traceparent + Prometheus 最小集 | NFR-O1 | 未做 |
| 8 | iframe 桌面预览 + 指挥大屏 v1（星群 L0 + 事件流 + KPI）+ 新建任务最小表单 | 大屏/新建任务 | 设计稿待评审 |
| 9 | 一键起子容器（真容器供给，#2）+ 中心配置下发到容器 env（#10） | #2/#10 | Fake/SPI 就位 |
| 10 | M4 端到端验收 5 条（建任务→沙箱开发→预览→审批→汇总；逃逸；预算 kill；审批门；大屏实时） | §8 | 0/5 |

### 3.3 P1 剩余（全部未开始，除注明）

#13 单机容灾（判死已有 ✅，缺重建/改派/在途重放）、#9 下发安装与角色配置、#19 知识源范围授权、部署纳管 host-bridge（agent-bridge 已有 ✅）、员工视图 UI、技能体系（SKILL.md 安装适配 + allowlist/签名/沙箱）、#20 Task-as-API 完整（per-caller Key/幂等/webhook HMAC；code+端点已有 ✅）、#21 Nacos provider（SPI 已留 ✅）、#18 Charter 触发/交接、#11 复杂 DAG、NFR：连接分片背压/租户 Accounts/部门配额/OTel 全套/SEC3/4/6/Vault/成本报表/回滚接管、大屏 v2（L1 任务下钻）。

### 3.4 P2/P3 剩余（全部未开始，方向正确地后置）

P2：#8 免密开界面完整、跨机容灾、Temporal 耐久编排、active-active、Nomad 评估、大屏 v3/v4、信创合规呈现（GX4/GX5）。
P3：#12 A2A 直连、#15 外部数据接入、投墙、S7 学习进化。

### 3.5 悬而未决的决策项（阻塞架构边界）

1. §8 三岔路：党政军/涉密？单体万级还是多个千级？完全离线？——未定前 P0 只做接口预留（当前做法正确）。
2. ~~AGPL 合规决策~~ → **已被实证解除**（Apache-2.0），改为"更正文档记载"。
3. OpenClaw 双重身份（§11.3）：借其 WS 网关 + node 协议当覆盖网底座，还是当被编排 agent？**建议尽快评估**——若可复用能省一大块自研 bridge。
4. 大屏 07-02 设计稿待评审（阻塞前端 v1 开工）。

---

## 四、四视角合理性与稳定性分析

### 4.1 产品视角

**合理的**：
- Beachhead = S1 开发流水线选得对：这是"单个聊天 agent 明显做不到"的场景（真运行时 + GUI 预览 + 沙箱），MVP 证明价值而非只证明管道——这一课设计文档自己已经上过（§10.0）并纠正了。
- 商业模式（私有化 License、租户=部门）与国内/离线/RBAC 侧重自洽；Apache-2.0 实证后发行灵活度更大。
- 护城河判断**经联网验证为真**：「异构 CLI 引擎 × 桌面工位舰队 × 企业治理 × 指挥驾驶舱」的完整组合在业界**没有直接对标物**（见第六节）。垂直"AI 员工"产品（11x、Maisa 等）有营收级落地但全是垂直封装，不做通用异构舰队。

**要警惕的**：
- **竞争窗口在收窄**：Cua 商业侧已宣传 "Scale computer fleets for computer-use agents" 且声称适配 Claude Code/Codex/OpenClaw；Anthropic Agent Teams 官方入场（虽是单机/单用户/同构/文件系统协调，尚非跨容器控制面【高置信 3/3】）。差异化窗口大约在"企业治理 + 私有化 + 驾驶舱"侧，纯"舰队跑 agent"的基础设施层会很快商品化。
- **bytebot 之鉴**：单 agent 桌面容器的头部开源项目已停止维护（2026-03 归档）【中置信】——"给 AI 一台电脑"本身不构成产品，舰队级调度+治理才是；这反过来支持 ChaCMD 的定位，但也说明该市场尚未被消费验证。
- 范围仍是头号产品风险：21 条功能 + 40 余条 NFR + 7 场景，P0 收窄纪律必须执行到底，任何"顺手做 P1"都在稀释闭环。

### 4.2 架构师视角

**合理且稳定性有先例背书的**（联网核实）：
- **lease 判死**：Kubernetes KEP-589 是教科书级先例（心跳吃掉 80% apiserver CPU 后改 Lease 对象）——ChaCMD "心跳与判死解耦" 的 C3 决策正是规避了同一失效模式。
- **万级反连控制面**：阿里 10k 节点 K8s 集群生产证据 + NATS leaf node 边缘设备反连（IoT 领域成熟用法）——"万级容器 + lease + NATS JetStream" 是已解决的工程问题，不是新颖风险。
- 四视角评审（C1-C9/S1-S6）质量很高且已内建到 P0 骨架：常驻会话接口、热路径禁 LLM、状态外置抽象、无 IP 寻址、插件 ABC、自研耐久引擎锁死无耐久（P2 切 Temporal）——这些都是对的。
- 信创红线 R8 的"P0 只抽象不实现"策略正确，且实测骨架确实全部走了可替换接口。

**不稳定/需修正的**：
1. **契约错配暴露流程缺陷**：接口写死了不存在的端点还全测试绿——因为测试全是 Fake。**必须给 CI 加一条"真实察元 docker-compose 冒烟"**，否则 HTTP 抽象层的每个方法都是潜在 404。
2. **Fake 滞留风险**：非 fake 路径也接 FakeAgentAdapter（M3 计划内），但 M2 完成后每多停留一周，"骨架完成"的幻觉成本越高。InMemoryEventBus/SQLite 同理——NFR-S1 明确说"第一天就上 Postgres"，实际 dev 还在 SQLite，迁移要趁表还少。
3. **workspace 目录按 `code` 而非 `job_id`**（`Workspace.job_dir`）：与设计 §6.4 `/workspace/<job_id>/` 有偏差——同一 code 多次运行会共用目录，与"每次调用产生新实例 job_id"语义冲突，趁早对齐。
4. **自研面仍偏大**：bridge-gateway/registrar/lease/reconcile 全自研。建议：工位供给层认真评估复用 Kasm 的 Manager/Agent 语义或 Cua 沙箱抽象；覆盖网评估 OpenClaw node 协议（§11.3 待定项）——"护城河在指挥语义与治理，不在传输层"。

### 4.3 用户视角（指挥官 / 员工 / 访客）

- **指挥官**：驾驶舱"对话即指挥 + @昵称直派"心智模型清晰；HITL 设计（Intent Preview、自主度调节钮 Suggest→Draft→Execute、动作回执/可撤销）是业界正确做法。但**审批门 API 还没做**——对企业用户，"能拦住 AI"是信任的第一块砖，它在 M3 的优先级应排最前，而不是与 OTel 并列。
- **员工（S7 / 非管理员）**：需求明确"员工视图必须能看状态/成果/工作记录"，但排 P1 且完全未开始。**日常打开系统次数最多的是员工不是指挥官**——建议员工视图最小版（我的任务 + 我的产物）提前进大屏 v2 周期，否则产品在员工眼里是"监控我的系统"而非"帮我的系统"，推行阻力会真实出现。学习进化（P3）涉及的"学习知情同意/正在学习指示"是隐私红线，评审 D5 已列，落地时不可省。
- **访客**：分享只读单任务结果，P1 合理。
- **跨视图一致性风险**：工作记录真源在中心、实时态读本地（agent-bridge）——两源展示同一履历，断连时序错乱要有明确的"以中心为准"降级提示，否则用户会看到"我明明做完了但大屏说没做"。

### 4.4 美工/设计视角

- **"3D 游戏化总览 + 2D 工程下钻"双层**：联网核实这不是臆想——Anduril Lattice（游戏引擎化 C2，单操作员督导自治资产群，74+ 系统接入）证明"游戏感舰队指挥 UI"在最高风险域都有用户接受度；数据中心数字孪生 3D 大屏是商业成熟品类。**但两者都遵守同一纪律：主决策在 2D/地图层，3D 只做态势氛围**——设计稿自己也写了"切勿只做炫的那层"（NOC 实测 3D 单用 MTTR +30%），执行时要顶住"演示效果"的诱惑。
- **裸机 GPU 原生渲染（不经 VNC 串流）**是关键正确决策，3D 流畅与炫酷才不矛盾。
- 星群皮肤（3d-force-graph）v1 / 城市皮肤（deck.gl+Cesium）后置：正确的成本排序；"同一份 scene graph 两套皮肤"防返工设计好。
- 头顶 emoji 气泡（Smallville 手法）、状态不用二元红绿灯、展示提炼后推理而非 raw CoT——都是有出处的成熟手法。
- **风险**：① 深色指挥风 theme 基于察元浅色办公组件体系派生，对比度/色觉校验要单独做（评审 D7 已列）；② "炫酷 3D"对**投墙/汇报场景**价值大、对**日常排障**价值小，v1 验收应以"2D 下钻能否 30 秒定位一个卡住的 job"为准，而非粒子流好不好看；③ onboarding/空状态全文无设计（评审 D8），冷启动第一屏（0 主机 0 员工）是新用户必经路径，别让驾驶舱开机是一片空星空。

---

## 五、需求可行性逐项判定（能否实现 + 业界证据）

| 需求 | 可行性 | 依据 |
|---|---|---|
| #2 容器供给 | ✅ 成熟可行 | Kasm Workspaces 商业验证（Manager/Agent 架构、ephemeral 会话）；Docker SDK 直管 |
| #3 昵称注册 | ✅ 已实现 | P0 骨架 + NATS subject 寻址范式 |
| #4/#7 工作区+聚合 | ✅ 可行 | 已实现卷+原子标记；语义汇总靠察元 LLM，成熟 |
| #5 @直派 | ✅ 已实现（后端） | 快路径无 LLM，无风险 |
| #5 NL 智能路由（P1） | ⚠️ 可行但须守纪律 | LLM 路由只做冷启（C2）；业界 supervisor-router 成熟（AWS Bedrock、LangGraph） |
| #6 实时流 | ✅ 可行 | OpenHands `--headless --json` 事件流实测存在；AG-UI 式增量事件是业界范式 |
| #8 免密开界面 | ✅ 可行 | Kasm session token 同类机制；一次性 token + 预认证反代是标准做法 |
| #10/#16 配置+网关 | ✅ 可行 | 察元网关 75 provider 实证；`/v1/messages` shim 有 LiteLLM/claude-code-router 两条现成路 |
| #11 线性→DAG | ✅ 可行 | 线性自研 OK；复杂 DAG/耐久 P2 切 Temporal（自研耐久=焦油坑判断正确） |
| #12 A2A 直连 | ⚠️ 无成熟先例 | 业界 A2A 协议尚早期；防环/审计自担——P3 后置正确，甚至可再砍 |
| #13 容灾 | ✅ 模式可行 | K8s reconcile/lease 先例充分；但跨机自研要先评 Nomad（S6），P2 前别碰 |
| #14 RBAC | ✅ 可行 | 察元 org/RBAC 实证成熟；资源维度扩展是增量工作 |
| #15 外部感知 | ✅ 技术可行，⚠️ 安全面大 | webhook/MQ 归一化常规；SSRF/投毒/降权设计已列——P3 正确 |
| #17 母体复用 | ✅ 实证成立 | 本报告第二节；唯契约需修 |
| #18 Charter | ✅ 可行 | CrewAI role/goal/backstory、OpenAI handoff 同构概念遍地 |
| #19 知识范围 | ✅ 可行 | 察元 kb_acl + `ku_ids` 契约已对齐 |
| #20 Task-as-API | ✅ 可行 | code+运行端点已实现；幂等/HMAC 是常规工程 |
| #21 Nacos/Feign | ✅ 可行 | REST+OpenAPI 天然；nacos-sdk-python 现成 |
| 无 IP 寻址 | ✅ 已实现且有先例 | NATS subject/K8s service 抽象同理 |
| 万级规模（NFR-SC） | ✅ 有先例但非近忧 | 阿里 10k 节点生产证据；私有化部门级客户 P2 再说 |
| 技能体系 SKILL.md | ✅ 押注正确，⚠️ 两个坑 | 标准已开放（agentskills.io），26+ 工具采纳、Codex 官方支持→跨 agent 兼容初步证明；坑①：**安装路径/高级特性不统一**（Claude `.claude/skills/`、Codex `.agents/skills/`…）→ 需自建安装适配层；坑②：**Snyk ToxicSkills 扫描 3984 个技能 36% 有安全缺陷、76 个确认恶意** → allowlist+签名+沙箱（NFR-SEC3）不是 P1 可选项而是上线前置【中置信】 |
| OpenHuman 无头派活 | ❌ 不可行 | 无任何官方无头接口（已核实）——定位人工桌面型正确 |
| 3D 游戏化大屏 | ✅ 接受度有先例，组合无先例 | Anduril Lattice/数字孪生大屏证明范式；"游戏化指挥 AI agent 舰队"具体组合无人做过——差异化机会 = 无路可抄 |

**总判**：21 条功能需求中 **19 条可实现**（多数有业界先例或已有骨架），1 条明确不可行已正确规避（OpenHuman 无头），1 条无先例高风险已正确后置（#12 A2A）。

---

## 六、同类开源/商业项目对标（能统一指挥多智能体的项目）

| 项目 | 与 ChaCMD 重合度 | 关键差异 / 可借鉴点 |
|---|---|---|
| **Cua (trycua/cua)** | **最高**：OS 级沙箱（macOS/Linux/Win/Android）+ 异构 CLI agent 适配 + 商业侧宣传 "computer fleets"【沙箱抽象 3/3 高置信】 | 定位训练/评测/批量基础设施，**无指挥驾驶舱、无企业 RBAC/知识库/审批**。→ 可评估复用其沙箱/fleet 层，把自研压到指挥语义 |
| **bytebot** | 同构单体：容器化 Linux 桌面 + REST/MCP 驱动 | 单 agent 产品，无舰队层；**已归档停维护**——佐证"光有桌面 agent 不够" |
| **Kasm Workspaces** | 工位供给层重合 | 商业成熟但编排的是**人类会话**；其 Manager/Agent 架构值得照抄语义 |
| **E2B Desktop / Daytona / Modal** | 工位供给层（云托管） | E2B 有 VNC 可视桌面；Daytona headless 沙箱 + OpenHands 官方集成；均非私有化、无指挥层 |
| **Anthropic Agent Teams** | 编排语义对照基准【3/3 高置信】 | 实验性、默认关；lead+队友+共享任务列表+mailbox；**单机/单用户/仅 Claude Code 同构/文件系统协调**，官方建议 3-5 队友——不是跨容器异构控制面，但其任务认领文件锁、mailbox 语义可借鉴 |
| **claude-flow(Ruflo) / Claude Squad / Conductor / Vibe Kanban / OpenClaw+Antfarm** | 本地并行 coding-agent 编排器 | worktree 隔离 + dashboard + diff 审查是已验证模式；无桌面工位、无企业治理、无跨机 |
| **LangGraph / CrewAI / AutoGen / AgentScope / MetaGPT / Dify / Coze / n8n** | 低：进程内 LLM-agent 编排 | 编排的是消息图不是"一容器一桌面"的异构 CLI 舰队——正是 ChaCMD 与红海编排器的分野（需求 §1.2 判断成立） |
| **Temporal / Restate / DBOS** | 耐久执行底座 | 非竞品，是 P2 该采的件 |
| **Anduril Lattice** | 驾驶舱 UI 先例 | 游戏引擎化 C2、单人督导自治群——3D+2D 分层与用户接受度的最强旁证 |
| **Okta for AI Agents / Entra Agent ID** | 身份层先例 | 佐证"身份外置"；启示：**别自造身份体系**，预留 OIDC 挂接 |

**格局结论**：市场分成四个互不重叠的层——①进程内编排框架（红海）②沙箱/工位基础设施（快速商品化）③垂直 AI 员工（营收验证但封闭）④单机 CLI 并行器（工具级）。**"跨全部四层 + 企业治理 + 私有化 + 驾驶舱"的整合者位置是空的**——ChaCMD 的定位成立；代价是集成工程量没有任何现成项目可整体搬运。

---

## 七、更好的实现方案建议（相对现设计的修正）

1. **契约先行，冒烟为证**（新增，最高优先）：修 `authz/check`→察元真实 authz 语义（或上游加端点+flag）、`whoami`→`/openapi/v1/whoami`；CI 加"真实察元 compose 冒烟"步骤。凡 `HttpChayuanClient` 新增方法，必须先 curl 通再写代码。
2. **工位供给层少自研**：起容器/回收/池化认真评估 Cua 沙箱抽象或照抄 Kasm Manager/Agent 语义；覆盖网评估 OpenClaw node 协议可否承载派活契约（§11.3 悬案尽快关闭）。护城河在指挥语义与治理，不在传输与供给。
3. **技能层直接押 SKILL.md，但加两层**：①安装适配层（抹平 `.claude/skills/` vs `.agents/skills/` 等路径差异）；②供应链闸门 allowlist+签名+沙箱执行**提前到技能功能首发即有**（36% 缺陷率的市场不容"先上后治"）。
4. **身份层不自造**：数字员工 ID 用察元 RBAC 做授权真源，但身份认证预留 OIDC 接口（对齐 Okta/Entra Agent ID 趋势），信创 GX6 也顺路。
5. **员工视图最小版提前**（P1 内前移）：日活主力是员工；"我的任务+我的产物"两屏即可。
6. **workspace 目录改按 `job_id`**（或 `code/job_id` 两级），对齐"每次调用新实例"语义。
7. **License 记载全面更正**：需求 §1.5、R3、设计 §3.5/§10.1-E 中 AGPL 表述改为 Apache-2.0，合规红线相应放宽（仍保留 R3 对第三方 copyleft 的禁令）。
8. **大屏 v1 验收加一条工程指标**："从 3D 总览定位一个 stuck job 并下钻到日志 ≤3 次点击/30 秒"——防"只做炫的那层"。

---

## 八、行动计划

### 近期（1–2 周）：闭合 P0
1. 修契约 + 真实察元冒烟（0.5–1 天）
2. 文档更正（License/契约/AGPL 决策项撤销）（0.5 天）
3. M3：真 OpenHandsAdapter → rootless 沙箱+加固 → `/v1/messages` shim → 审批门 API → 预算 kill → NATS+Postgres 切换 → OTel 最小
4. M4：五条验收逐条打勾（含实机逃逸测试）

### 中期（3–6 周）：可见价值
5. 大屏设计稿评审 → v1（星群 L0 + 事件流 + KPI + kiosk）+ 新建任务表单
6. 员工视图最小版（前移）
7. 一键起子容器（#2 真实现）+ 配置下发（#10）
8. OpenClaw 底座复用评估结论 + Cua 复用评估结论（各半天 spike）

### 决策项（用户拍板）
- §8 三岔路（党政军？万级单体？完全离线？）——影响 P1 起的 DB/密码学/联邦实现深度
- 大屏设计稿是否按现稿通过
- worktree 分支 `worktree-chacmd-p0-backend` 合并回 main 的时机（建议 M3 完成后一并合）

### 里程碑判定口径
P0 完成 = 五条验收全过 + 真实察元集成冒烟绿 + 分支合并。届时才能对外说"多容器 agent 舰队 > 单个强 agent"得到证明。

---

*配套文档：需求 SRS `2026-07-01-chacmd-requirements.md` · 总设计 `2026-06-30-chacmd-design.md` · 大屏设计 `2026-07-02-chacmd-command-dashboard-design.md` · P0 计划 `2026-07-01-chacmd-p0-backend-skeleton.md`*
