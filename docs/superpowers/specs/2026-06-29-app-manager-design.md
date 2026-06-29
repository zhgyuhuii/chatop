# 察元AI 云桌面 — 应用管理器设计文档

日期：2026-06-29
状态：设计已与用户逐节确认，待用户最终审阅 → 转 writing-plans

## 1. 背景与目标

chatop-ai 是基于 KasmVNC/noVNC 的网页云桌面。目标是在网页左侧控制栏增加一个**应用管理器**：

- 在控制栏「应用」入口打开一个应用商店式面板。
- 收录一批 **AI 编程智能体/工具**（CLI/runtime/IDE/VS Code 插件）+ **常用 GUI 应用**。
- **点击即可在容器内安装**，已安装的可**卸载**。
- 安装状态是**真实检测**的（不像参考项目 chatop 那样仅靠浏览器 localStorage 记录）。
- 已安装应用在容器重启/重建后**持久保留**。

参考来源：chatop（selkies 版）的 Manage Apps。其机制是前端 `postMessage` → selkies WebSocket 命令通道 → 后端 `subprocess` 执行 `proot-apps install/remove`。**chatop-ai（KasmVNC）没有这条命令通道，也没有 proot-apps**，因此执行链路需重新设计。

## 2. 范围

**做（In scope）**
- 应用管理器后端服务（HTTP API，旁挂，Caddy 反代 `/apps`）。
- 应用清单（catalog）+ 多种安装类型支持。
- noVNC 控制栏「应用」入口 + 模态框 UI。
- 真实安装状态检测、安装进度反馈。
- CLI/插件类应用的持久化（用户级 + home 数据卷）。
- 镜像预置 Node 22（npm 类工具前提）。

**非目标（Out of scope）/ 剔除**
- **NanoClaw**：需 Docker-in-Docker（每个 agent 套一个容器），成本最高，降级到后续专项，不进首批。
- **Qcode Agents**（奇安信）：闭源企业产品，无公开自助安装途径，剔除。
- **Modo**：调研查无可靠开源 AI 编辑器项目（疑名称碰撞），剔除（用户后续若提供确切链接再加）。
- 不在查询/安装阶段执行任何前端传入的任意命令（安全红线）。

## 3. 总体架构（方案 A：旁挂应用服务后端）

```
┌────────────────────────────────────────────┐
│ 浏览器前端（noVNC 控制栏「应用」模态框）       │
│  GET /apps/catalog   → 渲染卡片网格           │
│  GET /apps/status    → 真实已装状态（徽章）    │
│  POST /apps/install {id} / remove {id}        │
│  GET /apps/logs?id=  → 实时安装日志（SSE/轮询）│
└────────────────────────────────────────────┘
        │ 同源 /apps（Caddy 反代 + 登录鉴权）
┌────────────────────────────────────────────┐
│ Caddy（已存在，单端口收口）                    │
│  handle /apps*  → reverse_proxy 127.0.0.1:8686│
└────────────────────────────────────────────┘
        │
┌────────────────────────────────────────────┐
│ 应用服务（新增，Python3.10，监听 127.0.0.1:8686）│
│  · 读 catalog.json（命令字段只存后端）          │
│  · install/remove：按 id 白名单取预定义命令执行  │
│  · status：跑各 detect 命令，返回真实状态       │
│  · 异步任务队列（一次一个，避免 apt/npm 锁冲突） │
│  · 日志落 /tmp/app-mgr/<id>.log，供 logs 回显   │
└────────────────────────────────────────────┘
```

与现有旁挂服务（filebrowser、Caddy）同构：新增一个 `start-app-manager.sh`，由 `/dockerstartup/custom_startup.sh` 拉起。

## 4. Catalog 数据结构

一份 `apps-catalog.json`（打进镜像 `/etc/chatop/apps-catalog.json`，也可被 home 数据卷下的覆盖文件替换以便更新）。每个应用一条：

```json
{
  "id": "claude-code",
  "name": "Claude Code",
  "category": "ai-cli",
  "kind": "cli-npm",
  "icon": "claude-code.svg",
  "description": "Anthropic 官方 CLI，深度理解代码库",
  "install": "npm i -g @anthropic-ai/claude-code",
  "remove":  "npm rm -g @anthropic-ai/claude-code",
  "detect":  "command -v claude",
  "needs":   ["node22"],
  "homepage": "https://www.anthropic.com",
  "notes":   "运行需 ANTHROPIC_API_KEY；国内 API 需代理",
  "phase": 1
}
```

字段：
- `category`：`ai-cli` | `ai-runtime` | `gui` | `vscode-ext`（前端分类筛选用）。
- `kind`：安装类型（决定后端如何执行，见 §9）。
- `install`/`remove`/`detect`：命令字符串，**只存后端、前端 API 不下发**（安全核心）。
- `needs`：依赖（如 `node22`、`docker`），后端安装前校验。
- `phase`：1/2（分期）。

**安全约束**：前端 `POST /apps/install` 只传 `id`；后端在 catalog 中按 id 查到对应 `install` 命令执行，**绝不接受或拼接前端传入的命令字符串**。

## 5. 应用清单（分期）

> 标 ⚠ 的为冷门项目，落地前必须在容器内 `npm view <pkg>` / `pip index versions <pkg>` / `curl -fsSL -I <url>` 实测确认包名/URL 真实存在，不写死猜测命令。

### 第一期 — 纯 CLI / 插件（约 11 个，headless 全可非交互）

| id | 名称 | kind | 安装 | 检测 | 备注 |
|---|---|---|---|---|---|
| continue | Continue.dev | vscode-ext | `code --install-extension Continue.continue` | `code --list-extensions\|grep -i continue` | 零风险 |
| cline | Cline | vscode-ext | `code --install-extension saoudrizwan.claude-dev` | 同上 grep claude-dev | 零风险 |
| claude-code | Claude Code | cli-npm | `npm i -g @anthropic-ai/claude-code` | `command -v claude` | Node18+ |
| codex | Codex (OpenAI) | cli-npm | `npm i -g @openai/codex` | `command -v codex` | — |
| opencode | OpenCode | cli-npm | `npm i -g opencode-ai@latest` | `command -v opencode` | Node20+ |
| qwen-code | Qwen Code | cli-npm | `npm i -g @qwen-code/qwen-code@latest` | `command -v qwen` | **Node22+** |
| openclaw ⚠ | OpenClaw | cli-npm | `npm i -g openclaw@latest` | `command -v openclaw` | **Node22+**；daemon 改前台 |
| reasonix ⚠ | Reasonix | cli-npm | `npm i -g reasonix` | `command -v reasonix` | 社区项目，成熟度低 |
| aider | Aider | cli-pip | `pipx install aider-chat` | `command -v aider` | Py3.10 兼容，最稳 |
| plandex | Plandex | cli-script | `curl -sL https://plandex.ai/install.sh\|bash` | `command -v plandex` | Go 二进制 |
| nanobot ⚠ | Nanobot | cli-script | `curl -sfL https://install.nanobot.ai\|sh` | `command -v nanobot` | 域名国内可达性存疑 |
| hermes ⚠ | Hermes Agent | cli-script | 官方 install.sh `--skip-setup` | `command -v hermes` | 自带 uv+Py3.11；raw.githubusercontent 国内需代理 |

### 第二期 — 需特殊处理

| id | 名称 | kind | 处理要点 |
|---|---|---|---|
| void | Void IDE | deb (gui) | VSCode fork，免登录，推荐优于 Cursor；root 跑 Electron 需 `--no-sandbox` |
| cursor | Cursor | appimage (gui) | 闭源、需登录、国内可能需代理；`libfuse2` |
| openhuman ⚠ | OpenHuman | deb (gui) | Tauri/Rust 桌面助手；用 .deb（AppImage 容器内常报 unshare） |
| sovyx ⚠ | Sovyx | cli-pip | **需 Py3.11**（容器 3.10），用 uv/pipx 指定 3.11；AGPL-3.0 |
| mimo-code ⚠ | MiMo Code | cli-npm | 包名需 `npm view` 实测；首次运行有交互引导 |

### 剔除/降级
NanoClaw（DinD，降级）、Qcode（闭源剔除）、Modo（查无项目剔除）。

## 6. 后端「应用服务」API

实现：Python3.10 标准库（`http.server` + `subprocess`）或轻量 framework（避免额外重依赖）。监听 `127.0.0.1:8686`。

端点：
- `GET /apps/catalog` → 返回 catalog（**剥离 install/remove/detect 命令字段**，只给前端展示字段）。
- `GET /apps/status` → 对每个 app 跑 `detect`，返回 `{id: installed bool}`。带短缓存（如 5s）避免频繁 spawn。
- `POST /apps/install` body `{id}` → 校验 id ∈ catalog；校验 `needs`（如 node22 是否就绪）；入队执行该 id 的 `install`；返回 `task_id`。
- `POST /apps/remove` body `{id}` → 同理执行 `remove`。
- `GET /apps/logs?id=` → 返回该 app 最近一次安装/卸载日志（SSE 流式或轮询 tail）。

任务模型：
- **串行队列**，一次执行一个（apt/npm/dpkg 有全局锁，并发会失败）。
- 每个任务日志落 `/tmp/app-mgr/<id>.log`，stdout+stderr 都留（与 chatop 的 DEVNULL 丢弃不同，便于排错与前端回显）。
- 任务状态：`queued|running|success|failed`，前端轮询 status/logs 反映。

## 7. 前端 UI

- noVNC 控制栏（`chatop_header` 下方区域）新增「应用」按钮（图标）。
- 点击打开模态框（借鉴 chatop 的 AppsModal 视觉）：
  - 顶部：搜索框 + 分类筛选（AI CLI / AI runtime / GUI / 插件）。
  - 网格：`auto-fill minmax(180px,1fr)` 卡片（图标 + 名称 + **已安装徽章**）。
  - 卡片点击 → 详情：大图标 + 描述 + notes（如"需 API key/代理"）+ **安装/卸载按钮** + **实时日志区**。
  - 状态来源：`GET /apps/status`（真实），非 localStorage。
  - 安装中：按钮转 loading，日志区流式显示，完成后刷新 status。
- 复用控制栏 panel 模式（类似 files/clipboard 面板），与亮/暗主题变量兼容。

## 8. 持久化与安装位置

数据卷：compose 挂 `chatop-home:/home/kasm-user`（命名卷），跨重启/重建保留用户家目录。

各类型持久化策略：
- **cli-npm**：配置 npm 用户级前缀 `~/.npm-global`，`PATH` 加 `~/.npm-global/bin`（写入 `~/.bashrc` 与 `/etc/profile.d`）。`npm i -g` 落 home → 持久 ✅。
- **cli-pip**：用 `pipx`（装到 `~/.local`）→ 持久 ✅。
- **cli-script**：约束/包装为装到 `~/.local/bin` → 持久 ✅。
- **vscode-ext**：VSCode 扩展目录在 `~/.vscode`/home → 持久 ✅。
- **gui-appimage**：下载到 `~/Applications` + chmod + 生成桌面 `.desktop` → 持久 ✅（**GUI 首选**）。
- **gui-deb**（如 OpenHuman 无 AppImage）：`apt install` 写系统级 `/usr` → home 卷**无法持久**。二期处理：优先找 AppImage 替代；实在没有则记录"重建后需重装"或纳入镜像预装。

镜像预置（基础设施）：
- **Node 22**（一期前提：大半工具是 npm，且 Qwen/OpenClaw 强制 22+）。
- `pipx`、`uv`（pip 类与 Py3.11 卡点用）。
- 配好用户级 npm 前缀与 PATH。

## 9. 安装类型处理矩阵

| kind | 安装 | 卸载 | 检测 | 持久化 |
|---|---|---|---|---|
| cli-npm | `npm i -g <pkg>`（前缀 ~/.npm-global） | `npm rm -g <pkg>` | `command -v <bin>` | ✅ home 卷 |
| cli-pip | `pipx install <pkg>` | `pipx uninstall <pkg>` | `command -v <bin>` | ✅ |
| cli-script | `curl … \| bash`（装 ~/.local/bin） | `rm` 二进制/目录 | `command -v <bin>` | ✅ |
| vscode-ext | `code --install-extension <id>` | `code --uninstall-extension <id>` | `code --list-extensions` | ✅ |
| gui-appimage | 下载 ~/Applications + chmod + .desktop | 删文件 | `test -f` | ✅ |
| gui-deb | `apt install ./x.deb` | `apt remove` | `dpkg -l` | ❌（二期权衡） |
| docker | （NanoClaw，降级，不做） | — | — | — |

## 10. 安全

- 应用服务只监听 `127.0.0.1`，对外仅经 Caddy `/apps` + 现有登录鉴权（admin/VNC_PW）。
- install/remove **白名单**：前端只能传 catalog 中存在的 `id`；命令是 catalog 预定义固定串，**不拼接任何前端输入**。
- `needs` 前置校验（如 docker 缺失则拒绝）。
- 日志不回显敏感环境变量。

## 11. 错误处理与边界

- 包/URL 不可达（冷门项目、国内网络）：任务标 failed，日志给出原因，前端提示"可能需代理"。
- Node 版本不满足：安装前 `needs: node22` 校验，缺失给明确提示。
- 重复安装/卸载：以 `detect` 真实状态为准，幂等处理。
- 安装中断/容器重启：任务状态不跨重启持久（最佳努力）；重启后以 `detect` 重新对齐真实状态。
- apt/npm 锁冲突：串行队列规避。

## 12. 落地前实测（冷门项目核验，写进 plan 的第一步）

对 7 个 ⚠ 项目（openclaw / reasonix / nanobot / hermes / openhuman / sovyx / mimo-code），在目标容器内逐个核验后再写死 catalog：
```
npm view <pkg> version
pip index versions <pkg>
curl -fsSL -I <install-url 或 release 资产>
```
任何核验不通过的项标记为"未上架/待确认"，不放进可点击安装的清单（避免点了报错）。

## 13. 分期计划

- **一期**：Node22 预置 + 应用服务后端 + 控制栏入口与模态框 + catalog（11 个 CLI/插件，含 ⚠ 项实测）+ 持久化（home 卷 + 用户级 npm/pipx）。
- **二期**：GUI 类（Void/Cursor/OpenHuman）、Sovyx（Py3.11）、MiMo Code；GUI 持久化（AppImage 优先）。
- **后续**：NanoClaw（DinD 专项，若需要）。

## 14. 测试

- 后端单测：catalog 解析、id 白名单拒绝非法 id、status 检测逻辑、串行队列。
- 集成：容器内对 1-2 个确定可用的（Aider/Continue）跑 install → status 变已装 → remove → status 变未装。
- 持久化：装 Aider → `docker compose down/up` → status 仍已装。
- 安全：构造非白名单 id / 注入字符串 → 后端拒绝。
- 回归：不破坏现有 filebrowser/Caddy/控制栏。

## 15. 非目标重申

NanoClaw（DinD 降级）、Qcode（闭源剔除）、Modo（查无剔除）、任意命令执行通道（安全红线，永不实现）。
