#!/usr/bin/env bash
# chatop-fetch <url> <out> [--dry-run]
# 直连 → mirrors.conf 的 GH_PROXIES 逐个前缀拼接回退，任一成功即止。
# --dry-run: 只打印候选 URL 列表（每行一个），不下载。供测试与排障。
set -u
CONF="${MIRRORS_CONF:-/etc/chatop/mirrors.conf}"
URL="${1:?need url}"; OUT="${2:-}"; MODE="${3:-}"

GH_PROXIES=""
[ -f "$CONF" ] && GH_PROXIES="$(sed -n 's/^GH_PROXIES=//p' "$CONF")"

# 候选：先直连，再各代理前缀 + 原始 url
CANDIDATES=("$URL")
for p in $GH_PROXIES; do CANDIDATES+=("${p}${URL}"); done

if [ "$MODE" = "--dry-run" ] || [ "$OUT" = "--dry-run" ]; then
  printf '%s\n' "${CANDIDATES[@]}"; exit 0
fi

: "${OUT:?need out path}"
for u in "${CANDIDATES[@]}"; do
  echo "[chatop-fetch] try: $u" >&2
  if curl -fL --retry 2 --retry-delay 3 --connect-timeout 20 -o "$OUT" "$u"; then
    echo "[chatop-fetch] ok via: $u" >&2; exit 0
  fi
done
echo "[chatop-fetch] 全部源失败（直连+镜像），网络不可达或镜像不可用: $URL" >&2
exit 1
