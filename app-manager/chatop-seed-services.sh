#!/usr/bin/env bash
# app-manager/chatop-seed-services.sh
# 首启把镜像出厂服务 bundle 幂等播种到 chatop-home 卷的服务区。
# 卷里没有该服务 → 播种为版本 vFACTORY 并建 current 软链；已有 current → 不动(尊重用户升级)。
set -euo pipefail
FAC="${CHATOP_FACTORY_DIR:-/opt/chatop/factory}"
VOL="${CHATOP_SERVICES_DIR:-$HOME/.chatop/services}"
FVER="${CHATOP_FACTORY_VERSION:-$(cat /opt/chatop/factory/VERSION 2>/dev/null || echo 0.0.0)}"

for n in station agent-config dashboard-web openclaw-tool; do
  [ -d "$FAC/$n" ] || continue
  dst="$VOL/$n"
  if [ -L "$dst/current" ] && [ -e "$dst/current" ]; then
    continue   # 已有生效版(可能是用户升级过的)，不覆盖
  fi
  mkdir -p "$dst/$FVER"
  cp -an "$FAC/$n/." "$dst/$FVER/" 2>/dev/null || cp -rn "$FAC/$n/." "$dst/$FVER/"
  ln -sfn "$FVER" "$dst/current"
done
echo "seeded services into $VOL (factory v$FVER)"
