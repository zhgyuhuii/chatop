#!/usr/bin/env bash
# 启动前置 Caddy 反代：单端口收口 KasmVNC + filebrowser。
# tls internal 仅按 SNI 现签证书；而用户以 IP 直连(无 SNI)，Caddy 无默认证书会握手
# internal error。故此处自签一张固定证书(同 KasmVNC 自签，浏览器照常需点信任)，
# Caddy 用 `tls cert key` 对任意 SNI/无 SNI 都出示同一张证书。
set -e
CADDY_DIR=/tmp/caddy
CRT="$CADDY_DIR/tls.crt"
KEY="$CADDY_DIR/tls.key"
mkdir -p "$CADDY_DIR"
if [ ! -f "$CRT" ] || [ ! -f "$KEY" ]; then
  openssl req -x509 -newkey rsa:2048 -nodes \
    -keyout "$KEY" -out "$CRT" -days 3650 \
    -subj "/CN=chatop-ai" \
    -addext "subjectAltName=DNS:localhost,DNS:chatop-ai,IP:127.0.0.1" >/dev/null 2>&1
fi
exec /usr/local/bin/caddy run --config /etc/caddy/Caddyfile
