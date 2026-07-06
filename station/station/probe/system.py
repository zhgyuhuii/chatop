from __future__ import annotations

import time

import psutil

SERVICES = [("Xvnc", "Xvnc"), ("caddy", "caddy"), ("app-manager", "app_manager.py"),
            ("filebrowser", "filebrowser"), ("station", "station")]


def list_procs() -> list[dict]:
    out = []
    for p in psutil.process_iter(["pid", "name", "cmdline", "cpu_percent", "memory_info"]):
        try:
            info = p.info
            out.append({"pid": info["pid"], "name": info["name"] or "",
                        "cmdline": " ".join(info["cmdline"] or []),
                        "cpu": info["cpu_percent"] or 0.0,
                        "mem_mb": round((info["memory_info"].rss if info["memory_info"] else 0) / 1e6, 1)})
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    return out


def _live_res() -> dict:
    return {"cpu": psutil.cpu_percent(interval=None),
            "mem": psutil.virtual_memory().percent,
            "disk": psutil.disk_usage("/").percent,
            "uptime": time.time() - psutil.boot_time()}


def _live_ports_established() -> tuple[list[int], set[int]]:
    ports, est = [], set()
    try:
        for c in psutil.net_connections(kind="tcp"):
            if c.status == psutil.CONN_LISTEN and c.laddr:
                ports.append(c.laddr.port)
            elif c.status == psutil.CONN_ESTABLISHED and c.laddr:
                est.add(c.laddr.port)
    except psutil.AccessDenied:
        pass
    return sorted(set(ports)), est


def snapshot(procs: list[dict] | None = None, res: dict | None = None,
             ports: list[int] | None = None, established: set[int] | None = None) -> dict:
    procs = list_procs() if procs is None else procs
    res = _live_res() if res is None else res
    if ports is None or established is None:
        ports, established = _live_ports_established()
    services = [{"name": name, "ok": any(match in (p["name"] + " " + p["cmdline"]) for p in procs)}
                for name, match in SERVICES]
    return {**res, "services": services, "ports": ports,
            "vnc_online": bool({6901, 7443} & established), "ts": time.time()}
