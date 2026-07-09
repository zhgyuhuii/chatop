# syntax=docker/dockerfile:1.7
# ============================================================================
# chatop-ai 单一 Dockerfile（多阶段）
#   历史：2026-07-04 曾拆成 Dockerfile.base + 产品 Dockerfile；因双镜像盘面 footprint
#   翻倍，2026-07-07 合并回单文件。重/联网/固定层在前(分层缓存稳定、迭代不重下)，
#   快变 COPY 层在后。详见 docs/superpowers/specs/2026-07-07-merge-single-dockerfile-design.md
# ============================================================================

# 前端构建（改前端只重跑此 stage）
FROM node:20-alpine AS web
WORKDIR /src
COPY novnc-src/ ./
RUN --mount=type=cache,target=/root/.npm npm install && npm run build

# 工位大屏前端（改 dashboard-web 只重跑此 stage）
FROM node:20-alpine AS dashweb
WORKDIR /src
COPY dashboard-web/ ./
RUN --mount=type=cache,target=/root/.npm npm install && npm run build

# ============================================================================
# 运行镜像
# ============================================================================
FROM kasmweb/core-ubuntu-jammy:1.19.0
ARG VERSION=1.2.0
LABEL maintainer="chatop-ai" build_version="chatop-ai ${VERSION}"
USER root

# === filebrowser 二进制（KasmVNC 开源版无文件传输） ===
ARG FB_ARCH=linux-amd64
RUN set -eux; \
    curl -fsSL --retry 5 --retry-delay 3 --retry-all-errors --connect-timeout 30 -o /tmp/fb.tar.gz "https://github.com/filebrowser/filebrowser/releases/latest/download/${FB_ARCH}-filebrowser.tar.gz"; \
    tar -xzf /tmp/fb.tar.gz -C /usr/local/bin filebrowser; \
    rm -f /tmp/fb.tar.gz; \
    chmod +x /usr/local/bin/filebrowser; \
    /usr/local/bin/filebrowser version

# === Caddy 二进制（单端口反代 KasmVNC + filebrowser） ===
ARG CADDY_VERSION=2.11.4
RUN set -eux; \
    curl -fsSL --retry 5 --retry-delay 3 --retry-all-errors --connect-timeout 30 -o /tmp/caddy.tar.gz "https://github.com/caddyserver/caddy/releases/download/v${CADDY_VERSION}/caddy_${CADDY_VERSION}_linux_amd64.tar.gz"; \
    tar -xzf /tmp/caddy.tar.gz -C /usr/local/bin caddy; \
    rm -f /tmp/caddy.tar.gz; \
    chmod +x /usr/local/bin/caddy; \
    /usr/local/bin/caddy version
ENV XDG_DATA_HOME=/tmp/caddy XDG_CONFIG_HOME=/tmp/caddy

# === CJK 字体（中文渲染前提） ===
RUN apt-get update && apt-get install -y --no-install-recommends \
      fonts-noto-cjk fonts-noto-color-emoji \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

# === Node 22 + pipx（npm 类 AI 工具前提；pipx 供市场版 aider/nanobot/sovyx 运行时装） ===
RUN set -eux; \
    curl -fsSL --retry 5 --retry-delay 3 --retry-all-errors --connect-timeout 30 https://deb.nodesource.com/setup_22.x | bash -; \
    apt-get install -y --no-install-recommends nodejs; \
    node -v; npm -v; \
    apt-get install -y --no-install-recommends pipx; \
    apt-get clean; rm -rf /var/lib/apt/lists/*

# === 用户级 npm 前缀 + PATH（登录 shell 与交互 shell 都加载） ===
RUN set -eux; \
    printf '\n# chatop app-manager user-level tooling\nexport NPM_CONFIG_PREFIX="$HOME/.npm-global"\nexport PATH="$HOME/.npm-global/bin:$HOME/.local/bin:$PATH"\n' \
      > /etc/profile.d/chatop-apps.sh; \
    chmod +x /etc/profile.d/chatop-apps.sh; \
    printf '\n# chatop: 交互式(非登录)终端也加载用户级工具 PATH(桌面终端走这条;profile.d 只对登录 shell 生效)\n[ -f /etc/profile.d/chatop-apps.sh ] && . /etc/profile.d/chatop-apps.sh\n' \
      >> /etc/bash.bashrc

# === vnc_startup 登录名 + 剪贴板补丁 ===
RUN sed -i 's/-u kasm_user -wo/-u "${LOGIN_USER:-admin}" -wo/' /dockerstartup/vnc_startup.sh && \
    sed -i 's/kasm_user:\$VNC_PW/${LOGIN_USER:-admin}:\$VNC_PW/g' /dockerstartup/vnc_startup.sh && \
    sed -i '/^APP_NAME=/a if [ "${CLIPBOARD_OUT:-1}" = "0" ]; then export KASM_SVC_SEND_CUT_TEXT="-SendCutText=0"; else export KASM_SVC_SEND_CUT_TEXT="-SendCutText=1"; fi; if [ "${CLIPBOARD_IN:-1}" = "0" ]; then export KASM_SVC_ACCEPT_CUT_TEXT="-AcceptCutText=0"; else export KASM_SVC_ACCEPT_CUT_TEXT="-AcceptCutText=1"; fi' /dockerstartup/vnc_startup.sh && \
    echo "=== patched login-user + clipboard lines ===" && grep -nE 'LOGIN_USER|kasm_user|CLIPBOARD|CUT_TEXT' /dockerstartup/vnc_startup.sh
ENV LOGIN_USER=admin

# === Python 3.11（Sovyx 需 >=3.11；deadsnakes PPA）。加完 PPA 即 purge software-properties-common(纯构建期工具) ===
RUN apt-get update && apt-get install -y --no-install-recommends software-properties-common && \
    add-apt-repository -y ppa:deadsnakes/ppa && apt-get update && \
    apt-get install -y --no-install-recommends python3.11 python3.11-venv python3.11-distutils && \
    python3.11 --version && \
    apt-get purge -y software-properties-common && apt-get autoremove -y --purge && \
    apt-get clean && rm -rf /var/lib/apt/lists/*

# === station 运行环境（工位大屏常驻服务 venv；产品层只 COPY 源码保持离线）。国内优先阿里源，失败回退官方 ===
RUN python3.11 -m venv /opt/station-venv && \
    ( /opt/station-venv/bin/pip install --no-cache-dir -i https://mirrors.aliyun.com/pypi/simple/ \
        'fastapi>=0.110,<1' 'uvicorn>=0.30,<1' 'psutil>=5.9' || \
      /opt/station-venv/bin/pip install --no-cache-dir \
        'fastapi>=0.110,<1' 'uvicorn>=0.30,<1' 'psutil>=5.9' ) && \
    /opt/station-venv/bin/python -c "import fastapi, uvicorn, psutil"

# === 系统中文化：locale + 语言包 ===
RUN apt-get update && apt-get install -y --no-install-recommends \
      locales language-pack-zh-hans language-pack-gnome-zh-hans \
    && locale-gen zh_CN.UTF-8 \
    && update-locale LANG=zh_CN.UTF-8 LANGUAGE=zh_CN:zh \
    && apt-get clean && rm -rf /var/lib/apt/lists/*
ENV LANG=zh_CN.UTF-8 LANGUAGE=zh_CN:zh LC_ALL=zh_CN.UTF-8

# === Google Chrome（Web 智能体载体；容器内加 --no-sandbox） ===
RUN set -eux; \
    apt-get update; \
    curl -fsSL --retry 5 --retry-delay 3 --retry-all-errors --connect-timeout 30 -o /tmp/chrome.deb https://dl.google.com/linux/direct/google-chrome-stable_current_amd64.deb; \
    apt-get install -y --no-install-recommends /tmp/chrome.deb; \
    rm -f /tmp/chrome.deb; \
    sed -i 's#^Exec=/usr/bin/google-chrome-stable#Exec=/usr/bin/google-chrome-stable --no-sandbox --start-maximized#' \
        /usr/share/applications/google-chrome.desktop; \
    /usr/bin/google-chrome-stable --version; \
    : '--- 任务栏浏览器图标走 XFCE helper(exo-open --launch WebBrowser)→ %B=PATH 里的裸 google-chrome，' ; \
    : '    不带 --no-sandbox 会沙箱崩溃。故在 /usr/local/bin(PATH 优先于 /usr/bin)放 wrapper 强制加 flag，' ; \
    : '    覆盖任务栏/xdg-open/任何 PATH 启动路径。---' ; \
    printf '#!/bin/bash\nexec /opt/google/chrome/google-chrome --no-sandbox --start-maximized "$@"\n' \
        > /usr/local/bin/google-chrome-stable; \
    cp /usr/local/bin/google-chrome-stable /usr/local/bin/google-chrome; \
    chmod +x /usr/local/bin/google-chrome-stable /usr/local/bin/google-chrome; \
    : '--- 系统级默认浏览器：XFCE 首选应用(helpers.rc，fresh 开机读 /etc/xdg 回退) + xdg mime 默认 ---' ; \
    sed -i 's/^WebBrowser=.*/WebBrowser=google-chrome/' /etc/xdg/xfce4/helpers.rc; \
    printf '[Default Applications]\nx-scheme-handler/http=google-chrome.desktop\nx-scheme-handler/https=google-chrome.desktop\ntext/html=google-chrome.desktop\nx-scheme-handler/about=google-chrome.desktop\n' \
        > /etc/xdg/mimeapps.list; \
    apt-get clean; rm -rf /var/lib/apt/lists/*

# === proot-apps（userspace PRoot GUI 应用安装器） ===
# releases/latest/download 直链（同 filebrowser 步骤），免 api.github.com 查 tag（匿名限流 60/h 会 403）。
# 直连被阻断时依次回退 GitHub 加速镜像；置空 GH_MIRRORS 可禁用回退（走代理时传 --build-arg GH_MIRRORS=）。
ARG GH_MIRRORS="https://ghfast.top/ https://gh-proxy.com/"
RUN set -eux; mkdir -p /tmp/pa; \
    url="https://github.com/linuxserver/proot-apps/releases/latest/download/proot-apps-x86_64.tar.gz"; \
    ok=""; \
    for prefix in "" $GH_MIRRORS; do \
      if curl -fL --retry 2 --retry-delay 3 --retry-all-errors --connect-timeout 20 -o /tmp/pa.tar.gz "${prefix}${url}"; then ok=1; break; fi; \
      echo "[WARN] fetch via [${prefix:-direct}] failed, trying next source"; \
    done; \
    [ -n "$ok" ]; \
    tar -xzf /tmp/pa.tar.gz -C /tmp/pa/; \
    install -m755 /tmp/pa/proot-apps /tmp/pa/proot /tmp/pa/jq /tmp/pa/ncat /usr/local/bin/; \
    rm -rf /tmp/pa /tmp/pa.tar.gz

# === 用户改名 kasm-user → ${APP_USER} + home 实体迁移 ===
ARG APP_USER=admin
RUN if [ "$APP_USER" != "kasm-user" ]; then \
      usermod  -l "$APP_USER" -d "/home/$APP_USER" -m -s /bin/bash kasm-user && \
      groupmod -n "$APP_USER" kasm-user && \
      sed -i "s#/home/kasm-user#/home/$APP_USER#g" \
          /dockerstartup/vnc_startup.sh \
          /dockerstartup/kasm_pre_shutdown_user.sh \
          /etc/cups/cups-pdf.conf && \
      ! test -e /home/kasm-user ; \
    fi
WORKDIR /home/${APP_USER}
ENV HOME=/home/${APP_USER}
RUN mkdir -p /opt/chatop && \
    mv /home/kasm-default-profile /opt/chatop/default-profile && \
    sed -i 's#/home/kasm-default-profile#/opt/chatop/default-profile#' /dockerstartup/kasm_default_profile.sh && \
    ! test -e /home/kasm-default-profile && ! test -e /home/kasm-user
ENV XDG_CONFIG_HOME=/tmp/caddy XDG_DATA_HOME=${HOME}/.local/share
ENV NPM_CONFIG_PREFIX=${HOME}/.npm-global PATH=${HOME}/.npm-global/bin:${HOME}/.local/bin:${PATH}

# === 核心智能体预装(AI CLI：claude/codex/openclaw/tokscale/rtk；
#     OpenClaw 配置用 openclaw-tool(见产品层)；PREINSTALL_HEAVY=1 追加 Hermes) → 迁 seed-home，运行时播种回卷 ===
RUN mkdir -p /usr/local/lib/chatop /etc/chatop
COPY app-manager/chatop-preinstall.sh /usr/local/lib/chatop/chatop-preinstall.sh
COPY app-manager/gui-install.sh /usr/local/lib/chatop/gui-install.sh
RUN sed -i 's/\r$//' /usr/local/lib/chatop/chatop-preinstall.sh /usr/local/lib/chatop/gui-install.sh && \
    chmod +x /usr/local/lib/chatop/chatop-preinstall.sh /usr/local/lib/chatop/gui-install.sh
ARG PREINSTALL_HEAVY=1
# OpenHuman 默认不预装(解包 ~1.3GB，走应用市场按需装)；WPS 从不预装(proot-apps 市场应用)
ARG PREINSTALL_OPENHUMAN=0
RUN su admin -c "PREINSTALL_HEAVY=${PREINSTALL_HEAVY} PREINSTALL_OPENHUMAN=${PREINSTALL_OPENHUMAN} bash /usr/local/lib/chatop/chatop-preinstall.sh" && \
    mv /home/admin /opt/chatop-seed-home && \
    mkdir -p /home/admin && chown admin:admin /home/admin && chmod 755 /home/admin && \
    ! test -e /home/kasm-user

# ============================================================================
# 快变产品层（改这些才重打，且不联网）
# ============================================================================

# === OpenClaw 可视化配置器（openclaw-tool，tkinter）===
# python3-tk 是 GUI 运行前提；置于产品层顶（首次装好后缓存命中，不冲上方重层，也不联网重下 Chrome）
RUN apt-get update && apt-get install -y --no-install-recommends python3-tk \
    && apt-get clean && rm -rf /var/lib/apt/lists/*
COPY openclaw-tool /opt/openclaw-tool
RUN chmod +x /opt/openclaw-tool/*.sh 2>/dev/null || true

# 构建期烤入 openclaw 目录快照：GUI 启动只读此文件，**永不在启动路径调 CLI**
# （openclaw CLI 每次 8~12s 且无热缓存，挂在启动路径上会让配置器打不开）。
# 注意 openclaw 此时在 /opt/chatop-seed-home/.npm-global（上一层已 mv 走 /home/admin）。
# 采集失败**不阻断构建**：运行时自动降级到静态兜底，镜像永远能出。
RUN mkdir -p /usr/share/chatop && \
    ( cd /opt/openclaw-tool && \
      HOME=/opt/chatop-seed-home \
      PATH=/opt/chatop-seed-home/.npm-global/bin:$PATH \
      python3 -m openclaw_catalog --snapshot --out /usr/share/chatop/openclaw-catalog.json \
        --bin /opt/chatop-seed-home/.npm-global/bin/openclaw && \
      python3 -c "import json,sys; d=json.load(open('/usr/share/chatop/openclaw-catalog.json')); \
        n=len(d['channels']); assert n >= 20, n; \
        print('openclaw catalog snapshot OK: %s, %d channels' % (d['meta']['openclaw_version'], n))" \
    ) || echo "WARN: openclaw catalog 快照失败，运行时将降级到静态兜底"

# === app-manager：后端 + catalog + 图标 + 启动脚本 + GUI/CLI 脚本 + 播种脚本 ===
COPY app-manager/app_manager.py /usr/local/lib/chatop/app_manager.py
COPY app-manager/apps-catalog.json /etc/chatop/apps-catalog.json
COPY app-manager/icons/ /usr/share/kasmvnc/www/app-icons/
COPY app-manager/start-app-manager.sh /usr/local/bin/start-app-manager.sh
COPY app-manager/gui-uninstall.sh /usr/local/lib/chatop/gui-uninstall.sh
COPY app-manager/chatop-run-cli.sh /usr/local/bin/chatop-run-cli
COPY app-manager/chatop-seed-home.sh /usr/local/bin/chatop-seed-home.sh

# === 内置智能体：桌面图标 + 智能启动入口（双击=未配置先配置/已配置直接跑） ===
# 智能启动脚本（判据同 station AGENT_SPECS）；图标放系统路径供 .desktop 的 Icon= 绝对引用
COPY app-manager/chatop-agent-launch.sh /usr/local/bin/chatop-agent-launch
COPY app-manager/icons/ /usr/share/chatop/agent-icons/
# 为每个内置智能体 + 监控大屏生成 .desktop（写入 seed-home，运行时播种到用户卷；官方图标 Icon= 系统绝对路径）
RUN set -eux; \
    APPS=/opt/chatop-seed-home/.local/share/applications; DESK=/opt/chatop-seed-home/Desktop; \
    ICONS=/usr/share/chatop/agent-icons; mkdir -p "$APPS" "$DESK"; \
    gen() { \
      f="$APPS/chatop-$1.desktop"; \
      printf '[Desktop Entry]\nType=Application\nVersion=1.0\nName=%s\nComment=%s\nExec=%s\nIcon=%s/%s\nTerminal=false\nCategories=Development;\nStartupNotify=true\n' \
        "$2" "$2" "$4" "$ICONS" "$3" > "$f"; \
      chmod +x "$f"; cp -f "$f" "$DESK/chatop-$1.desktop"; \
    }; \
    gen claude-code   "Claude Code"      claude-code.png       "chatop-agent-launch claude-code"; \
    gen codex         "Codex"            codex.png             "chatop-agent-launch codex"; \
    gen openclaw      "OpenClaw"         openclaw.png          "chatop-agent-launch openclaw"; \
    gen hermes        "Hermes Agent"     hermes.png            "chatop-agent-launch hermes"; \
    gen rtk           "RTK 省Token"      rtk.png               "chatop-agent-launch rtk"; \
    gen tokscale      "tokscale 用量监控" tokscale.png          "chatop-agent-launch tokscale"; \
    gen dashboard     "智能体监控大屏"    dashboard-monitor.png "/usr/local/bin/start-dashboard-window.sh"; \
    cp -f "/opt/openclaw-tool/OpenClaw配置.desktop" "$APPS/chatop-openclaw-config.desktop"; \
    chmod +x "$APPS/chatop-openclaw-config.desktop"; \
    cp -f "$APPS/chatop-openclaw-config.desktop" "$DESK/chatop-openclaw-config.desktop"; \
    chown -R 1000:1000 /opt/chatop-seed-home/.local /opt/chatop-seed-home/Desktop

# === station：工位本地大屏常驻服务（venv 已在上方；此处离线只 COPY） ===
# 供 station 心跳上报真实版本；置于产品层，避免打穿上方重层缓存
ENV CHATOP_VERSION=${VERSION}
COPY station/station/ /opt/station/station/
COPY station/start-station.sh /usr/local/bin/start-station.sh
COPY --from=dashweb /src/dist/ /opt/station/station/web/
RUN sed -i 's/\r$//' /usr/local/bin/start-station.sh && chmod +x /usr/local/bin/start-station.sh && \
    mkdir -p /opt/chatop-seed-home/.config/autostart && \
    printf '[Desktop Entry]\nType=Application\nName=察元AI工舱 大屏\nComment=工位监控大屏\nExec=/usr/local/bin/start-dashboard-window.sh\nIcon=utilities-system-monitor\nX-GNOME-Autostart-enabled=true\n' \
      > /opt/chatop-seed-home/.config/autostart/chatop-dashboard.desktop && \
    printf '#!/bin/bash\nfor i in $(seq 1 60); do curl -fsS http://127.0.0.1:8787/dashboard/api/system >/dev/null 2>&1 && break; sleep 1; done\nexec /usr/bin/google-chrome-stable --no-sandbox --app=http://127.0.0.1:8787/dashboard --start-fullscreen --no-first-run\n' \
      > /usr/local/bin/start-dashboard-window.sh && \
    chmod +x /usr/local/bin/start-dashboard-window.sh && \
    chown -R 1000:1000 /opt/chatop-seed-home/.config

# === Caddy 反代配置 + 启动脚本；filebrowser 启动脚本 ===
COPY caddy/Caddyfile /etc/caddy/Caddyfile
COPY caddy/start-caddy.sh /usr/local/bin/start-caddy.sh
COPY filebrowser/start-filebrowser.sh /usr/local/bin/start-filebrowser.sh

# === 品牌资源 + KasmVNC 剪贴板配置 ===
COPY assets/background.png /usr/share/backgrounds/chayuanai/wallpaper.png
COPY assets/background.png /usr/share/backgrounds/bg_default.png
COPY assets/set-wallpaper.sh /usr/local/bin/set-wallpaper.sh
# 源文件已白标为 chatop-vnc.yaml；目标 /etc/kasmvnc/kasmvnc.yaml 是 KasmVNC 写死读取路径，保持不动
COPY chatop-vnc.yaml /etc/kasmvnc/kasmvnc.yaml

# === CRLF 兜底 + 可执行位（Windows 检出可能带 CRLF，shebang 会挂） ===
RUN sed -i 's/\r$//' \
        /usr/local/lib/chatop/gui-install.sh /usr/local/lib/chatop/gui-uninstall.sh \
        /usr/local/bin/start-app-manager.sh /usr/local/bin/chatop-run-cli \
        /usr/local/bin/chatop-seed-home.sh /usr/local/bin/start-caddy.sh \
        /usr/local/bin/start-filebrowser.sh /usr/local/bin/set-wallpaper.sh \
        /usr/local/bin/chatop-agent-launch \
        /etc/caddy/Caddyfile && \
    chmod +x /usr/local/lib/chatop/gui-install.sh /usr/local/lib/chatop/gui-uninstall.sh \
        /usr/local/bin/start-app-manager.sh /usr/local/bin/chatop-run-cli \
        /usr/local/bin/chatop-seed-home.sh /usr/local/bin/start-caddy.sh \
        /usr/local/bin/start-filebrowser.sh /usr/local/bin/set-wallpaper.sh \
        /usr/local/bin/chatop-agent-launch

# === filebrowser 启动脚本(幂等 authoritative 覆盖：noauth + db 放 /tmp) ===
RUN printf '%s\n' \
  '#!/usr/bin/env bash' \
  'set -e' \
  'ROOT="${FB_ROOT:-$HOME}"; PORT="${FB_PORT:-8585}"; DB="/tmp/filebrowser.db"' \
  'rm -f "$DB"' \
  'exec filebrowser --noauth -d "$DB" -r "$ROOT" -b /files -a 127.0.0.1 -p "$PORT"' \
  > /usr/local/bin/start-filebrowser.sh && chmod +x /usr/local/bin/start-filebrowser.sh

# === custom_startup（常驻，末尾 wait；否则被 KASM_PROCS 判死无限重启拖垮 VNC） ===
RUN printf '#!/bin/bash\nexport KASM_BASIC="$(echo -n "${LOGIN_USER:-admin}:${FILES_PW:-${VNC_PW:-password}}" | base64 -w0)"\n/usr/local/bin/chatop-seed-home.sh >/tmp/seed.log 2>&1\n/usr/local/bin/start-filebrowser.sh >/tmp/filebrowser.log 2>&1 &\nXDG_DATA_HOME=/tmp/caddy XDG_CONFIG_HOME=/tmp/caddy /usr/local/bin/start-caddy.sh >/tmp/caddy.log 2>&1 &\n/usr/local/bin/start-app-manager.sh >/tmp/app-mgr.log 2>&1 &\n/usr/local/bin/start-station.sh >/tmp/station.log 2>&1 &\n/usr/local/bin/set-wallpaper.sh >/tmp/set-wallpaper.log 2>&1 &\nmkdir -p $HOME/.local/bin; ln -sf /usr/local/bin/proot /usr/local/bin/jq /usr/local/bin/ncat /usr/local/bin/proot-apps $HOME/.local/bin/ 2>/dev/null\nwait\n' > /dockerstartup/custom_startup.sh && \
    chmod +x /dockerstartup/custom_startup.sh

# === 注入定制前端 dist（放最后：前端迭代只重跑这层）+ 品牌图标/splash 覆盖 ===
COPY --from=web --chown=root:root /src/dist/ /usr/share/kasmvnc/www/
COPY assets/logo-sm.png /usr/share/kasmvnc/www/app-icons/chatop-logo.png
COPY assets/follow-qr.jpg /usr/share/kasmvnc/www/app-icons/follow-qr.jpg
COPY app-manager/apps-icon.svg /usr/share/kasmvnc/www/app-icons/apps.svg
COPY assets/background-splash.jpg /usr/share/kasmvnc/www/app/images/splash.jpg

# 构建期可能建出 root 属主 /tmp/caddy，运行时 uid 1000 写不进，删掉让运行时重建
RUN rm -rf /tmp/caddy

# 恢复运行用户 uid 1000
USER 1000
