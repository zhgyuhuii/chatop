from station.probe.system import SERVICES, list_procs, snapshot


def test_snapshot_service_health_from_procs():
    procs = [{"pid": 1, "name": "Xvnc", "cmdline": "/usr/bin/Xvnc :1"},
             {"pid": 2, "name": "caddy", "cmdline": "caddy run"},
             {"pid": 3, "name": "python3", "cmdline": "python3 /usr/local/lib/chatop/app_manager.py"}]
    snap = snapshot(procs=procs, res={"cpu": 10.0, "mem": 40.0, "disk": 50.0, "uptime": 99.0},
                    ports=[7443, 8686], established=set())
    svc = {s["name"]: s["ok"] for s in snap["services"]}
    assert svc["Xvnc"] and svc["caddy"] and svc["app-manager"]
    assert not svc["filebrowser"] and not svc["station"]
    assert snap["cpu"] == 10.0 and 7443 in snap["ports"]


def test_vnc_online_from_established():
    snap = snapshot(procs=[], res={"cpu": 0, "mem": 0, "disk": 0, "uptime": 0},
                    ports=[], established={6901})
    assert snap["vnc_online"] is True


def test_list_procs_returns_dicts():
    procs = list_procs()
    assert isinstance(procs, list)
    assert all("pid" in p and "cmdline" in p for p in procs[:3])
