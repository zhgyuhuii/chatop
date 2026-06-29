# 自定义 察元AI (chatop) 与 Selkies 构建指南

本文档说明如何修改 Selkies 界面样式、察元AI 主题，并重新构建镜像。

## 镜像命名与版本

- 镜像名固定为 `chatop`，标签为版本号，例如 `chatop:1.0.0`，并额外打 `chatop:latest`。
- 版本号单一真源是根目录的 `VERSION` 文件（当前 `1.0.0`）。
- **约定：每次发布（提交）将 `VERSION` 中的版本号 +1**（如 1.0.0 → 1.0.1）。
- `docker compose` 会用 `${VERSION}` 自动给镜像打 tag；`build-and-run.sh` 会读取 `VERSION` 并自动同步 `chatop:latest`。

## 构建方式

**构建逻辑已全部在 Dockerfile 中**，无需单独脚本。推荐：

```bash
./build-and-run.sh run     # 读取 VERSION，构建并启动，自动打 chatop:latest
```

或直接用 compose（版本号取自 VERSION 文件 / .env）：

```bash
VERSION=$(cat VERSION) docker compose up -d --build
```

或仅手动构建单个镜像：

```bash
docker build --build-arg VERSION=$(cat VERSION) -t chatop:$(cat VERSION) .
```

访问 https://localhost:3001

**Logo**：项目根目录放置 `logo.png`（已为当前 logo），无则使用默认图标。

**构建时自动安装：**
- **openclaw-tool**：OpenClaw 配置程序，桌面有快捷方式
- **WhiteSur GTK 主题 + WhiteSur 图标**：用仓库根目录的 `WhiteSur-*-theme-master.zip` 安装，首次启动自动应用

> 注意：原 MacVentura-Dark KDE 主题依赖未提供的 `*-kde*.zip`，构建会失败，现已从 Dockerfile 移除。
> `/etc/skel/.config/kdeglobals` 仍写着 MacVentura，缺该主题时 KDE 回退默认 Breeze。
> 如需 Mac 风外观，请把对应 KDE Look-and-Feel zip 放进根目录并恢复 Dockerfile 中的 KDE 主题安装块。

**Dockerfile 构建参数：**
- `VERSION`：镜像版本号（默认取自 `VERSION` 文件，写入镜像 LABEL）
- `SELKIES_REPO`：Selkies 仓库地址（默认 selkies-project/selkies）
- `SELKIES_COMMIT`：默认锁定到验证过的 commit（可复现）；置空则取 main 最新；存在 `selkies-src/` 时优先用本地代码
- 基础镜像（`baseimage-alpine:3.22`、上游 `linuxserver/webtop:ubuntu-kde`）已用 `@sha256:` 锁 digest，升级时需重新解析 digest

**docker-compose 环境变量：** 可在 `docker-compose.yml` 或 `.env` 中修改 `PUID`、`PGID`、`TZ`、`CUSTOM_USER`、`PASSWORD` 等。

**可选：build-and-run.sh** 仅为便捷入口，等同于 `docker compose`：
```bash
./build-and-run.sh build   # docker compose build + 打 latest
./build-and-run.sh run     # docker compose up -d --build + 打 latest
./build-and-run.sh down    # docker compose down
```

## 构建结构（根目录 Dockerfile）

当前唯一生效的构建是仓库根目录的 `Dockerfile`，两阶段：

1. **Stage 1（selkies-build, Alpine）**：克隆/使用本地 Selkies 源码，构建三套 dashboard
   （`selkies-dashboard` / `-zinc` / `-wish`），并把根目录 logo 注入各 dashboard。
2. **Stage 2（上游 linuxserver/webtop:ubuntu-kde）**：注入构建好的 Selkies、安装 WhiteSur 主题与 openclaw-tool、
   写入 SDDM 登录主题与开机动画、放置 9 个 `custom-cont-init.d/*.sh` 首启脚本，最后跑
   `scripts/cleanup-image.sh` 瘦身。

> 早期版本曾保留 `docker-webtop-master/`、`docker-baseimage-selkies-master/` 两个上游整仓拷贝
> 作为 XFCE 备用构建路径，但主镜像是 **KDE 非 XFCE**，这两目录从不参与根 Dockerfile 构建，
> 已删除。若日后需要 XFCE 变体或自定义 baseimage，从 linuxserver 上游重新获取即可。

## 进一步自定义

| 想改什么 | 改哪里 |
|------|----------|
| 桌面/面板/主题等首启默认配置 | `custom-defaults/`（首次启动、空 volume 时复制到 `/config`） |
| KDE 面板居中、默认浏览器、终端、用户名、提示符等 | `custom-cont-init.d/9x-*.sh` |
| Selkies 前端版本 | Dockerfile `ARG SELKIES_COMMIT`，或放本地 `selkies-src/` |
| Logo | 根目录 `logo.png` |
| GTK/图标主题 | 替换根目录 `WhiteSur-*-theme-master.zip`，并按需调整 Dockerfile 安装块 |
| 登录界面 / 开机动画 | `custom-sddm/`、`custom-splash/` |

## 运行容器

```bash
docker run -d \
  --name chatop \
  -e PUID=1000 \
  -e PGID=1000 \
  -e TZ=Asia/Shanghai \
  -p 3001:3001 \
  --shm-size=1g \
  -v chatop-config:/config \
  chatop:1.0.0
```

访问 https://localhost:3001 查看效果。
