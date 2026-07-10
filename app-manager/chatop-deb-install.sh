#!/usr/bin/env bash
# chatop-deb-install <id> <deb_url> <显示名> [exec_args]
# 官方 .deb 免 root 安装：chatop-fetch 下载 → dpkg -x 解包到 ~/Applications/<id>/root(不跑 maintainer 脚本、不需 root)
# → 定位主程序与图标 → 生成稳定 run.sh + chatop-<id>.desktop(菜单/桌面)。
# 与 AppImage 路径同布局($HOME/Applications/<id> + chatop-<id>.desktop)，卸载共用 gui-uninstall.sh。
# <deb_url> 传字面 URL；动态链请在 catalog 的 install 里先 resolver 出 URL 再调本脚本。
# --dry-run 作为 exec_args 时只打印将写入的 run.sh Exec 行，不下载(供测试)。
set -euo pipefail
ID="${1:?need id}"; URL="${2:?need deb url}"; NAME="${3:-$1}"; ARGS="${4:-}"
FETCH="${CHATOP_FETCH:-chatop-fetch}"
APPDIR="$HOME/Applications/$ID"; ROOT="$APPDIR/root"

find_bin() {  # 从解包出的 .desktop 的 Exec 里取首个 token，解析成 $ROOT 下绝对路径
  local desk exec_line bin
  desk="$(find "$ROOT/usr/share/applications" "$ROOT/opt" -maxdepth 4 -name '*.desktop' 2>/dev/null | head -1 || true)"
  if [ -n "$desk" ]; then
    exec_line="$(sed -n 's/^Exec=//p' "$desk" | head -1)"
    bin="$(echo "$exec_line" | awk '{print $1}' | sed 's/%[A-Za-z]//g')"
  fi
  # Exec 里是绝对路径(/opt/... 或 /usr/bin/...) → 前缀 $ROOT；否则在 $ROOT 里搜同名可执行
  if [ -n "${bin:-}" ] && [ -x "$ROOT$bin" ]; then echo "$ROOT$bin"; return; fi
  if [ -n "${bin:-}" ] && [ -x "$ROOT/usr/bin/$(basename "$bin")" ]; then echo "$ROOT/usr/bin/$(basename "$bin")"; return; fi
  find "$ROOT/opt" "$ROOT/usr" -maxdepth 5 -type f -perm -u+x 2>/dev/null \
    | grep -iE "/(${ID}|$(basename "${bin:-$ID}"))$" | head -1
}
find_icon() {
  find "$ROOT/usr/share/icons" "$ROOT/opt" "$ROOT/usr/share/pixmaps" -maxdepth 6 \
    \( -iname '*.png' -o -iname '*.svg' \) 2>/dev/null \
    | grep -iE "(${ID}|256|scalable|128)" | head -1
}

if [ "$ARGS" = "--dry-run" ]; then
  echo "would: dpkg -x <deb> $ROOT ; run.sh -> exec <bin> (args stripped in dry-run)"
  exit 0
fi

TMP="$(mktemp -d)/${ID}.deb"
mkdir -p "$APPDIR" "$HOME/.local/share/applications" "$HOME/Desktop"
echo "下载 $NAME ..."; "$FETCH" "$URL" "$TMP"
echo "解包(dpkg -x, 免 root) ..."; rm -rf "$ROOT"; mkdir -p "$ROOT"; dpkg -x "$TMP" "$ROOT"; rm -f "$TMP"

BIN="$(find_bin || true)"
[ -n "$BIN" ] && [ -x "$BIN" ] || { echo "未能在 deb 里定位主程序，安装失败" >&2; rm -rf "$APPDIR"; exit 1; }
ICON="$(find_icon || true)"; [ -n "$ICON" ] || ICON="/usr/share/kasmvnc/www/app-icons/apps-icon.svg"

# 稳定启动脚本：补 deb 内置 lib 到 LD_LIBRARY_PATH，Electron 沙箱在容器内需靠 args 传 --no-sandbox
cat > "$APPDIR/run.sh" <<EOF
#!/usr/bin/env bash
export LD_LIBRARY_PATH="$ROOT/opt:$ROOT/usr/lib:\${LD_LIBRARY_PATH:-}"
exec "$BIN" $ARGS "\$@"
EOF
chmod +x "$APPDIR/run.sh"

DESKTOP="$HOME/.local/share/applications/chatop-$ID.desktop"
cat > "$DESKTOP" <<EOF
[Desktop Entry]
Name=$NAME
Exec=$APPDIR/run.sh %U
Icon=$ICON
Type=Application
Categories=Utility;
Terminal=false
EOF
chmod +x "$DESKTOP"; cp "$DESKTOP" "$HOME/Desktop/chatop-$ID.desktop" 2>/dev/null || true
echo "完成：$NAME 已安装到 $APPDIR（菜单/桌面已生成）"
