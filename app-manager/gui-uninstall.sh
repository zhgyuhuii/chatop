#!/usr/bin/env bash
# 卸载用户级 AppImage 类 GUI：删解包目录 + 菜单/桌面快捷方式。
# 用法: gui-uninstall.sh <id>
set -euo pipefail
ID="${1:?need id}"
rm -rf "$HOME/Applications/$ID" \
       "$HOME/.local/share/applications/chatop-$ID.desktop" \
       "$HOME/Desktop/chatop-$ID.desktop"
echo "$ID 已卸载"
