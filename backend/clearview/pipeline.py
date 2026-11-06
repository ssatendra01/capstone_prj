"""Orchestrator: runs Triage -> Evidence -> Policy -> Draft, validates every handshake against the
frozen JSON schemas, logs agent runs / MCP tool calls / audit records, and persists the result."""
from __future__ import annotations

import json
import sqlite3
import time
from datetime import datetime, timezone
from functools import lru_cache

from jsonschema import Draft202012Validator

from . import agents as agent_mod
from . import config
from .db import now_iso
from .graph import KnowledgeGraph, default_graph
from .tools import Tools

SCHEMA_DIR = config.REPO / "specs" / "contracts" / "schemas"
SCHEMA_FILES = {"input": "complaint_input", "triage": "triage_output", "evidence": "evidence_output",
                "policy": "policy_output", "draft": "draft_output"}


@lru_cache(maxsize=None)
def _validator(kind: str) -> Draft202012Validator:
    schema = json.loads((SCHEMA_DIR / f"{SCHEMA_FILES[kind]}.schema.json").read_text(encoding="utf-8"))
    return Draft202012Validator(schema)


def validate_contract(kind: str, payload: dict) -> None:
    errs = sorted(_validator(kind).iter_errors(payload), key=lambda e: list(e.path))
    if errs:
        raise ValueError(f"{kind} contract violation: " + "; ".join(f"{'/'.join(map(str, e.path))}: {e.message}" for e in errs[:3]))


def run_pipeline(conn: sqlite3.Connection, complaint_id: str, graph: KnowledgeGraph | None = None,
                 as_of: datetime | None = None, actor: str = "orchestrator") -> dict:
    graph = graph or default_graph()
    as_of = as_of or datetime.now(timezone.utc)
    row = conn.execute("SELECT * FROM complaints WHERE id = ?", (complaint_id,)).fetchone()
    if row is None:
        raise KeyError(complaint_id)
    complaint = dict(row)
    run_no = complaint["retriage_count"] + 1
    conn.execute("DELETE FROM tool_calls WHERE complaint_id = ? AND run_no = ?", (complaint_id, run_no))
    conn.execute("UPDATE complaints SET status='IN_FLIGHT' WHERE id=?", (complaint_id,))

    tools = Tools(conn, graph, complaint_id, run_no)
    tools.agent = "orchestrator"
    tools.audit(actor, "PIPELINE_STARTED", {"run_no": run_no})
    ctx: dict = {"complaint": complaint, "as_of": as_of}
    total_ms = 0
    try:
        validate_contract("input", {k: complaint[k] for k in ("id", "customer_id", "account_id", "channel", "text", "received_at", "src_due", "fca_deadline")})
        for name, fn in agent_mod.AGENTS:
            tools.agent = name
            started_at, t0 = now_iso(), time.perf_counter()
            status, err, out = "OK", None, None
            try:
                out = fn(ctx, tools)
                validate_contract(name, out)
                ctx[name] = out
            except Exception as exc:  # recorded, then re-raised to fail the run safely
                status, err = "ERROR", f"{type(exc).__name__}: {exc}"
            latency = int((time.perf_counter() - t0) * 1000)
            total_ms += latency
            conf = (out or {}).get("confidence", (out or {}).get("final_confidence"))
            conn.execute(
                "INSERT INTO agent_runs(complaint_id, run_no, agent, status, started_at, latency_ms, confidence, input_json, output_json, error)"
                " VALUES (?,?,?,?,?,?,?,?,?,?)",
                (complaint_id, run_no, name, status, started_at, latency, conf,
                 json.dumps({"keys": [k for k in ctx if k not in ("as_of",)]}), json.dumps(out, default=str) if out else None, err))
            tools.audit(name, f"AGENT_{status}", {"run_no": run_no, "latency_ms": latency, "confidence": conf,
                                                   "citations": (out or {}).get("citations", []), "error": err})
            if err:
                raise RuntimeError(err)
    except Exception as exc:
        conn.execute("UPDATE complaints SET status='ERROR_HITL', hitl_reasons=?, total_latency_ms=? WHERE id=?",
                     (json.dumps(["PIPELINE_ERROR"]), total_ms, complaint_id))
        tools.agent = "orchestrator"
        tools.audit(actor, "PIPELINE_FAILED", {"error": str(exc)})
        return {"complaint_id": complaint_id, "status": "ERROR_HITL", "error": str(exc)}

    tri, pol, dr = ctx["triage"], ctx["policy"], ctx["draft"]
    tools.agent = "draft"
    status = "PENDING_REVIEW"
    if dr["stp_eligible"]:
        tools.notify(dr["dispatch"]["channel"], dr["dispatch"]["recipient"], dr["dispatch"]["subject"], dr["letter"])
        status = "RESOLVED_STP"
    conn.execute(
        """UPDATE complaints SET status=?, intent=?, priority=?, sla_due=?, sentiment=?, vulnerable=?, legal_threat=?, route_team=?,
           outcome=?, refund_amount=?, compensation_amount=?, redress_total=?, authority_required=?, confidence=?, stp_eligible=?,
           hitl_reasons=?, letter=?, letter_type=?, total_latency_ms=?, processed_at=? WHERE id=?""",
        (status, tri["intent"], tri["priority"], tri["sla_due"], tri["sentiment"], int(tri["vulnerable"]), int(tri["legal_threat"]),
         tri["route_team"], pol["outcome"], pol["refund_amount"], pol["compensation_amount"], pol["redress_total"],
         pol["authority_required"], dr["final_confidence"], int(dr["stp_eligible"]), json.dumps(dr["hitl_reasons"]),
         dr["letter"], dr["letter_type"], total_ms, now_iso(), complaint_id))
    tools.agent = "orchestrator"
    tools.audit(actor, "PIPELINE_COMPLETED", {"status": status, "summary": dr["audit_summary"], "total_latency_ms": total_ms})
    return {"complaint_id": complaint_id, "status": status, "triage": tri, "evidence": ctx["evidence"], "policy": pol, "draft": dr,
            "total_latency_ms": total_ms}
