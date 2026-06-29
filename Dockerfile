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
USER 1000
