import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import asyncio
import json
import pytest
import websockets
from agent_bridge.main import BridgeClient


@pytest.mark.asyncio
async def test_bridge_client_registers_on_connect():
    received = []

    async def handler(ws):
        async for raw in ws:
            received.append(json.loads(raw))
            if len(received) >= 1:
                return

    server = await websockets.serve(handler, "127.0.0.1", 8788)
    try:
        client = BridgeClient(url="ws://127.0.0.1:8788", nickname="dev", dept="d1")
        await client.connect_and_register()
        for _ in range(50):                 # wait for server to process (avoid race)
            if received:
                break
            await asyncio.sleep(0.02)
        await client.close()
        assert received and received[0]["type"] == "register"
        assert received[0]["nickname"] == "dev"
        assert "ip" not in received[0]  # bridge dials out; no IP is ever sent
    finally:
        server.close()
        await server.wait_closed()
