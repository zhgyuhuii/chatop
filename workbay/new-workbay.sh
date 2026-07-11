#!/usr/bin/env bash
# 新建一个察元 AI 工舱（chatop）：输入用户名/密码 -> 自动避端口 -> 生成 workbays/<user>/ -> 起隔离容器。
# 同一台宿主可反复运行，部署任意多个互相隔离的工舱，端口自动往后顺延不冲突。
#
#   ./new-workbay.sh                 # 交互输入
#   WB_USER=alice WB_PW=secret ./new-workbay.sh   # 预置账号密码（非交互/自动化）
#   CHATOP_IMAGE=crpi-...aliyuncs.com/cmdbird/chatop:latest ./new-workbay.sh   # 指定 ACR 镜像
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
source "$ROOT/scripts/_workbay-lib.sh"
WORKBAYS_DIR="$ROOT/workbays"
TMPL="$ROOT/scripts/workbay.compose.tmpl.yml"
CHATOP_IMAGE="${CHATOP_IMAGE:-cmdbird/chatop:latest}"
BASE_PORT="${BASE_PORT:-6901}"
SUDO="$(wb_sudo)"

# 1) 用户名（登录显示名）
USER_NAME="${WB_USER:-}"
if [ -z "$USER_NAME" ]; then
  read -rp "工舱用户名（小写字母/数字，可含 -_，1-32 位）：" USER_NAME </dev/tty
fi
wb_valid_username "$USER_NAME" || wb_die "用户名不合法：$USER_NAME"
WB_DIR="$WORKBAYS_DIR/$USER_NAME"
[ -e "$WB_DIR" ] && wb_die "工舱已存在：$WB_DIR（改账号/密码请用 ./reset-workbay.sh $USER_NAME）"

# 2) 密码
PW="${WB_PW:-}"
if [ -z "$PW" ]; then
  read -rsp "登录密码：" PW </dev/tty; echo
fi
[ -n "$PW" ] || wb_die "密码不能为空"

# 3) 镜像存在性：本地没有就拉
if ! ${SUDO}docker image inspect "$CHATOP_IMAGE" >/dev/null 2>&1; then
  echo "本地无镜像 $CHATOP_IMAGE，开始拉取（首次较大，请耐心）..."
  ${SUDO}docker pull "$CHATOP_IMAGE" || wb_die "镜像拉取失败：$CHATOP_IMAGE（确认地址可访问，或用 CHATOP_IMAGE= 指定 ACR 加速地址）"
fi

# 4) 端口探测（宿主监听 + docker 已发布，取第一个空闲）
PORT="$(wb_find_free_port "$BASE_PORT")"
echo "分配端口：$PORT"

# 5) 落盘：目录 + .env（密码转义）+ compose
mkdir -p "$WB_DIR/home"
wb_write_env "$WB_DIR/.env" "$CHATOP_IMAGE" "$PORT" "$USER_NAME" "$PW"
wb_render_compose "$TMPL" "$USER_NAME" "$WB_DIR/home" "$WB_DIR/docker-compose.yml"
cat > "$WB_DIR/workbay.json" <<EOF
{"username":"$USER_NAME","port":$PORT,"container":"chatop-$USER_NAME","image":"$CHATOP_IMAGE"}
EOF

# 6) 起容器（显式 -f 指定本工舱 compose，避免 docker compose 向父目录回溯误抓别的 compose）
( cd "$WB_DIR" && ${SUDO}docker compose -p "chatop-$USER_NAME" -f docker-compose.yml up -d )

# 7) 汇报
echo "----------------------------------------"
echo "工舱已启动：$USER_NAME"
echo "  访问：  https://localhost:$PORT   （自签证书，首次浏览器提示继续访问）"
echo "  登录名：$USER_NAME"
echo "  目录：  $WB_DIR"
echo "  容器：  chatop-$USER_NAME"
echo "----------------------------------------"
