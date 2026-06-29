# 应用管理器（第一期）实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在 chatop-ai（KasmVNC 云桌面）控制栏增加一个应用管理器，第一期支持约 11 个纯 CLI / VS Code 插件类 AI 工具的点击安装/卸载，状态真实检测、持久化保留，每个应用带官方图标。

**Architecture:** 旁挂一个 Python HTTP「应用服务」(127.0.0.1:8686)，Caddy 反代 `/apps`；catalog.json 持有各应用的安装/卸载/检测命令（命令只存后端，前端只传 id 白名单）；noVNC 控制栏「应用」按钮打开模态框调用 API；CLI 工具配成用户级安装 + home 数据卷持久化。

**Tech Stack:** Python 3.10（标准库 http.server）、Caddy、Node 22（npm 类工具前提）、pipx、noVNC 前端（原生 JS/HTML/CSS）、Docker/compose。

设计依据：`docs/superpowers/specs/2026-06-29-app-manager-design.md`

---

## File Structure（第一期产出/改动）

```
/work/chatop-ai/
  app-manager/
    app_manager.py              # 新增：应用服务后端（HTTP API）
    apps-catalog.json           # 新增：一期应用清单（含命令、图标名）
    start-app-manager.sh        # 新增：启动脚本（接入 custom_startup）
    icons/                      # 新增：各应用官方 logo（svg/png）
    tests/test_app_manager.py   # 新增：后端单测
  caddy/Caddyfile               # 改：增加 handle /apps* 反代
  novnc-src/index.html          # 改：控制栏加「应用」按钮 + 模态框容器
  novnc-src/app/ui.js           # 改：应用管理器前端逻辑
  novnc-src/app/styles/base.css # 改：模态框/卡片样式
  docker-compose.yml            # 改：挂 home 命名卷持久化
  Dockerfile                    # 改：预置 Node22/pipx；装 app-manager + icons + 启动
```

职责：`app_manager.py` 只管 API+任务执行；`apps-catalog.json` 只管清单数据；前端只管展示+调用；Caddy 只管反代。

---

## Task 1: 镜像预置 Node 22 + pipx + 用户级 npm 前缀

**Files:**
- Modify: `Dockerfile`

- [ ] **Step 1: 在 Dockerfile 的 USER root 段（WPS 之后、轻量层之前）增加 Node 22 + pipx**

在 `ENV LOGIN_USER=admin` 之前插入：
```dockerfile
# === 应用管理器基础：Node 22（npm 类 AI 工具前提）+ pipx ===
RUN set -eux; \
    curl -fsSL https://deb.nodesource.com/setup_22.x | bash -; \
    apt-get install -y --no-install-recommends nodejs; \
    node -v; npm -v; \
    apt-get install -y --no-install-recommends pipx; \
    rm -rf /var/lib/apt/lists/*
```

- [ ] **Step 2: 配置用户级 npm 前缀 + PATH（持久化关键，写进 default-profile 与 profile.d）**

继续追加：
```dockerfile
# npm 用户级全局前缀（装到家目录 → home 数据卷持久），并把 ~/.npm-global/bin、~/.local/bin 入 PATH
RUN set -eux; \
    printf '\n# chatop app-manager user-level tooling\nexport NPM_CONFIG_PREFIX="$HOME/.npm-global"\nexport PATH="$HOME/.npm-global/bin:$HOME/.local/bin:$PATH"\n' \
      > /etc/profile.d/chatop-apps.sh; \
    chmod +x /etc/profile.d/chatop-apps.sh
```

- [ ] **Step 3: 构建验证 Node/pipx 存在**

Run:
```bash
cd /work/chatop-ai && sudo docker build --build-arg VERSION=1.1.0 -t chatop-ai:1.1.0 . 2>&1 | tail -5
sudo docker run --rm --entrypoint bash chatop-ai:1.1.0 -lc 'node -v && npm -v && pipx --version'
```
Expected: 打印 `v22.x`、npm 版本、pipx 版本，无报错。

- [ ] **Step 4: 提交**

```bash
cd /work/chatop-ai && git add Dockerfile && \
git commit -m "feat(chatop-ai): 预置 Node22 + pipx + 用户级 npm 前缀（应用管理器基础）"
```

---

## Task 2: 冷门项目包名/URL 容器内实测（先核验再写死 catalog）

> 设计 §12 要求。7 个 ⚠ 项目落地前必须实测，避免上架后点了报错。

**Files:**
- Create: `app-manager/PROBE.md`（记录实测结论）

- [ ] **Step 1: 在已构建镜像里逐个核验**

Run（一次性脚本）：
```bash
sudo docker run --rm --entrypoint bash chatop-ai:1.1.0 -lc '
for p in openclaw reasonix "@qwen-code/qwen-code" "@openai/codex" "@anthropic-ai/claude-code" opencode-ai "@mimo-ai/cli"; do
  echo -n "npm:$p => "; npm view "$p" version 2>/dev/null || echo "NOT FOUND";
done
echo "--- pip ---"; for p in aider-chat sovyx nanobot; do echo -n "pip:$p => "; pip index versions "$p" 2>/dev/null | head -1 || echo "NOT FOUND"; done
echo "--- script URLs ---"; for u in https://plandex.ai/install.sh https://install.nanobot.ai https://raw.githubusercontent.com/NousResearch/hermes-agent/main/scripts/install.sh; do
  echo -n "$u => "; curl -fsSL -I "$u" -o /dev/null -w "%{http_code}\n" --max-time 10 || echo "UNREACHABLE"; done'
```

- [ ] **Step 2: 把每项"确认存在/不存在/不可达"写进 `app-manager/PROBE.md`**

记录格式：`<id> | <核验命令> | <结果 version/HTTP/NOT FOUND> | 是否上架一期`。
判定规则：`NOT FOUND` / `UNREACHABLE` 的项**不进**一期可点击清单（或标 `"available": false` 灰显+提示）。

- [ ] **Step 3: 提交**

```bash
cd /work/chatop-ai && git add app-manager/PROBE.md && \
git commit -m "docs(chatop-ai): 应用管理器一期冷门项目包名实测核验"
```

---

## Task 3: apps-catalog.json（一期清单 + 图标名 + 命令）

**Files:**
- Create: `app-manager/apps-catalog.json`

- [ ] **Step 1: 写 catalog（按 Task 2 实测结果剔除不可用项；命令字段后端持有）**

```json
{
  "version": 1,
  "apps": [
    {"id":"continue","name":"Continue.dev","category":"vscode-ext","kind":"vscode-ext","icon":"continue.svg","description":"VS Code/JetBrains 开源 AI 插件","install":"code --install-extension Continue.continue","remove":"code --uninstall-extension Continue.continue","detect":"code --list-extensions | grep -qi continue.continue","needs":[],"homepage":"https://continue.dev","notes":"运行需配模型，可指向本地 Ollama"},
    {"id":"cline","name":"Cline","category":"vscode-ext","kind":"vscode-ext","icon":"cline.svg","description":"VS Code 自主编码 Agent","install":"code --install-extension saoudrizwan.claude-dev","remove":"code --uninstall-extension saoudrizwan.claude-dev","detect":"code --list-extensions | grep -qi saoudrizwan.claude-dev","needs":[],"homepage":"https://cline.bot","notes":"运行需 key 或本地模型"},
    {"id":"claude-code","name":"Claude Code","category":"ai-cli","kind":"cli-npm","icon":"claude-code.svg","description":"Anthropic 官方 CLI","install":"npm i -g @anthropic-ai/claude-code","remove":"npm rm -g @anthropic-ai/claude-code","detect":"command -v claude","needs":["node"],"homepage":"https://www.anthropic.com","notes":"需 ANTHROPIC_API_KEY，国内需代理"},
    {"id":"codex","name":"Codex","category":"ai-cli","kind":"cli-npm","icon":"codex.svg","description":"OpenAI 官方终端编码 Agent","install":"npm i -g @openai/codex","remove":"npm rm -g @openai/codex","detect":"command -v codex","needs":["node"],"homepage":"https://openai.com","notes":"需 OpenAI 登录/key"},
    {"id":"opencode","name":"OpenCode","category":"ai-cli","kind":"cli-npm","icon":"opencode.svg","description":"开源终端/TUI 代码代理","install":"npm i -g opencode-ai@latest","remove":"npm rm -g opencode-ai","detect":"command -v opencode","needs":["node"],"homepage":"https://opencode.ai","notes":"可接多模型"},
    {"id":"qwen-code","name":"Qwen Code","category":"ai-cli","kind":"cli-npm","icon":"qwen.svg","description":"阿里通义千问编码助手","install":"npm i -g @qwen-code/qwen-code@latest","remove":"npm rm -g @qwen-code/qwen-code","detect":"command -v qwen","needs":["node"],"homepage":"https://github.com/QwenLM","notes":"国内友好，需付费/自带 key"},
    {"id":"openclaw","name":"OpenClaw","category":"ai-runtime","kind":"cli-npm","icon":"openclaw.svg","description":"本地优先的个人 AI 助理网关","install":"npm i -g openclaw@latest","remove":"npm rm -g openclaw","detect":"command -v openclaw","needs":["node"],"homepage":"https://github.com/openclaw","notes":"前台运行 openclaw gateway"},
    {"id":"reasonix","name":"Reasonix","category":"ai-cli","kind":"cli-npm","icon":"reasonix.svg","description":"为 DeepSeek 优化的终端 Agent","install":"npm i -g reasonix","remove":"npm rm -g reasonix","detect":"command -v reasonix","needs":["node"],"homepage":"https://github.com/esengine/reasonix","notes":"社区项目，绑 DeepSeek key"},
    {"id":"aider","name":"Aider","category":"ai-cli","kind":"cli-pip","icon":"aider.svg","description":"终端 AI 结对编程，深度集成 Git","install":"pipx install aider-chat","remove":"pipx uninstall aider-chat","detect":"command -v aider","needs":[],"homepage":"https://aider.chat","notes":"Py3.10 兼容，最稳"},
    {"id":"plandex","name":"Plandex","category":"ai-cli","kind":"cli-script","icon":"plandex.svg","description":"终端 AI 编程工作流","install":"curl -sL https://plandex.ai/install.sh | bash","remove":"rm -f $HOME/.local/bin/plandex /usr/local/bin/plandex","detect":"command -v plandex","needs":[],"homepage":"https://plandex.ai","notes":"Go 二进制；Cloud 需自托管"},
    {"id":"nanobot","name":"Nanobot","category":"ai-runtime","kind":"cli-script","icon":"nanobot.svg","description":"超轻量个人 AI 助理","install":"curl -sfL https://install.nanobot.ai | sh","remove":"rm -f $HOME/.local/bin/nanobot","detect":"command -v nanobot","needs":[],"homepage":"https://nanobot.ai","notes":"域名国内可达性存疑"},
    {"id":"hermes","name":"Hermes Agent","category":"ai-runtime","kind":"cli-script","icon":"hermes.svg","description":"自改进型 AI 代理框架","install":"curl -fsSL https://raw.githubusercontent.com/NousResearch/hermes-agent/main/scripts/install.sh | bash -s -- --skip-setup","remove":"rm -rf $HOME/.hermes /usr/local/bin/hermes","detect":"command -v hermes","needs":[],"homepage":"https://github.com/NousResearch/hermes-agent","notes":"raw.githubusercontent 国内需代理"}
  ]
}
```

> 注：实际上架以 Task 2 `PROBE.md` 为准；核验为 `NOT FOUND/UNREACHABLE` 的项，从本文件移除或加 `"available": false`。

- [ ] **Step 2: 提交**

```bash
cd /work/chatop-ai && git add app-manager/apps-catalog.json && \
git commit -m "feat(chatop-ai): 应用管理器一期 catalog（11 项 CLI/插件）"
```

---

## Task 4: 收集各应用官方图标

**Files:**
- Create: `app-manager/icons/*.svg`（与 catalog 的 `icon` 字段一一对应）
- Create: `app-manager/fetch-icons.sh`（记录每个图标的官方获取来源，可复跑）

- [ ] **Step 1: 写 `fetch-icons.sh`，从各项目官方/GitHub logo 资源拉取**

```bash
#!/usr/bin/env bash
# 从各项目官方源拉取 logo，存为 app-manager/icons/<id>.svg|png。
# 仅作标识性展示用途（应用商店式图标）。失败的留占位由 Step 2 处理。
set -u
cd "$(dirname "$0")/icons"
declare -A SRC=(
  [continue]="https://raw.githubusercontent.com/continuedev/continue/main/media/icon.png"
  [cline]="https://raw.githubusercontent.com/cline/cline/main/assets/icons/icon.png"
  [claude-code]="https://www.anthropic.com/favicon.ico"
  [codex]="https://openai.com/favicon.ico"
  [opencode]="https://raw.githubusercontent.com/sst/opencode/dev/packages/web/src/assets/logo-ornate-dark.svg"
  [qwen]="https://raw.githubusercontent.com/QwenLM/Qwen/main/assets/logo.jpg"
  [openclaw]="https://avatars.githubusercontent.com/u/openclaw"
  [reasonix]="https://avatars.githubusercontent.com/esengine"
  [aider]="https://aider.chat/assets/icons/favicon-32x32.png"
  [plandex]="https://raw.githubusercontent.com/plandex-ai/plandex/main/releases/images/plandex-logo-dark.png"
  [nanobot]="https://avatars.githubusercontent.com/nanobot-ai"
  [hermes]="https://avatars.githubusercontent.com/NousResearch"
)
for id in "${!SRC[@]}"; do
  ext="${SRC[$id]##*.}"; [ "$ext" = "${SRC[$id]}" ] && ext="png"
  echo -n "fetch $id ($ext) ... "
  if curl -fsSL --max-time 15 -o "${id}.${ext}" "${SRC[$id]}"; then echo OK; else echo FAIL; fi
done
ls -la
```

- [ ] **Step 2: 运行并核对，缺失项用统一占位图**

Run:
```bash
cd /work/chatop-ai/app-manager && bash fetch-icons.sh
```
对 FAIL 的项：放一个统一占位 `placeholder.svg`（简单灰色方块带首字母），catalog 的 `icon` 暂指向它，并在 notes 标注"图标待补"。统一把 catalog 的 `icon` 字段对齐到实际落地的文件名/扩展名。

- [ ] **Step 3: 提交**

```bash
cd /work/chatop-ai && git add app-manager/icons app-manager/fetch-icons.sh && \
git commit -m "feat(chatop-ai): 收集应用管理器各应用官方图标"
```

---

## Task 5: 应用服务后端（Python http.server）+ 单测

**Files:**
- Create: `app-manager/app_manager.py`
- Test: `app-manager/tests/test_app_manager.py`

- [ ] **Step 1: 写失败测试（catalog 加载剥离命令字段 + id 白名单 + detect 状态）**

```python
# app-manager/tests/test_app_manager.py
import json, os, sys, tempfile, subprocess
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
import app_manager as am

CATALOG = {"version":1,"apps":[
  {"id":"aider","name":"Aider","category":"ai-cli","kind":"cli-pip","icon":"aider.svg",
   "description":"d","install":"pipx install aider-chat","remove":"pipx uninstall aider-chat",
   "detect":"command -v aider","needs":[],"homepage":"h","notes":"n"}]}

def _mgr(tmp_path):
    p = os.path.join(tmp_path, "c.json"); open(p,"w").write(json.dumps(CATALOG))
    return am.AppManager(p)

def test_public_catalog_strips_commands():
    with tempfile.TemporaryDirectory() as t:
        pub = _mgr(t).public_catalog()
        app = pub["apps"][0]
        assert app["id"] == "aider" and "icon" in app and "description" in app
        assert "install" not in app and "remove" not in app and "detect" not in app

def test_install_rejects_unknown_id():
    with tempfile.TemporaryDirectory() as t:
        try:
            _mgr(t).command_for("nope", "install"); assert False
        except KeyError:
            pass

def test_command_for_returns_predefined():
    with tempfile.TemporaryDirectory() as t:
        assert _mgr(t).command_for("aider","install") == "pipx install aider-chat"

def test_status_uses_detect(monkeypatch=None):
    with tempfile.TemporaryDirectory() as t:
        m = _mgr(t)
        m._run_detect = lambda cmd: cmd == "command -v aider"  # stub
        assert m.status() == {"aider": True}
```

- [ ] **Step 2: 运行验证失败**

Run: `cd /work/chatop-ai/app-manager && python3 -m pytest tests/test_app_manager.py -v`
Expected: FAIL（`No module named app_manager` 或属性缺失）。

- [ ] **Step 3: 实现 `app_manager.py`**

```python
#!/usr/bin/env python3
"""chatop-ai 应用管理器后端：catalog/status/install/remove/logs。
仅监听 127.0.0.1，命令只来自 catalog（白名单），绝不执行前端传入字符串。"""
import json, os, subprocess, threading, queue, time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

CATALOG_PATH = os.environ.get("APPS_CATALOG", "/etc/chatop/apps-catalog.json")
LOG_DIR = "/tmp/app-mgr"; PORT = int(os.environ.get("APPS_PORT", "8686"))
PUBLIC_FIELDS = ("id","name","category","kind","icon","description","needs","homepage","notes","available")

class AppManager:
    def __init__(self, catalog_path=CATALOG_PATH):
        self.catalog_path = catalog_path
        self._tasks = queue.Queue(); self._state = {}  # id -> queued|running|success|failed
        os.makedirs(LOG_DIR, exist_ok=True)
        threading.Thread(target=self._worker, daemon=True).start()

    def _load(self):
        with open(self.catalog_path) as f: return json.load(f)

    def public_catalog(self):
        cat = self._load()
        cat["apps"] = [{k:a[k] for k in PUBLIC_FIELDS if k in a} for a in cat["apps"]]
        return cat

    def _app(self, app_id):
        for a in self._load()["apps"]:
            if a["id"] == app_id: return a
        raise KeyError(app_id)

    def command_for(self, app_id, action):  # action in install|remove
        return self._app(app_id)[action]

    def _run_detect(self, cmd):
        return subprocess.run(["bash","-lc",cmd], stdout=subprocess.DEVNULL,
                              stderr=subprocess.DEVNULL).returncode == 0

    def status(self):
        return {a["id"]: self._run_detect(a["detect"]) for a in self._load()["apps"]}

    def enqueue(self, app_id, action):
        self._app(app_id)  # raises KeyError if unknown
        if action not in ("install","remove"): raise ValueError(action)
        self._state[app_id] = "queued"; self._tasks.put((app_id, action)); return True

    def task_state(self, app_id): return self._state.get(app_id, "unknown")

    def _worker(self):
        while True:
            app_id, action = self._tasks.get()
            cmd = self.command_for(app_id, action)
            self._state[app_id] = "running"
            logf = os.path.join(LOG_DIR, f"{app_id}.log")
            with open(logf,"w") as lf:
                lf.write(f"$ {cmd}\n"); lf.flush()
                rc = subprocess.run(["bash","-lc",cmd], stdout=lf, stderr=subprocess.STDOUT).returncode
            self._state[app_id] = "success" if rc==0 else "failed"
            self._tasks.task_done()

MGR = None
class Handler(BaseHTTPRequestHandler):
    def _json(self, code, obj):
        b=json.dumps(obj).encode(); self.send_response(code)
        self.send_header("Content-Type","application/json"); self.send_header("Content-Length",str(len(b)))
        self.end_headers(); self.wfile.write(b)
    def do_GET(self):
        if self.path.startswith("/apps/catalog"): return self._json(200, MGR.public_catalog())
        if self.path.startswith("/apps/status"):  return self._json(200, MGR.status())
        if self.path.startswith("/apps/logs"):
            from urllib.parse import urlparse, parse_qs
            qid = parse_qs(urlparse(self.path).query).get("id",[""])[0]
            p=os.path.join(LOG_DIR,f"{qid}.log"); txt=open(p).read() if os.path.exists(p) else ""
            return self._json(200, {"id":qid,"state":MGR.task_state(qid),"log":txt})
        return self._json(404, {"error":"not found"})
    def do_POST(self):
        if self.path.rstrip("/") in ("/apps/install","/apps/remove"):
            n=int(self.headers.get("Content-Length",0)); body=json.loads(self.rfile.read(n) or b"{}")
            action="install" if self.path.rstrip("/").endswith("install") else "remove"
            try:
                MGR.enqueue(body["id"], action); return self._json(202, {"id":body["id"],"state":"queued"})
            except KeyError: return self._json(400, {"error":"unknown app id"})
            except (ValueError,TypeError): return self._json(400, {"error":"bad request"})
        return self._json(404, {"error":"not found"})
    def log_message(self,*a): pass

def main():
    global MGR; MGR = AppManager()
    ThreadingHTTPServer(("127.0.0.1", PORT), Handler).serve_forever()

if __name__ == "__main__": main()
```

- [ ] **Step 4: 运行验证通过**

Run: `cd /work/chatop-ai/app-manager && python3 -m pytest tests/test_app_manager.py -v`
Expected: 4 passed。

- [ ] **Step 5: 提交**

```bash
cd /work/chatop-ai && git add app-manager/app_manager.py app-manager/tests && \
git commit -m "feat(chatop-ai): 应用管理器后端 API + 单测（白名单/状态/任务队列）"
```

---

## Task 6: Caddy 反代 /apps + 启动脚本接入 + Dockerfile 安装

**Files:**
- Modify: `caddy/Caddyfile`
- Create: `app-manager/start-app-manager.sh`
- Modify: `Dockerfile`

- [ ] **Step 1: Caddyfile 增加 /apps 反代**

在 `handle /files* { ... }` 之后、`handle { ... }` 之前插入：
```
    handle /apps* {
        reverse_proxy 127.0.0.1:8686
    }
```

- [ ] **Step 2: 写 `start-app-manager.sh`**

```bash
#!/usr/bin/env bash
set -e
export APPS_CATALOG="${APPS_CATALOG:-/etc/chatop/apps-catalog.json}"
export APPS_PORT="${APPS_PORT:-8686}"
exec python3 /usr/local/lib/chatop/app_manager.py
```

- [ ] **Step 3: Dockerfile 末尾轻量层增加 app-manager 安装 + 启动接入**

在末尾轻量资源层（前端 COPY 附近，USER root 上下文）加：
```dockerfile
# === 应用管理器：后端 + catalog + 图标 + 启动 ===
RUN mkdir -p /usr/local/lib/chatop /etc/chatop
COPY app-manager/app_manager.py /usr/local/lib/chatop/app_manager.py
COPY app-manager/apps-catalog.json /etc/chatop/apps-catalog.json
COPY app-manager/icons/ /usr/share/kasmvnc/www/app-icons/
COPY app-manager/start-app-manager.sh /usr/local/bin/start-app-manager.sh
RUN chmod +x /usr/local/bin/start-app-manager.sh
```
并把启动接入 `custom_startup.sh`（修改现有那行 printf，追加一行）：
```dockerfile
RUN printf '#!/bin/bash\n/usr/local/bin/start-filebrowser.sh >/tmp/filebrowser.log 2>&1 &\n/usr/local/bin/start-caddy.sh >/tmp/caddy.log 2>&1 &\n/usr/local/bin/start-app-manager.sh >/tmp/app-mgr.log 2>&1 &\n' > /dockerstartup/custom_startup.sh && chmod +x /dockerstartup/custom_startup.sh
```
（注：替换 Dockerfile 中现有的那条 custom_startup printf，加上 app-manager 一行。）

- [ ] **Step 4: 构建 + 端到端验证 API 在线**

Run:
```bash
cd /work/chatop-ai && sudo docker build --build-arg VERSION=1.1.0 -t chatop-ai:1.1.0 . 2>&1 | tail -4
sudo docker compose down; sudo docker compose up -d; sleep 12
echo -n "catalog: "; curl -ks -u admin:test12345 https://localhost:6901/apps/catalog | head -c 120; echo
echo -n "status:  "; curl -ks -u admin:test12345 https://localhost:6901/apps/status | head -c 200; echo
```
Expected: catalog 返回 JSON（无 install/remove/detect 字段）；status 返回各 id 的 true/false。

- [ ] **Step 5: 提交**

```bash
cd /work/chatop-ai && git add caddy/Caddyfile app-manager/start-app-manager.sh Dockerfile && \
git commit -m "feat(chatop-ai): Caddy 反代 /apps + 应用服务启动接入 + 镜像安装"
```

---

## Task 7: 前端控制栏「应用」入口 + 模态框

**Files:**
- Modify: `novnc-src/index.html`
- Modify: `novnc-src/app/ui.js`
- Modify: `novnc-src/app/styles/base.css`

- [ ] **Step 1: index.html 控制栏加「应用」按钮 + 模态框容器**

在 `chatop_header` 之后、其它按钮之前加按钮：
```html
                <!-- 应用管理器入口 -->
                <div class="noVNC_button_div noVNC_hide_on_disconnect">
                    <input type="image" alt="应用" src="app/images/icons/kasm_logo.svg"
                        id="chatop_apps_button" class="noVNC_button" title="应用管理">
                </div>
```
在 `</div> <!-- End of noVNC_control_bar -->` 之后加模态框：
```html
    <div id="chatop_apps_modal" class="chatop_apps_modal" style="display:none">
      <div class="chatop_apps_dialog">
        <div class="chatop_apps_head">
          <span>应用管理</span>
          <input id="chatop_apps_search" placeholder="搜索应用…">
          <button id="chatop_apps_close">×</button>
        </div>
        <div id="chatop_apps_grid" class="chatop_apps_grid"></div>
        <div id="chatop_apps_detail" class="chatop_apps_detail" style="display:none"></div>
      </div>
    </div>
```

- [ ] **Step 2: ui.js 加应用管理器逻辑（拉 catalog+status、渲染、安装/卸载、轮询日志）**

在 ui.js 末尾（其它 chatop 逻辑附近）加：
```javascript
const ChatopApps = {
  catalog: [], status: {},
  async open() {
    document.getElementById('chatop_apps_modal').style.display = 'flex';
    await this.refresh();
  },
  close() { document.getElementById('chatop_apps_modal').style.display = 'none'; },
  async refresh() {
    const [c, s] = await Promise.all([
      fetch('/apps/catalog').then(r=>r.json()),
      fetch('/apps/status').then(r=>r.json())
    ]);
    this.catalog = c.apps || []; this.status = s || {}; this.renderGrid();
  },
  renderGrid(filter='') {
    const g = document.getElementById('chatop_apps_grid'); g.innerHTML='';
    this.catalog.filter(a => (a.name+a.description+a.id).toLowerCase().includes(filter))
      .forEach(a => {
        const installed = !!this.status[a.id];
        const card = document.createElement('div'); card.className='chatop_app_card';
        card.innerHTML = `<img src="app-icons/${a.icon}" onerror="this.style.visibility='hidden'">
          <div class="chatop_app_name">${a.name}</div>
          ${installed?'<span class="chatop_app_badge">已安装</span>':''}`;
        card.onclick = () => this.detail(a);
        g.appendChild(card);
      });
  },
  detail(a) {
    const installed = !!this.status[a.id];
    const d = document.getElementById('chatop_apps_detail');
    d.style.display='block';
    d.innerHTML = `<button id="chatop_apps_back">← 返回</button>
      <img src="app-icons/${a.icon}" class="chatop_app_dicon">
      <h3>${a.name}</h3><p>${a.description}</p><p class="chatop_app_notes">${a.notes||''}</p>
      <button id="chatop_app_action" class="${installed?'remove':'install'}">${installed?'卸载':'安装'}</button>
      <pre id="chatop_app_log"></pre>`;
    document.getElementById('chatop_apps_back').onclick=()=>{d.style.display='none';};
    document.getElementById('chatop_app_action').onclick=()=>this.act(a, installed?'remove':'install');
  },
  async act(a, action) {
    const log = document.getElementById('chatop_app_log'); log.textContent='提交中…';
    await fetch('/apps/'+action, {method:'POST', headers:{'Content-Type':'application/json'},
      body: JSON.stringify({id:a.id})});
    const poll = setInterval(async () => {
      const r = await fetch('/apps/logs?id='+a.id).then(r=>r.json());
      log.textContent = r.log || '';
      if (r.state==='success' || r.state==='failed') {
        clearInterval(poll); await this.refresh(); this.detail(a);
      }
    }, 1500);
  }
};
UI.addClickHandle && UI.addClickHandle('chatop_apps_button', () => ChatopApps.open());
document.addEventListener('DOMContentLoaded', () => {
  const c=document.getElementById('chatop_apps_close'); if(c) c.onclick=()=>ChatopApps.close();
  const s=document.getElementById('chatop_apps_search'); if(s) s.oninput=e=>ChatopApps.renderGrid(e.target.value.toLowerCase());
});
```
> 注：`UI.addClickHandle` 在断开连接前可能未就绪；若 noVNC 的按钮绑定时机不同，改为在 `addControlbarHandlers()` 内调用 `UI.addClickHandle('chatop_apps_button', () => ChatopApps.open())`（与 files 按钮同处，参考 ui.js 现有 `addControlbarHandlers`）。

- [ ] **Step 3: base.css 加模态框/卡片样式**

```css
.chatop_apps_modal{position:fixed;inset:0;background:rgba(0,0,0,.5);z-index:10000;
  align-items:center;justify-content:center;}
.chatop_apps_dialog{width:min(900px,92vw);height:min(640px,88vh);background:#1b1f27;color:#eee;
  border-radius:10px;display:flex;flex-direction:column;overflow:hidden;}
.chatop_apps_head{display:flex;gap:10px;align-items:center;padding:12px 16px;
  border-bottom:1px solid rgba(255,255,255,.12);}
.chatop_apps_head span{font-weight:600;}
.chatop_apps_head input{flex:1;padding:6px 10px;border-radius:6px;border:1px solid #444;
  background:#11141a;color:#eee;}
.chatop_apps_head button{background:none;border:none;color:#aaa;font-size:22px;cursor:pointer;}
.chatop_apps_grid{flex:1;overflow:auto;display:grid;
  grid-template-columns:repeat(auto-fill,minmax(150px,1fr));gap:16px;padding:16px;}
.chatop_app_card{background:#232834;border:1px solid #333;border-radius:8px;padding:14px;
  text-align:center;cursor:pointer;transition:transform .15s;position:relative;}
.chatop_app_card:hover{transform:translateY(-4px);}
.chatop_app_card img{width:48px;height:48px;object-fit:contain;}
.chatop_app_name{margin-top:8px;font-size:13px;}
.chatop_app_badge{position:absolute;top:6px;right:6px;background:#2e7d32;color:#fff;
  font-size:10px;padding:2px 6px;border-radius:10px;}
.chatop_apps_detail{padding:20px;overflow:auto;}
.chatop_app_dicon{width:72px;height:72px;object-fit:contain;}
.chatop_app_notes{color:#f0ad4e;font-size:12px;}
#chatop_app_action{margin-top:12px;padding:8px 18px;border:none;border-radius:6px;
  color:#fff;cursor:pointer;}
#chatop_app_action.install{background:#1976d2;} #chatop_app_action.remove{background:#c62828;}
#chatop_app_log{margin-top:14px;background:#0d0f14;padding:10px;border-radius:6px;
  max-height:220px;overflow:auto;font-size:12px;white-space:pre-wrap;}
body.chatop-theme-light .chatop_apps_dialog{background:#fff;color:#1c1f23;}
```

- [ ] **Step 4: 重建 + 人工浏览器核对**

Run:
```bash
cd /work/chatop-ai && sudo docker build --build-arg VERSION=1.1.0 -t chatop-ai:1.1.0 . 2>&1 | tail -3
sudo docker compose down; sudo docker compose up -d; sleep 12
sudo docker run --rm --entrypoint bash chatop-ai:1.1.0 -lc 'grep -c "chatop_apps_button\|chatop_apps_modal" /usr/share/kasmvnc/www/index.html'
```
人工：硬刷新登录 → 控制栏点「应用」→ 模态框出现、卡片带图标+已安装徽章、搜索可过滤、点卡片进详情、装/卸按钮可见。

- [ ] **Step 5: 提交**

```bash
cd /work/chatop-ai && git add novnc-src/index.html novnc-src/app/ui.js novnc-src/app/styles/base.css && \
git commit -m "feat(chatop-ai): 应用管理器前端入口 + 模态框（卡片/图标/状态/装卸/日志）"
```

---

## Task 8: 持久化（home 命名卷）+ 端到端验证

**Files:**
- Modify: `docker-compose.yml`

- [ ] **Step 1: compose 挂 home 命名卷**

在 `chatop-ai` service 下加：
```yaml
    volumes:
      - chatop-home:/home/kasm-user
```
并在文件末尾加顶层：
```yaml
volumes:
  chatop-home:
```

- [ ] **Step 2: 重启并验证「装→状态→卸→持久化」全链路**

Run:
```bash
cd /work/chatop-ai && sudo docker compose down; sudo docker compose up -d; sleep 12
# 装 aider（pip 类，确定可用）
curl -ks -u admin:test12345 -X POST https://localhost:6901/apps/install -H 'Content-Type: application/json' -d '{"id":"aider"}'
sleep 40
echo -n "status aider: "; curl -ks -u admin:test12345 https://localhost:6901/apps/status | python3 -c 'import sys,json;print(json.load(sys.stdin).get("aider"))'
# 持久化：重建容器后仍在
sudo docker compose down; sudo docker compose up -d; sleep 12
echo -n "after rebuild: "; curl -ks -u admin:test12345 https://localhost:6901/apps/status | python3 -c 'import sys,json;print(json.load(sys.stdin).get("aider"))'
```
Expected: 第一次 `True`；重建后仍 `True`（home 卷持久化生效）。

- [ ] **Step 3: 安全验证（非白名单 id 拒绝）**

Run:
```bash
curl -ks -u admin:test12345 -X POST https://localhost:6901/apps/install -H 'Content-Type: application/json' -d '{"id":"rm -rf /;evil"}' -w " HTTP %{http_code}\n"
```
Expected: `{"error":"unknown app id"}` HTTP 400。

- [ ] **Step 4: 提交**

```bash
cd /work/chatop-ai && git add docker-compose.yml && \
git commit -m "feat(chatop-ai): 应用管理器持久化（home 命名卷）+ 端到端验证"
```

---

## Self-Review

**Spec coverage（对照 design doc）：**
- 旁挂后端 API（catalog/status/install/remove/logs）→ Task 5 ✓
- 白名单安全（只传 id、命令后端持有）→ Task 5（command_for/enqueue + KeyError）+ Task 8 Step 3 ✓
- 真实状态检测（detect）→ Task 5 status ✓
- catalog 多 kind（npm/pip/script/vscode-ext）→ Task 3 ✓
- 官方图标 → Task 4 ✓（用户新增要求已纳入）
- Node22 预置 → Task 1 ✓
- 持久化（home 卷 + 用户级 npm/pipx）→ Task 1 + Task 8 ✓
- 前端控制栏入口 + 模态框 + 进度日志 → Task 7 ✓
- Caddy /apps 反代 → Task 6 ✓
- 冷门项目落地前实测 → Task 2 ✓
- 串行队列防锁冲突 → Task 5 _worker（单线程队列）✓

**Placeholder scan：** catalog 命令以 Task 2 实测为准（先核验再写死，非占位）；前端 addClickHandle 绑定时机给了备选方案，非占位。

**一致性：** API 路径（/apps/catalog|status|install|remove|logs）、端口 8686、元素 id（chatop_apps_button/modal/grid/detail/search/close）、catalog 字段名在各 Task 间一致。

**非目标：** GUI/Sovyx/MiMo（二期）、NanoClaw（DinD 后续）、Qcode/Modo（剔除）—— 本计划不含，符合分期。
```
