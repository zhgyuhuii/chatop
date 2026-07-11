#!/bin/bash
# chatop-seed-home.sh —— 首启把镜像里预装好的工具播种回 home 卷。
# 机制：构建期把装好工具的 home 整棵迁到 /opt/chatop-seed-home；首启（或镜像升级到更高
# seed 版本）时 cp -an（归档+不覆盖）补进 $HOME。只补缺、绝不覆盖用户已有/已改数据；
# 版本哨兵保证同一版本只播一次（用户卸载某工具后不会被反复重新播种）。
set -u
SEED_SRC=/opt/chatop-seed-home
WANT=8   # 升级镜像、要补播新增工具时把这个数字 +1
         # v2: 大屏 autostart + Hermes/OpenHuman 预装
         # v3: 全部内置智能体桌面图标 + 智能启动(chatop-agent-launch) + 监控大屏图标(察元AI工舱改名)
         # v4: OpenClaw 配置改用 openclaw-tool(tkinter) 桌面图标；移除失效的 agent-builder 图标
         # v5: 察元桌面客户端(Lite) 图标(仅 WITH_CHAYUAN_DESKTOP=1 构建的镜像有该 .desktop)
         # v6: 桌面加固 autostart(chatop-desktop-tweak) + 「退出全屏」图标(chatop-unfullscreen)
         # v7: 自愈磁盘满写残的 0 字节种子文件（修 Hermes 等因 utils.py 被截断而打不开）；
         #     播种失败(磁盘满)不再误写哨兵，保证下次开机重试直到补全
         # v8: 自愈提到版本哨兵早退之前，改为每次开机恒跑——0 字节截断与版本无关，可能发生在
         #     播种完成之后；已误写哨兵(have>=WANT)的旧机器也要能被修（2026-07-11 沙盒测试暴露：
         #     v7 把自愈放在早退之后，have>=WANT 的机器根本进不到自愈代码，残文件永远补不回）
HOME="${HOME:-/home/$(id -un)}"
SENT="$HOME/.local/share/chatop/seed-version"

[ -d "$SEED_SRC" ] || exit 0
have="$(cat "$SENT" 2>/dev/null || echo 0)"
case "$have" in ''|*[!0-9]*) have=0;; esac

# 0) 自愈（恒跑，不受版本哨兵约束）：种子里非空、但卷内已是 0 字节的文件——磁盘满时 cp 写残的
#    残文件（cp -an 不覆盖，修不回）。0 字节截断可能发生在播种完成后的任何时刻，与 seed 版本无关，
#    所以必须每次开机都扫一遍，哪怕 have>=WANT。只修「存在且为空、而种子非空」的：不碰用户改过的
#    非空文件，也不碰种子本就为空的文件。纯 shell builtin 判空、只在真需修复时才 fork cp，开销可忽略。
heal_ok=1
heal_n=0
while IFS= read -r rel; do
  rel="${rel#./}"; dst="$HOME/$rel"
  if [ -f "$dst" ] && [ ! -s "$dst" ]; then
    cp -a "$SEED_SRC/$rel" "$dst" 2>/dev/null || heal_ok=0
    if [ -s "$dst" ]; then heal_n=$((heal_n+1)); else heal_ok=0; fi   # 复查：修完仍空=没修上(磁盘还满?)
  fi
done < <(cd "$SEED_SRC" && find . -type f ! -empty -print 2>/dev/null)
[ "$heal_n" -gt 0 ] && echo "[seed] 自愈 $heal_n 个 0 字节残文件"
[ "$heal_ok" = 1 ] || echo "[seed] 自愈未全部成功(疑似磁盘空间不足)，下次启动将重试" >&2

# 版本哨兵：同一版本的「全量补播」只做一次（上面的自愈已独立于此恒跑）。
[ "$have" -ge "$WANT" ] && exit 0

echo "[seed] 播种预装工具 $SEED_SRC -> $HOME (have=$have want=$WANT)"
# 1) 补缺、绝不覆盖：用户数据/已装工具只补不改。cp -an 真出错(如磁盘满 ENOSPC)返回非 0，
#    记下来——播种没成功就绝不写哨兵，否则会像 2026-07-11 那次：磁盘满写残一半却标记完成，
#    残文件(0 字节)从此再也补不回来，Hermes 等智能体永久打不开。全量 cp -an 还能补回被磁盘满
#    整个漏建的文件（自愈只修「存在但空」的，补不了「完全没有」的）——所以版本升级仍要跑一遍。
copy_ok=1
cp -an "$SEED_SRC/." "$HOME/" 2>/dev/null || copy_ok=0
[ "$heal_ok" = 1 ] || copy_ok=0
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
# 只有真正播全了才落哨兵；播种/自愈遇到磁盘满等失败时不写，下次开机自动重试直至补全。
if [ "$copy_ok" = 1 ]; then
  mkdir -p "$(dirname "$SENT")"
  echo "$WANT" > "$SENT"
  echo "[seed] done"
else
  echo "[seed] 播种未完成(疑似磁盘空间不足)，不写版本哨兵，下次启动将重试" >&2
fi
