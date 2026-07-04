#!/usr/bin/env bash
# 构建固定基础镜像 chatop-base:latest。依赖变了 / 想更新 AI 工具 / 新机器首次 才需跑。
# 可选：GitHub/Google 等被墙时，把本机代理传给构建下载：
#   ./build-base.sh                          # 直连
#   ./build-base.sh http://127.0.0.1:7890    # 走代理
# 也可在 .env 里写 BUILD_PROXY=http://127.0.0.1:7890
set -euo pipefail
cd "$(dirname "$0")"
if [ -f .env ]; then set -a; . ./.env; set +a; fi
PROXY="${1:-${BUILD_PROXY:-}}"
PROXY_ARGS=()
if [ -n "$PROXY" ]; then
  echo "使用构建代理：$PROXY"
  PROXY_ARGS=(--build-arg "HTTPS_PROXY=$PROXY" --build-arg "HTTP_PROXY=$PROXY" --build-arg "NO_PROXY=localhost,127.0.0.1")
fi
sudo docker build -f Dockerfile.base \
  --build-arg APP_USER="${LOGIN_USER:-admin}" \
  --build-arg LOGIN_USER="${LOGIN_USER:-admin}" \
  "${PROXY_ARGS[@]}" \
  -t chatop-base:latest .
echo "chatop-base:latest 构建完成。之后 ./build-and-run.sh 会自动使用它。"
