#!/usr/bin/env bash
# OpenClaw 配置器启动器。
#
# 历史：曾以为 tkinter 在 KasmVNC/Xvnc 下是「libX11 偶发堆破坏」，故加了崩溃重试。
# 该理论已被 gdb 推翻（2026-07-08）：真因是 **Tk 输入法(XIM)** —— zh_CN.UTF-8 环境下
# 容器内无 IME 服务器时，Tk 实现窗口会调 XCreateIC，在 libX11 的
# _XimLocalCreateIC→_XReply 里段错误。这是**确定性**崩溃，重试 5 次也是崩 5 次。
# 已在 OpenClawConfigApp.__init__ 里用 `tk useinputmethods 0` 根治。
#
# 下面的重试循环因此**不是**主要防线，仅作兜底（真有偶发原生崩溃时少一次用户重开）。
# 若配置器再次必崩，不要指望重试——去查 __init__ 里的 useinputmethods 是否还在。
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
