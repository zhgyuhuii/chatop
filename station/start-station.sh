#!/usr/bin/env bash
set -e
export STATION_PORT="${STATION_PORT:-8787}"
export APPS_CATALOG="${APPS_CATALOG:-/etc/chatop/apps-catalog.json}"

SVC="${CHATOP_SERVICES_DIR:-$HOME/.chatop/services}"
FAC="${CHATOP_FACTORY_DIR:-/opt/chatop/factory}"

# 服务生效目录：卷内 current 有效则用，否则回退出厂 factory（缺失再退旧 /opt 兼容）
resolve() { # $1=service name  $2=fallback-opt-path
  if [ -d "$SVC/$1/current" ]; then echo "$SVC/$1/current";
  elif [ -d "$FAC/$1" ]; then echo "$FAC/$1";
  else echo "$2"; fi
}

AGENT_CFG_DIR="$(resolve agent-config /opt/agent-config)"
OPENCLAW_DIR="$(resolve openclaw-tool /opt/openclaw-tool)"
STATION_DIR="$(resolve station /opt/station/station)"

# agent-config bundle 内层是 agentconfig/；PYTHONPATH 要指其父，import 名 agentconfig
if [ -d "$AGENT_CFG_DIR/agentconfig" ]; then PYPARENT="$AGENT_CFG_DIR"; else PYPARENT="/opt/agent-config"; fi
export PYTHONPATH="${PYPARENT}${PYTHONPATH:+:$PYTHONPATH}"
export OPENCLAW_TOOL_DIR="$OPENCLAW_DIR"

if [ "${STATION_DRY_RUN:-0}" = "1" ]; then
  echo "PYTHONPATH=$PYTHONPATH"
  echo "OPENCLAW_TOOL_DIR=$OPENCLAW_TOOL_DIR"
  echo "STATION_DIR=$STATION_DIR"
  exit 0
fi

# station 源可能在卷内 current/station（bundle 内层 station/），也可能出厂 /opt/station/station
if [ -d "$STATION_DIR/station" ]; then cd "$STATION_DIR"; else cd /opt/station; fi

MARKER="${CHATOP_RESTART_MARKER:-$HOME/.chatop/pending-restart}"
HEALTH_URL="http://127.0.0.1:${STATION_PORT}/dashboard/api/system"
HEALTH_TIMEOUT="${STATION_HEALTH_TIMEOUT:-30}"

/opt/station-venv/bin/python -m station &
STATION_PID=$!

healthy=0
for _ in $(seq 1 "$HEALTH_TIMEOUT"); do
  if curl -fsS "$HEALTH_URL" >/dev/null 2>&1; then healthy=1; break; fi
  kill -0 "$STATION_PID" 2>/dev/null || break   # 进程已退出，别再空等
  sleep 1
done

if [ "$healthy" = "1" ]; then
  rm -f "$MARKER"          # 本次启动/更新健康，清 pending 标记
  wait "$STATION_PID"      # 常驻；退出后由外层 supervisor 循环重起
else
  if [ -s "$MARKER" ]; then
    svc="$(cat "$MARKER" 2>/dev/null)"
    rm -f "$MARKER"
    echo "station 未在 ${HEALTH_TIMEOUT}s 内就绪，回滚服务 [$svc] 后重启" >&2
    /opt/station-venv/bin/python -m station rollback "$svc" >/tmp/station-rollback.log 2>&1 || true
  fi
  kill "$STATION_PID" 2>/dev/null || true
  exit 1                   # 交给外层 supervisor 用回滚后的 current 重起
fi
