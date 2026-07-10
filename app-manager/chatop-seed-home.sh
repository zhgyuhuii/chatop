#!/bin/bash
# chatop-seed-home.sh —— 首启把镜像里预装好的工具播种回 home 卷。
# 机制：构建期把装好工具的 home 整棵迁到 /opt/chatop-seed-home；首启（或镜像升级到更高
# seed 版本）时 cp -an（归档+不覆盖）补进 $HOME。只补缺、绝不覆盖用户已有/已改数据；
# 版本哨兵保证同一版本只播一次（用户卸载某工具后不会被反复重新播种）。
set -u
SEED_SRC=/opt/chatop-seed-home
WANT=6   # 升级镜像、要补播新增工具时把这个数字 +1
         # v2: 大屏 autostart + Hermes/OpenHuman 预装
         # v3: 全部内置智能体桌面图标 + 智能启动(chatop-agent-launch) + 监控大屏图标(察元AI工舱改名)
         # v4: OpenClaw 配置改用 openclaw-tool(tkinter) 桌面图标；移除失效的 agent-builder 图标
         # v5: 察元桌面客户端(Lite) 图标(仅 WITH_CHAYUAN_DESKTOP=1 构建的镜像有该 .desktop)
         # v6: 桌面加固 autostart(chatop-desktop-tweak) + 「退出全屏」图标(chatop-unfullscreen)
HOME="${HOME:-/home/$(id -un)}"
SENT="$HOME/.local/share/chatop/seed-version"

[ -d "$SEED_SRC" ] || exit 0
have="$(cat "$SENT" 2>/dev/null || echo 0)"
case "$have" in ''|*[!0-9]*) have=0;; esac
[ "$have" -ge "$WANT" ] && exit 0

echo "[seed] 播种预装工具 $SEED_SRC -> $HOME (have=$have want=$WANT)"
# 1) 补缺、绝不覆盖：用户数据/已装工具只补不改
cp -an "$SEED_SRC/." "$HOME/" 2>/dev/null || true
# 2) 版本升级时刷新 chatop 托管的桌面启动项(镜像资产，非用户数据)：图标/品牌/智能启动跟随镜像更新。
#    只覆盖 chatop-*.desktop 与大屏 autostart；用户自建的其它 .desktop 不动。
for d in "$SEED_SRC/.local/share/applications" "$SEED_SRC/Desktop" "$SEED_SRC/.config/autostart"; do
  [ -d "$d" ] || continue
  rel="${d#$SEED_SRC/}"; mkdir -p "$HOME/$rel"
  cp -f "$d"/chatop-*.desktop "$HOME/$rel/" 2>/dev/null || true
done
chmod +x "$HOME/.local/share/applications"/chatop-*.desktop "$HOME/Desktop"/chatop-*.desktop 2>/dev/null || true
# 3) 清理已废弃的 chatop 托管图标（agent-builder 已被 openclaw-tool 取代）；仅删 chatop 自管项，不碰用户自建
rm -f "$HOME/.local/share/applications/chatop-agent-builder.desktop" \
      "$HOME/Desktop/chatop-agent-builder.desktop" 2>/dev/null || true
rm -rf "$HOME/Applications/agent-builder" 2>/dev/null || true
mkdir -p "$(dirname "$SENT")"
echo "$WANT" > "$SENT"
echo "[seed] done"
