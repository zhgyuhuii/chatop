# syntax=docker/dockerfile:1.7
# 前端构建（改前端只重跑此 stage）
FROM node:20-alpine AS web
WORKDIR /src
COPY novnc-src/ ./
RUN --mount=type=cache,target=/root/.npm npm install && npm run build

# 产品镜像 = 固定 chatop-base + 快变内容（改这些才重打，且不联网）
FROM chatop-base:latest
ARG VERSION=1.1.0
LABEL maintainer="chatop-ai" build_version="chatop-ai ${VERSION}"
USER root

# === app-manager：后端 + catalog + 图标 + 启动脚本 + GUI/CLI 脚本 + 播种脚本 ===
RUN mkdir -p /usr/local/lib/chatop /etc/chatop
COPY app-manager/app_manager.py /usr/local/lib/chatop/app_manager.py
COPY app-manager/apps-catalog.json /etc/chatop/apps-catalog.json
COPY app-manager/icons/ /usr/share/kasmvnc/www/app-icons/
COPY app-manager/start-app-manager.sh /usr/local/bin/start-app-manager.sh
COPY app-manager/gui-install.sh app-manager/gui-uninstall.sh /usr/local/lib/chatop/
COPY app-manager/chatop-run-cli.sh /usr/local/bin/chatop-run-cli
COPY app-manager/chatop-seed-home.sh /usr/local/bin/chatop-seed-home.sh

# === Caddy 反代配置 + 启动脚本；filebrowser 启动脚本 ===
COPY caddy/Caddyfile /etc/caddy/Caddyfile
COPY caddy/start-caddy.sh /usr/local/bin/start-caddy.sh
COPY filebrowser/start-filebrowser.sh /usr/local/bin/start-filebrowser.sh

# === 品牌资源 + KasmVNC 剪贴板配置 ===
COPY assets/background.png /usr/share/backgrounds/chayuanai/wallpaper.png
COPY assets/background.png /usr/share/backgrounds/bg_default.png
COPY assets/set-wallpaper.sh /usr/local/bin/set-wallpaper.sh
COPY kasmvnc.yaml /etc/kasmvnc/kasmvnc.yaml

# === CRLF 兜底 + 可执行位（Windows 检出可能带 CRLF，shebang 会挂） ===
RUN sed -i 's/\r$//' \
        /usr/local/lib/chatop/gui-install.sh /usr/local/lib/chatop/gui-uninstall.sh \
        /usr/local/bin/start-app-manager.sh /usr/local/bin/chatop-run-cli \
        /usr/local/bin/chatop-seed-home.sh /usr/local/bin/start-caddy.sh \
        /usr/local/bin/start-filebrowser.sh /usr/local/bin/set-wallpaper.sh \
        /etc/caddy/Caddyfile && \
    chmod +x /usr/local/lib/chatop/gui-install.sh /usr/local/lib/chatop/gui-uninstall.sh \
        /usr/local/bin/start-app-manager.sh /usr/local/bin/chatop-run-cli \
        /usr/local/bin/chatop-seed-home.sh /usr/local/bin/start-caddy.sh \
        /usr/local/bin/set-wallpaper.sh

# === filebrowser 启动脚本(幂等 authoritative 覆盖：noauth + db 放 /tmp) ===
RUN printf '%s\n' \
  '#!/usr/bin/env bash' \
  'set -e' \
  'ROOT="${FB_ROOT:-$HOME}"; PORT="${FB_PORT:-8585}"; DB="/tmp/filebrowser.db"' \
  'rm -f "$DB"' \
  'exec filebrowser --noauth -d "$DB" -r "$ROOT" -b /files -a 127.0.0.1 -p "$PORT"' \
  > /usr/local/bin/start-filebrowser.sh && chmod +x /usr/local/bin/start-filebrowser.sh

# === custom_startup（常驻，末尾 wait；否则被 KASM_PROCS 判死无限重启拖垮 VNC） ===
RUN printf '#!/bin/bash\nexport KASM_BASIC="$(echo -n "${LOGIN_USER:-admin}:${FILES_PW:-${VNC_PW:-password}}" | base64 -w0)"\n/usr/local/bin/chatop-seed-home.sh >/tmp/seed.log 2>&1\n/usr/local/bin/start-filebrowser.sh >/tmp/filebrowser.log 2>&1 &\nXDG_DATA_HOME=/tmp/caddy XDG_CONFIG_HOME=/tmp/caddy /usr/local/bin/start-caddy.sh >/tmp/caddy.log 2>&1 &\n/usr/local/bin/start-app-manager.sh >/tmp/app-mgr.log 2>&1 &\n/usr/local/bin/set-wallpaper.sh >/tmp/set-wallpaper.log 2>&1 &\nmkdir -p $HOME/.local/bin; ln -sf /usr/local/bin/proot /usr/local/bin/jq /usr/local/bin/ncat /usr/local/bin/proot-apps $HOME/.local/bin/ 2>/dev/null\nwait\n' > /dockerstartup/custom_startup.sh && \
    chmod +x /dockerstartup/custom_startup.sh

# === 注入定制前端 dist（放最后：前端迭代只重跑这层）+ 品牌图标/splash 覆盖 ===
COPY --from=web --chown=root:root /src/dist/ /usr/share/kasmvnc/www/
COPY assets/logo-sm.png /usr/share/kasmvnc/www/app-icons/chatop-logo.png
COPY app-manager/apps-icon.svg /usr/share/kasmvnc/www/app-icons/apps.svg
COPY assets/background-splash.jpg /usr/share/kasmvnc/www/app/images/splash.jpg

# 恢复运行用户 uid 1000
USER 1000
