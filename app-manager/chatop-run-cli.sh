#!/bin/bash
# chatop-run-cli <command> [args...]
# 在桌面终端里运行 CLI 工具（如 claude / codex / openclaw），命令结束后保留一个
# 交互式登录 shell，方便用户继续操作或查看输出。用登录 shell 保证 PATH 里有
# ~/.npm-global/bin（CLI 工具的安装位置）。
set -u
export DISPLAY="${DISPLAY:-:1}"
TITLE="${CHATOP_CLI_TITLE:-${1:-CLI}}"

if [ "$#" -eq 0 ]; then
  INNER="exec bash -l"
else
  CMD="$*"
  INNER="printf '\033]0;%s\007' \"$TITLE\"; $CMD; ec=\$?; echo; echo \"[「$TITLE」已退出 (exit \$ec)，可继续使用此终端]\"; exec bash -l"
fi

if command -v xfce4-terminal >/dev/null 2>&1; then
  exec xfce4-terminal --title="$TITLE" -x bash -lc "$INNER"
elif command -v x-terminal-emulator >/dev/null 2>&1; then
  exec x-terminal-emulator -e bash -lc "$INNER"
elif command -v xterm >/dev/null 2>&1; then
  exec xterm -title "$TITLE" -e bash -lc "$INNER"
fi
echo "chatop-run-cli: no terminal emulator found" >&2
exit 1
