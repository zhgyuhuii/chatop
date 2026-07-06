# chatop 工位本地监控大屏（station + dashboard）设计

- 产品：chatop-ai 工位容器 · 本地监控大屏（= ChaCMD SRS「员工视图」的容器侧落地与扩展）
- 日期：2026-07-06
- 状态：设计已过用户逐节评审，待出实现计划
- 前置文档：`2026-07-01-chacmd-requirements.md`（SRS §3 员工视图 / §6.18 子容器内置能力）、`2026-07-05-chacmd-placement-and-requirements-master.md`（三仓边界）、`2026-07-02-chacmd-command-dashboard-design.md`（中心大屏，L2 将来 iframe 复用本屏）

---

## 0. 一句话定位

chatop 容器内嵌一个常驻服务 **station**（agent-bridge 升级而来），提供一张**本地自治的监控大屏**：进桌面即自启全屏窗口，外部浏览器也可经 Caddy 直达；展示本容器已装智能体（openclaw/Hermes/OpenHuman/claude-code/codex 等自动发现）的配置状态、工作状态、任务列表、技能清单与容器运行状态，并可本地派活。**不依赖 ChaCMD 中心即完整可用**；接入中心后同一事件流上报、同一页面被中心 L2 嵌入。

## 1. 已确认的五个关键决策

| 决策点 | 结论 |
|---|---|
| 与 ChaCMD 中心关系 | **本地自治优先**：大屏由容器内嵌服务独立提供，无中心完整可用；接入中心后叠加中心派发任务与履历（SRS「实时态读本地」兼容） |
| 入口形态 | **双入口**：①KDE 桌面自启全屏窗口（chromium --app，可切走不锁桌面）②外部浏览器 `https://<host>:7443/dashboard` 经 Caddy（带登录门） |
| 监控范围 | **已装 AI 类全部自动发现**（catalog 的 ai-cli/ai-runtime/vscode-ext 分组为真源；openclaw、hermes、OpenHuman、claude-code、codex、sovyx、nanobot、aider、opencode、qwen-code 等；新装 agent 零改动上屏） |
| 交互深度 | **监控 + 本地派活对话框**（v1 含 @agent 下任务），另每卡带快捷动作（启停/终端/配置/日志） |
| L2 复用 | **设计成可嵌入**：`?embed=1` 去壳 + `?ticket=` 免密参数位预留，中心 L2 将来 iframe 直接嵌本屏，不重建 |

## 2. 大屏信息架构（六区）

```
┌────────────────────────────────────────────────────────────────────┐
│ 顶栏KPI: 工位昵称·镜像版本 │ ●独立模式/已接中心 │ 智能体 6装/3跑      │
│         │ 今日任务 8·成功率 87% │ CPU/MEM/DISK 小表 │ 运行时长 │ 时钟 │
├──────────────────────────────────────┬─────────────────────────────┤
│ A 智能体卡片墙（自动发现，核心区）      │ B 任务列表                   │
│  每卡: 身份/配置状态/工作状态/当前动作  │  任务·agent·状态机·当前步·   │
│  /资源占用/统计/快捷动作               │  耗时·token·来源·产物        │
│                                      │  （点开→事件时间线抽屉）      │
│                                      ├─────────────────────────────┤
│                                      │ C 派活: [@agent▾] goal [派活]│
├───────────────────┬──────────────────┴─────────────────────────────┤
│ E 技能/MCP 插件    │ D 容器运行状态: 资源 sparkline·服务健康表·        │
│ (按 agent 分组)    │   端口监听表·容器级事件流                        │
└───────────────────┴────────────────────────────────────────────────┘
```

### 2.1 顶栏 KPI
工位昵称 + hostname + 镜像版本（VERSION）、运行时长、**中心连接徽标**（独立模式 / 已接入+租约状态，v2 点亮）、agent 已装/运行数、今日任务数 + 成功率、CPU/MEM/DISK 三小表、时钟。

### 2.2 A 区 · 智能体卡片（每张）
1. **身份**：图标/名称/版本/类型三档——常驻 runtime（openclaw/hermes/sovyx/nanobot）、会话式 CLI（claude-code/codex/aider/opencode/qwen-code/reasonix/mimo-code）、人工桌面型（OpenHuman）。
2. **配置状态**：已配置/未配置（探测各自配置文件 key/model/base_url 存在性），显示所连模型名；未配置给「去配置」按钮（跳 agent-builder 配置器）。**只报有无，API key 明文绝不出 probe 层**（R7/NFR-SEC5）。
3. **工作状态**：常驻型=进程+端口+健康端点；会话式=活动会话数+最近运行时间；OpenHuman=VNC 会话在线状态（无无头接口已核实，不派活，显示「人工处理中」）。
4. **当前动作**：最近事件 → emoji + 一句话（对齐中心大屏 Smallville 手法）。
5. **资源占用**：该进程 CPU/MEM。
6. **统计**：今日任务/会话数、token 用量（数据源可接已装 tokscale/rtk，v1.5）。
7. **快捷动作**：启/停/重启（仅常驻型）、打开终端（仅桌面入口，外部入口降级为「进入桌面」跳 VNC）、打开配置、看日志、派活给它（联动 C 区）。

### 2.3 B 区 · 任务列表
字段：任务名/goal、指派 agent、状态机（queued/running/**pending_approval**/succeeded/failed/cancelled——对齐 ChaCMD 8 态子集）、当前步、耗时、token、**来源标签**（本地手动 / 自动侦测会话 / 中心派发-v2）、产物（工作目录文件链接 → filebrowser）。点开抽屉 = 事件时间线 + 流式输出回放（回放 v1.5）。

### 2.4 C 区 · 派活对话框
@选 agent + goal 输入 + 可选工作目录；派活后任务入 B 区并流式跟随。

### 2.5 D 区 · 容器运行状态
CPU/MEM/NET/磁盘 sparkline、**服务健康表**（Xvnc / caddy / app-manager / filebrowser / station——Xvnc 有 wedge 前科，监控它有实用价值）、端口监听表、容器级事件流（应用装卸/登录/服务异常）。

### 2.6 E 区 · 技能/插件
扫描各 agent 技能目录（`~/.claude/skills/`、`~/.agents/skills/` 等，SKILL.md 标准）汇总：名称/描述/适用 agent/来源；MCP 插件列表。（v1.5）

## 3. 服务端架构（station daemon）

**进程形态**：`agent-bridge/` 升级为 `station`（Python 3.11，FastAPI + uvicorn，监听 `127.0.0.1:8787`），第 4 个常驻服务进 `custom_startup.sh`；Caddy 挂 `/dashboard`（静态页）与 `/dashboard/api`（反代 8787，含 SSE）。

```
station/
├─ probe/                探测层（只读，全容错——单探测失败=卡片降级不崩屏）
│   ├─ catalog.py        已装 agent 发现（真源=app-manager 已装清单+catalog 分组）
│   ├─ agent_probes.py   按类型注册的探测器（新 agent 加一个 probe 即上屏）
│   ├─ skills.py         技能/MCP 目录扫描
│   └─ system.py         CPU/MEM/DISK/NET、服务健康(pgrep+端口)、VNC 会话
├─ tasks/
│   ├─ store.py          SQLite 任务库(~/.local/share/chatop/station.db)：Job 表+事件表
│   ├─ dispatcher.py     本地派活：headless 拉起 agent CLI，JSONL 流→统一事件
│   └─ session_watch.py  自动侦测：tail 各 agent 会话目录→生成「侦测型任务」记录
├─ events.py             进程内事件枢纽（复用 ChaCMD EventStreamHub 扇出+背压丢最旧手法）
├─ bridge.py             预留：现 agent_bridge/main.py WS 反连客户端迁入，v2 接中心
├─ api.py                REST /api/agents /tasks /skills /system + POST /api/dispatch
│                        SSE /api/events（大屏唯一实时通道）
└─ web/                  大屏前端构建产物（station serve，Caddy 反代）
```

### 3.1 agent 探测/派活适配矩阵

| 类型 | 配置探测 | 运行探测 | 派活 |
|---|---|---|---|
| openclaw（常驻） | 配置文件 model/key 存在性 | 进程+端口+健康端点 | 其 CLI 无头模式（v1.5） |
| hermes（常驻） | 同上 | 进程/端口 | 其任务接口/CLI（v1.5） |
| claude-code（会话式） | `~/.claude/` | 进程扫描+会话目录 mtime | `claude -p --output-format stream-json`（v1） |
| codex（会话式） | `~/.codex/` | 同上 | `codex exec --json`（v1） |
| aider/opencode 等 | 各自配置目录 | 进程扫描 | 白名单逐个开（v1 只读监控） |
| OpenHuman（人工型） | 安装存在性 | VNC 会话在线+桌面活动 | 不派活 |

### 3.2 派活链路

```
POST /api/dispatch {agent, goal, workdir?}
  → store 建 Job(queued) → dispatcher spawn 子进程(headless CLI, cwd=workdir)
  → stdout JSONL 逐行 → event_adapter 归一化（扩展现有 event_adapter.py）
  → 同时: ①写事件表 ②推 events 枢纽 → SSE → 大屏实时更新
  → 进程退出 → Job 终态 + 产物=workdir 文件清单
```

**对齐约定（防 v2 返工）**：统一事件 schema 直接采用 ChaCMD 后端已定形状（kind/agent/job_id/ts/payload）；任务状态机为 ChaCMD 8 态子集。将来 bridge.py 接中心时同一条事件流原样上报，本地大屏与中心大屏消费同一种事件，零转换。

## 4. 前端

chatop 仓新增 `dashboard-web/`（独立 Vite + React，复用镜像内 Node22 构建链，产物 COPY 进 station/web）。**不依赖 chayuan-client workspace**——深色指挥风只拷一份 design token 色板（与 ChaCMD 中心 L0 同色系），保持工位镜像自包含（三仓边界）。数据流：`EventSource(/dashboard/api/events)` → 纯 reducer 累积状态 → 各区渲染；reducer 纯函数可单测。

## 5. 入口、鉴权与嵌入

| 入口 | 机制 | 鉴权 |
|---|---|---|
| 桌面内自启 | KDE autostart `.desktop` → `chromium --app=http://127.0.0.1:8787/dashboard` 全屏（可切走不锁桌面） | 回环直连视为已认证（能进桌面=已过登录；容器内进程本就同用户权限，明示接受） |
| 外部浏览器 | `https://<host>:7443/dashboard` 经 Caddy | 复用现有 `forward_auth → app-manager /auth` Cookie 门（与 KasmVNC/filebrowser 同套登录）；**SSE 与全部 POST 动作同样过门** |

**嵌入预留（中心 L2）**：`?embed=1` 隐藏壳元素+通知宿主高度；`?ticket=<一次性token>` 参数位 v1 只定义与校验桩，真实现（中心签发→station 验签）v2 随 bridge.py 落地（对齐 SRS #8 免密语义）。

## 6. 降级与错误处理

- 单 probe 失败 → 该卡「探测失败」徽标，其余区块不受影响。
- SSE 断线 → 前端指数退避重连 + 「已断开」横幅，保留最后快照。
- station 挂掉 → 桌面窗口显示重连页；KasmVNC/文件等既有功能零影响（独立故障域）。
- 冷启动零 agent/零任务 → 引导卡（「安装第一个智能体 →」跳 app-manager），不出现空白屏。

## 7. 测试与验收

**单测/集成测**（沿 app-manager tests 风格，TDD）：probe 各探测器（假目录/假进程表）；task store 状态机转移；dispatcher 用 fake CLI 脚本吐样例 JSONL 测事件归一化与终态；SSE 端点集成测；前端 reducer 单测。

**镜像级验收（需真机）**：build 后 5 服务健康；进桌面自启全屏大屏；外部 /dashboard 登录可达；派一个真任务给 claude-code 全链路（建任务→流式→终态→产物可见）；杀掉 openclaw 进程卡片状态灯变化。

## 8. 分期

- **v1（本次）**：station daemon + 顶栏/A/B/C/D 区 + 双入口自启 + claude-code/codex/openclaw 三个 probe + 派活（claude-code/codex 先行）+ SSE。
- **v1.5**：E 技能区、hermes/sovyx/nanobot/OpenHuman probe、token 统计接 tokscale、任务详情事件回放。
- **v2（接中心）**：bridge.py 反连 ChaCMD（租约/收派活/事件上报）、embed ticket 免密、中心派发任务进 B 区。

## 9. 红线对照

- R7/NFR-SEC5：key 明文不出 probe 层、不落日志。
- NFR-SEC7：外部永不直连 station（只听 127.0.0.1，一律经 Caddy 过登录门）。
- 三仓边界：本设计全部落 `/work/chatop`；不引入对 chayuan-desktop 的构建依赖；与 ChaCMD 的耦合只有「事件 schema/状态机形状对齐」这一纸面契约。
