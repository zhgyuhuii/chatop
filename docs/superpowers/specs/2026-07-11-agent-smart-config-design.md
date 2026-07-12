# 智能体统一智能化配置框架 — 设计

- 日期：2026-07-11
- 范围：为 chatop 工位内置智能体（一期 openclaw + Hermes）提供**自动化、智能化**的配置体验。
- 背景动机：现 `openclaw-tool`（tkinter 配置器）配置不够智能——模型要手打
  `provider/model` 字符串、启用通道后没有可扫码/填验证码的地方、25 个通道里只有 4 个有
  设置教程、无凭据有效性校验。用户要的是「傻瓜式」：填了 API Key 就能拉出模型清单选，
  启用微信/企业微信就地弹二维码，每个通道都有图文教程，甚至能用自然语言让助手代配。

## 决策速览（brainstorming 结论）

| 决策点 | 选择 |
|---|---|
| 范围 | 统一智能体配置框架（openclaw + Hermes 一期，claude-code/codex/OpenHuman 仅总览状态） |
| UI 载体 | Web 统一配置中心（station + dashboard-web 基座） |
| 架构 | C：引擎库 + station 薄壳 + dashboard-web 页面 |
| 一期能力 | 模型智能配置、通道动态认证交互、全通道设置教程库、体检自愈扩展到 Hermes、**LLM 配置助手** |
| 教程来源 | 烤入结构化教程包为主 + 官方文档链接为辅 |
| tkinter 去留 | 桌面图标改指向 Web；tkinter 配置器保留兜底，不再加新功能 |

## 硬约束（务必遵守）

- **纯 stdlib 引擎**：宿主与 `/opt/station-venv` 都**没有** `requests`/`httpx`/`yaml`。
  引擎库只用 stdlib（`urllib.request` 发 HTTP，教程/快照数据用 **JSON**）。
- **单一真源不重造**：openclaw 的 `openclaw_catalog` / `openclaw_orchestrator` / `openclaw_qr` /
  `catalog_overrides` 已是纯 stdlib 逻辑，引擎**复用**（import），不复制。openclaw-tool 的
  tkinter GUI 与 Web 并存，二者都以磁盘配置文件（`~/.openclaw/openclaw.json`、
  `~/.hermes/config.yaml`）为真源，互不另立配置库。
- **引擎无 UI / 无 HTTP-framework 依赖**：不 import tkinter，不 import fastapi。副作用（子进程、
  事件外发）通过注入的 `emit` 回调，保证纯函数可单测。
- **CLI 不上启动路径**：openclaw CLI 每调 8–12s 且无热缓存；引擎沿用烤入快照 + 惰性单例，
  配置中心首屏不阻塞在 CLI 上。
- **离线可用**：模型清单拉取失败时回退烤入快照；教程全部烤入。国内网络下不依赖外网可打开。

## 架构

```
/work/chatop/
├── agent-config/                       # 新：配置引擎库（纯 stdlib，无 UI/无 FastAPI）
│   ├── agentconfig/
│   │   ├── core/
│   │   │   ├── types.py                # AgentDescriptor/FieldSpec/AuthFlow/Diagnostic/ModelInfo/Event
│   │   │   ├── adapter.py              # AgentAdapter Protocol
│   │   │   └── registry.py            # {agent_id: adapter}
│   │   ├── adapters/
│   │   │   ├── openclaw_adapter.py    # 包一层：复用 openclaw-tool 的纯模块
│   │   │   └── hermes_adapter.py
│   │   ├── models/
│   │   │   ├── providers.py           # 各厂商 /models 端点表 + key 验证
│   │   │   └── snapshot.json          # 烤入模型清单兜底（含 ollama 本地探测）
│   │   ├── tutorials/
│   │   │   ├── loader.py
│   │   │   └── data.json              # 全通道结构化教程（步骤/凭据字段/申请链接/排错）
│   │   └── assistant/
│   │       ├── tools.py               # 助手可调工具（列通道/取教程/设字段/起认证流程）
│   │       ├── planner.py             # 意图路由（确定性）+ LLM 会话编排
│   │       └── llm.py                 # LLMClient 协议 + OpenAI 兼容 urllib 实现 + Fake
│   └── tests/
├── station/station/agentcfg_api.py     # 新：薄壳路由 /dashboard/api/agent-config/*
├── dashboard-web/src/config/           # 新：配置中心 React 页面
└── openclaw-tool/                      # 保留兜底（后续可改 import agentconfig，不在一期）
```

进程视图不变：仍只有 station 一个常驻服务；引擎被 station import。长任务（扫码 login、
装插件、拉模型）产出事件，经引擎 `emit` → station EventHub → 现有 `/dashboard/api/events`
SSE 推前端。前端不轮询扫码。

## 组件

### 1. core/types + adapter + registry

- `FieldSpec(key, label, kind, secret, help, options, apply_url, placeholder)`：一个配置字段。
- `AgentDescriptor(id, label, groups[])`：配置面板骨架；group 含字段与通道/厂商清单。
- `AgentStatus(installed, configured, running, version, model)`：三态 + 版本 + 当前模型。
- `AuthFlowDescriptor(kind, target, fields, apply_url, tutorial_id, cmd)`：
  `kind ∈ {qr, token, code, webhook, oauth, builtin}`，前端据此渲染扫码卡片 / 验证码输入 /
  Token 表单 / Webhook 展示 / OAuth 跳转。**这是「启用后就地出交互」的核心契约。**
- `Diagnostic(id, level, message, auto_fix)`：体检项。
- `ModelInfo(key, label, source)`：`source ∈ {live, snapshot}`。
- `Event(type, **data)`：引擎外发事件。
- `AgentAdapter` Protocol：`describe/status/read_config/apply/auth_flow/run_flow/health_check`。
- `registry`：`{id: adapter}`；station 按 agent_id 分发。

### 2. openclaw 适配器

包一层复用现有模块（不复制）：
- `describe()`：由 `openclaw_catalog.load_catalog()` + `catalog_overrides`（中文名/auth/申请链接/模型厂商）
  组装通道组、模型组、搜索组、网关组。
- `auth_flow(channel)`：把 `catalog_overrides.CHANNEL_AUTH` 的 qr/token/webhook/oauth/builtin
  翻译成 `AuthFlowDescriptor`，qr 通道带 `openclaw_orchestrator.build_login_cmd`。
- `run_flow(qr)`：复用 `openclaw_orchestrator.OneStop` 状态机；`OneStop.ui` 回调桥接到 `emit`，
  二维码矩阵经 `openclaw_qr` 抽取后作为事件 payload。
- `apply()`：写盘前跑 `openclaw_catalog.sanitize_config_for_gateway` 自愈，返回移除项诊断。
- `health_check()`：复用 `openclaw_orchestrator.verify_and_start` 的步骤 + 探活。

### 3. hermes 适配器

- 配置面小：`.hermes/config.yaml` / `.env` 的 API key、模型、基础开关；字段用**烤入 schema**
  （手工整理，同 openclaw 目录快照思路），一期不解析 hermes 内部 schema。
- `status()` 复用 station `agent_probes` 探测逻辑。
- `run_flow` 兜底：无 GUI 配对流程时回退 `hermes setup` 终端入口。
- 目的：以第二个实例验证适配器抽象没抽歪。

### 4. 模型智能配置（models/）

- `verify_and_list(provider, api_key, base_url=None) -> (ok, [ModelInfo], reason)`：
  按 `providers.py` 的端点表，用 `urllib` 打该厂商的 `GET /v1/models`（或等价）；
  200 且返回列表即 key 有效 → 产出 live 模型清单；失败 → 回退 `snapshot.json` 过滤该 provider
  前缀，`source=snapshot`，并给出可读原因。
- Ollama：打本地 `http://127.0.0.1:11434/api/tags` 列已装模型（无需 key）。
- 前端：provider 下拉 → 填 key → 「获取模型」→ 主模型/备选**下拉选择**，不再手打字符串。

### 5. 全通道设置教程库（tutorials/）

- `data.json`：每个通道一条：`{id, label, auth, steps[], credential_fields[], apply_url, docs_url, troubleshooting[]}`。
  一期烤入 openclaw 全部通道（覆盖现有 4 个 + 补齐其余）。
- `loader.get(agent, channel)`：查烤入数据；缺失回退通用兜底文案 + 官方 docs 链接。
- 前端：认证流程卡片内联展示 steps，随 auth 类型上下文（qr → 「扫码」，code → 「填验证码」）。

### 6. LLM 配置助手（assistant/）

- `tools.py`：声明助手可调的确定性工具——`list_channels()`、`get_tutorial(channel)`、
  `set_field(agent, key, value)`、`start_auth_flow(agent, channel)`、`list_models(provider, key)`。
  工具**只操作引擎**，不直接碰 UI。
- `planner.py`：
  - 确定性意图路由（无网络可测）：识别「接入企业微信」「配 deepseek 模型」等 → 直接产出 plan。
  - LLM 会话编排：把用户消息 + 工具 schema + 当前配置状态给 LLM，走「工具调用」循环。
- `llm.py`：`LLMClient` 协议（`chat(messages, tools) -> reply|tool_calls`）；
  - 真实实现：OpenAI 兼容端点（urllib），复用用户**已在 openclaw 配好的** provider+key
    （从 `~/.openclaw/openclaw.json` 读），避免自带 key。
  - `FakeLLMClient`：测试用，脚本化返回。
  - 无可用模型时助手降级为确定性意图路由 + 提示先配模型。

### 7. station 薄壳路由（agentcfg_api.py）

只做协议适配，业务在引擎：
- `GET  /dashboard/api/agent-config/agents` → 各 adapter `status()` 总览
- `GET  /dashboard/api/agent-config/{id}/describe`
- `GET  /dashboard/api/agent-config/{id}/config`（脱敏）
- `POST /dashboard/api/agent-config/{id}/apply`
- `POST /dashboard/api/agent-config/{id}/models`（provider+key → 清单）
- `GET  /dashboard/api/agent-config/{id}/auth-flow?channel=`
- `POST /dashboard/api/agent-config/{id}/auth-flow/start`（起 qr/pair 长任务，事件走 SSE）
- `GET  /dashboard/api/agent-config/{id}/tutorial?channel=`
- `POST /dashboard/api/agent-config/{id}/health`（体检，可选自愈）
- `POST /dashboard/api/agent-config/assistant`（自然语言 → plan/回复）
- 长任务事件复用现有 `EventHub` + `/dashboard/api/events` SSE。

### 8. dashboard-web 配置页

- 新路由 `#/config`（或独立入口），复用现有 `usePoll`/`useEventStream`。
- 组件：AgentPicker、ModelPanel（provider 下拉+取模型）、ChannelGrid（启用+动态认证卡片：
  扫码/验证码/Token/Webhook/OAuth）、TutorialDrawer、HealthPanel、AssistantChat。
- 桌面「OpenClaw 配置」图标改为打开浏览器进配置中心（`start-*.sh`）；tkinter 图标保留兜底。

## 数据流（启用企业微信为例）

前端点「启用企业微信」→ `GET auth-flow?channel=wecom` → 引擎 openclaw 适配器返回
`AuthFlowDescriptor(kind=token, fields=[corpId, secret...], apply_url, tutorial_id)` →
前端渲染 Token 表单 + 内联教程 + 「去企业微信后台」链接 → 填完 `POST apply` → 引擎 sanitize+写盘 →
可选 `POST health` 起网关探活，进度经 SSE。若通道是 qr（微信/WhatsApp）：`auth-flow/start` 起
`channels login` 子进程 → `openclaw_qr` 抽二维码 → SSE 推矩阵 → 前端画二维码 → 登录成功事件标绿。

## 错误处理

- 模型 key 无效：返回可读原因 + 回退快照清单（不空白）。
- 二维码抓不到：`Event(qr_missing)` → 前端提示「在终端窗口扫码」（沿用 orchestrator 保底）。
- 配置非法：`apply` 前 sanitize，移除项以诊断返回；网关探活失败给 failed_step + 末段日志。
- LLM 不可用：助手降级确定性意图路由；引导先配模型。
- 引擎任一适配器抛错：station 路由捕获转 HTTP 4xx/5xx，不 500 整页。

## 测试

Python 引擎（宿主 python3.11 + stdlib，无需 venv）：
- `core`：types 序列化、registry 分发。
- openclaw 适配器：describe 组装、auth_flow 翻译（qr/token/webhook/oauth/builtin 各一）、
  apply 触发 sanitize、健康检查步骤（注入假 runner）。
- hermes 适配器：status/describe/apply（临时 HOME）。
- models：verify_and_list（注入假 urlopen：live 成功 / 401 回退快照 / ollama tags）。
- tutorials：全通道有教程（覆盖度断言）、缺失回退。
- assistant：确定性意图路由（企业微信/模型）、LLM 工具调用循环（FakeLLMClient）、降级。
- station 路由：`fastapi.testclient` 打通各端点（describe/models/auth-flow/assistant）。

前端：`vitest` 对认证卡片选择逻辑（auth kind → 组件）与助手消息 reducer 做纯逻辑测试。

## 一期不做（二期路线图）

- claude-code/codex/OpenHuman 深度配置向导（一期仅总览状态）。
- 教程包热更新（从应用市场/CDN 拉新版）——一期烤入 + 官方链接。
- tkinter 配置器改 import 引擎（一期保留原实现兜底）。
- 助手代填敏感凭据的自动化（一期助手引导 + 可预填非敏感项，敏感项仍由用户手填确认）。
