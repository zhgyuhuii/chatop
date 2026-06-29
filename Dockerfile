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
