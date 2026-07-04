#!/usr/bin/env bash
# 日常构建 + 起容器。版本每次最后一位 +1；构建成功后删旧版本产品镜像 + 悬空层，省盘。
# 可选代理透传给首次 base 构建：./build-and-run.sh http://127.0.0.1:7890
set -euo pipefail
cd "$(dirname "$0")"
[ -f .env ] || { echo "请先 cp .env.example .env 并改密码"; exit 1; }
PROXY="${1:-${BUILD_PROXY:-}}"

# 自举：本地没有 base 就先建一次（把代理透传过去）
if ! sudo docker image inspect chatop-base:latest >/dev/null 2>&1; then
  echo "未发现 chatop-base:latest，先构建 base（首次较慢，之后飞快）..."
  ./build-base.sh "$PROXY"
fi

# 版本自增（最后一位 +1）
OLD="$(cat VERSION)"
NEW="${OLD%.*}.$(( ${OLD##*.} + 1 ))"
echo "版本 ${OLD} -> ${NEW}"

# 用新版本号构建并起容器（容器名固定 chatop，自动替换旧容器）
sudo env VERSION="$NEW" docker compose up -d --build

# 成功后：写回新版本号；删旧版本产品镜像 + 悬空层，省盘
echo "$NEW" > VERSION
[ "$OLD" != "$NEW" ] && sudo docker image rm "chatop:$OLD" >/dev/null 2>&1 || true
sudo docker image prune -f >/dev/null 2>&1 || true

echo "已启动 chatop:${NEW}：https://localhost:$(grep -E '^PORT=' .env | cut -d= -f2 || echo 6901)"
