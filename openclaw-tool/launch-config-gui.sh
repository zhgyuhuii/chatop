#!/usr/bin/env bash
# OpenClaw 配置器启动器。
# 背景：配置器基于 tkinter，在 KasmVNC/Xvnc 无头 X 环境下，libX11 偶发堆破坏
# 会在建控件时段错误(退出码 139，冷启/高负载时概率较高，重试通常即成)。
# 这里对「崩溃类」退出码自动重试若干次，让双击/命令行启动稳定成功；
# 用户正常关窗(退出码 0)或真实报错(非崩溃码)不重试。
GUI="$(dirname "$(readlink -f "$0")")/openclaw_config_gui.py"
for attempt in 1 2 3 4 5; do
  python3 "$GUI" "$@"
  rc=$?
  # 139=SIGSEGV，134=SIGABRT，132=SIGILL，136=SIGFPE：均视为原生崩溃，重试
  case "$rc" in
    139|134|132|136)
      sleep 0.4
      continue
      ;;
    *)
      exit "$rc"
      ;;
  esac
done
exit "$rc"
