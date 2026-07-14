#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
FAC="$(mktemp -d)"; VOL="$(mktemp -d)"
# 造出厂副本
for n in station agent-config dashboard-web openclaw-tool; do
  mkdir -p "$FAC/$n"; echo "factory-1.5.9" > "$FAC/$n/marker.txt"
done
export CHATOP_FACTORY_DIR="$FAC" CHATOP_SERVICES_DIR="$VOL" CHATOP_SERVICES_WANT=1
bash "$ROOT/app-manager/chatop-seed-services.sh"
# 首播种后：每个服务 current 指向 v1.5.9，marker 存在
for n in station agent-config dashboard-web openclaw-tool; do
  test -L "$VOL/$n/current" || { echo "FAIL: no current for $n"; exit 1; }
  test -f "$VOL/$n/current/marker.txt" || { echo "FAIL: no marker for $n"; exit 1; }
done
# 幂等：用户已升级 station 到更高版，再跑一次不得覆盖
mkdir -p "$VOL/station/9.9.9"; echo "user-999" > "$VOL/station/9.9.9/marker.txt"
ln -sfn 9.9.9 "$VOL/station/current"
bash "$ROOT/app-manager/chatop-seed-services.sh"
test "$(cat "$VOL/station/current/marker.txt")" = "user-999" || { echo "FAIL: clobbered user version"; exit 1; }
echo "PASS"
