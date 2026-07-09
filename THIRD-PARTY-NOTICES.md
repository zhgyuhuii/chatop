# 第三方组件与许可声明

本文件说明 chatop-ai（察元 AI 工舱）的许可结构、随镜像分发的第三方组件，
以及由此产生的源码提供义务。

---

## 1. 本项目的许可

chatop-ai 自身的代码 —— 包括 `app-manager/`、`station/`、`agent-bridge/`、
`openclaw-tool/`、`dashboard-web/`、`caddy/`、`filebrowser/`、`Dockerfile`、
`docker-compose.yml` 及各构建脚本 —— 以 **GNU General Public License v2.0**
发布，全文见仓库根目录的 [`LICENSE`](./LICENSE)。

选择 GPL-2.0 的原因：本项目以 **KasmVNC**（GPL-2.0）为云桌面底座并随镜像再分发，
统一采用同一许可可以让整个分发物的合规边界保持清晰。

---

## 2. 例外：`novnc-src/`

`novnc-src/` 是 vendored 的 **[@kasmtech/noVNC](https://github.com/kasmtech/noVNC) 1.3.0**
（`novnc-src/package.json` 声明 `"license": "MPL-2.0"`），**不适用**本项目根目录的
GPL-2.0，而是保留其自身的 [`novnc-src/LICENSE.txt`](./novnc-src/LICENSE.txt)：

| 部分 | 许可 |
|---|---|
| core 库 JS（`core/**/*.js`、`app/*.js`） | MPL-2.0 |
| `*.html`、`app/styles/*.css` | 2-Clause BSD |
| `app/styles/Orbitron*` 字体 | SIL OFL 1.1 |
| `app/images/` | CC BY-SA 3.0 |
| `core/des.js` | 多种 BSD 风格许可 |
| `vendor/pako/` | MIT |

该 noVNC 副本**未**声明 MPL-2.0 定义 1.5 所指的
"Incompatible With Secondary Licenses"。依据 MPL-2.0 第 3.3 条，其 Covered Software
可作为 Secondary License（含 GPL-2.0）的一部分组合分发。本项目据此将其与
GPL-2.0 代码一同分发，同时保留其原始许可与版权声明。

对 `novnc-src/` 中既有文件的修改，仍受 MPL-2.0 的文件级 copyleft 约束。

---

## 3. 基础镜像与 GPL-2.0 源码提供义务

镜像基于 **`kasmweb/core-ubuntu-jammy:1.19.0`** 构建，该镜像包含
**[KasmVNC](https://github.com/kasmtech/KasmVNC)**（GPL-2.0，见其
[`LICENSE.TXT`](https://github.com/kasmtech/KasmVNC/blob/master/LICENSE.TXT)）
及 Ubuntu 发行版组件（各自许可以其软件包声明为准）。

> **分发者注意**：以可执行形式（含容器镜像）分发 KasmVNC 时，GPL-2.0 第 3 条要求
> 随附完整的对应源代码，或提供一份有效期至少三年的书面源码获取要约。
> 转发你收到的源码要约同样满足该条。KasmVNC 的对应源码可从上述上游仓库获取。

本项目未修改 KasmVNC 服务端源码；定制发生在其 Web 前端资源（见第 2 节）与
运行时配置（`chatop-vnc.yaml`）。

---

## 4. 构建期写入镜像的第三方二进制

| 组件 | 版本 | 许可 | 来源 |
|---|---|---|---|
| Caddy | 2.11.4 | Apache-2.0 ✅已核实 | https://github.com/caddyserver/caddy |
| filebrowser | latest release | Apache-2.0 ✅已核实 | https://github.com/filebrowser/filebrowser |
| Google Chrome | stable | **专有软件** | https://www.google.com/chrome/ |

Python / Node 依赖（各自许可以其上游声明为准）：

- `station/`：FastAPI、uvicorn、psutil
- `agent-bridge/`：websockets
- `dashboard-web/`：React、React-DOM、Vite

---

## 5. 镜像内预装的第三方软件（**不受本项目 GPL-2.0 覆盖**）

以下软件由 `app-manager/chatop-preinstall.sh` 在构建期安装进镜像，或由应用市场按需
安装。它们**各自受其上游许可或服务条款约束**，本项目的 GPL-2.0 既不覆盖也不改变
这些条款：

| 软件 | 说明 |
|---|---|
| `@anthropic-ai/claude-code` | **专有软件**，受 Anthropic 的服务条款约束 |
| Google Chrome | **专有软件**，受 Google Chrome 服务条款约束 |
| `@openai/codex` | 以上游声明为准 · https://github.com/openai/codex |
| `openclaw` | 以上游声明为准 |
| `tokscale` | 以上游声明为准 |
| Hermes Agent | 以上游声明为准（`PREINSTALL_HEAVY=1` 时预装） |
| RTK (Token Killer) | 以上游声明为准 |
| proot-apps 及其应用目录 | 以 linuxserver/proot-apps 及各应用声明为准 |

> **公开再分发前请注意**：官方镜像内含 Google Chrome 与 Claude Code 等专有软件。
> 将该镜像公开推送到镜像仓库或对外分发，可能受这些组件各自的再分发条款限制。
> 若需完全无专有组件的分发物，请在构建时移除相应安装步骤。

---

## 6. 关于序列号与开源

本项目的源码公开且以 GPL-2.0 授权，你可以自由地获取、修改、再分发，并从源码
自行构建镜像 —— 这是 GPL-2.0 赋予你的权利，本项目不作任何附加限制，
既不限制并发会话数，也不锁定品牌。

官方发布的镜像内置序列号激活闸门（`app-manager/chatop_license/`，纯离线 HMAC 校验）。
购买序列号所获得的是**开箱即跑的官方构建、持续更新与商业支持**，而不是"解锁功能"。

依据 GPL-2.0 第 6 条，本项目不对你行使许可证所授予的权利施加进一步限制。

---

## 7. 版权

Copyright (C) 2026 北京智灵鸟科技中心

本程序是自由软件；你可以依据自由软件基金会发布的 GNU 通用公共许可证第 2 版的条款
重新发布和/或修改它。

本程序的发布是希望它能有用，但**不作任何担保**；甚至没有适销性或特定用途适用性的
默示担保。详见 GNU 通用公共许可证。
