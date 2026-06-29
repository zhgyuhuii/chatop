#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
[ -f .env ] || { echo "请先 cp .env.example .env 并改密码"; exit 1; }
export VERSION="$(cat VERSION)"
sudo docker compose up -d --build
echo "已启动：https://localhost:$(grep -E '^PORT=' .env | cut -d= -f2 || echo 6901)"
