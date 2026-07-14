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


def test_configure_openclaw_opens_config_gui(monkeypatch):
    # v1.2.0(f4fa25d) 起 agent-builder 已被 openclaw-tool 配置器取代。
    # 解释器钉死 python3.11：容器默认 python3 是 3.10，而 station venv / app-manager 均在 3.11，
    # 混用会让配置器与主环境分家（tkinter、依赖解析都不同）。
    # 显式清掉 OPENCLAW_TOOL_DIR：其它测试模块（如 test_agentcfg_api.py）用
    # os.environ.setdefault 在进程级别设过它，不清掉这里就会读到别的测试留下的值。
    monkeypatch.delenv("OPENCLAW_TOOL_DIR", raising=False)
    calls = []
    r = configure_agent("openclaw", spawn=calls.append, post=lambda p, b: None)
    assert r["ok"] and calls == [["python3.11", "/opt/openclaw-tool/openclaw_config_gui.py"]]


def test_configure_openclaw_honors_openclaw_tool_dir_env(monkeypatch):
    # start-station.sh 会把 OPENCLAW_TOOL_DIR 设成卷内 resolve() 出的热更目录；
    # 配置器启动命令必须在调用时读这个 env，而不是 import 时写死 /opt 路径，
    # 否则热更换了 openclaw-tool 版本后，配置界面还是打开旧目录的脚本。
    monkeypatch.setenv("OPENCLAW_TOOL_DIR", "/custom/x")
    calls = []
    r = configure_agent("openclaw", spawn=calls.append, post=lambda p, b: None)
    assert r["ok"] and calls == [["python3.11", "/custom/x/openclaw_config_gui.py"]]


def test_openclaw_dir_helper_defaults_and_honors_env(monkeypatch):
    from station.actions import _openclaw_dir
    monkeypatch.delenv("OPENCLAW_TOOL_DIR", raising=False)
    assert _openclaw_dir() == "/opt/openclaw-tool"
    monkeypatch.setenv("OPENCLAW_TOOL_DIR", "/custom/y")
    assert _openclaw_dir() == "/custom/y"


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
