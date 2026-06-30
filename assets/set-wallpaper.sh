#!/usr/bin/env bash
# 运行时强制把 XFCE 桌面背景设为察元壁纸。
#
# 为什么需要它：KasmVNC 的显示器 monitorVNC-* 是会话建立时动态出现的，xfconfd
# 不会从磁盘 xml 加载这个显示器的 backdrop 配置，xfdesktop 于是给它套上编译内置
# 的默认壁纸(/usr/share/backgrounds/xfce/xfce-verticals.png)。所以光改 xml 或
# bg_default.png 都不生效，必须等桌面就绪后用 xfconf-query 主动写入。

IMG="/usr/share/backgrounds/chayuanai/wallpaper.png"
export DISPLAY="${DISPLAY:-:1}"

apply() {
  # 1) 现存的所有 last-image 属性一律改成察元壁纸
  xfconf-query -c xfce4-desktop -l 2>/dev/null | grep '/last-image$' | while read -r p; do
    xfconf-query -c xfce4-desktop -p "$p" -s "$IMG" 2>/dev/null || true
  done
  # 2) 兜底：为当前每个已连接显示器创建/覆盖 workspace0-3 的背景属性
  for m in $(xrandr 2>/dev/null | awk '/ connected/{print $1}'); do
    for w in 0 1 2 3; do
      b="/backdrop/screen0/monitor$m/workspace$w"
      xfconf-query -c xfce4-desktop -p "$b/last-image" -n -t string -s "$IMG" 2>/dev/null || \
        xfconf-query -c xfce4-desktop -p "$b/last-image" -s "$IMG" 2>/dev/null || true
      # image-style=5 => Zoomed(铺满)
      xfconf-query -c xfce4-desktop -p "$b/image-style" -n -t int -s 5 2>/dev/null || \
        xfconf-query -c xfce4-desktop -p "$b/image-style" -s 5 2>/dev/null || true
    done
  done
}

# 等 xfconfd 就绪
for i in $(seq 1 60); do
  xfconf-query -c xfce4-desktop -l >/dev/null 2>&1 && break
  sleep 1
done

# 桌面/显示器可能晚于本脚本就绪，重复设置以覆盖热插拔与后续连接的会话
for i in 1 2 3 4 5 6; do apply; sleep 3; done
