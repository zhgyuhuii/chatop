#!/usr/bin/env bash
# 日常构建 + 起容器（单一 Dockerfile，无 base 拆分）。版本每次最后一位 +1；
# 构建成功后删旧版本镜像 + 悬空层，省盘。同机分层缓存保证迭代不重下。
# 可选代理透传给构建下载：./build-and-run.sh http://127.0.0.1:7890
set -euo pipefail
cd "$(dirname "$0")"
[ -f .env ] || { echo "请先 cp .env.example .env 并改密码"; exit 1; }
PROXY="${1:-${BUILD_PROXY:-}}"
PROXY_ARGS=()
if [ -n "$PROXY" ]; then
  echo "使用构建代理：$PROXY"
  PROXY_ARGS=(--build-arg "HTTPS_PROXY=$PROXY" --build-arg "HTTP_PROXY=$PROXY" --build-arg "NO_PROXY=localhost,127.0.0.1")
fi

# 版本自增（最后一位 +1）
OLD="$(cat VERSION)"
NEW="${OLD%.*}.$(( ${OLD##*.} + 1 ))"
echo "版本 ${OLD} -> ${NEW}"

# 用新版本号构建并起容器（容器名固定 chatop-ai，自动替换旧容器）
if [ ${#PROXY_ARGS[@]} -gt 0 ]; then
  sudo env VERSION="$NEW" docker compose build "${PROXY_ARGS[@]}"
  sudo env VERSION="$NEW" docker compose up -d
else
  sudo env VERSION="$NEW" docker compose up -d --build
fi

# 成功后：写回新版本号；删旧版本镜像 + 悬空层，省盘
echo "$NEW" > VERSION
[ "$OLD" != "$NEW" ] && sudo docker image rm "chatop-ai:$OLD" >/dev/null 2>&1 || true
sudo docker image prune -f >/dev/null 2>&1 || true

echo "已启动 chatop-ai:${NEW}：https://localhost:$(grep -E '^PORT=' .env | cut -d= -f2 || echo 6901)"
