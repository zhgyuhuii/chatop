#!/usr/bin/env bash
# chatop-ai filebrowser sidecar: 独立端口 8585, TLS 复用 KasmVNC 自签证书, 自带登录(VNC_PW)
# CLI flags 已对 File Browser v2.63.17 实测核对(见 S5 Task 4 报告)。
set -e
ROOT="${FB_ROOT:-$HOME}"
PORT="${FB_PORT:-8585}"
DB="${HOME}/.filebrowser.db"
CERT="${HOME}/.vnc/self.pem"
USER_NAME="${CUSTOM_USER:-kasm_user}"
PASS="${VNC_PW:-password}"
# 等证书就绪(KasmVNC 启动时生成 self.pem)
for i in $(seq 1 30); do [ -f "$CERT" ] && break; sleep 1; done
# 初始化数据库与全局配置(幂等)
if [ ! -f "$DB" ]; then
  filebrowser -d "$DB" config init
  # 监听 0.0.0.0:8585, 根=$HOME, TLS 证书+私钥都指向 self.pem(cert+key 同文件),
  # auth.method=json(自带登录); minimumPasswordLength=1 以允许较短的 VNC_PW(默认值 12 会拒绝)
  filebrowser -d "$DB" config set \
    --address 0.0.0.0 --port "$PORT" --root "$ROOT" \
    --cert "$CERT" --key "$CERT" --auth.method=json --minimumPasswordLength 1
  # 单一管理员 kasm_user / $VNC_PW(与桌面登录同凭据)。add 失败(已存在)则 update 密码。
  filebrowser -d "$DB" users add "$USER_NAME" "$PASS" --perm.admin 2>/dev/null || \
    filebrowser -d "$DB" users update "$USER_NAME" --password "$PASS" 2>/dev/null || true
fi
exec filebrowser -d "$DB"
