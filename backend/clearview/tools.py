"""The four MCP tools. The same functions back (a) the in-process agents and (b) the stdio MCP server.

  secure-query-executor      -> Tools.secure_query         (allow-listed, parameterised, read-only)
  context-broker-hybrid-query-> Tools.hybrid_query         (vector + graph over Context Studio ontology)
  notification-service       -> Tools.notify               (Email / SMS / Push -> outbox)
  audit-logger               -> Tools.audit                (hash-chained ledger)
"""
from __future__ import annotations

import json
import sqlite3
import time
from datetime import datetime, timedelta, timezone

from . import audit as audit_mod
from .db import now_iso, rows
from .graph import KnowledgeGraph

# Fixed allow-list: name -> (SQL, ordered parameter names). Agents can never submit SQL text.
ALLOWED_QUERIES: dict[str, tuple[str, tuple[str, ...]]] = {
    "customer_profile": (
        "SELECT id, name, email, tier, date_of_birth, vulnerability_flag, vulnerability_note "
        "FROM customers WHERE id = ?", ("customer_id",)),
    "account_summary": (
        "SELECT id, customer_id, product, balance FROM accounts WHERE id = ?", ("account_id",)),
    "account_transactions": (
        "SELECT id, account_id, posted_at, type, amount, merchant, status, fee_valid, fee_reason, related_tx_id "
        "FROM transactions WHERE account_id = ? AND posted_at >= ? AND posted_at <= ? ORDER BY posted_at DESC",
        ("account_id", "from_ts", "to_ts")),
    "card_disputes": (
        "SELECT id, account_id, tx_id, amount_disputed, atm_dispensed, fraud_score, cardholder_present, "
        "merchant_risk, status FROM card_disputes WHERE account_id = ?", ("account_id",)),
    "call_transcripts": (
        "SELECT id, customer_id, call_at, text FROM call_transcripts WHERE customer_id = ? "
        "AND call_at >= ? AND call_at <= ? ORDER BY call_at DESC", ("customer_id", "from_ts", "to_ts")),
    "crm_cases": (
        "SELECT id, customer_id, case_type, opened_at, closed_at, summary FROM crm_cases "
        "WHERE customer_id = ? ORDER BY opened_at DESC", ("customer_id",)),
    "prior_complaints": (
        "SELECT id, received_at, intent, outcome, status FROM complaints WHERE customer_id = ? AND id != ? "
        "ORDER BY received_at DESC", ("customer_id", "exclude_id")),
}


class ToolError(Exception):
    pass


class Tools:
    """Per-pipeline-run tool facade. Every call is recorded in `tool_calls`."""

    def __init__(self, conn: sqlite3.Connection, graph: KnowledgeGraph, complaint_id: str | None = None,
                 run_no: int | None = None):
        self.conn, self.graph = conn, graph
        self.complaint_id, self.run_no = complaint_id, run_no
        self.agent: str | None = None
        self.calls: list[dict] = []

    # -- helpers ---------------------------------------------------------------------------
    def _log(self, tool: str, args: dict, summary: str, started: float) -> None:
        latency = int((time.perf_counter() - started) * 1000)
        self.conn.execute(
            "INSERT INTO tool_calls(complaint_id, run_no, agent, tool, args_json, summary, latency_ms, called_at)"
            " VALUES (?,?,?,?,?,?,?,?)",
            (self.complaint_id, self.run_no, self.agent, tool, json.dumps(args, default=str), summary, latency, now_iso()))
        self.calls.append({"tool": tool, "summary": summary, "latency_ms": latency})

    # -- tool 1 ----------------------------------------------------------------------------
    def secure_query(self, query_name: str, params: dict) -> dict:
        started = time.perf_counter()
        spec = ALLOWED_QUERIES.get(query_name)
        if spec is None:
            raise ToolError(f"query '{query_name}' is not in the allow-list")
        sql, names = spec
        missing = [n for n in names if n not in params]
        if missing:
            raise ToolError(f"missing parameters: {missing}")
        data = rows(self.conn, sql, tuple(params[n] for n in names))
        self._log("secure-query-executor", {"query": query_name, "params": params}, f"{query_name}: {len(data)} rows", started)
        return {"query": query_name, "row_count": len(data), "rows": data, "source": "readonly-allowlist"}

    # -- tool 2 ----------------------------------------------------------------------------
    def hybrid_query(self, query: str, node_types: list[str] | None = None, top_k: int = 5) -> dict:
        started = time.perf_counter()
        result = self.graph.hybrid_query(query, node_types, top_k)
        top = ", ".join(h["id"] for h in result["hits"][:3]) or "no hits"
        self._log("context-broker-hybrid-query", {"query": query[:200], "node_types": node_types}, f"hits: {top}", started)
        return result

    # -- tool 3 ----------------------------------------------------------------------------
    def notify(self, channel: str, recipient: str, subject: str, body: str) -> dict:
        started = time.perf_counter()
        if channel not in ("EMAIL", "SMS", "PUSH"):
            raise ToolError("channel must be EMAIL, SMS or PUSH")
        cur = self.conn.execute(
            "INSERT INTO outbox(complaint_id, channel, recipient, subject, body, status, created_at) VALUES (?,?,?,?,?,?,?)",
            (self.complaint_id, channel, recipient, subject, body, "QUEUED", now_iso()))
        self._log("notification-service", {"channel": channel, "recipient": recipient, "subject": subject},
                  f"queued #{cur.lastrowid}", started)
        return {"notification_id": cur.lastrowid, "status": "QUEUED"}

    # -- tool 4 ----------------------------------------------------------------------------
    def audit(self, actor: str, event_type: str, payload: dict) -> dict:
        started = time.perf_counter()
        res = audit_mod.append(self.conn, self.complaint_id, actor, event_type, payload)
        self._log("audit-logger", {"actor": actor, "event_type": event_type}, f"seq {res['seq']}", started)
        return res


# ---- date helpers shared by agents / seeding ---------------------------------------------------
def parse_ts(ts: str) -> datetime:
    return datetime.fromisoformat(ts.replace("Z", "+00:00")).astimezone(timezone.utc)


def fmt_ts(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")


def add_business_days(dt: datetime, days: int) -> datetime:
    cur = dt
    while days > 0:
        cur += timedelta(days=1)
        if cur.weekday() < 5:
            days -= 1
    return cur
