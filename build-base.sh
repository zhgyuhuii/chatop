#!/usr/bin/env bash
# 构建固定基础镜像 chatop-base:latest。依赖变了 / 想更新 AI 工具 / 新机器首次 才需跑。
set -euo pipefail
cd "$(dirname "$0")"
# 读取 .env 里的 LOGIN_USER 作为系统用户名（默认 admin）
if [ -f .env ]; then set -a; . ./.env; set +a; fi
sudo docker build -f Dockerfile.base \
  --build-arg APP_USER="${LOGIN_USER:-admin}" \
  --build-arg LOGIN_USER="${LOGIN_USER:-admin}" \
  -t chatop-base:latest .
echo "chatop-base:latest 构建完成。之后 ./build-and-run.sh 会自动使用它。"
