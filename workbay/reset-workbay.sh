#!/usr/bin/env bash
# 重置某个察元 AI 工舱（chatop）的登录名和/或密码。用法：./reset-workbay.sh [用户名]
# 端口保持不变，只重写 .env 并重建容器应用新账号密码。
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
source "$ROOT/scripts/_workbay-lib.sh"
WORKBAYS_DIR="$ROOT/workbays"
TMPL="$ROOT/scripts/workbay.compose.tmpl.yml"
SUDO="$(wb_sudo)"

# 选工舱
TARGET="${1:-}"
if [ -z "$TARGET" ]; then
  echo "现有工舱："
  for d in "$WORKBAYS_DIR"/*/; do [ -d "$d" ] && echo "  - $(basename "$d")"; done
  read -rp "要重置哪个工舱？ " TARGET </dev/tty
fi
WB_DIR="$WORKBAYS_DIR/$TARGET"
[ -d "$WB_DIR" ] || wb_die "工舱不存在：$TARGET"

# 安全读取 .env（绝不 source：密码含空格/$/引号时 source 会把它当命令执行）
CHATOP_IMAGE="$(wb_env_get CHATOP_IMAGE "$WB_DIR/.env")"
PORT="$(wb_env_get PORT "$WB_DIR/.env")"
LOGIN_USER="$(wb_env_get LOGIN_USER "$WB_DIR/.env")"
# .env 里是转义后的密码，还原成原始值供「不改密码」时复用
PASSWORD="$(wb_unesc_pw "$(wb_env_get PASSWORD "$WB_DIR/.env")")"

# 新账号
read -rp "新用户名（回车=不改，当前 $LOGIN_USER）：" NEW_USER </dev/tty
read -rsp "新密码（回车=不改）：" NEW_PW </dev/tty; echo
[ -z "$NEW_USER" ] && [ -z "$NEW_PW" ] && wb_die "用户名和密码都没改，退出"

PW_VAL="${NEW_PW:-$PASSWORD}"

if [ -n "$NEW_USER" ] && [ "$NEW_USER" != "$LOGIN_USER" ]; then
  wb_valid_username "$NEW_USER" || wb_die "新用户名不合法：$NEW_USER"
  NEW_DIR="$WORKBAYS_DIR/$NEW_USER"
  [ -e "$NEW_DIR" ] && wb_die "目标已存在：$NEW_DIR"
  # 停旧、搬目录、重写配置、以新工程名起（显式 -f，避免向父目录回溯误抓别的 compose）
  ( cd "$WB_DIR" && ${SUDO}docker compose -p "chatop-$TARGET" -f docker-compose.yml down )
  mv "$WB_DIR" "$NEW_DIR"
  wb_write_env "$NEW_DIR/.env" "$CHATOP_IMAGE" "$PORT" "$NEW_USER" "$PW_VAL"
  wb_render_compose "$TMPL" "$NEW_USER" "$NEW_DIR/home" "$NEW_DIR/docker-compose.yml"
  cat > "$NEW_DIR/workbay.json" <<EOF
{"username":"$NEW_USER","port":$PORT,"container":"chatop-$NEW_USER","image":"$CHATOP_IMAGE"}
EOF
  ( cd "$NEW_DIR" && ${SUDO}docker compose -p "chatop-$NEW_USER" -f docker-compose.yml up -d )
  echo "已改名 $TARGET -> $NEW_USER，登录名/密码已更新：https://localhost:$PORT"
else
  # 只改密码：整写 .env（wb_write_env 自动转义 $，兼容含 $/空格/引号的密码）后重建容器应用新 env
  wb_write_env "$WB_DIR/.env" "$CHATOP_IMAGE" "$PORT" "$LOGIN_USER" "$PW_VAL"
  ( cd "$WB_DIR" && ${SUDO}docker compose -p "chatop-$TARGET" -f docker-compose.yml up -d )
  echo "已更新密码：$TARGET，登录 https://localhost:$PORT"
fi
