# 已安装应用分组功能 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把应用管理「本机已安装」视图改成手机桌面式分组网格——分组卡与应用卡混排、拖拽建组/归组/排序、居中浮层展开分组、多选批量入组、系统应用自动归组，分组持久化在卷。

**Architecture:** 后端 `app_manager.py` 新增 `GroupStore`（读写 `groups.json` + 纯函数 `reconcile` 对账已安装清单）和 `GET/PUT /apps/groups` 两个路由（走现有 Caddy cookie 网关）。前端 `ui.js` 的 `ChatopApps` 重写 `__installed__` 分支：混排渲染 + HTML5 拖拽 + 居中浮层 + 多选，布局变更防抖 `PUT` 落库。

**Tech Stack:** Python 3（stdlib http.server，pytest 风格 tempdir 测试）、原生 JS（noVNC，无构建期 JS 单测，靠 `node --check` 语法校验 + 容器内 curl/视觉验证）、CSS。

设计依据：`docs/2026-06-30-app-grouping-design.md`。

---

## 文件结构

- **修改** `app-manager/app_manager.py`：新增 `GROUPS_PATH` 常量、`GroupStore` 类（`load`/`save`/`reconcile`）、`do_GET` 增 `/apps/groups`、`do_POST` 增 `PUT 语义的 /apps/groups` 保存。
- **修改** `app-manager/tests/test_app_manager.py`：新增 `GroupStore` 的 TDD 用例。
- **修改** `novnc-src/app/ui.js`：`ChatopApps` 增 state、`refresh` 拉 groups、重写 `__installed__` 渲染、拖拽、浮层、多选、`saveGroups`。
- **修改** `novnc-src/app/styles/base.css`：分组卡封面拼贴 / 浮层 / 拖拽态 / 多选态样式（含 `body.chatop-theme-light` 适配）。
- **不新增独立文件**：遵循该仓库「逻辑集中在 app_manager.py / ui.js」的既有约定。

数据结构（groups.json）：
```json
{"version":1,
 "items":[{"type":"app","key":"google-chrome.desktop"},
          {"type":"group","id":"g1","name":"办公","apps":["wps-office-wps-pa.desktop"]}],
 "pulled_out_system":["xterm.desktop"]}
```
> 注意：`installed_apps()` 返回的 `key` 是**不带 `.desktop` 后缀**的文件名 stem（见 `app_manager.py` 第 198 行 `os.path.splitext(...)[0]`）。groups.json 全程用这个 stem 作 key，设计文档里的示例后缀仅为可读性，实现以 stem 为准。

---

## Task 1: 后端 GroupStore — load / save（原子写）

**Files:**
- Modify: `app-manager/app_manager.py`（顶部常量区 + 新增类）
- Test: `app-manager/tests/test_app_manager.py`

- [ ] **Step 1: 写失败测试**

在 `tests/test_app_manager.py` 末尾追加：

```python
def test_groupstore_load_missing_returns_empty():
    with tempfile.TemporaryDirectory() as t:
        gs = am.GroupStore(os.path.join(t, "nope", "groups.json"))
        assert gs.load() == {"version": 1, "items": [], "pulled_out_system": []}

def test_groupstore_save_then_load_roundtrip():
    with tempfile.TemporaryDirectory() as t:
        gs = am.GroupStore(os.path.join(t, "sub", "groups.json"))
        data = {"version": 1,
                "items": [{"type": "group", "id": "g1", "name": "办公", "apps": ["wps"]}],
                "pulled_out_system": []}
        gs.save(data)
        assert gs.load() == data

def test_groupstore_load_corrupt_returns_empty():
    with tempfile.TemporaryDirectory() as t:
        p = os.path.join(t, "groups.json"); open(p, "w").write("{not json")
        assert am.GroupStore(p).load() == {"version": 1, "items": [], "pulled_out_system": []}
```

- [ ] **Step 2: 跑测试确认失败**

Run: `cd app-manager && PYTHONPATH=. python -m pytest tests/test_app_manager.py -k groupstore -q`
Expected: FAIL（`AttributeError: module 'app_manager' has no attribute 'GroupStore'`）

- [ ] **Step 3: 实现 GroupStore.load/save**

在 `app_manager.py` 常量区（`LOG_DIR = ...` 那行下面）加：

```python
GROUPS_PATH = os.environ.get(
    "APPS_GROUPS", os.path.expanduser("~/.local/share/chatop/groups.json"))
_EMPTY_LAYOUT = {"version": 1, "items": [], "pulled_out_system": []}
```

在 `class AppManager` **定义之前**（紧挨着其它 helper）新增：

```python
class GroupStore:
    """读写 groups.json：原子保存 + 容错读取。布局校验/对账在 reconcile。"""
    def __init__(self, path=GROUPS_PATH):
        self.path = path

    def load(self):
        try:
            with open(self.path, encoding="utf-8") as f:
                d = json.load(f)
            if not isinstance(d, dict) or "items" not in d:
                return dict(_EMPTY_LAYOUT, items=[], pulled_out_system=[])
            d.setdefault("version", 1)
            d.setdefault("items", [])
            d.setdefault("pulled_out_system", [])
            return d
        except (OSError, ValueError):
            return {"version": 1, "items": [], "pulled_out_system": []}

    def save(self, data):
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        tmp = self.path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False)
        os.replace(tmp, self.path)
```

- [ ] **Step 4: 跑测试确认通过**

Run: `cd app-manager && PYTHONPATH=. python -m pytest tests/test_app_manager.py -k groupstore -q`
Expected: 3 passed

- [ ] **Step 5: 提交**

```bash
git add app-manager/app_manager.py app-manager/tests/test_app_manager.py
git commit -m "feat(apps): add GroupStore load/save for app grouping"
```

---

## Task 2: 后端 reconcile — 对账已安装清单

**Files:**
- Modify: `app-manager/app_manager.py`（`GroupStore` 增 `reconcile`）
- Test: `app-manager/tests/test_app_manager.py`

对账规则（设计 3.4）：剔除已卸载 key；过滤空组；未归位的新应用——系统应用且不在 `pulled_out_system` → 进「系统应用」组（`auto:true`，无则建）；其余 → 顶层末尾。

- [ ] **Step 1: 写失败测试**

追加到 `tests/test_app_manager.py`：

```python
def _layout(items, pulled=None):
    return {"version": 1, "items": items, "pulled_out_system": pulled or []}

def _inst(key, source="user"):
    return {"key": key, "name": key, "source": source}

def test_reconcile_drops_uninstalled_apps():
    gs = am.GroupStore("/x")
    layout = _layout([{"type": "app", "key": "gone"}, {"type": "app", "key": "chrome"}])
    out = gs.reconcile(layout, [_inst("chrome")])
    keys = [i["key"] for i in out["items"] if i["type"] == "app"]
    assert keys == ["chrome"]

def test_reconcile_drops_empty_group():
    gs = am.GroupStore("/x")
    layout = _layout([{"type": "group", "id": "g1", "name": "空", "apps": ["gone"]}])
    out = gs.reconcile(layout, [_inst("chrome")])
    groups = [i for i in out["items"] if i["type"] == "group"]
    assert groups == []
    assert [i["key"] for i in out["items"] if i["type"] == "app"] == ["chrome"]

def test_reconcile_new_user_app_goes_top_level_end():
    gs = am.GroupStore("/x")
    layout = _layout([{"type": "app", "key": "chrome"}])
    out = gs.reconcile(layout, [_inst("chrome"), _inst("newapp")])
    assert [i["key"] for i in out["items"] if i["type"] == "app"] == ["chrome", "newapp"]

def test_reconcile_system_app_auto_grouped():
    gs = am.GroupStore("/x")
    out = gs.reconcile(_layout([]), [_inst("thunar", "system")])
    grp = [i for i in out["items"] if i["type"] == "group"]
    assert len(grp) == 1 and grp[0].get("auto") is True
    assert "thunar" in grp[0]["apps"]

def test_reconcile_pulled_out_system_not_regrouped():
    gs = am.GroupStore("/x")
    layout = _layout([{"type": "app", "key": "thunar"}], pulled=["thunar"])
    out = gs.reconcile(layout, [_inst("thunar", "system")])
    grp = [i for i in out["items"] if i["type"] == "group"]
    assert grp == []
    assert [i["key"] for i in out["items"] if i["type"] == "app"] == ["thunar"]

def test_reconcile_keeps_existing_group_membership():
    gs = am.GroupStore("/x")
    layout = _layout([{"type": "group", "id": "g1", "name": "办公", "apps": ["wps"]}])
    out = gs.reconcile(layout, [_inst("wps"), _inst("chrome")])
    grp = [i for i in out["items"] if i["type"] == "group"][0]
    assert grp["apps"] == ["wps"]
    assert [i["key"] for i in out["items"] if i["type"] == "app"] == ["chrome"]
```

- [ ] **Step 2: 跑测试确认失败**

Run: `cd app-manager && PYTHONPATH=. python -m pytest tests/test_app_manager.py -k reconcile -q`
Expected: FAIL（`AttributeError: 'GroupStore' object has no attribute 'reconcile'`）

- [ ] **Step 3: 实现 reconcile**

在 `GroupStore` 类里加方法：

```python
    SYS_GROUP_ID = "__system__"

    def reconcile(self, layout, installed):
        valid = {a["key"] for a in installed}
        sys_keys = {a["key"] for a in installed if a.get("source") == "system"}
        pulled = [k for k in layout.get("pulled_out_system", []) if k in valid]
        referenced = set()
        items = []
        for it in layout.get("items", []):
            if it.get("type") == "app":
                k = it.get("key")
                if k in valid and k not in referenced:
                    referenced.add(k); items.append({"type": "app", "key": k})
            elif it.get("type") == "group":
                apps = [k for k in it.get("apps", []) if k in valid and k not in referenced]
                referenced.update(apps)
                if apps:
                    items.append({"type": "group", "id": it.get("id") or ("g" + str(len(items))),
                                  "name": it.get("name") or "新建分组", "apps": apps,
                                  **({"auto": True} if it.get("auto") else {})})
        # 新应用归位
        new_keys = [a["key"] for a in installed if a["key"] not in referenced]
        sys_new = [k for k in new_keys if k in sys_keys and k not in pulled]
        usr_new = [k for k in new_keys if k not in sys_new]
        if sys_new:
            grp = next((g for g in items if g.get("type") == "group" and g.get("auto")), None)
            if grp:
                grp["apps"].extend(sys_new)
            else:
                items.append({"type": "group", "id": self.SYS_GROUP_ID,
                              "name": "系统应用", "apps": sys_new, "auto": True})
        for k in usr_new:
            items.append({"type": "app", "key": k})
        return {"version": 1, "items": items, "pulled_out_system": pulled}
```

- [ ] **Step 4: 跑测试确认通过**

Run: `cd app-manager && PYTHONPATH=. python -m pytest tests/test_app_manager.py -k reconcile -q`
Expected: 6 passed

- [ ] **Step 5: 全量测试 + 提交**

Run: `cd app-manager && PYTHONPATH=. python -m pytest tests/test_app_manager.py -q`
Expected: 全部 passed

```bash
git add app-manager/app_manager.py app-manager/tests/test_app_manager.py
git commit -m "feat(apps): GroupStore.reconcile against installed apps"
```

---

## Task 3: 后端路由 GET/PUT /apps/groups

**Files:**
- Modify: `app-manager/app_manager.py`（模块级实例化 + `do_GET` + `do_POST`）

- [ ] **Step 1: 实例化 GroupStore**

找到模块级 `MGR = AppManager()`（在 `main()` 附近/`class Handler` 之前），其旁加：

```python
GROUPS = GroupStore()
```
> 若 `MGR` 在 `main()` 里创建，则在同一作用域加 `GROUPS = GroupStore()`，并确保 `Handler` 能引用（与 `MGR` 同样方式）。

- [ ] **Step 2: do_GET 增 /apps/groups**

在 `do_GET` 里 `if self.path.startswith("/apps/installed"):` 那行**之后**加：

```python
        if self.path.startswith("/apps/groups"):
            layout = GROUPS.reconcile(GROUPS.load(), MGR.installed_apps())
            GROUPS.save(layout)
            return self._json(200, layout)
```

- [ ] **Step 3: do_POST 增 /apps/groups 保存**

在 `do_POST` 里第一条 `if` **之前**加（保存整份布局；做最小校验）：

```python
        if self.path.rstrip("/") == "/apps/groups":
            n = int(self.headers.get("Content-Length", 0))
            try:
                body = json.loads(self.rfile.read(n) or b"{}")
            except ValueError:
                return self._json(400, {"error": "bad json"})
            if not isinstance(body, dict) or not isinstance(body.get("items"), list):
                return self._json(400, {"error": "bad layout"})
            body.setdefault("version", 1); body.setdefault("pulled_out_system", [])
            GROUPS.save(body)
            return self._json(200, {"ok": True})
```

- [ ] **Step 4: 语法校验 + 端到端验证**

Run: `cd app-manager && python -m py_compile app_manager.py && echo OK`
Expected: OK

容器内联调（容器已在跑新镜像）：

```bash
cd /work/chatop-ai
PW=$(grep -E "^PASSWORD=" .env|cut -d= -f2); B="https://localhost:6901"
CK=$(curl -sk -i -d "username=admin&password=$PW" "$B/login"|grep -i set-cookie|sed "s/.*set-cookie: //I;s/;.*//")
# 先把改动拷进运行容器快速验证（无需整轮重建）：
sudo docker cp app-manager/app_manager.py chatop-ai:/usr/local/lib/chatop/app_manager.py
sudo docker exec chatop-ai pkill -f app_manager.py; sleep 2
curl -sk -H "Cookie: $CK" "$B/apps/groups" | python3 -m json.tool | head
```
Expected: 返回含 `items`、`pulled_out_system` 的 JSON，系统应用已进「系统应用」组。

- [ ] **Step 5: 提交**

```bash
git add app-manager/app_manager.py
git commit -m "feat(apps): GET/PUT /apps/groups routes"
```

---

## Task 3B: 后端通用卸载（用户装的应用都可卸，系统应用不可）

**Files:**
- Modify: `app-manager/app_manager.py`（`AppManager.uninstall_cmd` + `installed_apps` 的 `removable` + `/apps/uninstall` 路由 + 通用命令入队）
- Test: `app-manager/tests/test_app_manager.py`

卸载命令按 .desktop 安装特征推断（设计 2.9）；系统应用（非 home 下的 .desktop）返回 None。

- [ ] **Step 1: 写失败测试**

追加到 `tests/test_app_manager.py`：

```python
def _write_desktop(d, key, exec_line):
    os.makedirs(d, exist_ok=True)
    open(os.path.join(d, key + ".desktop"), "w").write(
        "[Desktop Entry]\nType=Application\nName=%s\nExec=%s\nIcon=x\n" % (key, exec_line))

def test_uninstall_cmd_proot(monkeypatch):
    with tempfile.TemporaryDirectory() as t:
        home = os.path.join(t, "home"); appdir = os.path.join(home, ".local/share/applications")
        monkeypatch.setenv("HOME", home)
        monkeypatch.setattr(am, "APP_DIRS", [appdir])
        _write_desktop(appdir, "wechat-pa", "proot-apps run wechat")
        assert _mgr(t).uninstall_cmd("wechat-pa") == "proot-apps remove wechat"

def test_uninstall_cmd_appimage(monkeypatch):
    with tempfile.TemporaryDirectory() as t:
        home = os.path.join(t, "home"); appdir = os.path.join(home, ".local/share/applications")
        os.makedirs(os.path.join(home, "Applications", "void"))
        monkeypatch.setenv("HOME", home)
        monkeypatch.setattr(am, "APP_DIRS", [appdir])
        _write_desktop(appdir, "chatop-void", "/home/x/Applications/void/squashfs-root/AppRun")
        assert _mgr(t).uninstall_cmd("chatop-void") == \
            "bash /usr/local/lib/chatop/gui-uninstall.sh void"

def test_uninstall_cmd_system_returns_none(monkeypatch):
    with tempfile.TemporaryDirectory() as t:
        home = os.path.join(t, "home"); sysdir = os.path.join(t, "usr/share/applications")
        monkeypatch.setenv("HOME", home)
        monkeypatch.setattr(am, "APP_DIRS", [sysdir])
        _write_desktop(sysdir, "thunar", "thunar %F")
        assert _mgr(t).uninstall_cmd("thunar") is None

def test_uninstall_cmd_unknown_returns_none(monkeypatch):
    with tempfile.TemporaryDirectory() as t:
        monkeypatch.setattr(am, "APP_DIRS", [t])
        assert _mgr(t).uninstall_cmd("nope") is None
```

- [ ] **Step 2: 跑测试确认失败**

Run: `cd app-manager && PYTHONPATH=. python -m pytest tests/test_app_manager.py -k uninstall_cmd -q`
Expected: FAIL（`AttributeError ... 'uninstall_cmd'`）

- [ ] **Step 3: 实现 uninstall_cmd + removable**

在 `AppManager` 加方法（紧邻 `desktop_exec`）：

```python
    def uninstall_cmd(self, key):
        """按 key 从 .desktop 安装特征推断卸载命令；系统应用/无法推断 → None。"""
        if not key or "/" in key or ".." in key:
            return None
        home = os.path.realpath(os.path.expanduser("~"))
        for d in APP_DIRS:
            p = os.path.join(d, key + ".desktop")
            if not os.path.isfile(p):
                continue
            if not os.path.realpath(d).startswith(home):
                return None  # 系统目录 = apt 装的系统应用，不可卸
            info = _parse_desktop(p); ex = info["exec"] if info else ""
            if "proot-apps run " in ex:
                return "proot-apps remove " + ex.split("proot-apps run ", 1)[1].split()[0]
            if key.startswith("chatop-") and os.path.isdir(
                    os.path.expanduser("~/Applications/" + key[len("chatop-"):])):
                return "bash /usr/local/lib/chatop/gui-uninstall.sh " + key[len("chatop-"):]
            c = {a["id"]: a for a in self._load()["apps"]}.get(key)
            return c["remove"] if c and c.get("remove") else None
        return None
```

在 `installed_apps()` 的 `seen[key] = {...}` 字典里，把 `"removable"` 一行改为按推断结果：

```python
                    "removable": False,  # 占位，循环后统一回填（见下）
```
并在 `return sorted(...)` **之前**加：

```python
        for v in seen.values():
            v["removable"] = bool(v["source"] == "user" and self.uninstall_cmd(v["key"]))
```

- [ ] **Step 4: 加 `/apps/uninstall` 路由 + 通用命令入队**

`AppManager` 加一个按命令直接入队的方法（与现有 worker 兼容）：

```python
    def enqueue_cmd(self, log_id, command):
        self._state[log_id] = "queued"
        self._tasks.put(("__cmd__", (log_id, command)))
        return True
```

修改 `_worker`，让它识别 `("__cmd__", (log_id, command))`：把
```python
            app_id, action = self._tasks.get()
            cmd = self.command_for(app_id, action)
```
改为
```python
            app_id, action = self._tasks.get()
            if app_id == "__cmd__":
                log_id, cmd = action
            else:
                log_id, cmd = app_id, self.command_for(app_id, action)
```
并把该函数后续所有 `self._state[app_id]`、`f"{app_id}.log"`、`task_done` 里的 `app_id` 改用 `log_id`（install 成功后的 `xfdesktop --reload` 分支用 `action != "__cmd__"` 跳过即可，或保留——重载桌面无害）。

在 `do_POST` 顶部（`/apps/groups` 保存之后）加：

```python
        if self.path.rstrip("/") == "/apps/uninstall":
            n = int(self.headers.get("Content-Length", 0))
            body = json.loads(self.rfile.read(n) or b"{}")
            key = body.get("key", "")
            cmd = MGR.uninstall_cmd(key)
            if not cmd:
                return self._json(400, {"error": "not uninstallable"})
            MGR.enqueue_cmd(key, cmd)
            return self._json(202, {"key": key, "state": "queued"})
```

- [ ] **Step 5: 跑测试 + 语法校验**

Run: `cd app-manager && PYTHONPATH=. python -m pytest tests/test_app_manager.py -q && python -m py_compile app_manager.py && echo OK`
Expected: 全部 passed + OK

- [ ] **Step 6: 提交**

```bash
git add app-manager/app_manager.py app-manager/tests/test_app_manager.py
git commit -m "feat(apps): generic uninstall for user-installed apps (/apps/uninstall)"
```

---

## Task 4: 前端 — 拉取 groups + 混排渲染（分组卡/应用卡，点击启动，按钮改「详情」）

**Files:**
- Modify: `novnc-src/app/ui.js`（`ChatopApps`）

- [ ] **Step 1: 扩展 state + refresh**

把 `const ChatopApps = {` 后那行（约 3763）改为：

```javascript
  catalog: [], status: {}, installed: [], category: '',
  groups: {items:[], pulled_out_system:[]}, openGroupId: null,
  selectMode: false, selected: new Set(), _saveTimer: null,
```

在 `refresh()` 的 `Promise.all` 里加第 4 个请求，并存入 state：

```javascript
      const [c, s, ins, grp] = await Promise.all([
        fetch('/apps/catalog').then(r=>r.json()),
        fetch('/apps/status').then(r=>r.json()),
        fetch('/apps/installed').then(r=>r.json()).catch(()=>({installed:[]})),
        fetch('/apps/groups').then(r=>r.json()).catch(()=>({items:[],pulled_out_system:[]}))
      ]);
      this.catalog = c.apps || []; this.status = s || {}; this.installed = ins.installed || [];
      this.groups = grp && grp.items ? grp : {items:[],pulled_out_system:[]};
```

- [ ] **Step 2: 加按 key 取应用、保存布局的工具方法**

在 `ChatopApps` 里（`runInstalled` 附近）加：

```javascript
  appByKey(key){ return this.installed.find(a => a.key === key); },
  saveGroups(){
    clearTimeout(this._saveTimer);
    this._saveTimer = setTimeout(() => {
      fetch('/apps/groups', {method:'POST', headers:{'Content-Type':'application/json'},
        body: JSON.stringify(this.groups)}).catch(()=>{});
    }, 400);
  },
  groupCoverHTML(group){
    const icons = group.apps.slice(0,4).map(k => {
      const a = this.appByKey(k);
      return `<img src="${a&&a.icon||''}" onerror="this.style.visibility='hidden'">`;
    }).join('');
    return `<div class="chatop_group_cover n${Math.min(group.apps.length,4)}">${icons}</div>
      <div class="chatop_app_name">${group.name}</div>
      <span class="chatop_group_count">${group.apps.length}</span>`;
  },
```

- [ ] **Step 3: 重写 renderGrid 的 `__installed__` 分支**

把 `renderGrid` 里 `if (this.category === '__installed__') { ... return; }` 整段替换为：

```javascript
    if (this.category === '__installed__') {
      // 搜索时忽略分组，跨组平铺（设计 2.7）
      if (filter) {
        const items = this.installed.filter(a => (a.name+a.key).toLowerCase().includes(filter));
        if (!items.length){ g.innerHTML='<div class="chatop_apps_empty">无匹配应用</div>'; return; }
        items.forEach(a => g.appendChild(this.appCard(a)));
        return;
      }
      g.appendChild(this.toolbarRow());
      const referenced = new Set();
      (this.groups.items||[]).forEach(it => {
        if (it.type === 'group') { it.apps.forEach(k=>referenced.add(k)); g.appendChild(this.groupCard(it)); }
        else if (it.type === 'app') { referenced.add(it.key); const a=this.appByKey(it.key); if(a) g.appendChild(this.appCard(a)); }
      });
      // 兜底：未在布局里的已安装应用（布局尚未对账时）平铺到末尾
      this.installed.forEach(a => { if(!referenced.has(a.key)) g.appendChild(this.appCard(a)); });
      g.appendChild(this.newGroupCard());
      return;
    }
```

- [ ] **Step 4: 加 appCard / groupCard / toolbarRow / newGroupCard 渲染方法**

在 `ChatopApps` 里加（拖拽/多选/浮层细节在后续 Task 接入，这里先出静态结构 + 点击启动 + 详情）：

```javascript
  toolbarRow(){
    const bar = document.createElement('div'); bar.className='chatop_apps_toolbar';
    const btn = document.createElement('button');
    btn.textContent = this.selectMode ? '完成' : '多选';
    btn.onclick = () => { this.selectMode=!this.selectMode; this.selected.clear();
      this.renderGrid(''); };
    bar.appendChild(btn);
    if (this.selectMode) {
      const mv = document.createElement('button'); mv.textContent='移入分组…';
      mv.disabled = this.selected.size===0;
      mv.onclick = () => this.batchMove();
      bar.appendChild(mv);
    }
    return bar;
  },
  appCard(a){
    const card = document.createElement('div'); card.className='chatop_app_card';
    card.draggable = !this.selectMode; card.dataset.key = a.key;
    card.innerHTML = `<img src="${a.icon||''}" loading="lazy" onerror="this.style.visibility='hidden'">
      <div class="chatop_app_name"></div><button class="chatop_app_open">详情</button>`;
    card.querySelector('.chatop_app_name').textContent = a.name;
    card.querySelector('.chatop_app_open').onclick = (e)=>{ e.stopPropagation(); this.detailInstalled(a); };
    if (this.selectMode) {
      const chk = document.createElement('span'); chk.className='chatop_app_check'+(this.selected.has(a.key)?' on':'');
      card.appendChild(chk);
      card.onclick = () => { this.selected.has(a.key)?this.selected.delete(a.key):this.selected.add(a.key);
        this.renderGrid(''); };
    } else {
      card.onclick = () => this.runInstalled(a);   // 点卡片本体=启动（设计 2.2）
    }
    return card;
  },
  groupCard(group){
    const card = document.createElement('div'); card.className='chatop_app_card chatop_group_card';
    card.draggable = !this.selectMode; card.dataset.gid = group.id;
    card.innerHTML = this.groupCoverHTML(group);
    if (!this.selectMode) card.onclick = () => this.openGroup(group.id);
    return card;
  },
  newGroupCard(){
    const card = document.createElement('div'); card.className='chatop_app_card chatop_newgroup_card';
    card.innerHTML = '<div class="chatop_newgroup_plus">＋</div><div class="chatop_app_name">新建分组</div>';
    card.onclick = () => { this.groups.items.push({type:'group', id:'g'+Date.now(), name:'新建分组', apps:[]});
      this.saveGroups(); this.renderGrid(''); };
    return card;
  },
```

- [ ] **Step 5: 语法校验 + 视觉验证**

Run: `cd novnc-src && node --check app/ui.js && echo OK`
Expected: OK

把改动拷进运行容器的 www（无需整轮重建）：
```bash
sudo docker cp novnc-src/app/ui.js chatop-ai:/usr/share/kasmvnc/www/app/ui.js
```
浏览器刷新 → 应用管理 →「本机已安装」：应看到顶部多选条、应用卡（按钮显示「详情」）、自动出现的「系统应用」分组卡（2×2 封面+角标）、末尾「＋新建分组」卡。点应用卡=启动，点「详情」=详情页。

- [ ] **Step 5b: 详情页给用户应用加「卸载」按钮**

修改 `detailInstalled(a)`：在系统应用分支（无 catalog_id）里，若 `a.removable` 则显示卸载按钮。把该分支的 `chatop_app_actions` 一行改为：

```javascript
      <div class="chatop_app_actions">
        <button id="chatop_app_open_btn" class="open">在桌面打开</button>
        ${a.removable ? '<button id="chatop_app_uninstall" class="remove">卸载</button>' : ''}
      </div>
      <pre id="chatop_app_log"></pre>`;
```
并在该函数末尾（绑定打开按钮之后）加：

```javascript
    const ub=document.getElementById('chatop_app_uninstall');
    if(ub) ub.onclick=()=>this.uninstallInstalled(a);
```

加卸载方法（poll 用 key 作 log id）：

```javascript
  async uninstallInstalled(a){
    const log=document.getElementById('chatop_app_log'); if(log) log.textContent='卸载中…';
    try{ await fetch('/apps/uninstall',{method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({key:a.key})}); }catch(e){ if(log) log.textContent='请求失败：'+e; return; }
    const poll=setInterval(async()=>{ try{
      const r=await fetch('/apps/logs?id='+encodeURIComponent(a.key)).then(r=>r.json());
      if(log) log.textContent=r.log||'';
      if(r.state==='success'||r.state==='failed'){ clearInterval(poll); await this.refresh();
        this.showList(); this.renderGrid(''); }
    }catch(e){} },1500);
  },
```
> catalog 类应用走原 `detail()` 的卸载逻辑不变；这里只补无 catalog 映射的用户应用（proot/AppImage）。

Run: `cd novnc-src && node --check app/ui.js && echo OK` → OK

- [ ] **Step 6: 提交**

```bash
git add novnc-src/app/ui.js
git commit -m "feat(apps): installed view renders mixed group/app grid + uninstall"
```

---

## Task 5: 前端 — 拖拽（排序 / 应用→组 / 叠加建组 / 拖出）

**Files:**
- Modify: `novnc-src/app/ui.js`（拖拽事件）

- [ ] **Step 1: 加拖拽状态与工具**

在 `ChatopApps` 加：

```javascript
  _drag: null,   // {kind:'app'|'group', key?, gid?}
  topIndexOfApp(key){ return this.groups.items.findIndex(i=>i.type==='app'&&i.key===key); },
  topIndexOfGroup(gid){ return this.groups.items.findIndex(i=>i.type==='group'&&i.id===gid); },
  removeAppFromAnywhere(key){
    this.groups.items = this.groups.items.filter(i=>!(i.type==='app'&&i.key===key));
    this.groups.items.forEach(i=>{ if(i.type==='group') i.apps=i.apps.filter(k=>k!==key); });
  },
```

- [ ] **Step 2: appCard / groupCard 绑定拖拽**

在 `appCard(a)` 的 `return card;` 前加：

```javascript
    card.addEventListener('dragstart', e=>{ this._drag={kind:'app',key:a.key};
      e.dataTransfer.effectAllowed='move'; card.classList.add('dragging'); });
    card.addEventListener('dragend', ()=>card.classList.remove('dragging'));
    card.addEventListener('dragover', e=>{ if(this._drag){ e.preventDefault(); card.classList.add('dragover'); }});
    card.addEventListener('dragleave', ()=>card.classList.remove('dragover'));
    card.addEventListener('drop', e=>{ e.preventDefault(); card.classList.remove('dragover');
      this.dropOnApp(a.key); });
```

在 `groupCard(group)` 的 `return card;` 前加：

```javascript
    card.addEventListener('dragstart', e=>{ this._drag={kind:'group',gid:group.id};
      e.dataTransfer.effectAllowed='move'; card.classList.add('dragging'); });
    card.addEventListener('dragend', ()=>card.classList.remove('dragging'));
    card.addEventListener('dragover', e=>{ if(this._drag){ e.preventDefault(); card.classList.add('dragover'); }});
    card.addEventListener('dragleave', ()=>card.classList.remove('dragover'));
    card.addEventListener('drop', e=>{ e.preventDefault(); card.classList.remove('dragover');
      this.dropOnGroup(group.id); });
```

- [ ] **Step 3: 实现落点逻辑**

在 `ChatopApps` 加：

```javascript
  dropOnApp(targetKey){
    const d=this._drag; this._drag=null; if(!d||d.kind!=='app'||d.key===targetKey) return;
    // 应用叠应用：若目标在顶层 → 两者建组；否则把拖动应用排到目标前
    const ti=this.topIndexOfApp(targetKey);
    if (ti>=0){
      this.removeAppFromAnywhere(d.key);
      const idx=this.topIndexOfApp(targetKey);
      this.groups.items.splice(idx,1,{type:'group',id:'g'+Date.now(),name:'新建分组',apps:[targetKey,d.key]});
    }
    this.saveGroups(); this.renderGrid('');
  },
  dropOnGroup(gid){
    const d=this._drag; this._drag=null; if(!d) return;
    if (d.kind==='app'){
      this.removeAppFromAnywhere(d.key);
      const g=this.groups.items.find(i=>i.type==='group'&&i.id===gid); if(g) g.apps.push(d.key);
    } else if (d.kind==='group' && d.gid!==gid){
      const from=this.topIndexOfGroup(d.gid), to=this.topIndexOfGroup(gid);
      if(from>=0&&to>=0){ const [m]=this.groups.items.splice(from,1); this.groups.items.splice(to,0,m); }
    }
    this.saveGroups(); this.renderGrid('');
  },
```

> 系统应用拖出：在浮层里拖出（Task 6）时调用 `removeAppFromAnywhere` 并把 key 加入 `groups.pulled_out_system`，避免下次对账又被自动归回（设计 2.6）。

- [ ] **Step 4: 语法校验 + 验证**

Run: `cd novnc-src && node --check app/ui.js && echo OK`
Expected: OK

`sudo docker cp novnc-src/app/ui.js chatop-ai:/usr/share/kasmvnc/www/app/ui.js` → 刷新：拖应用到另一应用上→建组；拖应用到分组卡→入组；拖分组卡换位→重排。刷新后保持（已落库）。

- [ ] **Step 5: 提交**

```bash
git add novnc-src/app/ui.js
git commit -m "feat(apps): drag to reorder / create group / add to group"
```

---

## Task 6: 前端 — 分组居中浮层（改名 / +添加应用 / 组内拖出 / 自动解散）

**Files:**
- Modify: `novnc-src/app/ui.js`
- Modify: `novnc-src/index.html`（加浮层容器）

- [ ] **Step 1: index.html 加浮层节点**

在 `chatop_apps_modal` 的 `</div>` 闭合**之前**（约第 650 行 `chatop_apps_detail` 同级）加：

```html
        <div id="chatop_group_overlay" class="chatop_group_overlay" style="display:none">
          <div class="chatop_group_panel">
            <div class="chatop_group_head">
              <input id="chatop_group_title" class="chatop_group_title">
              <button id="chatop_group_close" title="关闭">×</button>
            </div>
            <div id="chatop_group_grid" class="chatop_apps_grid"></div>
            <button id="chatop_group_add" class="chatop_group_add">＋ 添加应用</button>
          </div>
        </div>
```

- [ ] **Step 2: openGroup / 浮层渲染**

在 `ChatopApps` 加：

```javascript
  openGroup(gid){
    this.openGroupId=gid;
    const g=this.groups.items.find(i=>i.type==='group'&&i.id===gid); if(!g) return;
    document.getElementById('chatop_group_overlay').style.display='flex';
    const title=document.getElementById('chatop_group_title'); title.value=g.name;
    title.onchange=()=>{ g.name=title.value.trim()||'新建分组'; this.saveGroups(); this.renderGrid(''); };
    this.renderGroupGrid(g);
    document.getElementById('chatop_group_close').onclick=()=>this.closeGroup();
    document.getElementById('chatop_group_add').onclick=()=>this.addToGroupPicker(g);
  },
  closeGroup(){ document.getElementById('chatop_group_overlay').style.display='none'; this.openGroupId=null; },
  renderGroupGrid(g){
    const grid=document.getElementById('chatop_group_grid'); grid.innerHTML='';
    g.apps.forEach(k=>{ const a=this.appByKey(k); if(!a) return;
      const card=this.appCard(a);
      // 浮层内额外：拖到浮层外=移出组
      grid.appendChild(card);
    });
    // 浮层空白处接收「拖出」由 overlay 的 dragover/drop 处理（Step 3）
  },
```

- [ ] **Step 3: 浮层「拖出移除」+ 自动解散**

在 `openGroup` 末尾加（绑定 overlay 容器接收拖出）：

```javascript
    const ov=document.getElementById('chatop_group_overlay');
    ov.ondragover=e=>{ if(this._drag&&this._drag.kind==='app') e.preventDefault(); };
    ov.ondrop=e=>{ if(e.target===ov && this._drag && this._drag.kind==='app'){
      const key=this._drag.key; this._drag=null;
      const grp=this.groups.items.find(i=>i.type==='group'&&i.id===this.openGroupId);
      if(grp){ grp.apps=grp.apps.filter(k=>k!==key);
        if(grp.auto) (this.groups.pulled_out_system=this.groups.pulled_out_system||[]).push(key);
        this.groups.items.push({type:'app',key});
        this.dissolveIfEmpty(grp);
        this.saveGroups();
        if(this.groups.items.find(i=>i.type==='group'&&i.id===this.openGroupId)) this.renderGroupGrid(grp);
        else this.closeGroup();
        this.renderGrid('');
      }
    }};
```

加自动解散工具：

```javascript
  dissolveIfEmpty(grp){
    if (grp.apps.length<=1){
      const leftover=grp.apps.slice();
      this.groups.items=this.groups.items.filter(i=>i!==grp);
      leftover.forEach(k=>this.groups.items.push({type:'app',key:k}));
    }
  },
```

- [ ] **Step 4: +添加应用选择器**

```javascript
  ungroupedApps(){
    const used=new Set();
    this.groups.items.forEach(i=>{ if(i.type==='app')used.add(i.key); if(i.type==='group')i.apps.forEach(k=>used.add(k)); });
    return this.installed.filter(a=>!used.has(a.key));
  },
  addToGroupPicker(g){
    const list=this.ungroupedApps();
    if(!list.length){ UI.showStatus('没有未归组的应用',' warn'); return; }
    const grid=document.getElementById('chatop_group_grid');
    grid.innerHTML='<div class="chatop_group_pick_hint">勾选要加入的应用，再次点击关闭</div>';
    list.forEach(a=>{ const card=this.appCard(a); card.onclick=()=>{
        g.apps.push(a.key); this.removeTopApp(a.key); this.saveGroups(); this.renderGroupGrid(g); this.renderGrid(''); };
      grid.appendChild(card); });
  },
  removeTopApp(key){ this.groups.items=this.groups.items.filter(i=>!(i.type==='app'&&i.key===key)); },
```

- [ ] **Step 5: 语法校验 + 验证**

Run: `cd novnc-src && node --check app/ui.js && echo OK`
Expected: OK

拷 ui.js + index.html 进容器验证：点分组卡→居中浮层；改标题保存；浮层内拖应用到浮层空白处→移出（系统应用移出后刷新不回流）；剩 ≤1 自动解散；＋添加应用可加未归组应用。

```bash
sudo docker cp novnc-src/app/ui.js chatop-ai:/usr/share/kasmvnc/www/app/ui.js
sudo docker cp novnc-src/index.html chatop-ai:/usr/share/kasmvnc/www/index.html
```

- [ ] **Step 6: 提交**

```bash
git add novnc-src/app/ui.js novnc-src/index.html
git commit -m "feat(apps): centered group overlay with rename/add/remove/dissolve"
```

---

## Task 7: 前端 — 多选批量入组

**Files:**
- Modify: `novnc-src/app/ui.js`

- [ ] **Step 1: 实现 batchMove**

```javascript
  batchMove(){
    if(!this.selected.size) return;
    const keys=[...this.selected];
    // 简单选择：现有分组名列表 + 新建
    const names=this.groups.items.filter(i=>i.type==='group').map(g=>g.name);
    const choice=prompt('移入分组（输入已有分组名，或留空=新建分组）：\n'+names.join(' / '),'');
    if(choice===null) return;
    let g=this.groups.items.find(i=>i.type==='group'&&i.name===choice.trim());
    if(!g){ g={type:'group',id:'g'+Date.now(),name:(choice.trim()||'新建分组'),apps:[]}; this.groups.items.push(g); }
    keys.forEach(k=>{ this.removeAppFromAnywhere(k); g.apps.push(k); });
    this.selected.clear(); this.selectMode=false; this.saveGroups(); this.renderGrid('');
  },
```
> prompt 是最小可用实现（YAGNI）；如需更精致的选择弹层可后续迭代。

- [ ] **Step 2: 语法校验 + 验证**

Run: `cd novnc-src && node --check app/ui.js && echo OK`
Expected: OK

拷进容器：开「多选」→勾若干应用→「移入分组…」→输入名→批量进组。

- [ ] **Step 3: 提交**

```bash
git add novnc-src/app/ui.js
git commit -m "feat(apps): multi-select batch move into group"
```

---

## Task 8: CSS 样式 + 整轮重建联调

**Files:**
- Modify: `novnc-src/app/styles/base.css`

- [ ] **Step 1: 加样式**

在 `base.css` 末尾加（含浅色主题适配）：

```css
/* 应用分组：分组卡封面 2x2 拼贴 */
.chatop_group_card { position: relative; }
.chatop_group_cover { display:grid; gap:2px; width:48px; height:48px; margin:0 auto 6px; }
.chatop_group_cover.n1 { grid-template-columns:1fr; }
.chatop_group_cover.n2 { grid-template-columns:1fr 1fr; }
.chatop_group_cover.n3, .chatop_group_cover.n4 { grid-template-columns:1fr 1fr; grid-template-rows:1fr 1fr; }
.chatop_group_cover img { width:100%; height:100%; object-fit:contain; }
.chatop_group_count { position:absolute; top:4px; right:6px; font-size:11px;
  background:rgba(0,0,0,.55); color:#fff; border-radius:8px; padding:0 5px; }
.chatop_newgroup_card { display:flex; flex-direction:column; align-items:center; justify-content:center;
  border:1px dashed rgba(255,255,255,.3); opacity:.8; }
.chatop_newgroup_plus { font-size:28px; line-height:1; }
.chatop_apps_toolbar { grid-column:1/-1; display:flex; gap:8px; padding:0 0 6px; }
.chatop_apps_toolbar button { padding:4px 12px; border-radius:6px; cursor:pointer; }
.chatop_app_card.dragging { opacity:.45; }
.chatop_app_card.dragover { outline:2px solid #3b82f6; outline-offset:2px; }
.chatop_app_check { position:absolute; top:4px; left:6px; width:16px; height:16px;
  border:2px solid #3b82f6; border-radius:50%; }
.chatop_app_check.on { background:#3b82f6; }
/* 分组居中浮层 */
.chatop_group_overlay { position:absolute; inset:0; background:rgba(0,0,0,.5);
  display:flex; align-items:center; justify-content:center; z-index:30; }
.chatop_group_panel { width:min(560px,86%); max-height:78%; overflow:auto;
  background:#1b2230; border-radius:14px; padding:18px; box-shadow:0 20px 60px rgba(0,0,0,.5); }
.chatop_group_head { display:flex; gap:8px; align-items:center; margin-bottom:12px; }
.chatop_group_title { flex:1; font-size:16px; padding:6px 10px; border-radius:8px;
  border:1px solid rgba(255,255,255,.15); background:rgba(255,255,255,.06); color:#fff; }
.chatop_group_add { margin-top:12px; padding:8px 14px; border-radius:8px; cursor:pointer; }
.chatop_group_pick_hint { grid-column:1/-1; font-size:12px; opacity:.7; padding-bottom:6px; }
/* 浅色主题 */
body.chatop-theme-light .chatop_group_panel { background:#fff; color:#1b2230; }
body.chatop-theme-light .chatop_group_title { background:#f3f4f6; color:#111; border-color:#d1d5db; }
body.chatop-theme-light .chatop_newgroup_card { border-color:rgba(0,0,0,.25); }
```

- [ ] **Step 2: 语法/构建校验**

Run: `cd novnc-src && node --check app/ui.js && echo OK`
（CSS 无编译；确认无明显括号不配：`grep -c '{' app/styles/base.css; grep -c '}' app/styles/base.css` 两数应相等）

- [ ] **Step 3: 整轮重建 + 切换**

```bash
cd /work/chatop-ai
VERSION=$(cat VERSION) sudo -E docker compose build 2>&1 | tail -3
VERSION=$(cat VERSION) sudo -E docker compose up -d 2>&1 | tail -1
```

- [ ] **Step 4: 验收（对照设计 §6）**

逐项人工验证：拖应用叠应用建组；拖入/拖出；空组自动解散；封面 2×2 + 角标随内容变；点应用=启动、「详情」=详情页；系统应用自动归组且拖出不回流；多选批量入组；搜索跨组平铺；`docker compose restart` 后分组仍在（groups.json 在卷）。

后端回归：
```bash
cd app-manager && PYTHONPATH=. python -m pytest tests/test_app_manager.py -q
```
Expected: 全部 passed

- [ ] **Step 5: 提交**

```bash
git add novnc-src/app/styles/base.css
git commit -m "feat(apps): grouping styles + light-theme; final integration"
```

---

## Self-Review（计划自检）

- **Spec 覆盖**：分组卡混排(T4)/拖拽排序建组入组(T5)/居中浮层改名+添加+拖出+解散(T6)/多选批量(T7)/系统应用自动归组+拖出不回流(T2 reconcile + T6)/搜索跨组(T4)/持久化(T1-3)/封面拼贴+角标(T4+T8)/点击启动+详情改名(T4)/**用户应用通用卸载(T3B 后端 + T4 Step5b 前端)、系统应用不可卸** —— 全部有对应 Task。
- **占位扫描**：无 TBD/TODO；每个改码步骤都给了实际代码。
- **类型/命名一致**：`groups={items,pulled_out_system}`、`appByKey`、`saveGroups`、`removeAppFromAnywhere`、`openGroupId`、`dissolveIfEmpty` 跨 Task 命名一致；后端 `GroupStore.load/save/reconcile`、`GROUPS`、`/apps/groups` 一致。
- **已知取舍**：多选目标选择用 `prompt`（最小实现，YAGNI）；前端无单测框架，靠 `node --check` + 容器内联调（用 `docker cp` 热替换快速验证，最终 T8 整轮重建）。
