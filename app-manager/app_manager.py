#!/usr/bin/env python3
"""chatop-ai 应用管理器后端：catalog/status/install/remove/logs。
仅监听 127.0.0.1，命令只来自 catalog（白名单），绝不执行前端传入字符串。"""
import json, os, shutil, subprocess, threading, queue
from http.server import BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs, quote

CATALOG_PATH = os.environ.get("APPS_CATALOG", "/etc/chatop/apps-catalog.json")
LOG_DIR = "/tmp/app-mgr"; PORT = int(os.environ.get("APPS_PORT", "8686"))
PUBLIC_FIELDS = ("id","name","category","kind","icon","description","needs","homepage","notes","available")

# === 文件传输（上传到桌面 / 仅下载桌面文件）配置 ===
def _envflag(name, default="1"):
    return os.environ.get(name, default).strip().lower() not in ("0", "false", "no", "off", "")
FILES_DIR = os.path.abspath(os.path.expanduser(os.environ.get("FILES_DIR", "~/Desktop")))
FILES_UPLOAD = _envflag("FILES_UPLOAD")
FILES_DOWNLOAD = _envflag("FILES_DOWNLOAD")
MAX_UPLOAD = int(os.environ.get("FILES_MAX_UPLOAD_MB", "1024")) * 1024 * 1024  # 单文件上限，默认 1GB

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
    def do_GET(self):
        if self.path.startswith("/apps/catalog"): return self._json(200, MGR.public_catalog())
        if self.path.startswith("/apps/status"):  return self._json(200, MGR.status())
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
