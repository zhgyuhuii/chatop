# app-manager/chatop-fetch-bundle.sh
# 用法: chatop-fetch-bundle.sh <name> <version>
# 从 CHATOP_BUNDLE_BASE 下载 <name>-<version>.{tar.gz,json} 到 updater inbox。
# 支持 file:// 与 http(s)://；http 走 curl（复用 mirrors 习惯）。
set -euo pipefail
NAME="$1"; VER="$2"
INBOX="${CHATOP_UPDATER_INBOX:-$HOME/.chatop/inbox}"
BASE="${CHATOP_BUNDLE_BASE:?set CHATOP_BUNDLE_BASE (e.g. https://mirror/chatop/bundles)}"
mkdir -p "$INBOX"
fetch() { # $1=filename
  local url="$BASE/$1" dst="$INBOX/$1"
  case "$url" in
    file://*) cp "${url#file://}" "$dst" ;;
    *) curl -fsSL --retry 3 -o "$dst" "$url" ;;
  esac
}
fetch "${NAME}-${VER}.tar.gz"
fetch "${NAME}-${VER}.json"
echo "fetched ${NAME}-${VER} into $INBOX"
