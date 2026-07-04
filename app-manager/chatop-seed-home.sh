#!/bin/bash
# chatop-seed-home.sh —— 首启把镜像里预装好的工具播种回 home 卷。
# 机制：构建期把装好工具的 home 整棵迁到 /opt/chatop-seed-home；首启（或镜像升级到更高
# seed 版本）时 cp -an（归档+不覆盖）补进 $HOME。只补缺、绝不覆盖用户已有/已改数据；
# 版本哨兵保证同一版本只播一次（用户卸载某工具后不会被反复重新播种）。
set -u
SEED_SRC=/opt/chatop-seed-home
WANT=1   # 升级镜像、要补播新增工具时把这个数字 +1
HOME="${HOME:-/home/$(id -un)}"
SENT="$HOME/.local/share/chatop/seed-version"

[ -d "$SEED_SRC" ] || exit 0
have="$(cat "$SENT" 2>/dev/null || echo 0)"
case "$have" in ''|*[!0-9]*) have=0;; esac
[ "$have" -ge "$WANT" ] && exit 0

echo "[seed] 播种预装工具 $SEED_SRC -> $HOME (have=$have want=$WANT)"
cp -an "$SEED_SRC/." "$HOME/" 2>/dev/null || true
mkdir -p "$(dirname "$SENT")"
echo "$WANT" > "$SENT"
echo "[seed] done"
