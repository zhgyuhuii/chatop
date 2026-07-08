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
FILES_DIR = os.path.abspath(os.path.expanduser(os.environ.get("FILES_DIR") or "~/Desktop"))
FILES_UPLOAD = _envflag("FILES_UPLOAD")
FILES_DOWNLOAD = _envflag("FILES_DOWNLOAD")
MAX_UPLOAD = int(os.environ.get("FILES_MAX_UPLOAD_MB", "1024")) * 1024 * 1024  # 单文件上限，默认 1GB

# === 登录鉴权：自定义品牌登录页 + 签名 Cookie，取代 KasmVNC 原生 basic-auth 浏览器弹窗 ===
# Caddy 用 forward_auth 调 /auth 把关；通过后由 Caddy 注入 Basic 头给 KasmVNC，原生弹窗永不出现。
import hmac, hashlib, base64, time, secrets, random
AUTH_USER = os.environ.get("LOGIN_USER", "admin")
AUTH_PW = os.environ.get("FILES_PW") or os.environ.get("VNC_PW") or ""
AUTH_TOKEN = hmac.new(hashlib.sha256(("chatop-auth|" + AUTH_PW).encode()).digest(),
                      b"v1", hashlib.sha256).hexdigest()
AUTH_COOKIE = "chatop_auth"

# === 登录图形验证码：纯 SVG + 无状态签名 cookie（复用 AUTH_TOKEN 做 HMAC，无需 PIL） ===
CAPTCHA_CHARS = "23456789ABCDEFGHJKMNPQRSTUVWXYZ"  # 去掉易混的 0/O/1/I/L
CAPTCHA_TTL = 120
CAPTCHA_COOKIE = "chatop_cap"

def _captcha_new(n=4):
    """生成 (答案, 签名cookie值)。答案小写入签名，校验时大小写不敏感。"""
    ans = "".join(secrets.choice(CAPTCHA_CHARS) for _ in range(n))
    payload = "%s|%d" % (ans.lower(), int(time.time()) + CAPTCHA_TTL)
    sig = hmac.new(AUTH_TOKEN.encode(), payload.encode(), hashlib.sha256).hexdigest()
    cookie = base64.urlsafe_b64encode(payload.encode()).decode() + "." + sig
    return ans, cookie

def _captcha_check(cookie_value, user_input):
    """验签 + 未过期 + 大小写不敏感比对。任一不过返回 False。"""
    if not cookie_value or "." not in cookie_value:
        return False
    b64, _, sig = cookie_value.partition(".")
    try:
        payload = base64.urlsafe_b64decode(b64.encode()).decode()
    except Exception:
        return False
    expect = hmac.new(AUTH_TOKEN.encode(), payload.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(sig, expect):
        return False
    ans, _, exp = payload.partition("|")
    try:
        if int(exp) < int(time.time()):
            return False
    except ValueError:
        return False
    return hmac.compare_digest(ans, (user_input or "").strip().lower())

def _captcha_svg(text):
    """把验证码渲染成扭曲 SVG 字符串（干扰线 + 每字随机旋转/位移/颜色）。"""
    W, H = 130, 44
    colors = ["#2563eb", "#7c3aed", "#0891b2", "#be123c", "#15803d"]
    out = ['<svg xmlns="http://www.w3.org/2000/svg" width="%d" height="%d" viewBox="0 0 %d %d">' % (W, H, W, H),
           '<rect width="100%%" height="100%%" fill="#0b1220"/>']
    for _ in range(2):
        out.append('<line x1="%d" y1="%d" x2="%d" y2="%d" stroke="%s" stroke-width="1" opacity="0.5"/>' % (
            random.randint(0, W), random.randint(0, H), random.randint(0, W), random.randint(0, H), random.choice(colors)))
    step = W // (len(text) + 1)
    for i, ch in enumerate(text):
        x = step * (i + 1); y = 30 + random.randint(-4, 4); rot = random.randint(-28, 28)
        out.append('<text x="%d" y="%d" fill="%s" font-size="26" font-family="monospace" font-weight="bold" transform="rotate(%d %d %d)">%s</text>' % (
            x, y, random.choice(colors), rot, x, y, ch))
    out.append('</svg>')
    return "".join(out)

def _logo_data_uri():
    try:
        with open("/usr/share/kasmvnc/www/app-icons/chatop-logo.png", "rb") as f:
            return "data:image/png;base64," + base64.b64encode(f.read()).decode()
    except OSError:
        return ""

_LOGIN_TMPL = """<!DOCTYPE html><html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>察元AI工舱 · 登录</title><style>
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
<div class="title">察元AI工舱</div><div class="sub">AI 云桌面 · 安全登录</div>
__ERR__
<form method="POST" action="/login" autocomplete="off">
<label>用户名</label><input name="username" value="" autofocus autocomplete="username">
<label>密码</label><input name="password" type="password" autocomplete="current-password">
<button type="submit">登 录</button></form>
<div class="foot">Powered by 察元AI工舱</div>
</div></body></html>"""

def _login_html(error=False):
    logo = _logo_data_uri()
    img = ('<img class="logo" src="%s" alt="察元AI工舱">' % logo) if logo else ''
    return (_LOGIN_TMPL
            .replace("__LOGOIMG__", img)
            .replace("__ERR__", '<div class="err">用户名或密码错误</div>' if error else ''))

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

LAYOUT_VERSION = 2
# freedesktop Categories → 功能桶（按优先级；先命中先归）。设置类放最前，
# 把一堆 XFCE 设置面板单独收纳，不与终端/文件管理器混在系统工具里。
_CAT_BUCKETS = (
    ("__cat_settings__", "系统设置",
     ("Settings", "X-XFCE-SettingsDialog", "DesktopSettings", "X-XFCE-PersonalSettings",
      "X-XFCE-HardwareSettings", "X-XFCE-SystemSettings", "X-GNOME-Settings-Panel")),
    ("__cat_net__", "网络",
     ("WebBrowser", "Network", "Email", "InstantMessaging", "Chat", "P2P", "Feed")),
    ("__cat_office__", "办公", ("Office", "WordProcessor", "Spreadsheet", "Presentation")),
    ("__cat_dev__", "开发", ("Development", "IDE", "Building", "Debugger")),
    ("__cat_graphics__", "图形", ("Graphics", "Photography", "Viewer", "Scanning")),
    ("__cat_av__", "影音", ("AudioVideo", "Audio", "Video", "Player", "Music", "Recorder")),
    ("__cat_game__", "游戏", ("Game",)),
    ("__cat_system__", "系统工具",
     ("TerminalEmulator", "FileManager", "Filesystem", "System", "Monitor", "Security")),
)
_CAT_MISC = ("__cat_misc__", "附件")

def _bucket_for(categories):
    cats = {c.strip() for c in (categories or "").split(";") if c.strip()}
    for gid, name, keys in _CAT_BUCKETS:
        if cats & set(keys):
            return gid, name
    return _CAT_MISC

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

    def reconcile(self, layout, installed):
        """对账布局：保留用户已排布的项；新增应用按 freedesktop 功能分类自动归桶。
        老布局(version<2，旧版"系统应用"单桶)整体丢弃、按分类重新播种一次。"""
        by_key = {a["key"]: a for a in installed}
        valid = set(by_key)
        if layout.get("version") != LAYOUT_VERSION:
            layout = {"version": LAYOUT_VERSION, "items": [], "pulled_out_system": []}
        pulled = [k for k in layout.get("pulled_out_system", []) if k in valid]
        pulled_set = set(pulled)
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
                # 手动空组保留（用户刚建、待加应用）；自动空组丢弃
                if apps or not it.get("auto"):
                    g = {"type": "group", "id": it.get("id") or ("g" + str(len(items))),
                         "name": it.get("name") or "新建分组", "apps": apps}
                    if it.get("auto"): g["auto"] = True
                    items.append(g)
        # 新增应用：未归组的逐个按分类落桶（已被拖出的进 pulled，留在顶层）
        auto_index = {g["id"]: g for g in items
                      if g.get("type") == "group" and g.get("auto")}
        for a in installed:
            k = a["key"]
            if k in referenced:
                continue
            if k in pulled_set:
                items.append({"type": "app", "key": k}); continue
            gid, gname = _bucket_for(a.get("categories", ""))
            grp = auto_index.get(gid)
            if grp is None:
                grp = {"type": "group", "id": gid, "name": gname, "apps": [], "auto": True}
                auto_index[gid] = grp; items.append(grp)
            grp["apps"].append(k)
        return {"version": LAYOUT_VERSION, "items": items, "pulled_out_system": pulled}

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
            # 有 launch（GUI）或属 CLI 且能定位命令 = 可在桌面打开
            d["launchable"] = bool(a.get("launch")) or bool(self._is_cli(a) and self._cli_run(a))
            out.append(d)
        cat["apps"] = out
        return cat
    @staticmethod
    def _is_cli(app):
        return (app.get("category") in ("ai-cli", "ai-runtime")
                or str(app.get("kind", "")).startswith("cli"))
    @staticmethod
    def _cli_run(app):
        """CLI 工具在终端里要跑的命令：优先 catalog 的 run 字段，否则取 detect 的 `command -v X`。"""
        if app.get("run"):
            return app["run"]
        m = re.search(r"command -v\s+([^\s;|&]+)", app.get("detect", ""))
        return m.group(1) if m else None
    def launch_cmd(self, app_id):
        a = self._app(app_id)
        if a.get("launch"):
            return a["launch"]          # GUI 应用：直接启动
        if self._is_cli(a):             # CLI 工具：在桌面终端里运行，结束后保留交互 shell
            run = self._cli_run(a)
            if run:
                title = re.sub(r"[^\w一-鿿 .-]", "", a.get("name", "CLI")) or "CLI"
                return "CHATOP_CLI_TITLE='%s' chatop-run-cli %s" % (title, run)
        return None
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
                    "removable": False,  # 循环后统一回填
                    "categories": info.get("categories", ""),
                    "source": "user" if os.path.realpath(d).startswith(
                        os.path.realpath(os.path.expanduser("~"))) else "system",
                }
        for v in seen.values():
            v["removable"] = bool(v["source"] == "user" and self.uninstall_cmd(v["key"]))
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
    def enqueue_cmd(self, log_id, command):
        self._state[log_id] = "queued"
        self._tasks.put(("__cmd__", (log_id, command)))
        return True
    def task_state(self, app_id): return self._state.get(app_id, "unknown")
    def _worker(self):
        while True:
            app_id, action = self._tasks.get()
            if app_id == "__cmd__":
                log_id, cmd = action
            else:
                log_id, cmd = app_id, self.command_for(app_id, action)
            self._state[log_id] = "running"
            logf = os.path.join(LOG_DIR, f"{log_id}.log")
            with open(logf,"w") as lf:
                lf.write(f"$ {cmd}\n"); lf.flush()
                rc = subprocess.run(["bash","-lc",cmd], stdout=lf, stderr=subprocess.STDOUT).returncode
            self._state[log_id] = "success" if rc==0 else "failed"
            if rc == 0:
                # 安装/卸载成功后刷新 XFCE 桌面，让快捷方式增删立即生效
                subprocess.run(["bash","-lc","DISPLAY=:1 xfdesktop --reload"],
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            self._tasks.task_done()

MGR = None
GROUPS = GroupStore()
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
        if self.path.startswith("/apps/groups"):
            layout = GROUPS.reconcile(GROUPS.load(), MGR.installed_apps())
            GROUPS.save(layout)
            return self._json(200, layout)
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
        if self.path.rstrip("/") == "/apps/uninstall":
            n = int(self.headers.get("Content-Length", 0))
            body = json.loads(self.rfile.read(n) or b"{}")
            key = body.get("key", "")
            cmd = MGR.uninstall_cmd(key)
            if not cmd:
                return self._json(400, {"error": "not uninstallable"})
            MGR.enqueue_cmd(key, cmd)
            return self._json(202, {"key": key, "state": "queued"})
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
        # 返回桌面：显示桌面（最小化所有窗口）。wmctrl -k on 置 _NET_SHOWING_DESKTOP，幂等。
        if self.path.rstrip("/") == "/apps/show-desktop":
            env = dict(os.environ); env["DISPLAY"] = env.get("DISPLAY", ":1") or ":1"
            subprocess.Popen(["bash","-lc","wmctrl -k on"], env=env, stdout=subprocess.DEVNULL,
                             stderr=subprocess.DEVNULL, start_new_session=True)
            return self._json(202, {"state":"show-desktop"})
        # 退出登录：清除签名 cookie（与登录同属性 + Max-Age=0），前端随后跳 /login
        if self.path.rstrip("/") == "/apps/logout":
            body = b'{"ok":true}'
            self.send_response(200)
            self.send_header("Content-Type","application/json")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Set-Cookie",
                "%s=; Path=/; HttpOnly; SameSite=Lax; Secure; Max-Age=0" % AUTH_COOKIE)
            self.end_headers(); self.wfile.write(body); return
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
