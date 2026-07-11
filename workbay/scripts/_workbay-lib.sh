#!/usr/bin/env bash
# 察元 AI 工舱（chatop）多工舱 公共函数库。被 new-workbay.sh / reset-workbay.sh source。
# 约定：ROOT=项目根，WORKBAYS_DIR=$ROOT/workbays。docker 命令需 sudo（非 root 时）。
# 端口探测/密码转义等与 tongyutop 同源，chatop 走 pull 镜像、内部用户恒为 admin。

wb_die() { echo "错误：$*" >&2; exit 1; }

# 非 root 时补 sudo 前缀
wb_sudo() { if [ "$(id -u)" -eq 0 ]; then printf ''; elif command -v sudo >/dev/null 2>&1; then printf 'sudo '; else wb_die "需要 root 或 sudo 运行 docker"; fi; }

# 用户名：小写字母/数字开头，后接小写字母/数字/-/_，总长 1..32
wb_valid_username() {
  [[ "$1" =~ ^[a-z0-9][a-z0-9_-]{0,31}$ ]]
}

# seam：宿主本机监听中的端口（每行一个）。测试会覆盖它。
_host_listen_ports() {
  ss -ltnH 2>/dev/null | awk '{print $4}' | sed -E 's/.*:([0-9]+)$/\1/' | grep -E '^[0-9]+$'
}

# seam：docker ps 的原始 Ports 列（每行一个容器的端口映射串）。测试会覆盖它。
_docker_ps_ports_raw() {
  $(wb_sudo)docker ps --format '{{.Ports}}' 2>/dev/null
}

# docker 已发布到宿主的端口（每行一个）。
# 只取「->」前那个冒号后的数字（真正的宿主发布端口），避免把 IP（如 0.0.0.0 里的 0）误当端口。
_docker_published_ports() {
  _docker_ps_ports_raw \
    | grep -oE ':[0-9]+->' \
    | grep -oE '[0-9]+' | sort -u
}

# 端口是否被占用（宿主监听 或 docker 已发布）
# 坑：`{ 列端口; } | grep -qx` 在 set -o pipefail 下，grep 命中即早退会给上游发 SIGPIPE，
# 上游以 141 退出 → pipefail 把整条管道判失败 → 明明占用却返回"未占用"，端口避让失效。
# 对策：先把端口清单收进变量，再用 herestring 喂 grep（非管道，无上游可 SIGPIPE）。
wb_port_in_use() {
  local p="$1" ports
  ports="$({ _host_listen_ports; _docker_published_ports; } 2>/dev/null || true)"
  grep -qx "$p" <<<"$ports"
}

# 从 start 起找第一个空闲端口（打印到 stdout）
wb_find_free_port() {
  local p="${1:-6901}"
  while wb_port_in_use "$p"; do p=$((p+1)); done
  printf '%s\n' "$p"
}

# 用模板生成工舱 compose。参数：tmpl user port image home_abs out
# 镜像/端口/用户/密码通过 .env 插值注入；这里只替换 __USER__(容器名) 与 __HOME__(绑定路径)。
wb_render_compose() {
  local tmpl="$1" user="$2" home="$3" out="$4"
  sed -e "s|__USER__|${user}|g" \
      -e "s|__HOME__|${home}|g" \
      "$tmpl" > "$out"
}

# --- 密码 / .env 安全处理 -----------------------------------------------------
# 坑：docker compose 对 .env 值做变量插值，裸 `$x` 会被当未定义变量吃成空；
# 密码含空格/反引号/引号在 `source .env` 时还会被 shell 当命令执行。
# 对策：写 .env 时把 `$` 转义成 `$$`（compose 插值后还原成字面 `$`），
# 读回时用 wb_env_get 逐字读（绝不 source），需要原始密码再 wb_unesc_pw。

wb_esc_pw()   { printf '%s' "$1" | sed 's/[$]/$$/g'; }   # $ -> $$
wb_unesc_pw() { printf '%s' "$1" | sed 's/[$][$]/$/g'; }  # $$ -> $

# 安全读取 .env 里某个键的字面值（不 source，不受特殊字符影响）。用法：wb_env_get KEY FILE
wb_env_get() {
  local key="$1" file="$2"
  [ -f "$file" ] || return 1
  sed -n "s/^${key}=//p" "$file" | head -1
}

# 写工舱 .env（密码自动转义）。参数：out image port login_user password_raw
wb_write_env() {
  local out="$1" image="$2" port="$3" login="$4" pw_raw="$5"
  local pw_esc; pw_esc="$(wb_esc_pw "$pw_raw")"
  cat > "$out" <<EOF
CHATOP_IMAGE=$image
PORT=$port
LOGIN_USER=$login
PASSWORD=$pw_esc
EOF
  chmod 600 "$out"
}
