#!/usr/bin/env bash
# 把 catalog 里所有远程图标(proot-gui 的 cdn.jsdelivr 指向 linuxserver/proot-apps/metadata/img/<file>)
# 拉到本地 icons/<file>。文件名与扩展名一律取自原始 URL(有 .svg 也有 .png)。
# 走 chatop-fetch(带 gh 代理回退)，命中 raw.githubusercontent 原路径。已存在则跳过。
set -u
cd "$(dirname "$0")"
FETCH="${CHATOP_FETCH:-./chatop-fetch.sh}"
mkdir -p icons
# 输出 "raw_url<TAB>本地文件名"：把 jsdelivr(@master) 换成 raw.githubusercontent(/master/)，
# 本地文件名取 URL 的 basename。
python3.11 - <<'PY' | while IFS=$'\t' read -r url out; do
import json
d=json.load(open("apps-catalog.json"))
for a in d["apps"]:
    ic=a.get("icon","")
    if a.get("category")=="proot-gui" and ic.startswith("http"):
        raw=ic.replace("https://cdn.jsdelivr.net/gh/linuxserver/proot-apps@master/",
                        "https://raw.githubusercontent.com/linuxserver/proot-apps/master/")
        print(raw + "\t" + ic.rsplit("/",1)[-1])
PY
  dest="icons/${out}"
  [ -s "$dest" ] && { echo "skip $out"; continue; }
  echo -n "fetch $out ... "
  if MIRRORS_CONF="${MIRRORS_CONF:-/etc/chatop/mirrors.conf}" bash "$FETCH" "$url" "$dest" 2>/dev/null && [ -s "$dest" ]; then
    echo OK
  else
    rm -f "$dest"; echo "FAIL（$out 需手工补图标）"
  fi
done
