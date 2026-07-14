#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
KEY="$(printf 'a%.0s' {1..64})"
VOL="$(mktemp -d)"; INBOX="$(mktemp -d)"; OUT="$(mktemp -d)"
# 1) 打 agent-config bundle 到 inbox
"$ROOT/tools/build-bundle.sh" agent-config 1.6.0 "$KEY" "$INBOX"
# 2) 用 updater 纯逻辑 apply（health skip），断言 current 生效
python3.11 - "$ROOT" "$VOL" "$INBOX" "$KEY" <<'PY'
import sys, json, os
sys.path.insert(0, sys.argv[1] + "/station")
from station import updater
root, vol, inbox, key = sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4]
from pathlib import Path
man = json.load(open(f"{inbox}/agent-config-1.6.0.json"))
res = updater.apply(Path(f"{inbox}/agent-config-1.6.0.tar.gz"), man,
                    services_dir=Path(vol), hmac_keys={"1": bytes.fromhex(key)},
                    health_check=lambda: True)
assert res.ok, res.detail
assert (Path(vol) / "agent-config" / "current" / "agentconfig").is_dir(), "agentconfig missing"
print("E2E OK")
PY
echo "PASS"
