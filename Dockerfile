# syntax=docker/dockerfile:1.7
FROM node:20-alpine AS web
WORKDIR /src
COPY novnc-src/ ./
RUN --mount=type=cache,target=/root/.npm npm install && npm run build

FROM kasmweb/ubuntu-jammy-desktop:1.19.0
ARG VERSION=1.1.0
LABEL maintainer="chatop-ai" build_version="chatop-ai ${VERSION}"
# 覆盖 KasmVNC 自带 noVNC 前端（合并覆盖，不删 www 中镜像自带、dist 没有的文件）
COPY --from=web --chown=root:root /src/dist/ /usr/share/kasmvnc/www/
# 保留镜像原有 KasmVNC override 配置，并显式声明剪贴板上/下行权限默认
COPY kasmvnc.yaml /etc/kasmvnc/kasmvnc.yaml

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
# 以 root 卸载 11 个不需要的内置应用 + 安装中文办公栈（搜狗输入法/WPS/CJK 字体/fcitx 框架）
USER root

# --- Task A：卸载 11 个内置应用 ---
# apt 安装的（含其插件/本地化子包）走 purge + autoremove；
# /opt 直装的（gimp、telegram，dpkg 查不到）走 rm -rf 目录 + 删 .desktop。
# 逐项 || true，缺失不致命；最后列残留以便核对。
RUN set -ux; \
    apt-get remove --purge -y \
        firefox xul-ext-ubufox \
        thunderbird \
        remmina remmina-common remmina-plugin-rdp remmina-plugin-secret remmina-plugin-spice remmina-plugin-vnc \
        obs-studio obs-v4l2sink \
        onlyoffice-desktopeditors \
        signal-desktop \
        slack-desktop \
        zoom \
        nextcloud-desktop nextcloud-desktop-common nextcloud-desktop-l10n \
        || true; \
    apt-get autoremove -y || true; \
    # 非 apt（/opt 直装）：gimp、telegram
    rm -rf /opt/gimp-3 /opt/Telegram \
           /usr/share/applications/gimp.desktop \
           /usr/share/applications/telegram.desktop || true; \
    # 兜底清理 purge 后可能残留的 /opt 目录与 .desktop
    rm -rf /opt/Signal /opt/zoom /opt/onlyoffice || true; \
    rm -f /usr/share/applications/signal-desktop.desktop \
          /usr/share/applications/slack.desktop \
          /usr/share/applications/Zoom.desktop \
          /usr/share/applications/firefox.desktop \
          /usr/share/applications/thunderbird.desktop \
          /usr/share/applications/onlyoffice-desktopeditors.desktop \
          /usr/share/applications/com.obsproject.Studio.desktop \
          /usr/share/applications/com.nextcloud.desktopclient.nextcloud.desktop \
          /usr/share/applications/org.remmina.Remmina.desktop \
          /usr/share/applications/org.remmina.Remmina-file.desktop \
          /usr/share/applications/remmina-gnome.desktop || true; \
    echo "=== S7 卸载后残留检查 ==="; \
    ls /usr/share/applications | grep -iE "signal|firefox|thunderbird|remmina|obs|telegram|onlyoffice|nextcloud|zoom|slack|gimp" || echo "（无残留 .desktop）"

# --- Task B-1：CJK 字体 + fcitx4 输入法框架（jammy 上搜狗适配 fcitx4）---
RUN apt-get update && apt-get install -y --no-install-recommends \
      fonts-noto-cjk fonts-noto-color-emoji \
      fcitx fcitx-bin fcitx-config-gtk fcitx-frontend-all fcitx-module-cloudpinyin \
      libqt5qml5 libqt5quick5 libqt5quickwidgets5 qml-module-qtquick2 libgsettings-qt1 \
    && (apt-get remove --purge -y 'ibus*' 'fcitx5*' 2>/dev/null || true)

# --- Task B-2：系统级输入法环境变量 + fcitx 自启动 ---
RUN printf 'GTK_IM_MODULE=fcitx\nQT_IM_MODULE=fcitx\nXMODIFIERS=@im=fcitx\n' >> /etc/environment && \
    (cp /usr/share/applications/fcitx.desktop /etc/xdg/autostart/ 2>/dev/null || true)

# --- Task B-3：搜狗拼音 .deb（gtimg CDN 在本环境 403，故 guard 后回退 fcitx 谷歌/sunpinyin 拼音）---
ARG SOGOU_URL="https://ime-sec.gtimg.com/pc/dl/gzindex/1680521603/sogoupinyin_4.2.1.145_amd64.deb"
RUN set -ux; \
    if curl -fsSL -o /tmp/sogou.deb "$SOGOU_URL"; then \
        (dpkg -i /tmp/sogou.deb || apt-get install -f -y); rm -f /tmp/sogou.deb; \
        echo "SOGOU_INSTALLED"; \
    else \
        echo "SOGOU_UNREACHABLE：回退 fcitx-googlepinyin/fcitx-sunpinyin 作为可用中文输入"; \
    fi; \
    apt-get install -y --no-install-recommends fcitx-googlepinyin fcitx-sunpinyin

# --- Task B-4：WPS Office .deb（wpscdn 实测 200 / 319MB）---
ARG WPS_URL="https://wdl1.pcfg.cache.wpscdn.com/wpsdl/wpsoffice/download/linux/11664/wps-office_11.1.0.11664.XA_amd64.deb"
RUN set -ux; \
    curl -fsSL -o /tmp/wps.deb "$WPS_URL"; \
    (dpkg -i /tmp/wps.deb || apt-get install -f -y); \
    rm -f /tmp/wps.deb; \
    (apt-get install -y --no-install-recommends libtiff5 2>/dev/null || true); \
    rm -rf /var/lib/apt/lists/*

USER root
# 登录名可配：把 vnc_startup.sh 里硬编码的 kasm_user(仅这两类:kasmvncpasswd -u 和 辅助服务 auth-token)
# 改为运行时变量 ${LOGIN_USER:-admin};绝不动 kasm_user_name / kasm_viewer / KASM_USER
RUN sed -i 's/-u kasm_user -wo/-u "${LOGIN_USER:-admin}" -wo/' /dockerstartup/vnc_startup.sh && \
    sed -i 's/kasm_user:\$VNC_PW/${LOGIN_USER:-admin}:\$VNC_PW/g' /dockerstartup/vnc_startup.sh && \
    echo "=== patched login-user lines ===" && grep -nE 'LOGIN_USER|kasm_user' /dockerstartup/vnc_startup.sh
ENV LOGIN_USER=admin

# 恢复运行用户 uid 1000（base 运行期身份）
USER 1000
