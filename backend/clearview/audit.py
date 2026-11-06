"""Tamper-evident, append-only audit ledger (hash chain) – backs the `audit-logger` MCP tool."""
from __future__ import annotations

import hashlib
import json
import sqlite3
import threading

from .db import now_iso

GENESIS = "0" * 64
_lock = threading.Lock()


def _digest(prev_hash: str, ts: str, complaint_id: str | None, actor: str, event_type: str, payload: str) -> str:
    material = json.dumps([prev_hash, ts, complaint_id, actor, event_type, payload], ensure_ascii=False)
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


def append(conn: sqlite3.Connection, complaint_id: str | None, actor: str, event_type: str, payload: dict) -> dict:
    body = json.dumps(payload, sort_keys=True, ensure_ascii=False, default=str)
    with _lock:
        conn.execute("BEGIN IMMEDIATE")
        try:
            row = conn.execute("SELECT hash FROM audit_log ORDER BY seq DESC LIMIT 1").fetchone()
            prev = row["hash"] if row else GENESIS
            ts = now_iso()
            h = _digest(prev, ts, complaint_id, actor, event_type, body)
            cur = conn.execute(
                "INSERT INTO audit_log(ts, complaint_id, actor, event_type, payload, prev_hash, hash)"
                " VALUES (?,?,?,?,?,?,?)", (ts, complaint_id, actor, event_type, body, prev, h))
            conn.execute("COMMIT")
        except Exception:
            conn.execute("ROLLBACK")
            raise
    return {"seq": cur.lastrowid, "hash": h, "prev_hash": prev, "ts": ts}


def verify(conn: sqlite3.Connection) -> dict:
    prev = GENESIS
    count = 0
    for r in conn.execute("SELECT * FROM audit_log ORDER BY seq"):
        expected = _digest(prev, r["ts"], r["complaint_id"], r["actor"], r["event_type"], r["payload"])
        if r["prev_hash"] != prev or r["hash"] != expected:
            return {"valid": False, "entries": count, "broken_at_seq": r["seq"]}
        prev = r["hash"]
        count += 1
    return {"valid": True, "entries": count, "head": prev}
