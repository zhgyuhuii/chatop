#!/bin/bash
# chatop-desktop-tweak —— 桌面默认行为加固，由 xfce 会话内的 autostart 拉起（此时 xfconfd + DBUS 已就绪）。
#
# 为什么用 xfconf-query 而不是直接改 XML：
#   vnc_startup.sh 先起 xfce(:244)、后跑 custom_startup(:642)，脚本改磁盘 XML 时 xfconfd 已把配置读进内存，
#   会话退出时还会覆写回去。必须跟活着的 xfconfd 对话。
#
# 快捷键用 `-n`（属性不存在才创建），用户后续改掉不会被反复覆盖。
# 哨兵必须与它守护的 xfconf 配置同生共死：镜像把 XDG_CONFIG_HOME 指到 /tmp，容器重建时配置会丢，
# 哨兵若放在持久的 $HOME 里，重建后就成了「配置没了、哨兵还在」，加固永不重跑。
set -u
export DISPLAY="${DISPLAY:-:1}"

WANT=1
SENT="${XDG_CONFIG_HOME:-$HOME/.config}/chatop/desktop-tweak-version"
have="$(cat "$SENT" 2>/dev/null || echo 0)"
case "$have" in ''|*[!0-9]*) have=0;; esac
[ "$have" -ge "$WANT" ] && exit 0

command -v xfconf-query >/dev/null 2>&1 || exit 0

# xfconfd 可能比 autostart 晚一点点就绪，等它
for _ in $(seq 1 15); do
  xfconf-query -c xfce4-panel -l >/dev/null 2>&1 && break
  sleep 1
done
xfconf-query -c xfce4-panel -l >/dev/null 2>&1 || exit 0

# 1) 底部 dock 常显：XFCE 出厂默认把 panel-2 设成 autohide(只留 3px 触发条)，
#    在 VNC 远程桌面里那条几乎点不中。查叶子属性而非 /panels/panel-2 分支节点——
#    分支节点是 empty 类型，xfconf-query 会返回非零，守卫会误判成「面板不存在」。
if xfconf-query -c xfce4-panel -p /panels/panel-2/autohide-behavior >/dev/null 2>&1; then
  xfconf-query -c xfce4-panel -p /panels/panel-2/autohide-behavior -t uint -s 0 || true
fi

# 2) WM 抢占裸 F11：绑成 fullscreen_key 后由窗口管理器处理，进出对称，必定能退出。
#    否则 F11 落进 Chrome，而外层浏览器也可能吃掉 F11，用户在容器里就没有退出手段。
xfconf-query -c xfce4-keyboard-shortcuts -p '/xfwm4/custom/F11' -n -t string -s 'fullscreen_key' 2>/dev/null || true

# 3) 兜底逃生快捷键：Ctrl+Alt+F 摘掉全屏。
xfconf-query -c xfce4-keyboard-shortcuts -p '/commands/custom/<Primary><Alt>f' -n -t string -s '/usr/local/bin/chatop-unfullscreen' 2>/dev/null || true

mkdir -p "$(dirname "$SENT")"
echo "$WANT" > "$SENT"
