#!/bin/bash
# =============================================================================
# 构建与运行：构建逻辑已全部在 Dockerfile 中
# 此脚本仅为便捷入口，可直接用 docker compose 替代
# 版本号取自根目录 VERSION 文件，构建后额外打 chatop:latest 标签
# 约定：每次发布（提交）将 VERSION 文件中的版本号 +1
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

case "${1:-run}" in
  build)
    docker compose build
    tag_latest
    ;;
  run|up)
    docker compose up -d --build
    tag_latest
    ;;
  down)
    docker compose down
    ;;
  -h|--help|help)
    echo "用法: $0 [build|run|down]"
    echo "  build - 仅构建（当前版本: chatop:${VERSION}）"
    echo "  run   - 构建并启动（默认）"
    echo "  down  - 停止"
    echo ""
    echo "或直接: VERSION=${VERSION} docker compose up -d --build"
    exit 0
    ;;
  *)
    echo "未知命令: $1，使用 -h 查看帮助"
    exit 1
    ;;
esac
