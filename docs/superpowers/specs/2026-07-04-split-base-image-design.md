# 拆分 base 镜像 + 增量产品镜像 —— 设计文档

- 日期：2026-07-04
- 状态：已实现（2026-07-04）
- 背景问题：`docker compose up --build` 每次都很慢、都在联网下载。

## 1. 问题与根因

当前是**单 `Dockerfile` + `docker compose up -d --build`**，产出单镜像 `chatop-ai:<VERSION>`。

慢的真正原因不只是"没拆 base"，而是**分层缓存被打穿的顺序问题**：

- 快变内容 COPY 得很靠前：`app-manager/app_manager.py`（第 140 行）、前端 dist（177 行）、`Caddyfile`、壁纸等。
- 最重的联网安装 `chatop-preinstall.sh`（`npm i -g openclaw/codex/claude-code/tokscale` + 下载 rtk 等）在**第 253 行，靠后**。

Docker 规则：某层变化会使**其后所有层**失效重跑。因此**每次改 app-manager 代码或前端，都会连累第 253 行的 AI 工具联网安装重跑**——这是"每次都在下载"的主因。

## 2. 目标与决策

目标：把**固定、重、联网**的内容沉到一个**很少重建的 base 镜像**，产品镜像只保留**快变内容**，实现秒级、零下载的迭代。

已确认的决策：

1. **分发方式**：本地双镜像，无需镜像仓库。每台机器本地 build 一次 `chatop-base`；可随时重建；重建后打产品镜像自动使用最新 base。
2. **AI CLI 工具**（claude-code / codex / openclaw / rtk 等）：**放 base**，重建 base 才更新（符合"base 固定"初衷）。

## 3. 架构

两个本地镜像：

| 镜像 | 来源 | 重建频率 | 内容 |
|---|---|---|---|
| `chatop-base:latest` | 新增 `Dockerfile.base` | 很少（依赖变了、想更新工具、新机器首次） | 所有重的、联网的、固定的 |
| `chatop-ai:<VERSION>` | 现有 `Dockerfile`（改成 `FROM chatop-base:latest`） | 每次迭代 | 只有快变内容，秒级、不联网 |

"始终用最新 base"：产品 `FROM chatop-base:latest`；重跑 `build-base.sh` 后 `latest` 指向新 base，下次产品构建自动吃到最新，**无需改任何产品文件**。

## 4. 拆分线（按当前 `Dockerfile` 的行）

### 进 `Dockerfile.base`（固定层）

- `# syntax=docker/dockerfile:1.7`
- `FROM kasmweb/core-ubuntu-jammy:1.19.0`，`ARG VERSION`、`ARG APP_USER=admin`、`ARG LOGIN_USER`
- filebrowser 二进制下载（原 25-30 行）
- caddy 二进制下载（原 37-42 行）
- `ENV XDG_DATA_HOME/XDG_CONFIG_HOME`（原 46 行）及后续 ENV 累积逻辑
- `fonts-noto-cjk` 等字体（原 60-62 行）
- Node 22 + pipx（原 67-72 行）
- profile.d / bash.bashrc 的 PATH 注入（原 75-80 行）
- vnc_startup.sh 登录名 + 剪贴板补丁（原 85-88 行）、`ENV LOGIN_USER`
- Python 3.11 / deadsnakes（原 98-101 行）
- 中文 locale + 语言包 + `ENV LANG/LANGUAGE/LC_ALL`（原 107-112 行）
- Google Chrome 预装 + 默认浏览器设置（原 117-136 行）
- proot-apps（原 198-202 行）
- 用户改名 `kasm-user→${APP_USER}` + home 迁移 + `WORKDIR` + `ENV HOME` + default-profile 迁移（原 213-234 行）
- `ENV XDG_CONFIG_HOME/XDG_DATA_HOME`、`ENV NPM_CONFIG_PREFIX/PATH`（原 244-248 行）
- `chatop-preinstall.sh`：COPY + `su admin` 安装 AI 工具 → 迁到 `/opt/chatop-seed-home`（原 149、253-256 行）
- `rm -rf /tmp/caddy`（原 259 行）
- 结尾 `USER 1000`（原 261 行）

> base 的**结束态**（ENV / WORKDIR / USER / PATH / 已装二进制与工具）必须与当前 `Dockerfile` 第 261 行的状态**逐字一致**，否则运行时行为会变。实现时逐条核对。

### 留在 `Dockerfile`（产品/增量层）

- `# syntax=docker/dockerfile:1.7`
- `FROM node:20-alpine AS web` + 构建 `novnc-src` → `/src/dist`（原 2-5 行；改前端只重跑此 stage）
- `FROM chatop-base:latest`
- `ARG VERSION`、`LABEL`
- `USER root`
- COPY app-manager：`app_manager.py`、`apps-catalog.json`、`icons/`、`start-app-manager.sh`、`gui-install.sh`/`gui-uninstall.sh`、`chatop-run-cli.sh`、`chatop-seed-home.sh`（原 140-150 行，去掉 `chatop-preinstall.sh`——它进了 base）
- COPY caddy：`Caddyfile`、`start-caddy.sh`、`start-filebrowser.sh`（原 31、43-44 行）
- COPY assets：`background.png`（壁纸两处）、`set-wallpaper.sh`、`logo-sm.png`、`apps-icon.svg`、`background-splash.jpg`（原 165-167、180-184 行）
- COPY `kasmvnc.yaml`（原 175 行）
- CRLF `sed 's/\r$//'` + `chmod +x` 覆盖以上所有脚本（合并原 49、153-158、168 行的 sed/chmod）
- 生成最终 `custom_startup.sh`（原 172-173 行那份，含 seed-home / caddy / filebrowser / app-manager / set-wallpaper + symlink + wait）
- filebrowser 启动脚本 heredoc（原 187-193 行，幂等覆盖）
- 注入前端：`COPY --from=web /src/dist/ /usr/share/kasmvnc/www/`（原 177 行）
- 结尾 `USER 1000`

> 现有 Dockerfile 中"为保缓存刻意打乱顺序"的注释与 workaround（如把中文化/Chrome 放 python3.11 之后、末尾重复 COPY Caddyfile 等）拆开后不再需要，可清理。

## 5. Build 流程与脚本

### 新增 `build-base.sh`

```bash
#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
[ -f .env ] && set -a && . ./.env && set +a || true
sudo docker build -f Dockerfile.base \
  --build-arg APP_USER="${LOGIN_USER:-admin}" \
  --build-arg LOGIN_USER="${LOGIN_USER:-admin}" \
  -t chatop-base:latest .
echo "chatop-base:latest 构建完成"
```

触发时机：base 依赖变了 / 想更新 AI 工具 / 新机器首次。

### 改 `build-and-run.sh`（自举）

```bash
#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
[ -f .env ] || { echo "请先 cp .env.example .env 并改密码"; exit 1; }
export VERSION="$(cat VERSION)"
# 自举：本地没有 base 就先建一次（新机器一条命令搞定）
if ! sudo docker image inspect chatop-base:latest >/dev/null 2>&1; then
  echo "未发现 chatop-base:latest，先构建 base ..."
  ./build-base.sh
fi
sudo docker compose up -d --build
echo "已启动：https://localhost:$(grep -E '^PORT=' .env | cut -d= -f2 || echo 6901)"
```

日常迭代仍是一条 `./build-and-run.sh`，但只重打产品层，秒级、零下载。

### `docker-compose.yml`

- `build.context` 不变、`build.dockerfile: Dockerfile`（产品）。
- 产品 `FROM chatop-base:latest` 为本地镜像；加 `pull_policy: build`（或产品 build 传 `--pull=false`），避免 Docker 把本地 base 误当远程去 pull。
- `APP_USER` build-arg 从 compose 移除（它现在是 base-build-time 参数）；compose 只需 `VERSION`。

## 6. 边界情况

- **CRLF**：`.gitattributes` 已强制 LF；两个 Dockerfile 各自对自己 COPY 的脚本保留 `sed 's/\r$//'` 兜底。
- **改用户名**：`APP_USER/LOGIN_USER` 是 base-build-time 参数，改用户名需重建 base。文档说明。
- **base 标签**：主用 `latest`（满足"始终用最新"）；可选再打 `chatop-base:1.19-<日期>` 快照便于回滚，不强制。
- **首次/新机器**：`build-and-run.sh` 自举会自动建 base，无需记额外命令。
- **行为一致性验证**：拆分后需实测容器起来、`https://localhost:6901` 进登录页、桌面正常、AI 工具在终端可用，与拆分前一致。

## 7. 非目标（YAGNI）

- 不引入镜像仓库 / registry 推送（用户明确要本地）。
- 不做 base 自动更新检测；重建 base 由人工触发。
- 不改运行时架构（Caddy 网关 / app-manager / KasmVNC 不动）。

## 8. 验收标准

1. `Dockerfile.base` 能独立 build 出 `chatop-base:latest`。
2. 改 `app-manager/app_manager.py` 或前端后跑 `build-and-run.sh`，**不触发**任何 apt/npm/二进制下载，仅重打 COPY 层，秒级完成。
3. 重建 base 后，产品构建自动使用新 base（无需改产品文件）。
4. 拆分前后运行时行为一致：登录页、桌面、中文、Chrome、AI CLI、文件传输、剪贴板均正常。
5. 新机器仅 `./build-and-run.sh` 一条命令即可从零跑起来（自动建 base）。
