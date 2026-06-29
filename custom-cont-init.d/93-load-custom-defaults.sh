#!/bin/bash
# 构建时界面定制：首次启动时，若 /config 为空，将 custom-defaults 复制到 /config
# 实现构建镜像时预置界面配置（主题、任务栏、壁纸等）

CUSTOM_DEFAULTS="/custom-defaults"

[ -d "$CUSTOM_DEFAULTS" ] || exit 0

# 仅当 /config 为空时复制（首次运行，新 volume）
if [ ! -d /config ] || [ ! -w /config ]; then
  exit 0
fi
# 若已有 plasma 配置，说明用户已运行过，不覆盖
if [ -f /config/.config/plasma-org.kde.plasma.desktop-appletsrc ] 2>/dev/null; then
  exit 0
fi

echo "**** Loading custom defaults (first run) ****"
# 使用 cp -rn 不覆盖已存在文件；若 custom-defaults 有子目录需递归复制
if [ -d "$CUSTOM_DEFAULTS/.config" ] || [ -d "$CUSTOM_DEFAULTS/.local" ] || [ -d "$CUSTOM_DEFAULTS/Desktop" ]; then
  for sub in .config .local Desktop; do
    [ -d "$CUSTOM_DEFAULTS/$sub" ] && cp -rn "$CUSTOM_DEFAULTS/$sub" /config/ 2>/dev/null || true
  done
else
  cp -rn "$CUSTOM_DEFAULTS"/* /config/ 2>/dev/null || true
fi

# 确保权限（abc 用户）
if [ -d /config ] && command -v chown &>/dev/null; then
  chown -R abc:abc /config 2>/dev/null || true
fi

echo "**** Custom defaults applied ****"
