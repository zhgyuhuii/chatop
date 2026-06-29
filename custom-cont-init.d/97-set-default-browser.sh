#!/bin/bash
# 设置默认浏览器并固定到任务栏/桌面，修复 "无法读取文件 preferred://browser"
# 检测可用浏览器：chromium-browser（Ubuntu）或 chromium（Alpine）或 firefox

BROWSER_DESKTOP=""
for candidate in chromium-browser chromium firefox firefox-esr; do
  if [ -f "/usr/share/applications/${candidate}.desktop" ]; then
    BROWSER_DESKTOP="${candidate}.desktop"
    break
  fi
done
# 部分发行版使用 chromium-browser-chromium.desktop
if [ -z "$BROWSER_DESKTOP" ] && [ -f /usr/share/applications/chromium-browser-chromium.desktop ]; then
  BROWSER_DESKTOP="chromium-browser-chromium.desktop"
fi

if [ -z "$BROWSER_DESKTOP" ]; then
  echo "**** No browser .desktop found, skipping default browser setup ****"
  exit 0
fi

for target in /defaults /config; do
  mkdir -p "$target/.config" "$target/.local/share/applications" "$target/Desktop" 2>/dev/null || continue

  # 1. mimeapps.list - 设置 http/https 默认打开方式
  mimeapps="$target/.config/mimeapps.list"
  touch "$mimeapps" 2>/dev/null || continue
  if ! grep -q '^\[Default Applications\]' "$mimeapps" 2>/dev/null; then
    echo -e "\n[Default Applications]\nx-scheme-handler/http=${BROWSER_DESKTOP}\nx-scheme-handler/https=${BROWSER_DESKTOP}" >> "$mimeapps"
  else
    sed -i "s|^x-scheme-handler/http=.*|x-scheme-handler/http=${BROWSER_DESKTOP}|" "$mimeapps" 2>/dev/null || true
    sed -i "s|^x-scheme-handler/https=.*|x-scheme-handler/https=${BROWSER_DESKTOP}|" "$mimeapps" 2>/dev/null || true
    grep -q 'x-scheme-handler/http=' "$mimeapps" 2>/dev/null || echo "x-scheme-handler/http=${BROWSER_DESKTOP}" >> "$mimeapps"
    grep -q 'x-scheme-handler/https=' "$mimeapps" 2>/dev/null || echo "x-scheme-handler/https=${BROWSER_DESKTOP}" >> "$mimeapps"
  fi

  # 2. kdeglobals - KDE 默认浏览器（preferred://browser 依赖此配置）
  kdeglobals="$target/.config/kdeglobals"
  mkdir -p "$(dirname "$kdeglobals")"
  if [ -f "$kdeglobals" ]; then
    if grep -q '^\[General\]' "$kdeglobals"; then
      sed -i "/^\[General\]/,/^\[/ s|^BrowserApplication=.*|BrowserApplication=${BROWSER_DESKTOP}|" "$kdeglobals" 2>/dev/null || true
      grep -q '^BrowserApplication=' "$kdeglobals" || sed -i "/^\[General\]/a BrowserApplication=${BROWSER_DESKTOP}" "$kdeglobals"
    else
      echo -e "[General]\nBrowserApplication=${BROWSER_DESKTOP}" >> "$kdeglobals"
    fi
  else
    echo -e "[General]\nBrowserApplication=${BROWSER_DESKTOP}" > "$kdeglobals"
  fi

  # 3. 桌面快捷方式 - 复制浏览器 .desktop 到桌面
  if [ -f "/usr/share/applications/${BROWSER_DESKTOP}" ]; then
    cp "/usr/share/applications/${BROWSER_DESKTOP}" "$target/Desktop/${BROWSER_DESKTOP}" 2>/dev/null || true
    chmod +x "$target/Desktop/${BROWSER_DESKTOP}" 2>/dev/null || true
  fi
done 2>/dev/null || true

# 4. 以 abc 用户执行 xdg-settings（若存在且可写 /config）
if [ -d /config ] && [ -w /config ] && command -v xdg-settings &>/dev/null; then
  su abc -s /bin/bash -c "export HOME=/config; xdg-settings set default-web-browser ${BROWSER_DESKTOP}" 2>/dev/null || true
fi

echo "**** Default browser set to ${BROWSER_DESKTOP} ****"
