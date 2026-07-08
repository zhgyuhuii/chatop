import uvicorn

from . import config
from .api import create_app
from .events import EventHub
from .heartbeat import start_heartbeat
from .tasks.dispatcher import Dispatcher
from .tasks.store import TaskStore


def main() -> None:
    store = TaskStore(config.DB_PATH)
    hub = EventHub()
    dispatcher = Dispatcher(store, hub, nickname=config.NICKNAME)
    start_heartbeat()  # 后台静默存活心跳(失败自吞，不影响服务)
    uvicorn.run(create_app(store, hub, dispatcher), host="127.0.0.1", port=config.PORT)


if __name__ == "__main__":
    main()
