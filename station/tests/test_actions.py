import pytest

from station.actions import configure_agent, install_agent, open_agent


def test_open_session_cli_spawns_terminal():
    calls = []
    r = open_agent("claude-code", spawn=calls.append, post=lambda p, b: pytest.fail("no post"))
    assert r["ok"] and calls == [["chatop-run-cli", "claude"]]


def test_open_gui_agent_goes_through_app_manager_launch():
    posts = []
    r = open_agent("openhuman", spawn=lambda c: pytest.fail("no spawn"),
                   post=lambda path, body: posts.append((path, body)) or {"state": "launched"})
    assert r["ok"] and posts == [("/apps/launch", {"id": "openhuman"})]


def test_configure_openclaw_opens_config_gui():
    # v1.2.0(f4fa25d) 起 agent-builder 已被 openclaw-tool 配置器取代。
    # 解释器钉死 python3.11：容器默认 python3 是 3.10，而 station venv / app-manager 均在 3.11，
    # 混用会让配置器与主环境分家（tkinter、依赖解析都不同）。
    calls = []
    r = configure_agent("openclaw", spawn=calls.append, post=lambda p, b: None)
    assert r["ok"] and calls == [["python3.11", "/opt/openclaw-tool/openclaw_config_gui.py"]]


def test_configure_hermes_runs_setup_in_terminal():
    calls = []
    configure_agent("hermes", spawn=calls.append, post=lambda p, b: None)
    assert calls == [["chatop-run-cli", "hermes", "setup"]]


def test_install_forwards_to_app_manager():
    posts = []
    r = install_agent("hermes", post=lambda path, body: posts.append((path, body)) or {"state": "queued"})
    assert r["ok"] and posts == [("/apps/install", {"id": "hermes"})]


def test_unknown_agent_raises():
    with pytest.raises(KeyError):
        open_agent("nope", spawn=lambda c: None, post=lambda p, b: None)
