#!/usr/bin/env python3
"""chatop-ai 应用管理器后端：catalog/status/install/remove/logs。
仅监听 127.0.0.1，命令只来自 catalog（白名单），绝不执行前端传入字符串。"""
import json, os, subprocess, threading, queue
from http.server import BaseHTTPRequestHandler

CATALOG_PATH = os.environ.get("APPS_CATALOG", "/etc/chatop/apps-catalog.json")
LOG_DIR = "/tmp/app-mgr"; PORT = int(os.environ.get("APPS_PORT", "8686"))
PUBLIC_FIELDS = ("id","name","category","kind","icon","description","needs","homepage","notes","available")

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
        cat["apps"] = [{k:a[k] for k in PUBLIC_FIELDS if k in a} for a in cat["apps"]]
        return cat
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
    from http.server import ThreadingHTTPServer
    ThreadingHTTPServer(("127.0.0.1", PORT), Handler).serve_forever()

if __name__ == "__main__": main()
