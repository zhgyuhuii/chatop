#!/bin/bash
# 禁用 PackageKit，避免 GUI 安装程序报错：
#   "Failed to execute program org.freedesktop.PackageKit: Permission denied"
# 容器中 PackageKit 无法正常运行，请使用终端安装：sudo apt update && sudo apt install 软件名

# 1. 禁用 apt 的 PackageKit 集成
for f in /etc/apt/apt.conf.d/20packagekit /etc/apt/apt.conf.d/99packagekit; do
  [ -f "$f" ] && mv "$f" "${f}.disabled" 2>/dev/null && echo "**** Disabled apt PackageKit: $f ****"
done

# 2. 移除 PackageKit D-Bus 服务，避免 GUI 尝试启动它
for f in /usr/share/dbus-1/services/org.freedesktop.PackageKit.service \
         /usr/share/dbus-1/services/org.freedesktop.packagekit.service; do
  if [ -f "$f" ]; then
    mv "$f" "${f}.disabled" 2>/dev/null && echo "**** Disabled PackageKit D-Bus: $f ****"
  fi
done

# 3. 在桌面添加快捷方式：用终端安装软件
for target in /defaults /config; do
  mkdir -p "$target/Desktop" 2>/dev/null || continue
  cat > "$target/Desktop/安装软件.desktop" << 'EOF'
[Desktop Entry]
Type=Application
Name=安装软件（终端）
Comment=在容器中请使用终端安装：sudo apt install 软件名
Exec=konsole -e bash -c "echo '=== 安装软件请使用终端命令 ==='; echo '  sudo apt update'; echo '  sudo apt install 软件名'; echo ''; exec bash"
Icon=system-software-install
Terminal=false
Categories=System;
EOF
  chmod +x "$target/Desktop/安装软件.desktop" 2>/dev/null || true
done

echo "**** PackageKit disabled. Use terminal: sudo apt install <package> ****"
