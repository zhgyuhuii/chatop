import json
import time

from station.probe.agent_probes import AGENT_SPECS, probe_agent


def _mk_home(tmp_path):
    (tmp_path / ".claude" / "projects" / "p1").mkdir(parents=True)
    (tmp_path / ".claude.json").write_text(json.dumps({"model": "opus"}))
    return tmp_path


def test_configured_when_candidate_exists(tmp_path):
    home = _mk_home(tmp_path)
    st = probe_agent("claude-code", AGENT_SPECS["claude-code"], home, procs=[])
    assert st["configured"] is True and st["model"] == "opus"


def test_not_configured_when_no_files(tmp_path):
    st = probe_agent("codex", AGENT_SPECS["codex"], tmp_path, procs=[])
    assert st["configured"] is False and st["model"] == ""


def test_runtime_running_via_proc_match(tmp_path):
    procs = [{"pid": 9, "name": "openclaw", "cmdline": "openclaw serve", "cpu": 1.5, "mem_mb": 80.0}]
    st = probe_agent("openclaw", AGENT_SPECS["openclaw"], tmp_path, procs=procs)
    assert st["running"] is True and st["cpu"] == 1.5 and st["mem_mb"] == 80.0


def test_session_activity_counts_recent_files(tmp_path):
    home = _mk_home(tmp_path)
    f = home / ".claude" / "projects" / "p1" / "s1.jsonl"
    f.write_text("{}")
    st = probe_agent("claude-code", AGENT_SPECS["claude-code"], home, procs=[], now=time.time())
    assert st["active_sessions"] == 1 and st["last_active"] > 0


def test_specs_cover_required_agents():
    assert {"claude-code", "codex", "openclaw", "hermes", "openhuman"} <= set(AGENT_SPECS)


def test_toml_model_read(tmp_path):
    (tmp_path / ".codex").mkdir()
    (tmp_path / ".codex" / "config.toml").write_text('model = "o4-mini"\n')
    st = probe_agent("codex", AGENT_SPECS["codex"], tmp_path, procs=[])
    assert st["configured"] is True and st["model"] == "o4-mini"
