#!/bin/bash
# 将 KDE Plasma 任务栏中的图标居中显示
# 通过在面板两侧添加灵活间隔器实现
# 通过 autostart 在 KDE 会话启动后执行配置

CONFIG_DIR="/config/.config"
AUTOSTART_DIR="$CONFIG_DIR/autostart"
SCRIPT_PATH="/config/.local/bin/kde-panel-center.sh"

mkdir -p "$AUTOSTART_DIR" "$(dirname "$SCRIPT_PATH")" 2>/dev/null || true

# 创建配置脚本：在面板两侧添加灵活间隔器，使图标居中
cat > "$SCRIPT_PATH" << 'SCRIPT_EOF'
#!/bin/bash
# 在任务栏两侧添加灵活间隔器，使图标居中显示
PLASMA_CFG="$HOME/.config/plasma-org.kde.plasma.desktop-appletsrc"
[ -f "$PLASMA_CFG" ] || exit 0

# 1. 查找 plugin=org.kde.panel 的 containment ID
panel_id=""
current_id=""
while IFS= read -r line; do
  if [[ "$line" =~ ^\[Containments\]\[([0-9]+)\]$ ]]; then
    current_id="${BASH_REMATCH[1]}"
  elif [[ "$line" =~ ^plugin=org\.kde\.(panel|plasma\.panel) ]] && [[ -n "$current_id" ]]; then
    panel_id="$current_id"
    break
  fi
done < "$PLASMA_CFG"

[[ -z "$panel_id" ]] && exit 0

# 2. 从 [Containments][panel_id][General] 中提取 AppletOrder
applet_order=""
in_gen=0
while IFS= read -r line; do
  if [[ "$line" == "[Containments][${panel_id}][General]" ]]; then
    in_gen=1
    continue
  fi
  if [[ "$in_gen" == 1 ]]; then
    if [[ "$line" =~ ^\[ ]]; then
      break
    fi
    if [[ "$line" =~ ^AppletOrder=(.+)$ ]]; then
      applet_order="${BASH_REMATCH[1]}"
      break
    fi
  fi
done < "$PLASMA_CFG"

[[ -z "$applet_order" ]] && exit 0

# 使用不冲突的 ID：9001 左间隔器，9002 右间隔器
SPACER_LEFT=9001
SPACER_RIGHT=9002

# 检查是否已添加
if [[ "$applet_order" == *"$SPACER_LEFT"* ]] && [[ "$applet_order" == *"$SPACER_RIGHT"* ]]; then
  # 已配置，仅重启 plasmashell 使生效
  (kquitapp5 plasmashell 2>/dev/null || kquitapp6 plasmashell 2>/dev/null
   sleep 2
   kstart5 plasmashell 2>/dev/null || kstart6 plasmashell 2>/dev/null) &
  exit 0
fi

# 3. 修改 AppletOrder：左侧间隔器 + 原顺序 + 右侧间隔器
new_order="${SPACER_LEFT};${applet_order};${SPACER_RIGHT}"

# 4. 在 [Containments][panel_id][General] 中替换 AppletOrder
sed -i "/^\[Containments\]\[${panel_id}\]\[General\]/,/^\[/ s|^AppletOrder=.*|AppletOrder=${new_order}|" "$PLASMA_CFG"

# 5. 添加两个间隔器 applet 的配置（若不存在）
for sid in $SPACER_LEFT $SPACER_RIGHT; do
  if ! grep -q "^\[Containments\]\[${panel_id}\]\[Applets\]\[${sid}\]" "$PLASMA_CFG" 2>/dev/null; then
    cat >> "$PLASMA_CFG" << SPACER

[Containments][${panel_id}][Applets][${sid}]
immutability=1
plugin=org.kde.plasma.panelspacer
SPACER
  fi
done

# 6. 重启 plasmashell 使配置生效
(kquitapp5 plasmashell 2>/dev/null || kquitapp6 plasmashell 2>/dev/null
 sleep 2
 kstart5 plasmashell 2>/dev/null || kstart6 plasmashell 2>/dev/null) &
SCRIPT_EOF

chmod +x "$SCRIPT_PATH" 2>/dev/null

# 创建 autostart 条目（延迟 8 秒等待 plasma 创建配置）
cat > "$AUTOSTART_DIR/kde-panel-center.desktop" << EOF
[Desktop Entry]
Type=Application
Name=KDE Panel Center
Comment=Center taskbar icons in Plasma panel
Exec=bash -c 'sleep 8; $SCRIPT_PATH'
Hidden=false
NoDisplay=true
X-GNOME-Autostart-enabled=true
EOF

# 同时写入 defaults 以便新用户
for target in /defaults /config; do
  [ -d "$target" ] || continue
  mkdir -p "$target/.config/autostart" "$target/.local/bin" 2>/dev/null || true
  cp -f "$AUTOSTART_DIR/kde-panel-center.desktop" "$target/.config/autostart/" 2>/dev/null || true
  cp -f "$SCRIPT_PATH" "$target/.local/bin/kde-panel-center.sh" 2>/dev/null || true
  chmod +x "$target/.local/bin/kde-panel-center.sh" 2>/dev/null || true
done 2>/dev/null

echo "**** KDE panel center autostart configured ****"
