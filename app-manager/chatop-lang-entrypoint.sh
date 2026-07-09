#!/usr/bin/env bash
# 在 KasmVNC 的启动链之前，把用户选的语言注入 LC_ALL/LANG/LANGUAGE。
#
# 为什么必须放在**入口点**而不是 custom_startup.sh：
#   进程树实测 —— xfce4-session 是 PID 90（由 vnc_startup.sh 第 241-250 行拉起），
#   custom_startup.sh 是 PID 137。XFCE 比 custom_startup 先跑，在那里 export 已经太晚。
#   已经在运行的进程改不了自己的 locale，所以桌面语言只能在容器启动那一刻定下来。
#   这也是登录页要提示「桌面语言将在重启工舱后生效」的原因。
#
# vnc_startup.sh 第 28-30 行：
#   if [ "${LC_ALL}" != "en_US.UTF-8" ]; then export LANG=${LC_ALL}; export LANGUAGE=${LC_ALL}; fi
# 注意它对 en_US.UTF-8 是**不做事**的（那是它的默认假设）。所以我们自己把 LANG/LANGUAGE
# 也设好，不能只设 LC_ALL —— 否则选英文时 LANG 会残留镜像 ENV 里的 zh_CN.UTF-8。
#
# 语言文件不存在 / 内容不认识 → 什么都不做，沿用镜像 ENV 的默认值（zh_CN.UTF-8）。
# 这就是「跟随系统」。

# 路径必须跟 chatop_i18n.DATA_DIR 同一套规则，否则 app-manager 写一处、桌面读另一处，
# 选了语言重启后却没生效，而且没有任何报错。
LANG_FILE="${CHATOP_DATA_DIR:-${HOME:-/home/admin}/.local/share/chatop}/lang"

if [ -r "$LANG_FILE" ]; then
    case "$(tr -d '[:space:]' < "$LANG_FILE" 2>/dev/null)" in
        zh_CN) _loc=zh_CN.UTF-8 ;;
        zh_TW) _loc=zh_TW.UTF-8 ;;
        en)    _loc=en_US.UTF-8 ;;
        ja)    _loc=ja_JP.UTF-8 ;;
        ko)    _loc=ko_KR.UTF-8 ;;
        *)     _loc="" ;;
    esac
    if [ -n "$_loc" ]; then
        export LC_ALL="$_loc"
        export LANG="$_loc"
        export LANGUAGE="${_loc%%.*}"
        echo "[chatop-lang] locale -> $_loc" >&2
    fi
fi

exec "$@"
