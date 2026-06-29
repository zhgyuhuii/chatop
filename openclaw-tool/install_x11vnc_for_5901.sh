#!/bin/bash
# 安装 x11vnc，使传统 VNC 客户端可连接 5901 端口
# 需要 sudo 权限，运行：sudo /openclaw-tool/install_x11vnc_for_5901.sh
set -e
apt-get update -qq
apt-get install -y -qq x11vnc
echo "x11vnc 已安装。重新登录或执行 /openclaw-tool/start_ports_1080_4901_5901.sh 后，5901 将提供 VNC 服务。"
