#!/bin/bash
# chatop-unfullscreen —— 退出全屏，让顶栏(菜单+任务栏)和底部 dock 重新可见。
#
# 背景：xfwm4 会把带 _NET_WM_STATE_FULLSCREEN 的窗口抬到 dock 层之上，两条面板同时被盖住。
# 若此时 F11 被外层浏览器吃掉，用户在容器里就没有退出手段了。本脚本是兜底逃生口。
#
#   chatop-unfullscreen          摘掉当前活动窗口的全屏
#   chatop-unfullscreen --all    摘掉所有窗口的全屏
set -u
export DISPLAY="${DISPLAY:-:1}"

unfs_all() {
  wmctrl -l | awk '{print $1}' | while read -r w; do
    wmctrl -i -r "$w" -b remove,fullscreen 2>/dev/null || true
  done
}

if [ "${1:-}" = "--all" ]; then
  unfs_all
else
  # 没有活动窗口时 wmctrl 会失败，退回全量处理
  wmctrl -r :ACTIVE: -b remove,fullscreen 2>/dev/null || unfs_all
fi
