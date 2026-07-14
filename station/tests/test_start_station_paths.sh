#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
VOL="$(mktemp -d)"; FAC="$(mktemp -d)"
mkdir -p "$VOL/agent-config/1.6.0/agentconfig" "$VOL/agent-config"
ln -sfn 1.6.0 "$VOL/agent-config/current"
mkdir -p "$VOL/openclaw-tool/1.6.0"; ln -sfn 1.6.0 "$VOL/openclaw-tool/current"
export CHATOP_SERVICES_DIR="$VOL" CHATOP_FACTORY_DIR="$FAC" STATION_DRY_RUN=1
out="$(bash "$ROOT/station/start-station.sh")"
echo "$out" | grep -q "PYTHONPATH=$VOL/agent-config/current" || { echo "FAIL: PYTHONPATH not volume"; exit 1; }
echo "$out" | grep -q "OPENCLAW_TOOL_DIR=$VOL/openclaw-tool/current" || { echo "FAIL: OPENCLAW_TOOL_DIR not volume"; exit 1; }
echo "PASS"
