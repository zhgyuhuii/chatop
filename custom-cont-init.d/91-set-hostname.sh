#!/bin/bash
# 强制设置主机名，避免 KDE 用户图标悬停显示容器 ID（如 abc@3579d035063d）
# 需在 docker-compose 中设置 CUSTOM_HOSTNAME 环境变量

if [ -d /var/run/s6/container_environment ]; then
  for f in /var/run/s6/container_environment/*; do
    [ -f "$f" ] && export "$(basename "$f")=$(cat "$f" 2>/dev/null)"
  done
fi

HOST="${CUSTOM_HOSTNAME:-chatop}"
echo "**** Setting hostname to ${HOST} ****"
echo "$HOST" > /etc/hostname
hostname "$HOST" 2>/dev/null || true
