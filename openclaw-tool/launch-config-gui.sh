#!/usr/bin/env bash
# OpenClaw 配置器启动器。
#
# 历史：曾以为 tkinter 在 KasmVNC/Xvnc 下是「libX11 偶发堆破坏」，故加了崩溃重试。
# 该理论已被 gdb 推翻（2026-07-08）：真因是 **Tk 输入法(XIM)** —— zh_CN.UTF-8 环境下
# 容器内无 IME 服务器时，Tk 实现窗口会调 XCreateIC，在 libX11 的
# _XimLocalCreateIC→_XReply 里段错误。这是**确定性**崩溃，重试 5 次也是崩 5 次。
# 已在 OpenClawConfigApp.__init__ 里用 `tk useinputmethods 0` 根治。
#
# 第二类确定性段错误（2026-07-11，gdb 定案，与上面 XIM 无关）：运行时 catalog 缓存
# ~/.cache/chatop/openclaw-catalog.json（GUI「刷新清单」拉实时 openclaw CLI 写出）里
# 某些结构会让 Tk8.6 在 Tk_TextWidth/Tk_MeasureChars 测量文本时于 libX11 _XReply 段错误，
# 建通道页控件时必崩、整个配置器打不开；baked factory snapshot(/usr/share/chatop/…)不触发。
# 由于是原生 SIGSEGV，Python 层 try/except 抓不住 → 只能在 launcher 层自愈：
# **一旦发生原生崩溃，先隔离运行时 catalog 缓存，再重试**——下次加载即回落 baked snapshot。
# 这对任何未来的坏缓存都兜底，且保留「刷新清单」功能（只在崩溃后才清）。
GUI="$(dirname "$(readlink -f "$0")")/openclaw_config_gui.py"
# 路径与 openclaw_catalog.py 的 CACHE_PATH=expanduser("~/.cache/chatop/openclaw-catalog.json")
# 严格一致（expanduser 只认 $HOME，不理会 XDG_CACHE_HOME）
CATALOG_CACHE="$HOME/.cache/chatop/openclaw-catalog.json"

quarantine_bad_cache() {
  # 把可能致崩的运行时 catalog 缓存挪走（可逆、便于事后取证），失败则直接删
  if [ -f "$CATALOG_CACHE" ]; then
    mv -f "$CATALOG_CACHE" "${CATALOG_CACHE}.crashbak" 2>/dev/null || rm -f "$CATALOG_CACHE" 2>/dev/null
    echo "[launch-config-gui] 检测到原生崩溃，已隔离运行时 catalog 缓存，回落内置快照后重试" >&2
  fi
}

for attempt in 1 2 3 4 5; do
  python3.11 "$GUI" "$@"
  rc=$?
  # 139=SIGSEGV，134=SIGABRT，132=SIGILL，136=SIGFPE：均视为原生崩溃
  case "$rc" in
    139|134|132|136)
      quarantine_bad_cache   # 崩溃自愈：隔离坏缓存 → 下次回落内置快照
      sleep 0.4
      continue
      ;;
    *)
      exit "$rc"
      ;;
  esac
done
exit "$rc"
