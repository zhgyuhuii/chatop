#!/bin/bash
# =============================================================================
# 构建与运行：构建逻辑已全部在 Dockerfile 中
# 此脚本仅为便捷入口，可直接用 docker compose 替代
# =============================================================================

set -e
cd "$(dirname "${BASH_SOURCE[0]}")"

case "${1:-run}" in
  build)
    docker compose build
    ;;
  run|up)
    docker compose up -d --build
    ;;
  down)
    docker compose down
    ;;
  -h|--help|help)
    echo "用法: $0 [build|run|down]"
    echo "  build - 仅构建"
    echo "  run   - 构建并启动（默认）"
    echo "  down  - 停止"
    echo ""
    echo "或直接: docker compose up -d --build"
    exit 0
    ;;
  *)
    echo "未知命令: $1，使用 -h 查看帮助"
    exit 1
    ;;
esac
