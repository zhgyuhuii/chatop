from __future__ import annotations

import asyncio
import json


class EventHub:
    """进程内事件扇出（ChaCMD EventStreamHub 手法：满则丢最旧，不阻塞发布方）。"""

    def __init__(self, maxsize: int = 256) -> None:
        self._subs: set[asyncio.Queue] = set()
        self._maxsize = maxsize

    def subscribe(self) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue(maxsize=self._maxsize)
        self._subs.add(q)
        return q

    def unsubscribe(self, q: asyncio.Queue) -> None:
        self._subs.discard(q)

    def publish(self, event: dict) -> None:
        for q in list(self._subs):
            if q.full():
                try:
                    q.get_nowait()
                except asyncio.QueueEmpty:
                    pass
            q.put_nowait(event)


def sse_format(event: dict) -> str:
    return f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
