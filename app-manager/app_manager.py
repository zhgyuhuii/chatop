#!/usr/bin/env python3
"""chatop-ai 应用管理器后端：catalog/status/install/remove/logs。
仅监听 127.0.0.1，命令只来自 catalog（白名单），绝不执行前端传入字符串。"""
import json, os, re, glob, shutil, subprocess, threading, queue
from http.server import BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs, quote

CATALOG_PATH = os.environ.get("APPS_CATALOG", "/etc/chatop/apps-catalog.json")
LOG_DIR = "/tmp/app-mgr"; PORT = int(os.environ.get("APPS_PORT", "8686"))
GROUPS_PATH = os.environ.get(
    "APPS_GROUPS", os.path.expanduser("~/.local/share/chatop/groups.json"))
_EMPTY_LAYOUT = {"version": 1, "items": [], "pulled_out_system": []}
PUBLIC_FIELDS = ("id","name","category","kind","icon","description","needs","homepage","notes","available")

# === 文件传输（上传到桌面 / 仅下载桌面文件）配置 ===
def _envflag(name, default="1"):
    return os.environ.get(name, default).strip().lower() not in ("0", "false", "no", "off", "")
FILES_DIR = os.path.abspath(os.path.expanduser(os.environ.get("FILES_DIR", "~/Desktop")))
FILES_UPLOAD = _envflag("FILES_UPLOAD")
FILES_DOWNLOAD = _envflag("FILES_DOWNLOAD")
MAX_UPLOAD = int(os.environ.get("FILES_MAX_UPLOAD_MB", "1024")) * 1024 * 1024  # 单文件上限，默认 1GB

# === 登录鉴权：自定义品牌登录页 + 签名 Cookie，取代 KasmVNC 原生 basic-auth 浏览器弹窗 ===
# Caddy 用 forward_auth 调 /auth 把关；通过后由 Caddy 注入 Basic 头给 KasmVNC，原生弹窗永不出现。
import hmac, hashlib, base64
AUTH_USER = os.environ.get("LOGIN_USER", "admin")
AUTH_PW = os.environ.get("FILES_PW") or os.environ.get("VNC_PW") or ""
AUTH_TOKEN = hmac.new(hashlib.sha256(("chatop-auth|" + AUTH_PW).encode()).digest(),
                      b"v1", hashlib.sha256).hexdigest()
AUTH_COOKIE = "chatop_auth"

def _logo_data_uri():
    try:
        with open("/usr/share/kasmvnc/www/app-icons/chatop-logo.png", "rb") as f:
            return "data:image/png;base64," + base64.b64encode(f.read()).decode()
    except OSError:
        return ""

_LOGIN_TMPL = """<!DOCTYPE html><html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>察元AI · 登录</title><style>
*{box-sizing:border-box}html,body{height:100%;margin:0}
body{font-family:-apple-system,"Segoe UI","Microsoft YaHei",sans-serif;
 background:radial-gradient(1200px 600px at 50% -10%,#1b3a6b 0%,#0b1220 55%,#070b14 100%);
 display:flex;align-items:center;justify-content:center;color:#eaf0fa}
.card{width:360px;max-width:92vw;background:rgba(255,255,255,.04);
 border:1px solid rgba(255,255,255,.10);border-radius:16px;padding:36px 32px;
 box-shadow:0 20px 60px rgba(0,0,0,.45);backdrop-filter:blur(6px);text-align:center}
.logo{width:72px;height:72px;object-fit:contain;margin-bottom:14px}
.title{font-size:22px;font-weight:700;letter-spacing:1px}
.sub{font-size:13px;color:#8aa0c0;margin:6px 0 24px}
form{display:flex;flex-direction:column;gap:14px;text-align:left}
label{font-size:12px;color:#9fb3d1;margin-bottom:-6px}
input{width:100%;padding:11px 13px;border-radius:9px;border:1px solid rgba(255,255,255,.14);
 background:rgba(255,255,255,.06);color:#fff;font-size:14px;outline:none}
input:focus{border-color:#3b82f6;background:rgba(59,130,246,.10)}
button{margin-top:8px;padding:12px;border:0;border-radius:9px;cursor:pointer;
 background:linear-gradient(135deg,#3b82f6,#2563eb);color:#fff;font-size:15px;font-weight:600}
button:hover{filter:brightness(1.08)}
.err{background:rgba(220,38,38,.15);border:1px solid rgba(220,38,38,.4);color:#fca5a5;
 font-size:13px;padding:8px 10px;border-radius:8px;margin-bottom:6px}
.foot{margin-top:20px;font-size:11px;color:#5f7399}
</style></head><body><div class="card">
__LOGOIMG__
<div class="title">察元AI</div><div class="sub">AI 云桌面 · 安全登录</div>
__ERR__
<form method="POST" action="/login" autocomplete="off">
<label>用户名</label><input name="username" value="__USER__" autofocus autocomplete="username">
<label>密码</label><input name="password" type="password" autocomplete="current-password">
<button type="submit">登 录</button></form>
<div class="foot">Powered by 察元AI</div>
</div></body></html>"""

def _login_html(error=False):
    logo = _logo_data_uri()
    img = ('<img class="logo" src="%s" alt="察元AI">' % logo) if logo else ''
    return (_LOGIN_TMPL
            .replace("__LOGOIMG__", img)
            .replace("__ERR__", '<div class="err">用户名或密码错误</div>' if error else '')
            .replace("__USER__", AUTH_USER))

def _cookie_ok(cookie_header):
    for part in (cookie_header or "").split(";"):
        k, _, v = part.strip().partition("=")
        if k == AUTH_COOKIE and v and hmac.compare_digest(v, AUTH_TOKEN):
            return True
    return False

def _safe_path(name):
    """把前端传来的文件名收敛到 FILES_DIR 内的单个文件，杜绝 ../ 越权。"""
    name = os.path.basename((name or "").strip())
    if not name or name in (".", ".."):
        return None
    p = os.path.abspath(os.path.join(FILES_DIR, name))
    if os.path.dirname(p) != FILES_DIR:
        return None
    return p

def files_list():
    if not os.path.isdir(FILES_DIR):
        return []
    out = []
    for n in sorted(os.listdir(FILES_DIR)):
        p = os.path.join(FILES_DIR, n)
        if os.path.isfile(p):
            st = os.stat(p)
            out.append({"name": n, "size": st.st_size, "mtime": int(st.st_mtime)})
    return out

# === 遍历容器内真实已安装应用（.desktop）+ 图标解析 ===
# 不再只看 catalog detect：扫描标准 freedesktop 应用入口，proot-apps/AppImage 安装时都会在
# 这些目录生成 .desktop，于是“本机已安装”能列出容器里所有 GUI 应用（带各自真实图标）。
APP_DIRS = [
    os.path.expanduser("~/.local/share/applications"),  # 用户级（proot-apps/AppImage）优先
    "/usr/share/applications",                            # 系统级（XFCE 等）
]
_ICON_PIXMAP_DIRS = ["/usr/share/pixmaps", os.path.expanduser("~/.local/share/icons")]
_ICON_EXTS = (".png", ".svg", ".xpm")
# /apps/icon 只允许喂这些根下的文件，杜绝任意路径读取
ICON_ROOTS = tuple(os.path.realpath(d) for d in (
    ["/usr/share/icons", "/usr/share/pixmaps"] + APP_DIRS +
    [os.path.expanduser("~/.local/share/icons"), os.path.expanduser("~/proot-apps"), "/opt"]
))
_ICON_MIME = {".png": "image/png", ".svg": "image/svg+xml", ".xpm": "image/x-xpixmap",
              ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".ico": "image/x-icon"}

def _parse_desktop(path):
    """读 .desktop 的 [Desktop Entry]；跳过 NoDisplay/Hidden/非 Application/无 Exec。"""
    data = {}
    try:
        with open(path, encoding="utf-8", errors="ignore") as f:
            in_entry = False
            for line in f:
                line = line.rstrip("\n")
                s = line.strip()
                if s.startswith("[") and s.endswith("]"):
                    in_entry = (s == "[Desktop Entry]"); continue
                if not in_entry or "=" not in s or s.startswith("#"): continue
                k, v = s.split("=", 1); data[k] = v
    except OSError:
        return None
    if data.get("Type", "Application") != "Application": return None
    if data.get("NoDisplay", "").lower() == "true": return None
    if data.get("Hidden", "").lower() == "true": return None
    if not data.get("Exec"): return None
    name = (data.get("Name[zh_CN]") or data.get("Name[zh]") or data.get("Name")
            or os.path.splitext(os.path.basename(path))[0])
    return {"name": name, "icon": data.get("Icon", ""), "exec": data.get("Exec", ""),
            "categories": data.get("Categories", "")}

def _resolve_icon(icon):
    """Icon 字段（名字或绝对路径）→ 真实图标文件路径；找不到返回 None。"""
    if not icon: return None
    if icon.startswith("/"):
        return icon if os.path.isfile(icon) else None
    for d in _ICON_PIXMAP_DIRS:
        for e in _ICON_EXTS:
            p = os.path.join(d, icon + e)
            if os.path.isfile(p): return p
    # 图标主题，挑大尺寸 / 矢量
    for theme in ("hicolor", "Adwaita", "elementary-xfce", "elementary-xfce-dark"):
        base = "/usr/share/icons/" + theme
        for size in ("scalable", "256x256", "128x128", "96x96", "64x64", "48x48", "32x32"):
            for e in _ICON_EXTS:
                p = os.path.join(base, size, "apps", icon + e)
                if os.path.isfile(p): return p
    hits = glob.glob("/usr/share/icons/hicolor/*/apps/" + glob.escape(icon) + ".*")
    return sorted(hits)[-1] if hits else None

def _exec_clean(ex):
    """去掉 .desktop Exec 里的字段码（%u %f 等），用于启动。"""
    return re.sub(r"%[a-zA-Z]", "", ex).strip()

class GroupStore:
    """读写 groups.json：原子保存 + 容错读取。布局校验/对账在 reconcile。"""
    def __init__(self, path=GROUPS_PATH):
        self.path = path

    def load(self):
        try:
            with open(self.path, encoding="utf-8") as f:
                d = json.load(f)
            if not isinstance(d, dict) or "items" not in d:
                return {"version": 1, "items": [], "pulled_out_system": []}
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

class AppManager:
    def __init__(self, catalog_path=CATALOG_PATH):
        self.catalog_path = catalog_path
        self._tasks = queue.Queue(); self._state = {}
        os.makedirs(LOG_DIR, exist_ok=True)
        threading.Thread(target=self._worker, daemon=True).start()
    def _load(self):
        with open(self.catalog_path) as f: return json.load(f)
    def public_catalog(self):
        cat = self._load()
        out = []
        for a in cat["apps"]:
            d = {k: a[k] for k in PUBLIC_FIELDS if k in a}
            d["launchable"] = bool(a.get("launch"))  # 有 launch 命令 = 可在桌面打开
            out.append(d)
        cat["apps"] = out
        return cat
    def launch_cmd(self, app_id):
        return self._app(app_id).get("launch")
    def installed_apps(self):
        """遍历容器内所有已安装 GUI 应用（.desktop），带真实图标，匹配 catalog 富化。"""
        cat = self._load()["apps"]; by_id = {a["id"]: a for a in cat}
        seen = {}
        for d in APP_DIRS:
            for path in sorted(glob.glob(os.path.join(d, "*.desktop"))):
                info = _parse_desktop(path)
                if not info: continue
                key = os.path.splitext(os.path.basename(path))[0]
                if key in seen: continue  # APP_DIRS 顺序：用户级覆盖系统级同名
                ex = info["exec"]; c = None
                if "proot-apps run " in ex:  # proot-apps 装的 → 取 id 匹配 catalog
                    pid = ex.split("proot-apps run ", 1)[1].split()[0]; c = by_id.get(pid)
                c = c or by_id.get(key)
                ic = _resolve_icon(info["icon"])
                seen[key] = {
                    "key": key, "name": info["name"],
                    "icon": ("/apps/icon?p=" + quote(os.path.realpath(ic))) if ic else "",
                    "catalog_id": c["id"] if c else None,
                    "removable": bool(c and c.get("remove")),
                    "source": "user" if os.path.realpath(d).startswith(
                        os.path.realpath(os.path.expanduser("~"))) else "system",
                }
        return sorted(seen.values(), key=lambda x: (x["source"] != "user", x["name"].lower()))
    def desktop_exec(self, key):
        """按 key 取已扫描 .desktop 的清理后 Exec（受信任的系统文件，非前端字符串）。"""
        if not key or "/" in key or ".." in key: return None
        for d in APP_DIRS:
            p = os.path.join(d, key + ".desktop")
            if os.path.isfile(p):
                info = _parse_desktop(p)
                if info: return _exec_clean(info["exec"])
        return None
    def _app(self, app_id):
        for a in self._load()["apps"]:
            if a["id"] == app_id: return a
        raise KeyError(app_id)
    def command_for(self, app_id, action):
        return self._app(app_id)[action]
    def _run_detect(self, cmd):
        return subprocess.run(["bash","-lc",cmd], stdout=subprocess.DEVNULL,
                              stderr=subprocess.DEVNULL).returncode == 0
    def status(self):
        return {a["id"]: self._run_detect(a["detect"]) for a in self._load()["apps"]}
    def enqueue(self, app_id, action):
        self._app(app_id)
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
            if rc == 0 and action == "install":
                # 安装成功后刷新 XFCE 桌面，让新生成的桌面快捷方式立即出现
                subprocess.run(["bash","-lc","DISPLAY=:1 xfdesktop --reload"],
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            self._tasks.task_done()

MGR = None
class Handler(BaseHTTPRequestHandler):
    def _json(self, code, obj):
        b=json.dumps(obj).encode(); self.send_response(code)
        self.send_header("Content-Type","application/json"); self.send_header("Content-Length",str(len(b)))
        self.end_headers(); self.wfile.write(b)
    def _send_html(self, code, html_text):
        b = html_text.encode("utf-8"); self.send_response(code)
        self.send_header("Content-Type","text/html; charset=utf-8")
        self.send_header("Content-Length",str(len(b)))
        self.end_headers(); self.wfile.write(b)
    def do_GET(self):
        # 登录页（品牌化，取代 KasmVNC 原生 basic-auth 弹窗）
        if self.path.split("?",1)[0].rstrip("/") == "/login":
            err = "e=1" in (urlparse(self.path).query or "")
            return self._send_html(200, _login_html(err))
        # Caddy forward_auth 校验端点：cookie 有效 → 200；否则 302 回登录页
        if self.path.split("?",1)[0].rstrip("/") == "/auth":
            if _cookie_ok(self.headers.get("Cookie","")):
                return self._json(200, {"ok":True})
            self.send_response(302); self.send_header("Location","/login"); self.end_headers(); return
        if self.path.startswith("/apps/catalog"): return self._json(200, MGR.public_catalog())
        if self.path.startswith("/apps/status"):  return self._json(200, MGR.status())
        if self.path.startswith("/apps/installed"): return self._json(200, {"installed": MGR.installed_apps()})
        if self.path.startswith("/apps/icon"):
            p = parse_qs(urlparse(self.path).query).get("p", [""])[0]
            return self._send_icon(p)
        if self.path.startswith("/apps/logs"):
            qid = parse_qs(urlparse(self.path).query).get("id",[""])[0]
            p=os.path.join(LOG_DIR,f"{qid}.log"); txt=open(p).read() if os.path.exists(p) else ""
            return self._json(200, {"id":qid,"state":MGR.task_state(qid),"log":txt})
        if self.path.startswith("/apps/files/config"):
            return self._json(200, {"upload":FILES_UPLOAD, "download":FILES_DOWNLOAD, "dir":FILES_DIR})
        if self.path.startswith("/apps/files/list"):
            if not FILES_DOWNLOAD: return self._json(403, {"error":"download disabled"})
            return self._json(200, {"dir":FILES_DIR, "files":files_list()})
        if self.path.startswith("/apps/files/download"):
            if not FILES_DOWNLOAD: return self._json(403, {"error":"download disabled"})
            name = parse_qs(urlparse(self.path).query).get("name",[""])[0]
            p = _safe_path(name)
            if not p or not os.path.isfile(p): return self._json(404, {"error":"not found"})
            return self._send_file(p, os.path.basename(p))
        return self._json(404, {"error":"not found"})

    def _send_icon(self, path):
        rp = os.path.realpath(path or "")
        if not any(rp == r or rp.startswith(r + os.sep) for r in ICON_ROOTS) or not os.path.isfile(rp):
            return self._json(404, {"error": "not found"})
        ext = os.path.splitext(rp)[1].lower()
        if ext not in _ICON_MIME: return self._json(404, {"error": "not an icon"})
        try:
            with open(rp, "rb") as f: data = f.read()
        except OSError:
            return self._json(404, {"error": "not found"})
        self.send_response(200); self.send_header("Content-Type", _ICON_MIME[ext])
        self.send_header("Content-Length", str(len(data))); self.send_header("Cache-Control", "max-age=86400")
        self.end_headers(); self.wfile.write(data)
    def _send_file(self, path, filename):
        size = os.path.getsize(path)
        self.send_response(200)
        self.send_header("Content-Type", "application/octet-stream")
        self.send_header("Content-Length", str(size))
        # filename* 用 UTF-8 编码，支持中文文件名
        self.send_header("Content-Disposition",
                         "attachment; filename*=UTF-8''%s" % quote(filename))
        self.end_headers()
        with open(path, "rb") as f:
            shutil.copyfileobj(f, self.wfile)
    def do_POST(self):
        # 登录提交：校验用户名/密码 → 下发签名 cookie；失败回登录页带错误
        if self.path.split("?",1)[0].rstrip("/") == "/login":
            n=int(self.headers.get("Content-Length",0))
            form=parse_qs(self.rfile.read(n).decode("utf-8","ignore"))
            u=form.get("username",[""])[0]; p=form.get("password",[""])[0]
            if u==AUTH_USER and AUTH_PW and hmac.compare_digest(p, AUTH_PW):
                self.send_response(302); self.send_header("Location","/")
                self.send_header("Set-Cookie",
                    "%s=%s; Path=/; HttpOnly; SameSite=Lax; Secure; Max-Age=86400" % (AUTH_COOKIE, AUTH_TOKEN))
                self.end_headers(); return
            self.send_response(302); self.send_header("Location","/login?e=1"); self.end_headers(); return
        if self.path.rstrip("/") in ("/apps/install","/apps/remove"):
            n=int(self.headers.get("Content-Length",0)); body=json.loads(self.rfile.read(n) or b"{}")
            action="install" if self.path.rstrip("/").endswith("install") else "remove"
            try:
                MGR.enqueue(body["id"], action); return self._json(202, {"id":body["id"],"state":"queued"})
            except KeyError: return self._json(400, {"error":"unknown app id"})
            except (ValueError,TypeError): return self._json(400, {"error":"bad request"})
        if self.path.rstrip("/") == "/apps/launch":
            n=int(self.headers.get("Content-Length",0)); body=json.loads(self.rfile.read(n) or b"{}")
            try:
                cmd = MGR.launch_cmd(body["id"])
            except (KeyError, TypeError):
                return self._json(400, {"error":"unknown app id"})
            if not cmd:
                return self._json(400, {"error":"not launchable"})
            env = dict(os.environ); env["DISPLAY"] = env.get("DISPLAY", ":1") or ":1"
            subprocess.Popen(["bash","-lc",cmd], env=env, stdout=subprocess.DEVNULL,
                             stderr=subprocess.DEVNULL, start_new_session=True)
            return self._json(202, {"id":body["id"],"state":"launched"})
        if self.path.rstrip("/") == "/apps/run":
            n=int(self.headers.get("Content-Length",0)); body=json.loads(self.rfile.read(n) or b"{}")
            ex = MGR.desktop_exec(body.get("key",""))
            if not ex: return self._json(400, {"error":"unknown app"})
            env = dict(os.environ); env["DISPLAY"] = env.get("DISPLAY", ":1") or ":1"
            subprocess.Popen(["bash","-lc",ex], env=env, stdout=subprocess.DEVNULL,
                             stderr=subprocess.DEVNULL, start_new_session=True)
            return self._json(202, {"key":body.get("key"),"state":"launched"})
        if self.path.startswith("/apps/files/upload"):
            if not FILES_UPLOAD: return self._json(403, {"error":"upload disabled"})
            name = parse_qs(urlparse(self.path).query).get("name",[""])[0]
            p = _safe_path(name)
            if not p: return self._json(400, {"error":"bad filename"})
            n = int(self.headers.get("Content-Length", 0))
            if n <= 0: return self._json(400, {"error":"empty body"})
            if n > MAX_UPLOAD: return self._json(413, {"error":"file too large"})
            os.makedirs(FILES_DIR, exist_ok=True)
            remaining = n
            try:
                with open(p, "wb") as f:
                    while remaining > 0:
                        chunk = self.rfile.read(min(65536, remaining))
                        if not chunk: break
                        f.write(chunk); remaining -= len(chunk)
            except OSError as e:
                return self._json(500, {"error":str(e)})
            return self._json(201, {"name":os.path.basename(p), "size":n - remaining})
        return self._json(404, {"error":"not found"})
    def log_message(self,*a): pass

def main():
    global MGR; MGR = AppManager()
    from http.server import ThreadingHTTPServer
    ThreadingHTTPServer(("127.0.0.1", PORT), Handler).serve_forever()

if __name__ == "__main__": main()
