#!/usr/bin/env bash
# chatop 一键安装器（Linux / macOS）
#
#   curl -fsSL https://<你的域名>/install.sh | bash
#   # 或指定镜像 / 端口 / 账号（非交互）：
#   CHATOP_IMAGE=chatop:latest CHATOP_PORT=6901 \
#   CHATOP_USER=admin CHATOP_PASSWORD=xxxx curl -fsSL https://<你的域名>/install.sh | bash
#
# 步骤：检查/安装 docker + docker compose → 让用户设账号密码 → 生成 compose → 拉镜像 → 起容器 → 开浏览器。
# 幂等：重复运行只做缺失的步骤；已存在的安装目录会复用其 .env（除非用环境变量覆盖）。
set -euo pipefail

# ---- 可配置项（环境变量覆盖）----
# 镜像统一为 chatop:latest（用户始终拉最新版）。若推到 Docker Hub 需带命名空间，
# 例如 CHATOP_IMAGE=<你的用户名>/chatop:latest；自建 registry 用裸 chatop:latest 即可。
CHATOP_IMAGE="${CHATOP_IMAGE:-chatop:latest}"
CHATOP_PORT="${CHATOP_PORT:-6901}"
CHATOP_DIR="${CHATOP_DIR:-$HOME/.chatop}"
CHATOP_USER="${CHATOP_USER:-}"
CHATOP_PASSWORD="${CHATOP_PASSWORD:-}"

# ---- 输出助手（纯 ASCII，避免终端乱码）----
c_info() { printf '\033[36m[chatop]\033[0m %s\n' "$*"; }
c_ok()   { printf '\033[32m[OK]\033[0m %s\n' "$*"; }
c_warn() { printf '\033[33m[!]\033[0m %s\n' "$*"; }
c_err()  { printf '\033[31m[ERR]\033[0m %s\n' "$*" >&2; }
die()    { c_err "$*"; exit 1; }

# curl|bash 时脚本占了 stdin，交互输入要从 /dev/tty 读
read_tty() { # read_tty <varname> <prompt> [silent]
  local __var="$1" __prompt="$2" __silent="${3:-}" __val=""
  if [ ! -t 0 ] && [ ! -e /dev/tty ]; then
    die "无法交互读取「$2」，请用环境变量 CHATOP_USER / CHATOP_PASSWORD 预设后重跑"
  fi
  if [ -n "$__silent" ]; then
    printf '%s' "$__prompt" > /dev/tty
    IFS= read -rs __val < /dev/tty; printf '\n' > /dev/tty
  else
    printf '%s' "$__prompt" > /dev/tty
    IFS= read -r __val < /dev/tty
  fi
  printf -v "$__var" '%s' "$__val"
}

OS="$(uname -s)"
ARCH="$(uname -m)"

need_sudo() { # 在非 root 且有 sudo 时前缀 sudo
  if [ "$(id -u)" -eq 0 ]; then printf ''; elif command -v sudo >/dev/null 2>&1; then printf 'sudo '; else
    die "需要 root 权限安装 docker，但没有 sudo。请用 root 重跑。"; fi
}

# ---- 1) docker ----
install_docker_linux() {
  c_info "未检测到 docker，正在用官方脚本安装（get.docker.com）..."
  local S; S="$(need_sudo)"
  curl -fsSL https://get.docker.com -o /tmp/get-docker.sh || die "下载 docker 安装脚本失败"
  ${S}sh /tmp/get-docker.sh || die "docker 安装失败"
  rm -f /tmp/get-docker.sh
  ${S}systemctl enable --now docker 2>/dev/null || ${S}service docker start 2>/dev/null || true
  # 把当前用户加进 docker 组（免每次 sudo；本次会话仍需 sudo 或重登生效）
  if [ "$(id -u)" -ne 0 ]; then ${S}usermod -aG docker "$(id -un)" 2>/dev/null || true; fi
  c_ok "docker 安装完成"
}

install_docker_mac() {
  c_warn "未检测到 Docker Desktop。"
  if command -v brew >/dev/null 2>&1; then
    c_info "用 Homebrew 安装 Docker Desktop（brew install --cask docker）..."
    brew install --cask docker || die "brew 安装 Docker Desktop 失败，请手动安装：https://www.docker.com/products/docker-desktop"
    c_info "正在启动 Docker Desktop..."
    open -a Docker || true
  else
    c_warn "未装 Homebrew，无法自动安装。请手动下载安装 Docker Desktop："
    c_warn "  https://www.docker.com/products/docker-desktop"
    open "https://www.docker.com/products/docker-desktop" 2>/dev/null || true
    die "装好 Docker Desktop 并启动后，重跑本脚本即可自动继续。"
  fi
}

ensure_docker() {
  if ! command -v docker >/dev/null 2>&1; then
    case "$OS" in
      Linux)  install_docker_linux ;;
      Darwin) install_docker_mac ;;
      *) die "不支持的系统：$OS（本脚本仅支持 Linux / macOS，Windows 请用 install.ps1）" ;;
    esac
  else
    c_ok "docker 已安装：$(docker --version 2>/dev/null || echo '?')"
  fi
}

ensure_daemon() {
  local S; [ "$(id -u)" -eq 0 ] || command -v sudo >/dev/null 2>&1 && S="$(need_sudo)" || S=""
  for i in $(seq 1 60); do
    if docker info >/dev/null 2>&1 || ${S}docker info >/dev/null 2>&1; then c_ok "docker 守护进程就绪"; return 0; fi
    if [ "$i" -eq 1 ]; then
      [ "$OS" = "Darwin" ] && { c_info "等待 Docker Desktop 启动（首次可能要 1-2 分钟）..."; open -a Docker 2>/dev/null || true; } \
                           || c_info "等待 docker 守护进程启动..."
    fi
    sleep 3
  done
  die "docker 守护进程未就绪。macOS 请确认 Docker Desktop 已启动；Linux 请检查 systemctl status docker。"
}

ensure_compose() {
  # docker compose(v2 插件) 优先；get.docker.com 与 Docker Desktop 都自带
  local S; S="$(need_sudo)"
  if docker compose version >/dev/null 2>&1 || ${S}docker compose version >/dev/null 2>&1; then
    c_ok "docker compose 已就绪"; DC="docker compose"; return 0
  fi
  if command -v docker-compose >/dev/null 2>&1; then c_ok "docker-compose(v1) 可用"; DC="docker-compose"; return 0; fi
  die "缺少 docker compose 插件。请升级 docker 到含 compose v2 的版本。"
}

# docker 是否需要 sudo 前缀（用户没在 docker 组时）
DOCKER=""
resolve_docker_prefix() {
  if docker info >/dev/null 2>&1; then DOCKER=""; else DOCKER="$(need_sudo)"; fi
}

# ---- 2) 账号密码 ----
gen_pw() { LC_ALL=C tr -dc 'A-Za-z0-9' < /dev/urandom 2>/dev/null | head -c 16 || openssl rand -base64 12 | tr -dc 'A-Za-z0-9' | head -c 16; }

collect_credentials() {
  # 已有安装目录且未强制覆盖 → 复用旧 .env
  if [ -z "$CHATOP_USER$CHATOP_PASSWORD" ] && [ -f "$CHATOP_DIR/.env" ]; then
    c_info "复用已有配置 $CHATOP_DIR/.env"
    return 0
  fi
  [ -n "$CHATOP_USER" ] || read_tty CHATOP_USER "设置登录用户名 [admin]: "
  [ -n "$CHATOP_USER" ] || CHATOP_USER="admin"
  if [ -z "$CHATOP_PASSWORD" ]; then
    local p1 p2
    while :; do
      read_tty p1 "设置登录密码（留空自动生成）: " silent
      if [ -z "$p1" ]; then CHATOP_PASSWORD="$(gen_pw)"; c_info "已生成随机密码：$CHATOP_PASSWORD"; break; fi
      read_tty p2 "再次输入密码: " silent
      [ "$p1" = "$p2" ] && { CHATOP_PASSWORD="$p1"; break; } || c_warn "两次不一致，请重试"
    done
  fi
}

# ---- 3) 生成 compose + .env ----
write_config() {
  mkdir -p "$CHATOP_DIR"
  # compose 会对 .env 值做变量插值：含 $ 的密码里的 $x 会被当未定义变量吃掉。
  # 转义 $ -> $$，compose 读回还原成字面 $。
  local pw_esc; pw_esc="$(printf '%s' "$CHATOP_PASSWORD" | sed 's/[$]/$$/g')"
  cat > "$CHATOP_DIR/.env" <<EOF
LOGIN_USER=$CHATOP_USER
PASSWORD=$pw_esc
PORT=$CHATOP_PORT
CHATOP_IMAGE=$CHATOP_IMAGE
EOF
  chmod 600 "$CHATOP_DIR/.env"
  cat > "$CHATOP_DIR/docker-compose.yml" <<'EOF'
name: chatop-ai
services:
  chatop-ai:
    image: ${CHATOP_IMAGE}
    container_name: chatop-ai
    pull_policy: always
    environment:
      - VNC_PW=${PASSWORD:?}
      - LOGIN_USER=${LOGIN_USER:-admin}
      - FILES_PW=${PASSWORD:?}
    ports:
      - "${PORT:-6901}:7443"
    shm_size: "1gb"
    volumes:
      - chatop-home:/home/${LOGIN_USER:-admin}
    restart: unless-stopped
volumes:
  chatop-home:
EOF
  c_ok "配置已写入 $CHATOP_DIR"
}

# ---- 4) 拉镜像 + 起容器 ----
start_chatop() {
  c_info "拉取镜像 $CHATOP_IMAGE（首次较大，请耐心）..."
  ( cd "$CHATOP_DIR" && ${DOCKER}$DC pull ) || die "镜像拉取失败，请确认 CHATOP_IMAGE=$CHATOP_IMAGE 可访问"
  c_info "启动 chatop..."
  ( cd "$CHATOP_DIR" && ${DOCKER}$DC up -d ) || die "启动失败"
  c_ok "容器已启动"
}

# ---- 5) 等就绪 + 开浏览器 ----
open_browser() {
  local url="https://localhost:$CHATOP_PORT"
  c_info "等待服务就绪..."
  for i in $(seq 1 40); do
    if curl -ksS "$url" >/dev/null 2>&1; then break; fi
    sleep 2
  done
  c_ok "chatop 已就绪：$url"
  case "$OS" in
    Darwin) open "$url" 2>/dev/null || true ;;
    Linux)  (command -v xdg-open >/dev/null && xdg-open "$url" 2>/dev/null &) || true ;;
  esac
}

main() {
  c_info "chatop 一键安装器（$OS/$ARCH）"
  ensure_docker
  ensure_daemon
  ensure_compose
  resolve_docker_prefix
  collect_credentials
  write_config
  start_chatop
  open_browser
  echo
  c_ok "安装完成！"
  echo    "  地址:   https://localhost:$CHATOP_PORT  （自签证书，浏览器会提示不安全，点继续即可）"
  echo    "  用户名: $CHATOP_USER"
  echo    "  密码:   $CHATOP_PASSWORD"
  echo    "  配置:   $CHATOP_DIR （docker compose down 可停止，up -d 可重启）"
}

# CHATOP_INSTALL_LIB=1 时只加载函数不执行（供测试 source）
if [ "${CHATOP_INSTALL_LIB:-}" != "1" ]; then
  main "$@"
fi
