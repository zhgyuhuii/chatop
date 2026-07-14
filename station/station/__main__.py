import sys

import uvicorn

from . import config
from .api import create_app
from .events import EventHub
from .heartbeat import start_heartbeat
from .tasks.dispatcher import Dispatcher
from .tasks.store import TaskStore


def _rollback_cli(service: str) -> None:
    """python -m station rollback <service>：供外层 supervisor(start-station.sh)
    在健康门不过时调用，把 current 指回上一个可用版本。"""
    import os
    from pathlib import Path
    from . import updater, services
    if not service:
        print("usage: python -m station rollback <service>")
        raise SystemExit(2)
    sd = Path(os.environ.get("CHATOP_SERVICES_DIR", str(services.SERVICES_DIR)))
    res = updater.rollback(service, services_dir=sd)
    print(f"rollback {service}: ok={res.ok} -> {res.version} ({res.detail})")
    raise SystemExit(0 if res.ok else 1)


def main() -> None:
    if len(sys.argv) >= 2 and sys.argv[1] == "rollback":
        _rollback_cli(sys.argv[2] if len(sys.argv) > 2 else "")
        return
    store = TaskStore(config.DB_PATH)
    hub = EventHub()
    dispatcher = Dispatcher(store, hub, nickname=config.NICKNAME)
    start_heartbeat()  # 后台静默存活心跳(失败自吞，不影响服务)
    uvicorn.run(create_app(store, hub, dispatcher), host="127.0.0.1", port=config.PORT)


if __name__ == "__main__":
    main()
