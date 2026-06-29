#!/bin/bash
# 应用 MacVentura 主题、WhiteSur 图标，并放置 OpenClaw 配置桌面快捷方式
# 参考 xiami 项目 custom-cont-init.d/98-create-user-dirs

mkdir -p /config/.config /config/Desktop /config/.config/autostart

# 确定默认浏览器
BROWSER_DESKTOP=""
for d in chromium.desktop chromium-browser.desktop firefox.desktop org.kde.falkon.desktop; do
  [ -f /usr/share/applications/$d ] && BROWSER_DESKTOP=$d && break
done
[ -z "$BROWSER_DESKTOP" ] && BROWSER_DESKTOP="chromium.desktop"

# 强制写入 KDE 主题配置（MacVentura-Dark + WhiteSur 图标）
cat > /config/.config/kdeglobals << KDE_EOF
[General]
ColorScheme=MacVenturaDark
BrowserApplication=$BROWSER_DESKTOP

[KDE]
LookAndFeelPackage=com.github.vinceliuice.MacVentura-Dark

[Icons]
Theme=WhiteSur
KDE_EOF

# 窗口装饰主题
cat > /config/.config/kwinrc << 'KWIN_EOF'
[org.kde.kdecoration2]
theme=MacVentura
KWIN_EOF

# 首次登录时强制应用主题（解决 base 覆盖 config 的时序问题）
cat > /config/.config/autostart/apply-macventura-theme.desktop << 'AUTOSTART_EOF'
[Desktop Entry]
Type=Application
Name=Apply MacVentura-Dark Theme
Exec=sh -c "sleep 20 && (plasma-apply-lookandfeel -a com.github.vinceliuice.MacVentura-Dark --resetLayout 2>/dev/null || lookandfeeltool -a com.github.vinceliuice.MacVentura-Dark --resetLayout 2>/dev/null); rm -f /config/.config/autostart/apply-macventura-theme.desktop"
Hidden=false
NoDisplay=true
X-GNOME-Autostart-enabled=true
AUTOSTART_EOF

# OpenClaw 配置桌面快捷方式
if [ -f /usr/share/applications/openclaw-tool.desktop ]; then
  cp /usr/share/applications/openclaw-tool.desktop /config/Desktop/ 2>/dev/null || true
fi

# 同时写入 defaults 以便新用户
for target in /defaults /config; do
  [ -d "$target" ] || continue
  mkdir -p "$target/.config" "$target/Desktop" 2>/dev/null || true
  [ -f /usr/share/applications/openclaw-tool.desktop ] && cp /usr/share/applications/openclaw-tool.desktop "$target/Desktop/" 2>/dev/null || true
  cat > "$target/.config/ksplashrc" << 'KSPLASH_EOF'
[KSplash]
Engine=KSplashQML
Theme=org.webtop.custom-splash
KSPLASH_EOF
done 2>/dev/null

# 设置所有权
if [ -n "${PUID}" ] && [ -n "${PGID}" ]; then
  chown -R ${PUID}:${PGID} /config/.config /config/Desktop 2>/dev/null || true
fi

echo "**** MacVentura theme + OpenClaw icon configured ****"
