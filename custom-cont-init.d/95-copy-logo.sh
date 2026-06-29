#!/bin/bash
# 运行时 logo 覆盖：若挂载了 logo.png，复制到 www 和各 dashboard，供 init-nginx 使用
# 挂载方式：-v ./logo.png:/custom-logo/logo.png 或 -v ./assets:/custom-logo（assets 内含 logo.png）
if [ -d /var/run/s6/container_environment ]; then
  for f in /var/run/s6/container_environment/*; do
    [ -f "$f" ] && export "$(basename "$f")=$(cat "$f" 2>/dev/null)"
  done
fi

LOGO_SRC="/custom-logo/logo.png"
[ -n "${LOGO_PATH}" ] && [ -f "${LOGO_PATH}" ] && LOGO_SRC="${LOGO_PATH}"

if [ -f "$LOGO_SRC" ]; then
  for dir in /usr/share/selkies/www \
    /usr/share/selkies/selkies-dashboard \
    /usr/share/selkies/selkies-dashboard-zinc \
    /usr/share/selkies/selkies-dashboard-wish; do
    [ -d "$dir" ] && cp "$LOGO_SRC" "$dir/logo.png" && cp "$LOGO_SRC" "$dir/icon.png" 2>/dev/null || true
  done
  echo "**** Custom logo applied from $LOGO_SRC ****"
fi
