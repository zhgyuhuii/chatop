# syntax=docker/dockerfile:1.7
FROM node:20-alpine AS web
WORKDIR /src
COPY novnc-src/ ./
RUN --mount=type=cache,target=/root/.npm npm install && npm run build

# 精简 base：用 core(只含 XFCE + KasmVNC + 音频 + 文件传输，无任何 GUI 应用)而非
# desktop(= core + 一堆内置 GUI 应用)。省去"装完再卸载内置应用"(apt purge 只加白障层、
# 镜像反而更大)的整段无用功。镜像 12.4G → ~3G。
# 版本必须用 1.19：本项目原 base 即 desktop:1.19.0，Dockerfile/kasmvnc.yaml/vnc_startup 补丁
# 都按 1.19 写的。1.14 太老(差 ~2 年)不认 kasmvnc.yaml 里的
# server.allow_environment_variables_to_override_config_settings，会崩溃重启。
FROM kasmweb/core-ubuntu-jammy:1.19.0
ARG VERSION=1.1.0
LABEL maintainer="chatop-ai" build_version="chatop-ai ${VERSION}"
# 注：前端注入(COPY --from=web)与资源层移至 Dockerfile 末尾，置于 WPS/字体等重型下载层之后，
# 使前端 UI 迭代只重跑最后一层，不再触发 WPS(319MB) 等重新下载。

# === filebrowser 旁挂（文件上传/下载，KasmVNC 开源版无文件传输） ===
# 装 filebrowser 需 root 写 /usr/local/bin 与 /dockerstartup；装完恢复运行用户 1000(kasm-user)
USER root
# 直接拉官方 release 二进制（get.sh 在内部 404 时仍 exit 0，会跳过 || 兜底，故不再用它）。
# 装完显式校验二进制存在且可执行，缺失则让构建当场失败，避免产出无文件传输能力的坏镜像。
ARG FB_ARCH=linux-amd64
RUN set -eux; \
    curl -fsSL -o /tmp/fb.tar.gz "https://github.com/filebrowser/filebrowser/releases/latest/download/${FB_ARCH}-filebrowser.tar.gz"; \
    tar -xzf /tmp/fb.tar.gz -C /usr/local/bin filebrowser; \
    rm -f /tmp/fb.tar.gz; \
    chmod +x /usr/local/bin/filebrowser; \
    /usr/local/bin/filebrowser version
COPY filebrowser/start-filebrowser.sh /usr/local/bin/start-filebrowser.sh

# === Caddy 反向代理（单端口收口：KasmVNC + filebrowser → 一个对外端口/证书） ===
# 官方 GitHub release 静态二进制（caddyserver.com/api/download 在该环境会挂起，
# 改用 release tarball；与 filebrowser 同走 GitHub，实测秒级可达）。
ARG CADDY_VERSION=2.11.4
RUN set -eux; \
    curl -fsSL -o /tmp/caddy.tar.gz "https://github.com/caddyserver/caddy/releases/download/v${CADDY_VERSION}/caddy_${CADDY_VERSION}_linux_amd64.tar.gz"; \
    tar -xzf /tmp/caddy.tar.gz -C /usr/local/bin caddy; \
    rm -f /tmp/caddy.tar.gz; \
    chmod +x /usr/local/bin/caddy; \
    /usr/local/bin/caddy version
COPY caddy/Caddyfile /etc/caddy/Caddyfile
COPY caddy/start-caddy.sh /usr/local/bin/start-caddy.sh
# Caddy 以 uid 1000 运行：data/config 写到 /tmp 下可写目录
ENV XDG_DATA_HOME=/tmp/caddy XDG_CONFIG_HOME=/tmp/caddy

RUN mkdir -p /dockerstartup && \
    chmod +x /usr/local/bin/start-filebrowser.sh /usr/local/bin/start-caddy.sh && \
    printf '#!/bin/bash\n/usr/local/bin/start-filebrowser.sh >/tmp/filebrowser.log 2>&1 &\n/usr/local/bin/start-caddy.sh >/tmp/caddy.log 2>&1 &\n' > /dockerstartup/custom_startup.sh && \
    chmod +x /dockerstartup/custom_startup.sh

# ================== S7：定制桌面内置软件 ==================
# === 桌面基本无内置应用 ===
# core base 不含任何内置 GUI 应用；本镜像也不预装 WPS/fcitx 等。唯一刻意预装的 GUI 应用是
# Google Chrome（openclaw/Hermes 等 Web 智能体的运行载体，见下）。其余一切走应用市场按需装。
# CJK 字体是中文「渲染」前提(不是应用)，否则桌面/文件名/察元AI 全是豆腐块。
USER root
RUN apt-get update && apt-get install -y --no-install-recommends \
      fonts-noto-cjk fonts-noto-color-emoji \
    && apt-get clean && rm -rf /var/lib/apt/lists/*
# 注：系统中文化(locale/语言包)与 Google Chrome 预装层刻意放在 python3.11 之后、app-manager
# 之前（见下方），让 node/python3.11 等重型层保持缓存命中、不被这两个新层挤掉重建。

# === 应用管理器基础：Node 22（npm 类 AI 工具前提）+ pipx ===
RUN set -eux; \
    curl -fsSL https://deb.nodesource.com/setup_22.x | bash -; \
    apt-get install -y --no-install-recommends nodejs; \
    node -v; npm -v; \
    apt-get install -y --no-install-recommends pipx; \
    rm -rf /var/lib/apt/lists/*

# npm 用户级全局前缀（装到家目录 → home 数据卷持久），并把 ~/.npm-global/bin、~/.local/bin 入 PATH
RUN set -eux; \
    printf '\n# chatop app-manager user-level tooling\nexport NPM_CONFIG_PREFIX="$HOME/.npm-global"\nexport PATH="$HOME/.npm-global/bin:$HOME/.local/bin:$PATH"\n' \
      > /etc/profile.d/chatop-apps.sh; \
    chmod +x /etc/profile.d/chatop-apps.sh; \
    printf '\n# chatop: 交互式(非登录)终端也加载用户级工具 PATH(桌面终端走这条;profile.d 只对登录 shell 生效)\n[ -f /etc/profile.d/chatop-apps.sh ] && . /etc/profile.d/chatop-apps.sh\n' \
      >> /etc/bash.bashrc

USER root
# 登录名可配：把 vnc_startup.sh 里硬编码的 kasm_user(仅这两类:kasmvncpasswd -u 和 辅助服务 auth-token)
# 改为运行时变量 ${LOGIN_USER:-admin};绝不动 kasm_user_name / kasm_viewer / KASM_USER
RUN sed -i 's/-u kasm_user -wo/-u "${LOGIN_USER:-admin}" -wo/' /dockerstartup/vnc_startup.sh && \
    sed -i 's/kasm_user:\$VNC_PW/${LOGIN_USER:-admin}:\$VNC_PW/g' /dockerstartup/vnc_startup.sh && \
    sed -i '/^APP_NAME=/a if [ "${CLIPBOARD_OUT:-1}" = "0" ]; then export KASM_SVC_SEND_CUT_TEXT="-SendCutText=0"; else export KASM_SVC_SEND_CUT_TEXT="-SendCutText=1"; fi; if [ "${CLIPBOARD_IN:-1}" = "0" ]; then export KASM_SVC_ACCEPT_CUT_TEXT="-AcceptCutText=0"; else export KASM_SVC_ACCEPT_CUT_TEXT="-AcceptCutText=1"; fi' /dockerstartup/vnc_startup.sh && \
    echo "=== patched login-user + clipboard lines ===" && grep -nE 'LOGIN_USER|kasm_user|CLIPBOARD|CUT_TEXT' /dockerstartup/vnc_startup.sh
ENV LOGIN_USER=admin

# ============ 轻量资源层（置于重型下载层之后，便于前端/资源快速迭代）============
# 修复：custom_startup 必须常驻(末尾 wait)。kasm vnc_startup 把它当 service 监控(KASM_PROCS)，
# 一次性脚本退出后会被监控循环判定为"死亡"并无限重启，日志狂刷 "Unknown Service: custom_startup"
# + "kill (137) No such process"，高频循环拖累 VNC bridge->relay 导致连不上。wait 让脚本常驻即解决。
RUN printf '#!/bin/bash\nexport FILES_HASH="$(/usr/local/bin/caddy hash-password --plaintext "${FILES_PW:-${VNC_PW:-password}}" 2>/dev/null)"\n/usr/local/bin/start-filebrowser.sh >/tmp/filebrowser.log 2>&1 &\n/usr/local/bin/start-caddy.sh >/tmp/caddy.log 2>&1 &\n/usr/local/bin/start-app-manager.sh >/tmp/app-mgr.log 2>&1 &\nwait\n' > /dockerstartup/custom_startup.sh && \
    chmod +x /dockerstartup/custom_startup.sh
# 应用管理器二期：Python 3.11（Sovyx 需 >=3.11；deadsnakes PPA）
RUN apt-get update && apt-get install -y --no-install-recommends software-properties-common && \
    add-apt-repository -y ppa:deadsnakes/ppa && apt-get update && \
    apt-get install -y --no-install-recommends python3.11 python3.11-venv python3.11-distutils && \
    python3.11 --version && rm -rf /var/lib/apt/lists/*

# === 系统中文化：locale + 中文语言包 + LANG（XFCE 菜单/Thunar/右键/对话框显示中文）===
# 参考 Ubuntu 官方：装 language-pack-zh-hans(+gnome 覆盖 GTK 应用翻译)，locale-gen 生成
# zh_CN.UTF-8，update-locale 写 /etc/default/locale，再用 ENV LANG 让 KasmVNC 会话继承。
# 放此处(python3.11 之后)是为保住上方 node/python 重型层缓存。
RUN apt-get update && apt-get install -y --no-install-recommends \
      locales language-pack-zh-hans language-pack-gnome-zh-hans \
    && locale-gen zh_CN.UTF-8 \
    && update-locale LANG=zh_CN.UTF-8 LANGUAGE=zh_CN:zh \
    && apt-get clean && rm -rf /var/lib/apt/lists/*
ENV LANG=zh_CN.UTF-8 LANGUAGE=zh_CN:zh LC_ALL=zh_CN.UTF-8

# === 预装最新版 Google Chrome（openclaw / Hermes 等 Web 智能体的运行载体）===
# 用 Google 官方 _current_ 直链，始终拉最新 stable；apt 装本地 deb 自动解析依赖。
# 容器内无 user-namespace 沙箱权限，故给 .desktop 启动加 --no-sandbox，否则 Chrome 起不来。
RUN set -eux; \
    apt-get update; \
    curl -fsSL -o /tmp/chrome.deb https://dl.google.com/linux/direct/google-chrome-stable_current_amd64.deb; \
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

# === 应用管理器：后端 + catalog + 图标 + 启动脚本 ===
RUN mkdir -p /usr/local/lib/chatop /etc/chatop
COPY app-manager/app_manager.py /usr/local/lib/chatop/app_manager.py
COPY app-manager/apps-catalog.json /etc/chatop/apps-catalog.json
COPY app-manager/icons/ /usr/share/kasmvnc/www/app-icons/
COPY app-manager/start-app-manager.sh /usr/local/bin/start-app-manager.sh
# 应用管理器二期：GUI（AppImage）安装/卸载脚本
COPY app-manager/gui-install.sh app-manager/gui-uninstall.sh /usr/local/lib/chatop/
RUN chmod +x /usr/local/lib/chatop/gui-install.sh /usr/local/lib/chatop/gui-uninstall.sh
RUN chmod +x /usr/local/bin/start-app-manager.sh
# 末尾再次 COPY Caddyfile（覆盖前面层的旧版），使 Caddyfile 改动只重建末尾层、不触发 WPS 重下
COPY caddy/Caddyfile /etc/caddy/Caddyfile
# 注：原"删除内置应用桌面快捷方式"段已删除——core base 桌面本就没有这些 .desktop。
# 炫酷品牌桌面壁纸。放到独立的 chayuanai 目录作为真源；运行时由 set-wallpaper.sh
# 用 xfconf-query 强制设为 XFCE 桌面背景(monitorVNC-* 动态显示器不会自动加载磁盘
# xml，xfdesktop 会套内置默认 xfce-verticals.png，故必须运行时主动写入)。
COPY assets/background.png /usr/share/backgrounds/chayuanai/wallpaper.png
COPY assets/background.png /usr/share/backgrounds/bg_default.png
COPY assets/set-wallpaper.sh /usr/local/bin/set-wallpaper.sh
RUN chmod +x /usr/local/bin/set-wallpaper.sh
# 在末尾重新生成 custom_startup（追加 set-wallpaper 后台任务）。放末尾是为了不破坏
# 上方 python3.11 等重型层的构建缓存（改 custom_startup 不再触发 python3.11 重装）。
RUN printf '#!/bin/bash\nexport KASM_BASIC="$(echo -n "${LOGIN_USER:-admin}:${FILES_PW:-${VNC_PW:-password}}" | base64 -w0)"\n/usr/local/bin/start-filebrowser.sh >/tmp/filebrowser.log 2>&1 &\nXDG_DATA_HOME=/tmp/caddy XDG_CONFIG_HOME=/tmp/caddy /usr/local/bin/start-caddy.sh >/tmp/caddy.log 2>&1 &\n/usr/local/bin/start-app-manager.sh >/tmp/app-mgr.log 2>&1 &\n/usr/local/bin/set-wallpaper.sh >/tmp/set-wallpaper.log 2>&1 &\nmkdir -p $HOME/.local/bin; ln -sf /usr/local/bin/proot /usr/local/bin/jq /usr/local/bin/ncat /usr/local/bin/proot-apps $HOME/.local/bin/ 2>/dev/null\nwait\n' > /dockerstartup/custom_startup.sh && \
    chmod +x /dockerstartup/custom_startup.sh
# KasmVNC 剪贴板上/下行权限默认
COPY kasmvnc.yaml /etc/kasmvnc/kasmvnc.yaml
# 注入定制 noVNC 前端（放最后：前端迭代只重跑这一层，不影响上面重型层缓存）
COPY --from=web --chown=root:root /src/dist/ /usr/share/kasmvnc/www/
# 注入察元 logo（顶部品牌 + favicon + 连接等待页用）。用 256px 压缩版(51KB)而非
# 原图(1489px/783KB)：favicon 每个标签都拉、等待页首屏就显示，大图会明显拖慢加载。
COPY assets/logo-sm.png /usr/share/kasmvnc/www/app-icons/chatop-logo.png
# 应用管理按钮的网格图标（与其它控制栏按钮一致的图标+文字风格）
COPY app-manager/apps-icon.svg /usr/share/kasmvnc/www/app-icons/apps.svg
# noVNC 网页背景(splash)换成察元壁纸
COPY assets/background-splash.jpg /usr/share/kasmvnc/www/app/images/splash.jpg
# filebrowser 启动脚本(幂等)：改 noauth——filebrowser 强制密码复杂度(test12345 报 too easy)无法用弱 VNC_PW
# 做登录。改由前置 Caddy 对 /files 做 BasicAuth(同 VNC_PW)。db 放 /tmp(容器层，避开数据卷 bbolt flock 超时)。
RUN printf '%s\n' \
  '#!/usr/bin/env bash' \
  'set -e' \
  'ROOT="${FB_ROOT:-$HOME}"; PORT="${FB_PORT:-8585}"; DB="/tmp/filebrowser.db"' \
  'rm -f "$DB"' \
  'exec filebrowser --noauth -d "$DB" -r "$ROOT" -b /files -a 127.0.0.1 -p "$PORT"' \
  > /usr/local/bin/start-filebrowser.sh && chmod +x /usr/local/bin/start-filebrowser.sh

# proot-apps：linuxserver 的 userspace PRoot GUI 应用安装器（应用市场分类的 ~94 个应用按需
# 安装到用户目录、持久化、免 root）。工具装到 /usr/local/bin；脚本内部 hardcode
# $HOME/.local/bin/proot，故由 custom_startup 启动时 symlink 到用户目录。
RUN mkdir -p /tmp/pa && \
    PAPPS=$(curl -sX GET "https://api.github.com/repos/linuxserver/proot-apps/releases/latest" | awk '/tag_name/{print $4;exit}' FS='[""]') && \
    curl -L "https://github.com/linuxserver/proot-apps/releases/download/${PAPPS}/proot-apps-x86_64.tar.gz" | tar -xzf - -C /tmp/pa/ && \
    install -m755 /tmp/pa/proot-apps /tmp/pa/proot /tmp/pa/jq /tmp/pa/ncat /usr/local/bin/ && \
    rm -rf /tmp/pa

# === 自定义系统用户名（kasm-user → ${APP_USER}）===
# 让 home 目录、右上角面板、文件管理器都显示自定义名。做法（零数据迁移）：
#  - usermod -l 把 uid 1000 改名为 ${APP_USER}，whoami/$USER/右上角随之变；
#  - 保留 kasm-user 作同 uid 别名，兜底 KasmVNC 脚本里残留的 kasm-user 硬编码（chown 等）；
#  - home 实体仍是 volume 挂载点 /home/kasm-user，/home/${APP_USER} 软链过去；
#  - ENV HOME 指向 /home/${APP_USER}，桌面/文件管理器据此显示新名。
ARG APP_USER=admin
RUN if [ "$APP_USER" != "kasm-user" ]; then \
      usermod -l "$APP_USER" kasm-user && \
      usermod -d "/home/$APP_USER" -s /bin/bash "$APP_USER" && \
      ln -sfn /home/kasm-user "/home/$APP_USER" && \
      useradd -o -u 1000 -g 1000 -M -s /bin/bash -d /home/kasm-user kasm-user ; \
    fi
ENV HOME=/home/${APP_USER}

# 只把 XDG_CONFIG_HOME 移到临时 /tmp/caddy（不读持久卷里的旧 xfce 配置，每次开机从 /etc/xdg
# 默认重新生成：顶部菜单+底部任务栏、退出、通知区都正常；曾指向持久卷读到 kasm 单面板陈旧状态，
# 引发面板消失/无法退出/通知区异常）。
# 关键：XDG_DATA_HOME 必须保持默认(~/.local/share，即持久卷)，绝不能也指到 /tmp/caddy——否则
# proot-apps 装到 ~/.local/share/icons 的应用图标、~/.local/share/applications 的菜单项都会被
# 排除出搜索路径，桌面图标变光秃、菜单缺失；且 /tmp/caddy 曾被烤成 root 属主，pulse 写不进而崩溃。
# 显式把 XDG_DATA_HOME 覆盖回持久卷默认值，抵消上方第 46 行那条早期 ENV（ENV 是累积的，
# 后面只设 XDG_CONFIG_HOME 不会取消前面的 XDG_DATA_HOME，故必须在此显式重设）。
ENV XDG_CONFIG_HOME=/tmp/caddy XDG_DATA_HOME=/home/kasm-user/.local/share
# 命令行工具(claude/openclaw/codex/opencode/hermes 等)PATH 进全局 ENV——彻底不依赖 shell 类型:
# 桌面终端默认 shell 是 dash(/bin/sh,不读 bash.bashrc/profile.d),靠全局 ENV 任何进程都能找到命令。
# NPM_CONFIG_PREFIX 同入全局,任意 shell `npm i -g` 都装到用户卷目录。(上面已把默认 shell 也改成 bash)
ENV NPM_CONFIG_PREFIX=${HOME}/.npm-global PATH=${HOME}/.npm-global/bin:${HOME}/.local/bin:${PATH}
# 构建期 root 步骤可能以 /tmp/caddy 作 XDG_CONFIG 建出 root 属主目录，运行时 uid 1000 的
# caddy/xfce 写不进。删掉它，运行时由首个 uid 1000 进程重建为可写。
RUN rm -rf /tmp/caddy
# 恢复运行用户 uid 1000（base 运行期身份）
USER 1000
