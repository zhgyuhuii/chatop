import pytest

from chacmd.interfaces.chayuan_client import ChayuanClient, FakeChayuanClient


@pytest.mark.asyncio
async def test_fake_chayuan_client_authz_and_weburl():
    c: ChayuanClient = FakeChayuanClient(web_url="http://chayuan.local")
    assert await c.authorize(subject="u1", resource="container:pm", action="dispatch") is True
    c.deny("u1", "container:secret", "dispatch")
    assert await c.authorize(subject="u1", resource="container:secret", action="dispatch") is False
    assert c.web_url() == "http://chayuan.local"


@pytest.mark.asyncio
async def test_fake_chayuan_client_chat_records_calls():
    c = FakeChayuanClient()
    out = await c.chat_completions(model="deepseek", messages=[{"role": "user", "content": "hi"}])
    assert out["choices"][0]["message"]["content"]  # non-empty stub reply
    assert c.calls[-1]["model"] == "deepseek"
