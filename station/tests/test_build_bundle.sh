#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
KEY="$(printf 'a%.0s' {1..64})"   # 64 hex 字符（合法 hex）
OUT="$(mktemp -d)"
"$ROOT/tools/build-bundle.sh" agent-config 1.6.0 "$KEY" "$OUT"
test -f "$OUT/agent-config-1.6.0.tar.gz" || { echo "FAIL: no tarball"; exit 1; }
test -f "$OUT/agent-config-1.6.0.json" || { echo "FAIL: no manifest"; exit 1; }
python3.11 - "$OUT/agent-config-1.6.0.json" "$OUT/agent-config-1.6.0.tar.gz" "$KEY" <<'PY'
import hashlib, hmac, json, sys
man = json.load(open(sys.argv[1])); tar = sys.argv[2]; key = bytes.fromhex(sys.argv[3])
sha = hashlib.sha256(open(tar,'rb').read()).hexdigest()
assert man["sha256"] == sha, "sha mismatch"
assert man["sig"] == hmac.new(key, sha.encode(), hashlib.sha256).hexdigest(), "sig mismatch"
assert man["name"] == "agent-config" and man["version"] == "1.6.0"
print("OK")
PY
echo "PASS"
