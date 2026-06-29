# 方向定调与决策记录：开源 AI 智能体云桌面

日期：2026-06-29
状态：已定调（取代最初"仅定制 KasmVNC standalone"的窄范围）

## 终极目标（用户最终澄清）

做一个**开源**的、浏览器可访问的 **AI 智能体云桌面系统**：
- 支持 **Linux 与 Windows** 两种桌面（Windows 是硬需求）。
- 系统做完后把**察元AI 嵌入**进去，**开机自动运行、打开界面**。
- 预装 **OpenClaw / Hermes / Codex / Claude Code** 等 AI coding agent。
- 全开源、可嵌入、可自由改品牌、无并发限制。

## 关键决策与依据

### 1. 走开源 DIY，放弃 Kasm Workspaces 平台（CE 与 Pro 都不用）

- **Community Edition 法律红线**：EULA 明确 CE "may not be used for revenue-generating
  business activities"，仅限评估/个人/非营利，限 5 并发，未经书面同意不得转让/再授权第三方。
  → 不能作为可商用/可分发产品的底座。
- **Pro/Enterprise**：合法商用但要付费授权，且品牌/底层 UI 受平台约束。
- 用户选择**开源路线**，正好绕开以上全部授权问题。

### 2. Linux 与 Windows 是两种机制（"分系统打包"的根源）

- **Linux 桌面** = Docker 容器内置 **KasmVNC**（开源）。容器即桌面，打包=构建镜像。
- **Windows 桌面** ≠ 容器。必须通过 **RDP** 连真实 Windows 机器/VM。
  选 **Apache Guacamole**（Apache 2.0，可商用）作 RDP→浏览器 的网页网关，
  原生支持 RDP + 文件上传下载（drive redirection）+ 剪贴板。

### 3. 文件上传/下载的来源澄清

- 开源 KasmVNC standalone **没有**文件传输（属 Kasm 平台功能）。
- 本系统：Linux 侧用旁挂方案（filebrowser，参考 chatop 的 `/files`）；
  Windows 侧用 Guacamole 自带的 RDP 文件传输。

## 子系统分解（各自 design → plan → build）

| 子系统 | 内容 | 状态 |
|---|---|---|
| **S1 Linux 桌面底座** | KasmVNC 注入定制（本项目 phase-1） | ✅ 注入管线已通 + e2e 自动验证过；待人工浏览器核对像素流 |
| **S2 Windows 桌面接入** | Guacamole + RDP + 文件传输 | 待设计 |
| **S3 AI 智能体预装层** | OpenClaw/Hermes/Codex/Claude Code 装进桌面镜像（与串流技术无关，可独立） | 待设计 |
| **S4 察元AI 嵌入 + 开机自启** | 开机自动打开察元AI 界面 | 待设计 |
| **S5 统一品牌/权限/语言/主题** | 最初的定制 5 项，跨 Linux/Windows 统一 | 待设计 |

## S1 已完成成果（phase-1）

- 独立仓 `/work/chatop-ai`，基于 `kasmweb/ubuntu-jammy-desktop:1.16.1`。
- 自构建 noVNC（kasmtech/noVNC 1.3.0，Vite）注入 web 根 `/usr/share/kasmvnc/www`（合并覆盖，不破坏原有）。
- compose + 运行脚本齐备；端到端验证：注入前端在线服务、Xvnc+xfce 运行、原有特性保留。
- 提交链：脚手架 → recon → vendor noVNC → 注入 Dockerfile → compose/验证。

## 待人工确认（S1 唯一剩余）

浏览器开 `https://localhost:6901`（`kasm_user` / 运行时设的密码）确认：远程桌面像素流渲染、
键鼠可交互、剪贴板与控制条正常。若因 noVNC 版本耦合异常，则把 `novnc-src` 锁到镜像内置版本再构建。

## 下一步（待用户定序）

S2（Windows/Guacamole）、S3（AI 智能体预装）、S5（品牌等）三选一优先推进。
S3 与串流技术解耦、可在 S1 Linux 底座上立即开展；S2 是独立大子系统；S5 依赖 S1 的 noVNC 定制已验证。
