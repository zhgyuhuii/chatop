#!/bin/bash
# 1. 禁用开机自动打开的 st 终端
# 2. 修复 Konsole 配置：将空 shell 命令设为 /bin/bash，消除警告

# 禁用 st 自动启动（在 autostart 中创建 Hidden=true 覆盖）
# /defaults 用于首次复制到用户目录；/config 为 abc 用户主目录
for target in /defaults /config; do
  mkdir -p "$target/.config/autostart" 2>/dev/null || continue
  if [ -f /usr/share/applications/st.desktop ]; then
    cp /usr/share/applications/st.desktop "$target/.config/autostart/st.desktop" 2>/dev/null || true
    sed -i '/^\[Desktop Entry\]/a Hidden=true' "$target/.config/autostart/st.desktop" 2>/dev/null || true
  else
    cat > "$target/.config/autostart/st.desktop" 2>/dev/null << 'EOF'
[Desktop Entry]
Type=Application
Name=st
Hidden=true
EOF
  fi
done 2>/dev/null || true

# 修复 Konsole 配置：确保默认 profile 使用 /bin/bash
KONSOLE_PROFILE='Custom.profile'
for target in /defaults /config; do
  mkdir -p "$target/.local/share/konsole" 2>/dev/null || continue
  profile_path="$target/.local/share/konsole/$KONSOLE_PROFILE"
    if [ ! -f "$profile_path" ] || ! grep -q '^Command=' "$profile_path" 2>/dev/null; then
      if [ -f "$profile_path" ]; then
        # 若已有 profile 但 Command 为空，则添加或修正
        if grep -q '^\[General\]' "$profile_path"; then
          sed -i '/^\[General\]/,/^\[/ s/^Command=.*/Command=\/bin\/bash/' "$profile_path"
          grep -q '^Command=' "$profile_path" || sed -i '/^\[General\]/a Command=/bin/bash' "$profile_path"
        else
          echo -e "[General]\nCommand=/bin/bash" >> "$profile_path"
        fi
      else
        # 创建新 profile
        cat > "$profile_path" << 'KONSOLE_EOF'
[General]
Command=/bin/bash
Name=Custom
KONSOLE_EOF
      fi
    fi
    # 设为默认 profile
    mkdir -p "$target/.config"
    konsolerc="$target/.config/konsolerc"
    if [ -f "$konsolerc" ]; then
      sed -i 's/^DefaultProfile=.*/DefaultProfile=Custom.profile/' "$konsolerc" 2>/dev/null || true
    else
      echo -e "[Desktop Entry]\nDefaultProfile=Custom.profile" > "$konsolerc"
    fi
done 2>/dev/null || true

echo "**** Terminal autostart and Konsole profile fixed ****"
