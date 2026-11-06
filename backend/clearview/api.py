"""FastAPI backend for the Monitoring Workbench.   uvicorn clearview.api:app --port 8000"""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timedelta, timezone
from typing import Iterator, Literal

from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from . import audit as audit_mod
from . import config, db
from . import demo as demo_mod
from .graph import default_graph
from .pipeline import run_pipeline
from .review import ReviewError, decide
from .tools import add_business_days, fmt_ts

app = FastAPI(title="Clearview Agentic Complaints Management", version="1.0.0")
app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
                   allow_methods=["*"], allow_headers=["*"])

_initialised = False


def get_conn() -> Iterator[sqlite3.Connection]:
    global _initialised
    conn = db.connect()
    if not _initialised:
        db.init_db(conn)
        _initialised = True
    try:
        yield conn
    finally:
        conn.close()


Conn = Depends(get_conn)
CHANNELS = Literal["Branch", "Call Centre", "Mobile App", "Email", "Social Media"]


class NewComplaint(BaseModel):
    customer_id: str
    account_id: str
    channel: CHANNELS
    text: str = Field(min_length=10, max_length=5000)
    process: bool = True


class ReviewIn(BaseModel):
    action: Literal["APPROVE", "RETRIAGE", "ESCALATE"]
    user: str = Field(min_length=1)
    role: Literal["ANALYST", "LEAD", "MANAGER"]
    final_redress: float | None = None
    justification: str | None = None
    letter: str | None = None


class GraphQuery(BaseModel):
    query: str = Field(min_length=2)
    node_types: list[str] | None = None
    top_k: int = Field(5, ge=1, le=20)


def _complaint_row(r: dict) -> dict:
    r["hitl_reasons"] = json.loads(r["hitl_reasons"]) if r.get("hitl_reasons") else []
    for k in ("vulnerable", "legal_threat", "stp_eligible"):
        if r.get(k) is not None:
            r[k] = bool(r[k])
    now = datetime.now(timezone.utc)
    try:
        dl = datetime.fromisoformat(r["fca_deadline"].replace("Z", "+00:00"))
        r["hours_to_deadline"] = round((dl - now).total_seconds() / 3600, 1)
    except (KeyError, ValueError):
        r["hours_to_deadline"] = None
    return r


@app.get("/api/health")
def health(conn: sqlite3.Connection = Conn):
    return {"status": "ok", "complaints": conn.execute("SELECT COUNT(*) FROM complaints").fetchone()[0],
            "ontology_nodes": len(default_graph().nodes)}


@app.get("/api/kpis")
def kpis(conn: sqlite3.Connection = Conn):
    one = lambda sql: conn.execute(sql).fetchone()[0]  # noqa: E731
    processed = one("SELECT COUNT(*) FROM complaints WHERE processed_at IS NOT NULL")
    stp = one("SELECT COUNT(*) FROM complaints WHERE status='RESOLVED_STP'")
    open_states = "('RECEIVED','IN_FLIGHT','PENDING_REVIEW','ERROR_HITL','ESCALATED')"
    avg_redress = conn.execute("SELECT AVG(COALESCE(final_redress, redress_total)) FROM complaints WHERE redress_total > 0 AND status LIKE 'RESOLVED%'").fetchone()[0]
    return {
        "total": one("SELECT COUNT(*) FROM complaints"),
        "active_cases": one(f"SELECT COUNT(*) FROM complaints WHERE status IN {open_states}"),
        "in_flight": one("SELECT COUNT(*) FROM complaints WHERE status IN ('RECEIVED','IN_FLIGHT')"),
        "pending_review": one("SELECT COUNT(*) FROM complaints WHERE status IN ('PENDING_REVIEW','ERROR_HITL','ESCALATED')"),
        "p1_breach_risk": one(f"SELECT COUNT(*) FROM complaints WHERE status IN {open_states} AND (priority='P1' OR vulnerable=1 "
                              "OR julianday(fca_deadline) - julianday('now') < 2)"),
        "vulnerable_open": one(f"SELECT COUNT(*) FROM complaints WHERE vulnerable=1 AND status IN {open_states}"),
        "avg_redress": round(avg_redress or 0, 2),
        "stp_rate": round(stp / processed, 4) if processed else 0,
        "avg_pipeline_ms": round(conn.execute("SELECT AVG(total_latency_ms) FROM complaints WHERE processed_at IS NOT NULL").fetchone()[0] or 0),
        "by_status": db.rows(conn, "SELECT status, COUNT(*) AS n FROM complaints GROUP BY status"),
        "by_intent": db.rows(conn, "SELECT intent, COUNT(*) AS n FROM complaints WHERE intent IS NOT NULL GROUP BY intent ORDER BY n DESC"),
        "by_priority": db.rows(conn, "SELECT priority, COUNT(*) AS n FROM complaints WHERE priority IS NOT NULL GROUP BY priority ORDER BY priority"),
    }


@app.get("/api/complaints")
def list_complaints(status: str | None = None, priority: str | None = None, channel: str | None = None,
                    sentiment: Literal["negative", "neutral", "positive"] | None = None, vulnerable: bool | None = None,
                    q: str | None = None, limit: int = Query(50, ge=1, le=500), offset: int = Query(0, ge=0),
                    conn: sqlite3.Connection = Conn):
    where, args = [], []
    for col, val in (("status", status), ("priority", priority), ("channel", channel)):
        if val:
            where.append(f"c.{col} = ?")
            args.append(val)
    if vulnerable is not None:
        where.append("c.vulnerable = ?")
        args.append(int(vulnerable))
    if sentiment:
        where.append({"negative": "c.sentiment < -0.2", "positive": "c.sentiment > 0.2", "neutral": "c.sentiment BETWEEN -0.2 AND 0.2"}[sentiment])
    if q:
        where.append("(c.id LIKE ? OR c.text LIKE ? OR cu.name LIKE ?)")
        args += [f"%{q}%"] * 3
    w = ("WHERE " + " AND ".join(where)) if where else ""
    total = conn.execute(f"SELECT COUNT(*) FROM complaints c JOIN customers cu ON cu.id=c.customer_id {w}", args).fetchone()[0]
    data = db.rows(conn, f"""SELECT c.id, c.channel, c.received_at, c.fca_deadline, c.status, c.intent, c.priority, c.sentiment, c.vulnerable,
        c.legal_threat, c.outcome, c.redress_total, c.confidence, c.stp_eligible, c.hitl_reasons, c.total_latency_ms, cu.name AS customer_name
        FROM complaints c JOIN customers cu ON cu.id=c.customer_id {w}
        ORDER BY CASE c.priority WHEN 'P1' THEN 1 WHEN 'P2' THEN 2 WHEN 'P3' THEN 3 ELSE 4 END, c.received_at DESC
        LIMIT ? OFFSET ?""", args + [limit, offset])
    return {"total": total, "items": [_complaint_row(r) for r in data]}


@app.get("/api/complaints/{cid}")
def get_complaint(cid: str, conn: sqlite3.Connection = Conn):
    c = db.rows(conn, "SELECT * FROM complaints WHERE id=?", (cid,))
    if not c:
        raise HTTPException(404, "complaint not found")
    c = _complaint_row(c[0])
    cust = db.rows(conn, "SELECT id, name, email, tier, date_of_birth, vulnerability_flag, vulnerability_note FROM customers WHERE id=?", (c["customer_id"],))[0]
    runs = db.rows(conn, "SELECT * FROM agent_runs WHERE complaint_id=? ORDER BY id", (cid,))
    for r in runs:
        r["output"] = json.loads(r.pop("output_json")) if r["output_json"] else None
        r.pop("input_json", None)
    return {"complaint": c, "customer": cust, "agent_runs": runs,
            "tool_calls": db.rows(conn, "SELECT * FROM tool_calls WHERE complaint_id=? ORDER BY id", (cid,)),
            "audit": [{**a, "payload": json.loads(a["payload"])} for a in db.rows(conn, "SELECT * FROM audit_log WHERE complaint_id=? ORDER BY seq", (cid,))]}


@app.post("/api/complaints", status_code=201)
def create_complaint(body: NewComplaint, conn: sqlite3.Connection = Conn):
    acct = conn.execute("SELECT id FROM accounts WHERE id=? AND customer_id=?", (body.account_id, body.customer_id)).fetchone()
    if acct is None:
        raise HTTPException(422, "account does not belong to customer")
    n = conn.execute("SELECT COALESCE(MAX(CAST(SUBSTR(id,5) AS INTEGER)),10000)+1 FROM complaints").fetchone()[0]
    cid = f"CMP-{n}"
    now = datetime.now(timezone.utc).replace(microsecond=0)
    conn.execute("INSERT INTO complaints(id, customer_id, account_id, channel, text, received_at, src_due, fca_deadline, status) VALUES (?,?,?,?,?,?,?,?,?)",
                 (cid, body.customer_id, body.account_id, body.channel, body.text, fmt_ts(now), fmt_ts(add_business_days(now, 3)),
                  fmt_ts(now + timedelta(weeks=8)), "RECEIVED"))
    result = run_pipeline(conn, cid) if body.process else None
    return {"id": cid, "result_status": result["status"] if result else "RECEIVED"}


@app.post("/api/complaints/{cid}/process")
def process_complaint(cid: str, conn: sqlite3.Connection = Conn):
    row = conn.execute("SELECT status FROM complaints WHERE id=?", (cid,)).fetchone()
    if row is None:
        raise HTTPException(404, "complaint not found")
    if row["status"] != "RECEIVED":
        raise HTTPException(409, f"complaint is {row['status']}; only RECEIVED complaints can be processed (use review/RETRIAGE)")
    r = run_pipeline(conn, cid)
    return {"id": cid, "status": r["status"], "error": r.get("error"), "total_latency_ms": r.get("total_latency_ms")}


@app.post("/api/process-batch")
def process_batch(limit: int = Query(10, ge=1, le=100), conn: sqlite3.Connection = Conn):
    ids = [r["id"] for r in conn.execute("SELECT id FROM complaints WHERE status='RECEIVED' ORDER BY received_at DESC LIMIT ?", (limit,))]
    out = [run_pipeline(conn, i) for i in ids]
    return {"processed": len(out), "results": [{"id": o["complaint_id"], "status": o["status"]} for o in out]}


@app.post("/api/complaints/{cid}/review")
def review(cid: str, body: ReviewIn, conn: sqlite3.Connection = Conn):
    try:
        return decide(conn, cid, body.action, body.user, body.role, body.final_redress, body.justification, body.letter)
    except ReviewError as e:
        raise HTTPException(e.status, str(e))


@app.get("/api/audit")
def audit_list(complaint_id: str | None = None, limit: int = Query(100, ge=1, le=1000), conn: sqlite3.Connection = Conn):
    where, args = ("WHERE complaint_id=?", [complaint_id]) if complaint_id else ("", [])
    return db.rows(conn, f"SELECT * FROM audit_log {where} ORDER BY seq DESC LIMIT ?", args + [limit])


@app.get("/api/audit/verify")
def audit_verify(conn: sqlite3.Connection = Conn):
    return audit_mod.verify(conn)


@app.post("/api/graph/query")
def graph_query(body: GraphQuery):
    return default_graph().hybrid_query(body.query, body.node_types, body.top_k)


@app.get("/api/outbox")
def outbox(conn: sqlite3.Connection = Conn):
    return db.rows(conn, "SELECT id, complaint_id, channel, recipient, subject, status, created_at FROM outbox ORDER BY id DESC LIMIT 100")


@app.get("/api/agents/stats")
def agent_stats(conn: sqlite3.Connection = Conn):
    return db.rows(conn, "SELECT agent, COUNT(*) AS runs, ROUND(AVG(latency_ms),1) AS avg_ms, MAX(latency_ms) AS max_ms, "
                         "ROUND(AVG(confidence),3) AS avg_confidence, SUM(status='ERROR') AS errors FROM agent_runs GROUP BY agent")



# ---- demo helpers -------------------------------------------------------------------------------------
@app.get("/api/demo/scenarios")
def demo_scenarios(conn: sqlite3.Connection = Conn):
    return demo_mod.scenarios_with_state(conn)


@app.post("/api/demo/reset")
def demo_reset(conn: sqlite3.Connection = Conn):
    return {"seeded": demo_mod.reset(conn)}