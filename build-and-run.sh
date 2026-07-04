#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
[ -f .env ] || { echo "请先 cp .env.example .env 并改密码"; exit 1; }
export VERSION="$(cat VERSION)"
# 自举：本地没有 base 就先建一次（新机器一条命令搞定）
if ! sudo docker image inspect chatop-base:latest >/dev/null 2>&1; then
  echo "未发现 chatop-base:latest，先构建 base（首次较慢，之后飞快）..."
  ./build-base.sh
fi
sudo docker compose up -d --build
echo "已启动：https://localhost:$(grep -E '^PORT=' .env | cut -d= -f2 || echo 6901)"
