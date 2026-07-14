# -*- coding: utf-8 -*-
import json

from agentconfig.models import providers
from agentconfig.core import types


def test_live_list_from_openai_shape():
    def opener(url, headers, timeout=8.0):
        assert "Authorization" in headers
        return 200, json.dumps({"data": [{"id": "deepseek-chat"}, {"id": "deepseek-reasoner"}]}).encode()
    r = providers.verify_and_list("deepseek", "key", opener=opener)
    assert r["ok"] and r["source"] == types.SRC_LIVE
    keys = {m["key"] for m in r["models"]}
    assert "deepseek/deepseek-chat" in keys


def test_401_falls_back_to_snapshot():
    def opener(url, headers, timeout=8.0):
        return 401, b"{}"
    r = providers.verify_and_list("deepseek", "bad", opener=opener)
    assert r["ok"] is False and r["source"] == types.SRC_SNAPSHOT
    assert r["models"]  # 快照非空
    assert "无效" in r["reason"]


def test_network_error_falls_back():
    def opener(url, headers, timeout=8.0):
        return 0, b"Connection refused"
    r = providers.verify_and_list("deepseek", "k", opener=opener)
    assert r["source"] == types.SRC_SNAPSHOT and "网络" in r["reason"]


def test_ollama_uses_tags_endpoint():
    seen = {}
    def opener(url, headers, timeout=8.0):
        seen["url"] = url
        return 200, json.dumps({"models": [{"name": "llama3:8b"}]}).encode()
    r = providers.verify_and_list("ollama", "", opener=opener)
    assert seen["url"].endswith("/api/tags")
    assert r["ok"] and r["models"][0]["key"] == "ollama/llama3:8b"


def test_unknown_provider_returns_snapshot():
    r = providers.verify_and_list("xiaomi", "", opener=lambda *a, **k: (200, b"{}"))
    assert r["source"] == types.SRC_SNAPSHOT


def test_list_providers_merges_curated_and_live():
    provs = providers.list_providers()
    by = {p["id"]: p for p in provs}
    assert "deepseek" in by and by["deepseek"]["has_live"] is True
    assert by["deepseek"]["auth_kind"] == "key"
    assert "github-copilot" in by and by["github-copilot"]["auth_kind"] == "oauth"
    assert by["byteplus"]["has_live"] is False
    assert "label" in by["deepseek"] and "apply_url" in by["deepseek"]
