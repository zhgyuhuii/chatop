#!/bin/bash
# 系统与用户痕迹深度清理脚本 - 最佳实践
set -e
echo "========== 开始系统深度清理 =========="

# 1) 浏览器与通讯软件痕迹
echo "[1/6] 清理浏览器与通讯软件..."
rm -rf /home/kasm-user/.cache/google-chrome/*
rm -rf /home/kasm-user/.cache/mozilla/*
rm -rf /home/kasm-user/.cache/thunderbird/*
rm -rf /home/kasm-user/.config/google-chrome/Default/Cache 2>/dev/null
rm -rf /home/kasm-user/.config/google-chrome/Default/Code\ Cache 2>/dev/null
rm -rf /home/kasm-user/.config/google-chrome/Default/GPUCache 2>/dev/null
rm -rf /home/kasm-user/.config/google-chrome/Default/Service\ Worker 2>/dev/null
rm -rf /home/kasm-user/.config/google-chrome/Default/Cached\ Data 2>/dev/null
rm -rf /home/kasm-user/.config/google-chrome/Default/Cookies 2>/dev/null
rm -rf /home/kasm-user/.config/google-chrome/Default/History 2>/dev/null
rm -rf /home/kasm-user/.config/google-chrome/Default/Local\ Storage 2>/dev/null
rm -rf /home/kasm-user/.config/google-chrome/Default/Session\ Storage 2>/dev/null
rm -rf /home/kasm-user/.config/google-chrome/Default/Web\ Data 2>/dev/null
rm -rf /home/kasm-user/.mozilla/firefox/*.default*/cache2 2>/dev/null
rm -rf /home/kasm-user/.mozilla/firefox/*.default*/cookies.sqlite 2>/dev/null
rm -rf /home/kasm-user/.mozilla/firefox/*.default*/places.sqlite 2>/dev/null
rm -rf /home/kasm-user/.mozilla/firefox/*.default*/storage 2>/dev/null
rm -rf /home/kasm-user/.config/cef_user_data/* 2>/dev/null
echo "  浏览器/通讯缓存已清理"

# 2) Cursor 本地日志、缓存、聊天与项目状态
echo "[2/6] 清理 Cursor 本地数据..."
rm -rf /home/kasm-user/.config/Cursor/Cache
rm -rf /home/kasm-user/.config/Cursor/CachedData
rm -rf /home/kasm-user/.config/Cursor/CachedProfilesData
rm -rf "/home/kasm-user/.config/Cursor/Code Cache"
rm -rf /home/kasm-user/.config/Cursor/Crashpad
rm -rf /home/kasm-user/.config/Cursor/Backups
rm -rf /home/kasm-user/.config/Cursor/blob_storage
rm -rf /home/kasm-user/.config/Cursor/logs
rm -rf /home/kasm-user/.config/Cursor/sentry
rm -rf /home/kasm-user/.config/Cursor/GPUCache
rm -rf /home/kasm-user/.config/Cursor/snapshots
rm -rf "/home/kasm-user/.config/Cursor/Service Worker"
rm -rf /home/kasm-user/.config/Cursor/WebStorage
rm -rf "/home/kasm-user/.config/Cursor/Session Storage"
rm -rf "/home/kasm-user/.config/Cursor/Local Storage"
rm -rf /home/kasm-user/.config/Cursor/User/History
rm -rf /home/kasm-user/.config/Cursor/User/workspaceStorage
rm -rf /home/kasm-user/.config/Cursor/User/globalStorage
rm -rf /home/kasm-user/.config/Cursor/process-monitor
rm -rf /home/kasm-user/.config/Cursor/DawnGraphiteCache
rm -rf /home/kasm-user/.config/Cursor/DawnWebGPUCache
rm -rf /home/kasm-user/.cursor/chats
rm -rf /home/kasm-user/.cursor/ai-tracking
rm -rf /home/kasm-user/.cursor/projects
rm -f /home/kasm-user/.cursor/statsig-cache.json
rm -rf /home/kasm-user/.cache/cursor-compile-cache
# 清除 Cursor 内 Cookies/Trust Tokens 等
rm -f /home/kasm-user/.config/Cursor/Cookies /home/kasm-user/.config/Cursor/Cookies-journal 2>/dev/null
rm -f /home/kasm-user/.config/Cursor/Trust\ Tokens /home/kasm-user/.config/Cursor/Trust\ Tokens-journal 2>/dev/null
echo "  Cursor 日志/缓存/聊天/项目状态已清理"

# 3) 用户 Shell 与脚本历史
echo "[3/6] 清理用户历史痕迹..."
cat /dev/null > /home/kasm-user/.bash_history 2>/dev/null
rm -f /home/kasm-user/.python_history /home/kasm-user/.node_repl_history 2>/dev/null
rm -rf /home/kasm-user/.local/share/recently-used.xbel 2>/dev/null
rm -rf /home/kasm-user/.config/Thunar/recents.xbel 2>/dev/null
echo "  用户历史已清理"

# 4) 通用缓存与缩略图
echo "[4/6] 清理通用缓存与缩略图..."
rm -rf /home/kasm-user/.cache/thumbnails/*
rm -rf /home/kasm-user/.cache/fontconfig
rm -rf /home/kasm-user/.cache/gstreamer-1.0
rm -rf /home/kasm-user/.cache/mesa_shader_cache
rm -rf /home/kasm-user/.cache/mesa_shader_cache_db
rm -rf /home/kasm-user/.cache/sublime-text
rm -rf /home/kasm-user/.cache/remmina
rm -rf /home/kasm-user/.cache/at-spi
rm -rf /home/kasm-user/.cache/dconf
rm -rf /home/kasm-user/.cache/ibus
rm -rf /home/kasm-user/.cache/Microsoft
rm -rf /home/kasm-user/.cache/sessions
rm -rf /home/kasm-user/.cache/doc
rm -rf /home/kasm-user/.cache/gvfs
rm -rf /home/kasm-user/.cache/gvfsd
echo "  通用缓存已清理"

# 5) 系统临时文件与包缓存 (仅删除当前用户可写的)
echo "[5/6] 清理系统临时与包缓存..."
find /tmp -maxdepth 1 -user "$(whoami)" -exec rm -rf {} \; 2>/dev/null || true
find /var/tmp -maxdepth 1 -user "$(whoami)" -exec rm -rf {} \; 2>/dev/null || true
rm -rf /tmp/.X11-unix 2>/dev/null || true
apt-get clean 2>/dev/null || true
apt-get autoclean 2>/dev/null || true
# 可选: 删除未使用的包 (会提示确认，这里用 -y)
apt-get autoremove -y 2>/dev/null || true
journalctl --vacuum-time=1d 2>/dev/null || true
echo "  系统临时与包缓存已清理"

# 6) 下载目录中的临时/更新包 (仅删除常见缓存与安装包)
echo "[6/6] 清理下载目录中的缓存与更新包..."
find /home/kasm-user/下载 /home/kasm-user/Downloads -maxdepth 2 -type f \( -name "*.deb" -o -name "*.rpm" -o -name "*.tar.gz" -o -name "*.zip" -o -name "*cache*" -o -name "*update*" \) 2>/dev/null | head -50
# 不自动删用户下载文件，仅报告。若需清空下载目录可取消下一行注释
# rm -rf /home/kasm-user/下载/* /home/kasm-user/Downloads/*
echo "  清理脚本执行完成"
echo "========== 请手动执行: cursor agent logout =========="
