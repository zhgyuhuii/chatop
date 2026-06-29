# 应用管理器一期 — 冷门项目包名/URL 容器内实测核验

- 镜像：`chatop-ai:1.1.0`（容器内含 Node 22 / npm / pip3 / curl）
- 核验日期：2026-06-29
- 判定规则：结果为 `NOT FOUND` / `UNREACHABLE` → 一期**不上架**（否）；有版本号 / HTTP 2xx/3xx → **上架**（是）。

## 实测结果表

| id | 核验命令 | 结果 | 是否上架一期 |
|---|---|---|---|
| openclaw | `npm view openclaw version` | 2026.6.10 | 是 |
| reasonix | `npm view reasonix version` | 0.53.2 | 是 |
| @qwen-code/qwen-code | `npm view @qwen-code/qwen-code version` | 0.19.3 | 是 |
| @openai/codex | `npm view @openai/codex version` | 0.142.4 | 是 |
| @anthropic-ai/claude-code | `npm view @anthropic-ai/claude-code version` | 2.1.195 | 是 |
| opencode-ai | `npm view opencode-ai version` | 1.17.11 | 是 |
| @mimo-ai/cli | `npm view @mimo-ai/cli version` | 0.1.3 | 是 |
| aider-chat | `pip3 index versions aider-chat` | 0.86.2 | 是 |
| sovyx | `pip3 index versions sovyx` | NOT FOUND（No matching distribution found for sovyx） | 否 |
| nanobot (pip) | `pip3 index versions nanobot` | 0.4.1 | 是 |
| plandex (script) | `curl -I https://plandex.ai/install.sh` | UNREACHABLE（Could not resolve host，code 000） | 否 |
| nanobot (script) | `curl -I https://install.nanobot.ai` | UNREACHABLE（Could not resolve host，code 000） | 否 |
| hermes-agent (script) | `curl -I https://raw.githubusercontent.com/NousResearch/hermes-agent/main/scripts/install.sh` | 200 | 是 |

## 结论

**确认可上架（一期可点击清单）：**
- npm：`openclaw`、`reasonix`、`@qwen-code/qwen-code`、`@openai/codex`、`@anthropic-ai/claude-code`、`opencode-ai`、`@mimo-ai/cli`
- pip：`aider-chat`、`nanobot`
- script：`hermes-agent`（raw.githubusercontent.com，HTTP 200）

**需剔除/降级（一期不上架）：**
- `sovyx`（pip 源无此包，确认 NOT FOUND）— 剔除
- `plandex`（脚本域名 `plandex.ai` 容器内无法解析）— 降级/暂缓
- `nanobot` 的脚本安装入口 `install.nanobot.ai`（无法解析）— 降级；但 **pip 包 `nanobot==0.4.1` 可用**，建议改用 pip 安装方式上架，而非脚本

## 备注 / 顾虑

- `plandex.ai` 与 `install.nanobot.ai` 在容器内均返回 “Could not resolve host”。同环境下 `raw.githubusercontent.com`、npm、pip 源、`google.com` 均可达，说明并非整体断网，而是这两个域名在当前容器 DNS 下解析不到。这有可能是构建/运行环境的 DNS 出口限制，而非 URL 本身失效；若后续放开网络可复测。按既定判定规则，本期先标“否”。
- `nanobot` 存在两种安装途径：pip 包可用、脚本域名不可达。已在上面拆分记录——建议一期采用 pip 安装路径。
