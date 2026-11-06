"""Demo helpers: five fixed scenarios (seed data is deterministic) and a one-call reset.

The scenario ids below were verified against the pipeline output; see docs/demo_script.md.
"""
from __future__ import annotations

import sqlite3

from . import db
from .seed import seed

SCENARIOS = [
    {"id": "CMP-10009", "key": "A", "title": "Duplicate fee - straight-through",
     "show": "Happy path: agents resolve and send the letter with no human. Uphold GBP 35 (10 refund + 25 compensation).",
     "expect": "RESOLVED_STP"},
    {"id": "CMP-10030", "key": "B", "title": "Vulnerable customer - hard stop",
     "show": "Customer is 80 (CRM date of birth). Forced P1, red banner, human review even though redress is only GBP 37.",
     "expect": "PENDING_REVIEW"},
    {"id": "CMP-10020", "key": "C", "title": "Unauthorised card payments - authority limit",
     "show": "Uphold GBP 688.50. Approve as Analyst (blocked, limit GBP 50), then as Manager (allowed).",
     "expect": "PENDING_REVIEW"},
    {"id": "CMP-10005", "key": "D", "title": "Legal threat - escalate",
     "show": "Solicitor mentioned: P1 and human review. Use Escalate to Investigations.",
     "expect": "PENDING_REVIEW"},
    {"id": "CMP-10014", "key": "E", "title": "Mortgage fee - AI rejects",
     "show": "Valid early-repayment charge so the agent rejects (GBP 0). Rejections need approval. Use Request re-triage.",
     "expect": "PENDING_REVIEW"},
]

_TABLES = ["ground_truth", "outbox", "audit_log", "tool_calls", "agent_runs", "complaints", "crm_cases",
           "call_transcripts", "card_disputes", "transactions", "accounts", "customers"]


def reset(conn: sqlite3.Connection) -> int:
    """Drop all data and re-seed the 300 deterministic complaints (nothing processed)."""
    conn.execute("PRAGMA foreign_keys=OFF")
    for t in _TABLES:
        conn.execute(f"DROP TABLE IF EXISTS {t}")
    conn.execute("DELETE FROM sqlite_sequence") if conn.execute(
        "SELECT 1 FROM sqlite_master WHERE name='sqlite_sequence'").fetchone() else None
    conn.execute("PRAGMA foreign_keys=ON")
    return seed(conn)


def scenarios_with_state(conn: sqlite3.Connection) -> list[dict]:
    out = []
    for s in SCENARIOS:
        row = db.rows(conn, "SELECT status FROM complaints WHERE id=?", (s["id"],))
        out.append({**s, "status": row[0]["status"] if row else "MISSING"})
    return out
