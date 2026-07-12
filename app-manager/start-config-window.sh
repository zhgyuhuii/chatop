#!/bin/bash
# 智能体配置中心窗口：打开 station 大屏的 #/config 路由（同一前端，hash 路由切页）。
# station 未就绪时回退拉起 tkinter 经典配置器，保证「配置」入口永不打不开。
# 加固（2026-07-12）：
#  - 清理上次容器重建/崩溃残留的 Chrome SingletonLock，避免顶着残锁开窗异常；
#  - station 冷启动可能较慢（venv + 首次拉起），等待放宽到 ~90s，尽量走 Web 配置中心而非
#    回退 tkinter（经典配置器交互弱且历史上有 Tk 段错误坑）。
PROFILE="$HOME/.config/chatop-config-chrome"
rm -f "$PROFILE"/Singleton* 2>/dev/null
for i in $(seq 1 90); do
  if curl -fsS http://127.0.0.1:8787/dashboard/api/system >/dev/null 2>&1; then
    exec /usr/bin/google-chrome-stable --no-sandbox --user-data-dir="$PROFILE" \
      --app="http://127.0.0.1:8787/dashboard/#/config" \
      --start-maximized --no-first-run --no-default-browser-check
  fi
  sleep 1
done
exec bash /opt/openclaw-tool/launch-config-gui.sh
