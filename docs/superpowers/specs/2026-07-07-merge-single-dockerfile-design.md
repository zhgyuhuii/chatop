# 合并回单一 Dockerfile（移除 Dockerfile.base）+ 瘦身 + 内置智能体 —— 设计文档

- 日期：2026-07-07
- 状态：已批准，待实现
- 关联/取代：`docs/superpowers/specs/2026-07-04-split-base-image-design.md`（base/product 拆分，本设计将其回退为单文件）

## 1. 背景与动机

2026-07-04 把镜像拆成 `chatop-base:latest`（重/联网/固定）+ `chatop-ai:<VERSION>`（快变），
目的是解决"每次迭代都联网重下 AI 工具"。拆分设计文档自己已指出：**慢的真因是分层缓存被
COPY 打穿的顺序问题**，而非"没拆 base"。

用户 2026-07-07 反馈：**基于 base 打包后镜像变大**，要求：

1. 移除 `Dockerfile.base`，合并回**单一 Dockerfile**。
2. 在**本环境**能真正构建并部署（已实测联网可达：nodesource/google/github/npm/aliyun/launchpad/hermes 全部 200/30x）。
3. 移除旧的（base 及其构建脚本）。
4. 按历史需求**内置智能体**。

### 现状事实（构建/盘面实测）

- 稼働中：容器 `chatop-ai`，镜像 `chatop-ai:1.1.0`，**4.72GB**，Up 3 天，提供 `:6901->7443`。
  compose 标签 project/service=`chatop-ai`。
- `docker system df`：Images 12.44GB，**62% 可回收**（孤立的旧 kasm desktop 7.73GB）。
- 最大自定义层：**预装层 `chatop-preinstall` = 1.19GB**（AI CLI + Hermes + OpenHuman + npm/pip/uv 缓存混入）。
  次之 Chrome apt 层 427MB、locale 131MB。
- 命名漂移：稼働中用 `chatop-ai`，但仓库现行 `docker-compose.yml`/脚本已改成 `chatop`。
  若直接 `docker compose up -d` 会新建 `chatop` 容器与旧 `chatop-ai` 抢 6901 → 冲突。

### 为什么"拆 base"会让盘面变大

单机保留 `chatop-base`(~4.5GB) + `chatop-ai`(~4.7GB) 两个 tag；每次重建 base 又留下悬空的旧 base 层，
`docker save`/盘面核算按整镜像计 → 观感"翻倍"。合并回单镜像可消除这份二重 footprint。

## 2. 目标与非目标

**目标**

- 单一 `Dockerfile`（多阶段），本环境可 `docker compose up -d --build` 直接构建并切换上线。
- 镜像**更小**：不删任何智能体，靠清缓存 / 去构建残渣 / 合层 / 去二重镜像瘦身。
- **内置智能体保持现状全套**：`claude-code / codex / openclaw / tokscale / rtk` + `agent-builder`(HTML)
  + `Hermes` + `OpenHuman`，保留 `PREINSTALL_HEAVY` 开关。
- 迭代速度不退化：靠 Docker 分层缓存（同机重建不重下）。

**非目标（YAGNI）**

- 不引入镜像仓库/registry。
- 不改运行时架构（Caddy 网关 / app-manager / station 大屏 / KasmVNC 不动）。
- 不改 seed-home 播种机制（`cp -an` 幂等，`WANT=2` 已含 Hermes/OpenHuman）。
- 不做 `--squash`（kasm 基底 flatten 困难、需 experimental daemon，风险过大）。

## 3. 方案（选定：单一多阶段 Dockerfile + 顺序最优 + 瘦身）

### 3.1 阶段与层顺序（重/联网/固定在前，快变 COPY 在后）

1. `FROM node:20-alpine AS web` —— 构建 `novnc-src` → `/src/dist`（改前端只重跑此 stage）
2. `FROM node:20-alpine AS dashweb` —— 构建 `dashboard-web` → `/src/dist`
3. `FROM kasmweb/core-ubuntu-jammy:1.19.0`（运行基底）
4. 二进制：filebrowser、caddy（github 直链 + 重试）
5. apt 群：CJK 字体、Node 22、Python 3.11(deadsnakes)、中文 locale、Google Chrome、proot-apps
6. vnc_startup 登录名/剪贴板补丁、PATH/profile 注入
7. 用户改名 `kasm-user→admin` + home 迁移 + default-profile 迁移
8. station venv（fastapi/uvicorn/psutil，阿里源优先回退官方）
9. **AI CLI 预装 → `/opt/chatop-seed-home`**（`chatop-preinstall.sh`，含清缓存，`PREINSTALL_HEAVY` 维持）
10. 快变 COPY：app-manager、station 源、Caddy/filebrowser 脚本、品牌资源、kasmvnc.yaml
11. 生成 `custom_startup.sh`、注入前端 dist（`--from=web`/`--from=dashweb`）、`USER 1000`

> 结束态（ENV/WORKDIR/USER/PATH/已装二进制）与拆分前 `Dockerfile` 第 86 行 + `Dockerfile.base`
> 第 149 行合并后**逐条一致**，避免运行时行为漂移。

### 3.2 瘦身措施（一个智能体都不删）

| 措施 | 落点 | 预期 |
|---|---|---|
| 清 npm/pip/uv 缓存（`npm cache clean --force`、删 `~/.cache`、`~/.npm/_cacache`）在迁 seed-home 前 | `chatop-preinstall.sh` 结尾 | 压缩 1.19GB 预装层 |
| 去 `pipx`（预装脚本从未使用） | Dockerfile apt 行 | 去 python-apt/dbus 等依赖 |
| deadsnakes PPA 加完后 `apt-get purge software-properties-common` | Dockerfile python3.11 层 | 数十 MB |
| 每个 apt RUN 都 `apt-get clean && rm -rf /var/lib/apt/lists/*` | Dockerfile 全 apt 层 | 不把 .deb 留层里 |
| 去二重镜像：只产出单个 `chatop-ai:<VERSION>` | 删 Dockerfile.base | 盘面 footprint 减半 |

> 瘦身仅动"缓存/构建残渣/二重镜像"，**不动** Hermes venv、OpenHuman squashfs、任何 CLI 本体。

### 3.3 脚本与 compose 变更

- **删除**：`Dockerfile.base`、`build-base.sh`、`build-base.bat`。
- `docker-compose.yml`：命名统一回**稼働中一致的 `chatop-ai`**——
  `services.chatop-ai`、`image: chatop-ai:${VERSION}`、`container_name: chatop-ai`、`pull_policy: build`。
  这样 `up -d --build` 干净替换旧容器（同名同项目），不产生 6901 冲突。
- `build-and-run.sh` / `.bat`：删掉 base 自举分支，简化为版本自增 + 单条 `docker compose up -d --build`
  + 删旧版本产品镜像 `chatop-ai:<OLD>` + `image prune`。
- 分离设计文档头部加"已被本设计取代"注记。

### 3.4 内置智能体（历史需求汇总）

沿用 `app-manager/chatop-preinstall.sh` 现有实现（v1.2.0 已成型）：

- npm 全局：`openclaw` `@openai/codex` `@anthropic-ai/claude-code` `tokscale`（直连失败回退 npmmirror）
- `rtk`（musl 静态二进制，latest/download 直链 + GH 镜像回退）
- `agent-builder`（openclaw-agent-builder 单文件 HTML + 桌面图标）
- `PREINSTALL_HEAVY=1` 时追加：`Hermes`（install.sh --skip-setup）、`OpenHuman`（AppImage 解包）
- 桌面图标：agent-builder、tokscale
- 未内置的智能体（opencode/qwen-code/aider/… 及 100+ proot-gui）仍走应用市场一键装。

## 4. 边界情况

- **命名切换**：新 compose 用 `chatop-ai`，与稼働容器同名同项目，`up -d` 原地替换；旧 `chatop-ai:1.1.0`
  镜像由脚本 `image rm` 清掉。
- **seed 卷升级**：现有 `chatop-home` 卷 sentinel < 2，新镜像 `WANT=2` 会 `cp -an` 补种 Hermes/OpenHuman，
  不覆盖用户数据。
- **CRLF**：`.gitattributes` 强制 LF；Dockerfile 对所有 COPY 脚本保留 `sed 's/\r$//'` 兜底。
- **联网失败**：Hermes/OpenHuman 失败会 `exit 1` 中断构建；网络/盘受限可 `PREINSTALL_HEAVY=0` 跳过后走市场装。
- **迭代速度**：不再拆 base，但同机分层缓存保证改前端/改 app-manager 时只重跑靠后 COPY 层，不重下。

## 5. 验收标准（本环境实测）

1. 单一 `Dockerfile` 能 `docker compose up -d --build` 出 `chatop-ai:1.2.0` 并起容器。
2. 旧 `chatop-ai` 容器被干净替换，无 6901 端口冲突。
3. `https://localhost:6901` 进登录页、桌面正常、中文渲染正常、Chrome 可开。
4. 终端 AI CLI 可用：`claude`/`codex`/`openclaw`/`rtk`/`tokscale`；`hermes` 在；`~/Applications/openhuman/squashfs-root` 在。
5. `/dashboard` 工位大屏可开、SSE 有数据。
6. 记录构建前后 `docker images` 尺寸，报告瘦身量（目标：≤ 拆分前单镜像，且显著小于 base+product 二重）。
7. `Dockerfile.base` / `build-base.*` 已删除，仓库无残留引用。

## 6. 回滚

旧镜像 `chatop-ai:1.1.0` 在脚本删除前先保留；若新镜像验收不过，`docker compose down` 后
`docker run` 旧 tag 或还原 compose 即可恢复。确认新镜像 OK 再删旧 tag。
