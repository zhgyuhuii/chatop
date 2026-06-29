# 自定义 Webtop 与 Selkies 构建指南

本文档说明如何修改 Selkies 界面样式、Webtop 主题，并重新构建镜像。

## 构建方式

**构建逻辑已全部在 Dockerfile 中**，无需单独脚本。可直接使用：

```bash
docker compose up -d --build
```

或仅构建：

```bash
docker build -t webtop:custom .
```

访问 https://localhost:3001

**Logo**：项目根目录放置 `logo.png` 或 `logo.svg`，无则使用默认图标。

**构建时自动安装：**
- **openclaw-tool**：OpenClaw 配置程序，桌面有快捷方式
- **MacVentura-Dark 主题** + **WhiteSur 图标**：构建时从 GitHub 下载安装，首次启动自动应用

**Dockerfile 构建参数：**
- `SELKIES_REPO`：Selkies 仓库地址（默认 selkies-project/selkies）
- `SELKIES_COMMIT`：指定 commit，空则使用 main 最新；存在 `selkies-src/` 时优先用本地代码

**docker-compose 环境变量：** 可在 `docker-compose.yml` 或 `.env` 中修改 `PUID`、`PGID`、`TZ`、`CUSTOM_USER`、`PASSWORD` 等。

**可选：build-and-run.sh** 仅为便捷入口，等同于 `docker compose`：
```bash
./build-and-run.sh build   # docker compose build
./build-and-run.sh run     # docker compose up -d --build
./build-and-run.sh down    # docker compose down
```

## 已完成的修改

### 1. Webtop 界面修改 (docker-webtop-master)

| 文件 | 修改内容 |
|------|----------|
| `root/defaults/xfce/xfwm4.xml` | 窗口透明度：frame_opacity=90, inactive_opacity=85 等 |
| `root/defaults/xfce/xfce4-panel.xml` | 面板位置：从底部(p=6)改为左侧(p=12) |
| `root/defaults/selkies-custom/custom.css` | Selkies 侧边栏透明度与按钮位置 |

### 2. Selkies Baseimage 修改 (docker-baseimage-selkies-master)

| 文件 | 修改内容 |
|------|----------|
| `root/etc/s6-overlay/s6-rc.d/init-nginx/run` | 支持从 `/defaults/selkies-custom/` 加载自定义 CSS 覆盖 |

## 进一步自定义

### 修改 XFCE 透明度
编辑 `docker-webtop-master/root/defaults/xfce/xfwm4.xml`：
- `frame_opacity` (0-100): 活动窗口透明度
- `inactive_opacity` (0-100): 非活动窗口透明度
- 数值越小越透明

### 修改 XFCE 面板位置
编辑 `docker-webtop-master/root/defaults/xfce/xfce4-panel.xml`：
- `p=0`: 顶部
- `p=6`: 底部
- `p=12`: 左侧
- `p=18`: 右侧
- `x`/`y`: 偏移量

### 修改主题
编辑 `docker-webtop-master/root/defaults/xfce/xsettings.xml`：
- `ThemeName`: 如 `adw-gtk3-dark`、`adw-gtk3`(浅色)、`Arc-Dark` 等
- `IconThemeName`: 图标主题，如 `adwaita-xfce`

### 修改 Selkies 侧边栏样式
编辑 `docker-webtop-master/root/defaults/selkies-custom/custom.css`，可调整：
- 侧边栏透明度 (`opacity`)
- 背景色 (`background-color`)
- 切换按钮位置 (`top`, `left`)

## 构建步骤

### 方式一：使用官方镜像（仅 Webtop 修改生效）

若只修改了 Webtop 相关文件，可直接构建 webtop：

```bash
cd docker-webtop-master
docker build -t webtop:custom .
```

**注意**：Selkies 自定义 CSS 需要 baseimage 支持。使用官方 `ghcr.io/linuxserver/baseimage-selkies:alpine323` 时，init-nginx 不含自定义 overlay 逻辑，`selkies-custom` 不会生效。

### 方式二：完整自定义（Baseimage + Webtop）

需要同时修改 Selkies 和 Webtop 时，先构建 baseimage，再构建 webtop：

```bash
# 1. 构建自定义 baseimage-selkies（包含 Selkies CSS overlay 支持）
cd docker-baseimage-selkies-master
docker build -t baseimage-selkies:custom .

# 2. 修改 webtop Dockerfile 第一行为：
#    FROM baseimage-selkies:custom

# 3. 构建 webtop
cd ../docker-webtop-master
docker build -t webtop:custom .
```

**说明**：
- 官方 `baseimage-selkies:alpine323` 为 Alpine 变体，本地仓库中的主 Dockerfile 构建的是 Debian 镜像。若需 Alpine 版本，需使用与 linuxserver CI 相同的构建流程。
- 若仅需 XFCE 修改（透明度、面板位置）而无需 Selkies CSS 覆盖，可直接用方式一构建 webtop。

### 方式三：多阶段构建（推荐）

在 `docker-webtop-master/Dockerfile` 中，将第一行改为使用本地 baseimage：

```dockerfile
# 若已构建 baseimage-selkies:custom，使用：
FROM baseimage-selkies:custom
# 否则使用官方：
# FROM ghcr.io/linuxserver/baseimage-selkies:alpine323
```

## 运行容器

```bash
docker run -d \
  --name webtop \
  -e PUID=1000 \
  -e PGID=1000 \
  -e TZ=Asia/Shanghai \
  -p 3001:3001 \
  --shm-size=1g \
  -v webtop-config:/config \
  webtop:custom
```

访问 https://localhost:3001 查看效果。
