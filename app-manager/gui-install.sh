#!/usr/bin/env bash
# 用户级安装 AppImage 类 GUI：下载 → --appimage-extract 到 ~/Applications/<id>/squashfs-root
# → 生成开始菜单/桌面 .desktop。全程以运行用户(kasm-user)身份、装在 home 卷 → 免 root + 持久化。
# 容器内 FUSE 被禁(无 /dev/fuse)，故用 --appimage-extract 解包跑，不直接挂载。
#
# 用法: gui-install.sh <id> <appimage_url|CURSOR_API> <display_name> [exec_args]
set -euo pipefail
ID="${1:?need id}"; URL="${2:?need url}"; NAME="${3:-$1}"; ARGS="${4:-}"

# Cursor 的下载地址是动态的，需先解析官方 API
if [ "$URL" = "CURSOR_API" ]; then
  echo "解析 Cursor 最新下载地址 ..."
  URL="$(curl -fsSL 'https://www.cursor.com/api/download?platform=linux-x64&releaseTrack=latest' \
        | grep -oE 'https://[^"]+\.AppImage' | head -1)"
  [ -n "$URL" ] || { echo "无法解析 Cursor 下载地址" >&2; exit 1; }
fi

APPDIR="$HOME/Applications/$ID"
TMP="$(mktemp -d)/${ID}.AppImage"
mkdir -p "$HOME/Applications" "$HOME/.local/share/applications" "$HOME/Desktop"

echo "下载 $NAME ..."
# 走 chatop-fetch(GitHub 多域名镜像回退)；不可用时回退直连 curl
if command -v chatop-fetch >/dev/null 2>&1; then
  chatop-fetch "$URL" "$TMP"
else
  curl -fSL --progress-bar -o "$TMP" "$URL"
fi
chmod +x "$TMP"

echo "解包到 $APPDIR ..."
rm -rf "$APPDIR"; mkdir -p "$APPDIR"
( cd "$APPDIR" && "$TMP" --appimage-extract >/dev/null )
rm -f "$TMP"

RUN="$APPDIR/squashfs-root/AppRun"
chmod +x "$RUN" 2>/dev/null || true

# 取一个图标（AppImage 解包后通常根目录有 .png/.DirIcon）
ICON="$(find "$APPDIR/squashfs-root" -maxdepth 2 -iname '*.png' 2>/dev/null | head -1 || true)"
[ -n "$ICON" ] || ICON="$APPDIR/squashfs-root/.DirIcon"

DESKTOP="$HOME/.local/share/applications/chatop-$ID.desktop"
cat > "$DESKTOP" <<EOF
[Desktop Entry]
Name=$NAME
Exec=$RUN $ARGS %U
Icon=$ICON
Type=Application
Categories=Development;
Terminal=false
EOF
chmod +x "$DESKTOP"
cp "$DESKTOP" "$HOME/Desktop/chatop-$ID.desktop" 2>/dev/null || true

echo "完成：$NAME 已安装到 $APPDIR（开始菜单/桌面已生成快捷方式）"
