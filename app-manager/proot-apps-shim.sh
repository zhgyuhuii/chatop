#!/usr/bin/env bash
# proot-apps 垫片：install <短名> → 改写为 ghcr 国内镜像完整引用并按 GHCR_MIRRORS 回退，
# 最后回退直连官方短名。其余子命令(run/remove/update…)原样透传给 proot-apps-real。
# --dry-run 放在最后一个参数时，只打印将尝试的 install 引用列表。
set -u
CONF="${MIRRORS_CONF:-/etc/chatop/mirrors.conf}"
REAL="${PROOT_APPS_REAL:-proot-apps-real}"

SUB="${1:-}"; APP="${2:-}"
# 非 install，或 install 的目标已是完整引用(含 / 或 :)，直接透传
if [ "$SUB" != "install" ] || [ -z "$APP" ] || [[ "$APP" == *[/:]* ]]; then
  exec "$REAL" "$@"
fi

GHCR_MIRRORS=""
[ -f "$CONF" ] && GHCR_MIRRORS="$(sed -n 's/^GHCR_MIRRORS=//p' "$CONF")"

REFS=()
for m in $GHCR_MIRRORS; do REFS+=("${m}/linuxserver/proot-apps:${APP}"); done
REFS+=("$APP")   # 最后回退官方直连短名

# 末参 --dry-run 时只打印
if [ "${!#}" = "--dry-run" ]; then printf '%s\n' "${REFS[@]}"; exit 0; fi

for ref in "${REFS[@]}"; do
  echo "[proot-apps] install via: $ref" >&2
  if "$REAL" install "$ref"; then exit 0; fi
  echo "[proot-apps] 失败，尝试下一镜像源" >&2
done
echo "[proot-apps] 全部 ghcr 源失败: $APP" >&2
exit 1
