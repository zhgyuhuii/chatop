#!/usr/bin/env bash
# chatop-ai filebrowser sidecar: 内部 HTTP 127.0.0.1:8585, baseurl=/files,
# 由 Caddy 反代到同源 /files（不再独立端口/TLS）。自带登录(VNC_PW)。
# CLI flags 已对 File Browser v2.63.17 实测核对(见 S5 Task 4 报告)。
set -e
ROOT="${FB_ROOT:-$HOME}"
PORT="${FB_PORT:-8585}"
DB="${HOME}/.filebrowser.db"
USER_NAME="${CUSTOM_USER:-kasm_user}"
PASS="${VNC_PW:-password}"
# 初始化数据库与全局配置(幂等)
if [ ! -f "$DB" ]; then
  filebrowser -d "$DB" config init
  # 监听内部环回 127.0.0.1:8585, 根=$HOME, 明文 HTTP(TLS 由前置 Caddy 负责),
  # baseurl=/files 让 Caddy 以同源 /files 前缀反代; auth.method=json(自带登录);
  # minimumPasswordLength=1 以允许较短的 VNC_PW(默认值 12 会拒绝)
  filebrowser -d "$DB" config set \
    --address 127.0.0.1 --port "$PORT" --root "$ROOT" \
    --baseurl /files --auth.method=json --minimumPasswordLength 1
  # 单一管理员 kasm_user / $VNC_PW(与桌面登录同凭据)。add 失败(已存在)则 update 密码。
  filebrowser -d "$DB" users add "$USER_NAME" "$PASS" --perm.admin 2>/dev/null || \
    filebrowser -d "$DB" users update "$USER_NAME" --password "$PASS" 2>/dev/null || true
fi
exec filebrowser -d "$DB"
