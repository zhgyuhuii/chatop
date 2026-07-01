import pytest
from httpx import ASGITransport, AsyncClient

from chacmd.api.app import create_app
from chacmd.interfaces.db import Database


@pytest.fixture
async def client():
    db = Database(url="sqlite+aiosqlite:///:memory:")
    await db.create_all()
    app = create_app(db)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c
    await db.dispose()


@pytest.mark.asyncio
async def test_openapi_served(client):
    resp = await client.get("/openapi.json")
    assert resp.status_code == 200
    assert "/api/v1/tasks/{code}/runs" in resp.json()["paths"]


@pytest.mark.asyncio
async def test_create_run_by_code_returns_job_id(client):
    resp = await client.post("/api/v1/tasks/world-rank-app/runs",
                             json={"goal": "build ranking app", "dept": "d1"})
    assert resp.status_code == 201
    body = resp.json()
    assert body["job_id"]
    assert body["state"] == "queued"


@pytest.mark.asyncio
async def test_get_run_status(client):
    created = await client.post("/api/v1/tasks/c/runs", json={"goal": "g", "dept": "d1"})
    job_id = created.json()["job_id"]
    resp = await client.get(f"/api/v1/runs/{job_id}")
    assert resp.status_code == 200
    assert resp.json()["code"] == "c"


@pytest.mark.asyncio
async def test_list_containers(client):
    resp = await client.get("/api/v1/containers")
    assert resp.status_code == 200
    assert resp.json() == []
