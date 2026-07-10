# 应用市场国内化 P1（离线可用 + 国内镜像回退）Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让应用市场在离线/被墙时列表与图标不裂，并给所有运行时安装命令加国内镜像回退——不改前端交互、不改 catalog 语义，纯可用性打底。

**Architecture:** 三条独立能力：(1) 统一镜像配置真源 `/etc/chatop/mirrors.conf`；(2) 三处消费它——`app_manager._worker` 注入 npm/pip env、`chatop-fetch` 助手做 GitHub 多域名回退、`proot-apps` PATH 垫片改写 ghcr 镜像引用；(3) 94 个 proot 图标本地化 + catalog 图标去远程化 + lint 守护。

**Tech Stack:** Python 3.11（app_manager.py，stdlib only）、Bash（助手脚本）、pytest、Docker（Ubuntu 22.04 base）。

**基线说明：** `app-manager/tests/test_app_manager.py` 现有 5 个 `test_reconcile_*` 失败属历史遗留，与本计划无关，勿动、勿以其为回归信号。本计划新增测试均独立。

**设计依据：** `docs/superpowers/specs/2026-07-10-app-store-china-localization-design.md` 第 4.4、4.6 节。

---

### Task 1: 镜像配置真源 `mirrors.conf` + Dockerfile 部署

**Files:**
- Create: `app-manager/mirrors.conf`
- Modify: `Dockerfile`（在 `COPY app-manager/apps-catalog.json ...` 一行附近，约 212 行后新增一行 COPY）

- [ ] **Step 1: 写配置文件**

Create `app-manager/mirrors.conf`（shell 可 `source`、python 可逐行解析的 `KEY=VALUE`，无 `export`，`#` 注释）：

```sh
# chatop 应用市场国内镜像真源。app_manager/_worker、chatop-fetch、proot-apps 垫片三处共读。
# 改镜像策略只改此文件（或用容器 env 覆盖同名变量）。空格分隔的列表按先后顺序回退。
NPM_REGISTRY=https://registry.npmmirror.com
NPM_DISTURL=https://npmmirror.com/dist
PIP_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple
PIP_EXTRA_INDEX_URL=https://mirrors.aliyun.com/pypi/simple/
GH_PROXIES=https://ghfast.top/ https://gh-proxy.com/ https://gh-proxy.org/
GHCR_MIRRORS=ghcr.m.daocloud.io ghcr.nju.edu.cn
```

- [ ] **Step 2: Dockerfile 部署到 `/etc/chatop/mirrors.conf`**

在 `COPY app-manager/apps-catalog.json /etc/chatop/apps-catalog.json` 之后新增：

```dockerfile
COPY app-manager/mirrors.conf /etc/chatop/mirrors.conf
```

- [ ] **Step 3: Commit**

```bash
git add app-manager/mirrors.conf Dockerfile
git commit -m "feat(market): 新增国内镜像配置真源 mirrors.conf 并烤入镜像"
```

---

### Task 2: `_worker` 安装时注入 npm/pip 镜像 env

**Files:**
- Modify: `app-manager/app_manager.py`（顶部常量区加 `MIRRORS_CONF`/`_load_mirrors`/`_install_env`；`_worker` 的 `subprocess.run` 加 `env=`）
- Test: `app-manager/tests/test_mirrors.py`

- [ ] **Step 1: 写失败测试**

Create `app-manager/tests/test_mirrors.py`:

```python
import os, sys, tempfile
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
import app_manager as am

_CONF = (
    "NPM_REGISTRY=https://registry.npmmirror.com\n"
    "NPM_DISTURL=https://npmmirror.com/dist\n"
    "PIP_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple\n"
    "PIP_EXTRA_INDEX_URL=https://mirrors.aliyun.com/pypi/simple/\n"
    "# a comment line\n"
    "GH_PROXIES=https://ghfast.top/ https://gh-proxy.com/\n"
)

def _conf(tmp):
    p = os.path.join(tmp, "mirrors.conf"); open(p, "w").write(_CONF); return p

def test_load_mirrors_parses_keys_and_skips_comments():
    with tempfile.TemporaryDirectory() as t:
        m = am._load_mirrors(_conf(t))
        assert m["NPM_REGISTRY"] == "https://registry.npmmirror.com"
        assert m["GH_PROXIES"] == "https://ghfast.top/ https://gh-proxy.com/"
        assert "# a comment line" not in m and len(m) == 5

def test_install_env_sets_npm_and_pip_vars():
    with tempfile.TemporaryDirectory() as t:
        env = am._install_env(_conf(t))
        assert env["npm_config_registry"] == "https://registry.npmmirror.com"
        assert env["npm_config_disturl"] == "https://npmmirror.com/dist"
        assert env["PIP_INDEX_URL"] == "https://pypi.tuna.tsinghua.edu.cn/simple"
        assert env["PIP_EXTRA_INDEX_URL"] == "https://mirrors.aliyun.com/pypi/simple/"
        # 必须是 os.environ 的超集，别把 PATH/HOME 丢了
        assert "PATH" in env

def test_install_env_missing_conf_is_harmless():
    env = am._install_env("/nonexistent/mirrors.conf")
    assert "PATH" in env and "npm_config_registry" not in env
```

- [ ] **Step 2: 跑测试确认失败**

Run: `cd app-manager && python3.11 -m pytest tests/test_mirrors.py -q`
Expected: FAIL（`AttributeError: module 'app_manager' has no attribute '_load_mirrors'`）

- [ ] **Step 3: 实现**

在 `app_manager.py` 顶部常量区（`CATALOG_PATH` 一行下方）加：

```python
MIRRORS_CONF = os.environ.get("MIRRORS_CONF", "/etc/chatop/mirrors.conf")

def _load_mirrors(path=None):
    """解析 mirrors.conf → dict；文件缺失返回空 dict（安装退化成默认源，绝不报错）。"""
    path = path or MIRRORS_CONF
    out = {}
    try:
        with open(path) as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, v = line.split("=", 1)
                out[k.strip()] = v.strip()
    except OSError:
        pass
    return out

def _install_env(path=None):
    """os.environ 的副本 + npm/pip 国内镜像变量，供安装子进程使用。"""
    m = _load_mirrors(path)
    env = dict(os.environ)
    if m.get("NPM_REGISTRY"):       env["npm_config_registry"] = m["NPM_REGISTRY"]
    if m.get("NPM_DISTURL"):        env["npm_config_disturl"]  = m["NPM_DISTURL"]
    if m.get("PIP_INDEX_URL"):      env["PIP_INDEX_URL"]       = m["PIP_INDEX_URL"]
    if m.get("PIP_EXTRA_INDEX_URL"):env["PIP_EXTRA_INDEX_URL"] = m["PIP_EXTRA_INDEX_URL"]
    return env
```

在 `_worker` 里把安装命令的 `subprocess.run` 改为带 `env`（仅这一处业务安装子进程）：

```python
            with open(logf,"w") as lf:
                lf.write(f"$ {cmd}\n"); lf.flush()
                rc = subprocess.run(["bash","-lc",cmd], stdout=lf, stderr=subprocess.STDOUT,
                                    env=_install_env()).returncode
```

- [ ] **Step 4: 跑测试确认通过**

Run: `cd app-manager && python3.11 -m pytest tests/test_mirrors.py -q`
Expected: PASS（3 passed）

- [ ] **Step 5: Commit**

```bash
git add app-manager/app_manager.py app-manager/tests/test_mirrors.py
git commit -m "feat(market): 安装子进程注入 npm/pip 国内镜像 env"
```

---

### Task 3: `chatop-fetch` 助手（GitHub 多域名回退下载）

**Files:**
- Create: `app-manager/chatop-fetch.sh`
- Modify: `Dockerfile`（COPY 到 `/usr/local/bin/chatop-fetch` 并 `chmod +x`）
- Test: `app-manager/tests/test_helpers.py`

- [ ] **Step 1: 写助手脚本**

Create `app-manager/chatop-fetch.sh`:

```bash
#!/usr/bin/env bash
# chatop-fetch <url> <out> [--dry-run]
# 直连 → mirrors.conf 的 GH_PROXIES 逐个前缀拼接回退，任一成功即止。
# --dry-run: 只打印候选 URL 列表（每行一个），不下载。供测试与排障。
set -u
CONF="${MIRRORS_CONF:-/etc/chatop/mirrors.conf}"
URL="${1:?need url}"; OUT="${2:-}"; MODE="${3:-}"

GH_PROXIES=""
[ -f "$CONF" ] && GH_PROXIES="$(sed -n 's/^GH_PROXIES=//p' "$CONF")"

# 候选：先直连，再各代理前缀 + 原始 url
CANDIDATES=("$URL")
for p in $GH_PROXIES; do CANDIDATES+=("${p}${URL}"); done

if [ "$MODE" = "--dry-run" ] || [ "$OUT" = "--dry-run" ]; then
  printf '%s\n' "${CANDIDATES[@]}"; exit 0
fi

: "${OUT:?need out path}"
for u in "${CANDIDATES[@]}"; do
  echo "[chatop-fetch] try: $u" >&2
  if curl -fL --retry 2 --retry-delay 3 --connect-timeout 20 -o "$OUT" "$u"; then
    echo "[chatop-fetch] ok via: $u" >&2; exit 0
  fi
done
echo "[chatop-fetch] 全部源失败（直连+镜像），网络不可达或镜像不可用: $URL" >&2
exit 1
```

- [ ] **Step 2: 写失败测试**

Create `app-manager/tests/test_helpers.py`:

```python
import os, subprocess, tempfile
HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FETCH = os.path.join(HERE, "chatop-fetch.sh")

_CONF = "GH_PROXIES=https://ghfast.top/ https://gh-proxy.com/\n"

def _run(args, conf):
    env = dict(os.environ, MIRRORS_CONF=conf)
    return subprocess.run(["bash", FETCH, *args], env=env,
                          capture_output=True, text=True)

def test_fetch_dryrun_lists_direct_then_proxies():
    with tempfile.TemporaryDirectory() as t:
        cp = os.path.join(t, "mirrors.conf"); open(cp, "w").write(_CONF)
        url = "https://github.com/foo/bar/releases/download/v1/x.tgz"
        r = _run([url, "--dry-run"], cp)
        lines = [l for l in r.stdout.strip().splitlines() if l]
        assert lines[0] == url
        assert lines[1] == "https://ghfast.top/" + url
        assert lines[2] == "https://gh-proxy.com/" + url
        assert len(lines) == 3

def test_fetch_dryrun_no_conf_only_direct():
    url = "https://github.com/foo/bar.tgz"
    r = _run([url, "--dry-run"], "/nonexistent/mirrors.conf")
    lines = [l for l in r.stdout.strip().splitlines() if l]
    assert lines == [url]
```

- [ ] **Step 3: 跑测试确认失败**

Run: `cd app-manager && python3.11 -m pytest tests/test_helpers.py -q`
Expected: FAIL（脚本尚未 executable / 逻辑未就位前断言不符；确认红）

- [ ] **Step 4: Dockerfile 部署 + 本地可执行**

在 Dockerfile 的助手脚本 COPY 区（`gui-install.sh` 那批附近）新增：

```dockerfile
COPY app-manager/chatop-fetch.sh /usr/local/bin/chatop-fetch
RUN chmod +x /usr/local/bin/chatop-fetch
```

- [ ] **Step 5: 跑测试确认通过**

Run: `cd app-manager && python3.11 -m pytest tests/test_helpers.py -q`
Expected: PASS（2 passed）

- [ ] **Step 6: Commit**

```bash
git add app-manager/chatop-fetch.sh app-manager/tests/test_helpers.py Dockerfile
git commit -m "feat(market): chatop-fetch 助手做 GitHub 多域名镜像回退下载"
```

---

### Task 4: `proot-apps` PATH 垫片（ghcr 镜像回退）

**Files:**
- Create: `app-manager/proot-apps-shim.sh`
- Modify: `Dockerfile`（proot-apps 安装段：真二进制装成 `proot-apps-real`，垫片装成 `proot-apps`）
- Test: `app-manager/tests/test_helpers.py`（追加）

- [ ] **Step 1: 写垫片脚本**

Create `app-manager/proot-apps-shim.sh`:

```bash
#!/usr/bin/env bash
# proot-apps 垫片：install <短名> → 改写为 ghcr 国内镜像完整引用并按 GHCR_MIRRORS 回退，
# 最后回退直连官方短名。其余子命令(run/remove/update…)原样透传给 proot-apps-real。
# --dry-run 放在最后一个参数时，只打印将尝试的 install 引用列表。
set -u
CONF="${MIRRORS_CONF:-/etc/chatop/mirrors.conf}"
REAL="${PROOT_APPS_REAL:-proot-apps-real}"

SUB="${1:-}"; APP="${2:-}"
# 非 install，或 install 的目标已是完整引用(含 / 或 :)，直接透传
if [ "$SUB" != "install" ] || [ -z "$APP" ] || [[ "$APP" == *[/:]* ]]; then
  exec "$REAL" "$@"
fi

GHCR_MIRRORS=""
[ -f "$CONF" ] && GHCR_MIRRORS="$(sed -n 's/^GHCR_MIRRORS=//p' "$CONF")"

REFS=()
for m in $GHCR_MIRRORS; do REFS+=("${m}/linuxserver/proot-apps:${APP}"); done
REFS+=("$APP")   # 最后回退官方直连短名

# 末参 --dry-run 时只打印
for a in "$@"; do :; done
if [ "${!#}" = "--dry-run" ]; then printf '%s\n' "${REFS[@]}"; exit 0; fi

for ref in "${REFS[@]}"; do
  echo "[proot-apps] install via: $ref" >&2
  if "$REAL" install "$ref"; then exit 0; fi
  echo "[proot-apps] 失败，尝试下一镜像源" >&2
done
echo "[proot-apps] 全部 ghcr 源失败: $APP" >&2
exit 1
```

- [ ] **Step 2: 追加失败测试**

在 `app-manager/tests/test_helpers.py` 末尾追加：

```python
SHIM = os.path.join(HERE, "proot-apps-shim.sh")

def test_shim_rewrites_shortname_to_ghcr_mirrors():
    with tempfile.TemporaryDirectory() as t:
        cp = os.path.join(t, "mirrors.conf")
        open(cp, "w").write("GHCR_MIRRORS=ghcr.m.daocloud.io ghcr.nju.edu.cn\n")
        env = dict(os.environ, MIRRORS_CONF=cp)
        r = subprocess.run(["bash", SHIM, "install", "wechat", "--dry-run"],
                           env=env, capture_output=True, text=True)
        lines = [l for l in r.stdout.strip().splitlines() if l]
        assert lines == [
            "ghcr.m.daocloud.io/linuxserver/proot-apps:wechat",
            "ghcr.nju.edu.cn/linuxserver/proot-apps:wechat",
            "wechat",
        ]
```

- [ ] **Step 3: 跑测试确认失败**

Run: `cd app-manager && python3.11 -m pytest tests/test_helpers.py::test_shim_rewrites_shortname_to_ghcr_mirrors -q`
Expected: FAIL（脚本不存在）

- [ ] **Step 4: Dockerfile 改装真二进制 + 垫片**

改 Dockerfile proot-apps 段的 `install -m755 ...` 那行，把 `proot-apps` 装成 `proot-apps-real`：

```dockerfile
    install -m755 /tmp/pa/proot-apps /usr/local/bin/proot-apps-real; \
    install -m755 /tmp/pa/proot /tmp/pa/jq /tmp/pa/ncat /usr/local/bin/; \
```

并在该 RUN 之后新增垫片 COPY：

```dockerfile
COPY app-manager/proot-apps-shim.sh /usr/local/bin/proot-apps
RUN chmod +x /usr/local/bin/proot-apps
```

> 注意 custom_startup.sh（约 297 行）里 `ln -sf ... /usr/local/bin/proot-apps $HOME/.local/bin/` 仍成立——软链指向垫片即可，无需改。

- [ ] **Step 5: 跑测试确认通过**

Run: `cd app-manager && python3.11 -m pytest tests/test_helpers.py -q`
Expected: PASS（3 passed）

- [ ] **Step 6: Commit**

```bash
git add app-manager/proot-apps-shim.sh app-manager/tests/test_helpers.py Dockerfile
git commit -m "feat(market): proot-apps 垫片改写 ghcr 国内镜像并回退"
```

---

### Task 5: 94 个 proot 图标本地化 + catalog 去远程 + lint 守护

**Files:**
- Create: `app-manager/fetch-proot-icons.sh`
- Create（脚本产出，二进制入库）: `app-manager/icons/<id>.svg` × 94
- Modify: `app-manager/apps-catalog.json`（proot-gui 条目 `icon` 改本地名）
- Test: `app-manager/tests/test_catalog_icons.py`

- [ ] **Step 1: 写图标抓取脚本**

Create `app-manager/fetch-proot-icons.sh`:

```bash
#!/usr/bin/env bash
# 把 catalog 里所有远程图标(proot-gui 的 cdn.jsdelivr 指向 linuxserver/proot-apps/metadata/img/<id>.svg)
# 拉到本地 icons/<id>.svg。走 chatop-fetch(带 gh 代理回退)。已存在则跳过。
set -u
cd "$(dirname "$0")"
FETCH="${CHATOP_FETCH:-./chatop-fetch.sh}"
BASE="https://raw.githubusercontent.com/linuxserver/proot-apps/master/metadata/img"
mkdir -p icons
python3.11 - <<'PY' | while read -r id; do
import json
d=json.load(open("apps-catalog.json"))
for a in d["apps"]:
    ic=a.get("icon","")
    if a.get("category")=="proot-gui" and ic.startswith("http"):
        print(a["id"])
PY
  out="icons/${id}.svg"
  [ -s "$out" ] && { echo "skip $id"; continue; }
  echo -n "fetch $id ... "
  if MIRRORS_CONF="${MIRRORS_CONF:-/etc/chatop/mirrors.conf}" bash "$FETCH" "$BASE/${id}.svg" "$out" 2>/dev/null && [ -s "$out" ]; then
    echo OK
  else
    rm -f "$out"; echo "FAIL（$id 需手工补图标）"
  fi
done
```

- [ ] **Step 2: 运行抓取脚本（产出本地图标）**

Run: `cd app-manager && MIRRORS_CONF=./mirrors.conf bash fetch-proot-icons.sh`
Expected: 94 行 `fetch <id> ... OK`（失败的项手工从对应官方仓库补 `icons/<id>.svg`，不留空）

- [ ] **Step 3: 改写 catalog 图标字段为本地名**

Run（用脚本批量改，避免手改 83KB JSON 出错）:

```bash
cd app-manager && python3.11 - <<'PY'
import json
p="apps-catalog.json"; d=json.load(open(p))
for a in d["apps"]:
    ic=a.get("icon","")
    if a.get("category")=="proot-gui" and ic.startswith("http"):
        a["icon"]=a["id"]+".svg"
json.dump(d, open(p,"w"), ensure_ascii=False, indent=2)
print("done")
PY
```

- [ ] **Step 4: 写 lint 测试**

Create `app-manager/tests/test_catalog_icons.py`:

```python
import json, os
HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CAT = os.path.join(HERE, "apps-catalog.json")
ICONS = os.path.join(HERE, "icons")

def test_no_remote_icons_in_catalog():
    d = json.load(open(CAT))
    remote = [a["id"] for a in d["apps"] if str(a.get("icon","")).startswith("http")]
    assert remote == [], f"仍有远程图标(离线会裂): {remote}"

def test_every_icon_file_exists_locally():
    d = json.load(open(CAT))
    missing = [a["icon"] for a in d["apps"]
               if a.get("icon") and not os.path.isfile(os.path.join(ICONS, a["icon"]))]
    assert missing == [], f"catalog 引用了不存在的本地图标: {missing}"
```

- [ ] **Step 5: 跑测试确认通过**

Run: `cd app-manager && python3.11 -m pytest tests/test_catalog_icons.py -q`
Expected: PASS（2 passed）。若 `test_every_icon_file_exists_locally` 失败，说明 Step 2 有 FAIL 项未补齐，回去补图标。

- [ ] **Step 6: Commit**

```bash
git add app-manager/fetch-proot-icons.sh app-manager/icons/ app-manager/apps-catalog.json app-manager/tests/test_catalog_icons.py
git commit -m "feat(market): proot 图标全本地化, catalog 去远程 icon + lint 守护"
```

---

### Task 6: 前端图标兜底 + P1 收尾验证

**Files:**
- Modify: `novnc-src/app/ui.js`（图标 onerror 兜底占位，不留空白格）

- [ ] **Step 1: 加图标兜底占位**

`ui.js` 现有 `onerror="this.style.visibility='hidden'"`（约 3861/3884/3923/3959 行）会把裂图藏成空白格。改为回退到统一占位图标 `app-icons/apps-icon.svg`（仓库已有 `app-manager/apps-icon.svg`，随 icons 一起进 www）。把这些行的 onerror 统一改为：

```js
onerror="if(this.dataset.fb!=1){this.dataset.fb=1;this.src='app-icons/apps-icon.svg'}else{this.style.visibility='hidden'}"
```

> 先本地化后，正常情况不会触发 onerror；此步是双保险，防少数图标缺失时留空白。同时确认 Dockerfile 把 `app-manager/apps-icon.svg` COPY 进 `www/app-icons/`（若未 COPY 则补一行 `COPY app-manager/apps-icon.svg /usr/share/kasmvnc/www/app-icons/apps-icon.svg`）。

- [ ] **Step 2: 全量跑 app-manager 测试（确认无回归，忽略历史 reconcile 5 红）**

Run: `cd app-manager && python3.11 -m pytest tests/ -q`
Expected: 新增的 test_mirrors / test_helpers / test_catalog_icons 全绿；仅历史 `test_reconcile_*` 5 个红（基线，非本计划引入）。

- [ ] **Step 3: 语法自检**

Run: `cd app-manager && python3.11 -m py_compile app_manager.py && bash -n chatop-fetch.sh proot-apps-shim.sh fetch-proot-icons.sh && echo OK`
Expected: `OK`

- [ ] **Step 4: Commit**

```bash
git add novnc-src/app/ui.js Dockerfile
git commit -m "feat(market): 前端图标缺失回退统一占位, 不留空白格"
```

---

## 自检（写完计划对照 spec）

- **spec 4.4 ①npm ②pip**：Task 2 `_install_env` 注入 `npm_config_registry/disturl` + `PIP_INDEX_URL/EXTRA` ✅
- **spec 4.4 ③GitHub 回退**：Task 3 `chatop-fetch` 直连+GH_PROXIES 回退 ✅
- **spec 4.4 ④proot 垫片**：Task 4 `proot-apps` 垫片 DaoCloud→南大→直连 ✅
- **spec 4.4 镜像配置真源**：Task 1 `mirrors.conf`，三处共读（env/fetch/shim）✅
- **spec 4.6 图标本地化 + lint**：Task 5 抓取+改写+两条 lint 测试 ✅
- **spec 6 离线契约（图标不裂/安装诊断）**：Task 5+6 图标本地化+占位兜底；`chatop-fetch`/垫片全失败打印明确诊断到日志 ✅
- **未纳入 P1（属 P2/P3，符合分期）**：`public_catalog(lang)` 语言感知、origin/rank/variants 数据模型、deb-user、内容扩充——留 P2/P3 计划。
- **占位扫描**：无 TBD/TODO；每个代码步给了完整代码/命令 ✅
- **类型/命名一致**：`_load_mirrors`/`_install_env`/`GH_PROXIES`/`GHCR_MIRRORS`/`proot-apps-real` 全篇一致 ✅

## 执行前提

- catalog install 命令本身 P1 不改（npm/pip 靠 env、proot 靠垫片、GitHub 类的 `curl→chatop-fetch` 改写属 P3 触达 void/rtk/hermes 时再做；P1 只保证机制就位）。
- Task 5 Step 2 需网络可达 GitHub（走 gh 代理）；离线构建环境请预先把 `icons/*.svg` 提交入库后再跑 lint。
