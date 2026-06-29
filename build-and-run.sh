#!/bin/bash
# =============================================================================
# 构建与运行：构建逻辑已全部在 Dockerfile 中
# 此脚本仅为便捷入口，可直接用 docker compose 替代
# 版本号取自根目录 VERSION 文件，构建后额外打 chatop:latest 标签
# 约定：每次发布（提交）将 VERSION 文件中的版本号 +1
# 主机端口用 HOST_PORT 覆盖（默认 3001），例：HOST_PORT=3002 ./build-and-run.sh start
# =============================================================================

set -e
cd "$(dirname "${BASH_SOURCE[0]}")"

# 读取版本号（VERSION 文件为单一真源），并导出供 docker compose 变量替换
VERSION="$(tr -d ' \t\r\n' < VERSION 2>/dev/null || echo 1.0.0)"
[ -z "$VERSION" ] && VERSION="1.0.0"
export VERSION
export BUILD_DATE="$(date -u +%Y-%m-%dT%H:%M:%SZ)"

tag_latest() {
  docker tag "chatop:${VERSION}" chatop:latest 2>/dev/null || true
}

case "${1:-start}" in
  build)
    docker compose build
    tag_latest
    ;;
  run)
    # 重新构建并启动（改了 Dockerfile/源码时用）
    docker compose up -d --build
    tag_latest
    ;;
  start|up)
    # 用现成镜像启动，不重新构建（日常启动用这个，避免无谓的重建/导出）
    docker compose up -d
    ;;
  down)
    docker compose down
    ;;
  -h|--help|help)
    echo "用法: $0 [build|run|start|down]"
    echo "  build - 仅构建（当前版本: chatop:${VERSION}）"
    echo "  run   - 重新构建并启动（改了 Dockerfile/源码时用）"
    echo "  start - 用现成镜像启动，不重建（默认）"
    echo "  down  - 停止"
    echo ""
    echo "主机端口: HOST_PORT=3002 $0 start   （默认 3001）"
    echo "或直接: HOST_PORT=3002 VERSION=${VERSION} docker compose up -d"
    exit 0
    ;;
  *)
    echo "未知命令: $1，使用 -h 查看帮助"
    exit 1
    ;;
esac
