from __future__ import annotations

import asyncio
import json

import websockets


class BridgeClient:
    """子容器 resident service: reverse-connect to gateway, register by nickname, heartbeat.

    The container DIALS OUT (NAT-friendly). It never advertises an IP; identity is the nickname.
    """

    def __init__(self, url: str, nickname: str, dept: str, heartbeat_s: float = 10.0) -> None:
        self._url = url.rstrip("/")
        self._nickname = nickname
        self._dept = dept
        self._heartbeat_s = heartbeat_s
        self._ws: websockets.WebSocketClientProtocol | None = None
        self._hb_task: asyncio.Task | None = None

    async def connect_and_register(self) -> None:
        self._ws = await websockets.connect(f"{self._url}/bridge")
        await self._send("register", {})

    async def start_heartbeat(self) -> None:
        async def loop():
            while self._ws is not None:
                await self._send("heartbeat", {})
                await asyncio.sleep(self._heartbeat_s)
        self._hb_task = asyncio.create_task(loop())

    async def _send(self, type_: str, data: dict) -> None:
        assert self._ws is not None
        await self._ws.send(json.dumps({"type": type_, "nickname": self._nickname, "dept": self._dept, "data": data}))

    async def close(self) -> None:
        if self._hb_task:
            self._hb_task.cancel()
        if self._ws:
            await self._ws.close()
            self._ws = None
