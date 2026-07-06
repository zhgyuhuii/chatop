from __future__ import annotations

import json
import sqlite3
import time
import uuid
from pathlib import Path

STATES = {"queued", "running", "pending_approval", "succeeded", "failed", "cancelled"}
TERMINAL = {"succeeded", "failed", "cancelled"}
_ALLOWED = {
    "queued": {"running", "cancelled"},
    "running": {"pending_approval", "succeeded", "failed", "cancelled"},
    "pending_approval": {"running", "cancelled"},
}

_SCHEMA = """
CREATE TABLE IF NOT EXISTS jobs(
  id TEXT PRIMARY KEY, agent TEXT NOT NULL, goal TEXT NOT NULL,
  workdir TEXT, source TEXT NOT NULL DEFAULT 'manual',
  state TEXT NOT NULL DEFAULT 'queued', current_step TEXT DEFAULT '',
  tokens INTEGER DEFAULT 0, created_at REAL, updated_at REAL);
CREATE TABLE IF NOT EXISTS job_events(
  rid INTEGER PRIMARY KEY AUTOINCREMENT, job_id TEXT NOT NULL,
  seq INTEGER, kind TEXT, payload TEXT, ts REAL);
CREATE INDEX IF NOT EXISTS ix_events_job ON job_events(job_id);
"""


class TaskStore:
    def __init__(self, db_path: Path | str) -> None:
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self._db = sqlite3.connect(str(db_path), check_same_thread=False)
        self._db.row_factory = sqlite3.Row
        self._db.executescript(_SCHEMA)

    def create_job(self, agent: str, goal: str, workdir: str | None,
                   source: str = "manual", job_id: str | None = None) -> dict:
        jid = job_id or uuid.uuid4().hex[:12]
        now = time.time()
        self._db.execute(
            "INSERT INTO jobs(id,agent,goal,workdir,source,state,created_at,updated_at)"
            " VALUES(?,?,?,?,?,'queued',?,?)", (jid, agent, goal, workdir, source, now, now))
        self._db.commit()
        return self.get_job(jid)

    def get_job(self, job_id: str) -> dict:
        row = self._db.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()
        if row is None:
            raise KeyError(job_id)
        return dict(row)

    def list_jobs(self, limit: int = 200) -> list[dict]:
        rows = self._db.execute(
            "SELECT * FROM jobs ORDER BY created_at DESC LIMIT ?", (limit,)).fetchall()
        return [dict(r) for r in rows]

    def transition(self, job_id: str, new_state: str) -> None:
        cur = self.get_job(job_id)["state"]
        if new_state not in _ALLOWED.get(cur, set()):
            raise ValueError(f"illegal transition {cur} -> {new_state}")
        self._db.execute("UPDATE jobs SET state=?, updated_at=? WHERE id=?",
                         (new_state, time.time(), job_id))
        self._db.commit()

    def set_step(self, job_id: str, step: str) -> None:
        self._db.execute("UPDATE jobs SET current_step=?, updated_at=? WHERE id=?",
                         (step[:200], time.time(), job_id))
        self._db.commit()

    def add_tokens(self, job_id: str, n: int) -> None:
        self._db.execute("UPDATE jobs SET tokens=tokens+?, updated_at=? WHERE id=?",
                         (n, time.time(), job_id))
        self._db.commit()

    def append_event(self, ev: dict) -> None:
        self._db.execute(
            "INSERT INTO job_events(job_id,seq,kind,payload,ts) VALUES(?,?,?,?,?)",
            (ev["job_id"], ev.get("seq", 0), ev.get("kind", "progress"),
             json.dumps(ev.get("payload", {}), ensure_ascii=False), ev.get("ts", time.time())))
        self._db.commit()

    def list_events(self, job_id: str, limit: int = 500) -> list[dict]:
        rows = self._db.execute(
            "SELECT * FROM job_events WHERE job_id=? ORDER BY rid LIMIT ?",
            (job_id, limit)).fetchall()
        out = []
        for r in rows:
            d = dict(r)
            d["payload"] = json.loads(d["payload"] or "{}")
            out.append(d)
        return out

    def upsert_detected(self, job_id: str, agent: str, goal: str, state: str) -> None:
        """侦测型任务：允许直接落任意状态（历史会话无从走状态机）。"""
        now = time.time()
        self._db.execute(
            "INSERT INTO jobs(id,agent,goal,workdir,source,state,created_at,updated_at)"
            " VALUES(?,?,?,NULL,'detected',?,?,?)"
            " ON CONFLICT(id) DO UPDATE SET state=excluded.state, updated_at=excluded.updated_at",
            (job_id, agent, goal, state, now, now))
        self._db.commit()
