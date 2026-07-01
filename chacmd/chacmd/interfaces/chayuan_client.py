from __future__ import annotations

from typing import Any, Protocol

import httpx


class ChayuanClient(Protocol):
    """I1 — ALL 察元 dependencies via HTTP. Default Http (localhost=形态B / remote=形态C).

    Because it is HTTP, ChaCMD never needs 察元 in-process; enables 轻量挂载 (§3.9).
    """

    async def chat_completions(self, model: str, messages: list[dict], **kw: Any) -> dict: ...
    async def kb_query(self, ku_ids: list[str], query: str, **kw: Any) -> dict: ...
    async def authorize(self, subject: str, resource: str, action: str) -> bool: ...
    async def whoami(self, token: str) -> dict: ...
    def web_url(self) -> str: ...


class HttpChayuanClient:
    """Default: talk to a deployed 察元 over HTTP (localhost or remote)."""

    def __init__(self, base_url: str, web_url: str, *, timeout: float = 30.0) -> None:
        self._base = base_url.rstrip("/")
        self._web = web_url.rstrip("/")
        self._client = httpx.AsyncClient(base_url=self._base, timeout=timeout)

    async def chat_completions(self, model: str, messages: list[dict], **kw: Any) -> dict:
        resp = await self._client.post("/v1/chat/completions", json={"model": model, "messages": messages, **kw})
        resp.raise_for_status()
        return resp.json()

    async def kb_query(self, ku_ids: list[str], query: str, **kw: Any) -> dict:
        resp = await self._client.post("/api/v1/kb-query/search", json={"ku_ids": ku_ids, "query": query, **kw})
        resp.raise_for_status()
        return resp.json()

    async def authorize(self, subject: str, resource: str, action: str) -> bool:
        resp = await self._client.post(
            "/api/v1/authz/check", json={"subject": subject, "resource": resource, "action": action}
        )
        resp.raise_for_status()
        return bool(resp.json().get("allowed", False))

    async def whoami(self, token: str) -> dict:
        resp = await self._client.get("/api/v1/whoami", headers={"Authorization": f"Bearer {token}"})
        resp.raise_for_status()
        return resp.json()

    def web_url(self) -> str:
        return self._web

    async def aclose(self) -> None:
        await self._client.aclose()


class FakeChayuanClient:
    """Test double: no network. Records calls, allow-by-default authz."""

    def __init__(self, web_url: str = "http://chayuan.test") -> None:
        self._web = web_url
        self._denied: set[tuple[str, str, str]] = set()
        self.calls: list[dict] = []

    def deny(self, subject: str, resource: str, action: str) -> None:
        self._denied.add((subject, resource, action))

    async def chat_completions(self, model: str, messages: list[dict], **kw: Any) -> dict:
        self.calls.append({"model": model, "messages": messages, **kw})
        return {"choices": [{"message": {"role": "assistant", "content": "[fake reply]"}}]}

    async def kb_query(self, ku_ids: list[str], query: str, **kw: Any) -> dict:
        self.calls.append({"kb": ku_ids, "query": query})
        return {"hits": []}

    async def authorize(self, subject: str, resource: str, action: str) -> bool:
        return (subject, resource, action) not in self._denied

    async def whoami(self, token: str) -> dict:
        return {"subject": "test-user", "dept": "test-dept"}

    def web_url(self) -> str:
        return self._web
