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
RUN curl -fsSL https://raw.githubusercontent.com/filebrowser/filebrowser/master/get.sh | bash || \
    ( set -e; ARCH=linux-amd64; \
      curl -fsSL -o /tmp/fb.tar.gz "https://github.com/filebrowser/filebrowser/releases/latest/download/${ARCH}-filebrowser.tar.gz"; \
      tar -xzf /tmp/fb.tar.gz -C /usr/local/bin filebrowser; rm -f /tmp/fb.tar.gz; chmod +x /usr/local/bin/filebrowser )
COPY filebrowser/start-filebrowser.sh /usr/local/bin/start-filebrowser.sh
RUN mkdir -p /dockerstartup && \
    chmod +x /usr/local/bin/start-filebrowser.sh && \
    printf '#!/bin/bash\n/usr/local/bin/start-filebrowser.sh >/tmp/filebrowser.log 2>&1 &\n' > /dockerstartup/custom_startup.sh && \
    chmod +x /dockerstartup/custom_startup.sh
USER 1000
