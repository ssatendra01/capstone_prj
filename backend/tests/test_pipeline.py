from __future__ import annotations

import pytest

from clearview import audit
from clearview.evaluate import evaluate
from clearview.graph import default_graph
from clearview.pipeline import run_pipeline
from clearview.review import ReviewError, decide
from clearview.tools import Tools, ToolError


def _first(conn, **gt):
    cond = " AND ".join(f"{k}=?" for k in gt)
    return conn.execute(f"SELECT complaint_id FROM ground_truth WHERE {cond} ORDER BY complaint_id", tuple(gt.values())).fetchone()[0]


def test_ground_truth_300_cases_meet_targets(conn):
    m = evaluate(conn)
    assert m["cases"] == 300
    assert m["passed"], m
    assert m["vulnerable_recall"] == 1.0 and m["hitl_recall"] == 1.0


def test_hybrid_queries_three_use_cases():
    g = default_graph()
    assert g.hybrid_query("DISP 1.6 eight week final response deadline")["hits"][0]["id"] == "cv:Rule/DISP-1.6"
    assert g.hybrid_query("vulnerable customer hard stop human review")["hits"][0]["id"] == "cv:Rule/VULNERABLE-POLICY"
    redress = g.hybrid_query("redress scale moderate compensation", ["RedressBand"])["hits"][0]
    assert redress["id"] == "cv:Redress/MODERATE"


def test_query_allowlist_rejects_free_form_sql(conn):
    t = Tools(conn, default_graph(), None, None)
    with pytest.raises(ToolError):
        t.secure_query("SELECT * FROM customers", {})
    with pytest.raises(ToolError):
        t.secure_query("customer_profile", {})


def test_vulnerable_is_p1_and_hitl(conn, as_of):
    cid = _first(conn, vulnerable=1)
    res = run_pipeline(conn, cid, as_of=as_of)
    assert res["triage"]["vulnerable"] and res["triage"]["priority"] == "P1"
    assert res["draft"]["hitl_required"] and "VULNERABLE_CUSTOMER" in res["draft"]["hitl_reasons"]
    assert any(g["type"] == "VULNERABLE_CUSTOMER" for g in res["draft"]["guardrails"])
    assert res["status"] == "PENDING_REVIEW"


def test_stp_case_is_dispatched_and_audited(conn, as_of):
    cid = conn.execute("""SELECT g.complaint_id FROM ground_truth g WHERE hitl_required=0 ORDER BY complaint_id""").fetchone()[0]
    res = run_pipeline(conn, cid, as_of=as_of)
    assert res["status"] == "RESOLVED_STP" and res["draft"]["stp_eligible"]
    assert conn.execute("SELECT COUNT(*) FROM outbox WHERE complaint_id=?", (cid,)).fetchone()[0] == 1
    assert "Financial Ombudsman" in res["draft"]["letter"]
    assert audit.verify(conn)["valid"]


def test_redress_over_150_is_hitl(conn, as_of):
    cid = conn.execute("SELECT complaint_id FROM ground_truth WHERE redress_total>150 AND vulnerable=0 AND legal_threat=0 LIMIT 1").fetchone()[0]
    res = run_pipeline(conn, cid, as_of=as_of)
    assert "REDRESS_OVER_150" in res["draft"]["hitl_reasons"] and not res["draft"]["stp_eligible"]


def test_audit_chain_detects_tampering(conn, as_of):
    run_pipeline(conn, _first(conn, intent="ATM_PAYMENT_FAILURE", vulnerable=0), as_of=as_of)
    assert audit.verify(conn)["valid"]
    conn.execute("UPDATE audit_log SET payload='{}' WHERE seq=2")
    v = audit.verify(conn)
    assert not v["valid"] and v["broken_at_seq"] == 2


def test_authority_limits_and_override_justification(conn, as_of):
    cid = conn.execute("SELECT complaint_id FROM ground_truth WHERE redress_total BETWEEN 160 AND 249 AND vulnerable=0 AND legal_threat=0 LIMIT 1").fetchone()[0]
    res = run_pipeline(conn, cid, as_of=as_of)
    assert res["status"] == "PENDING_REVIEW"
    total = res["policy"]["redress_total"]
    assert total > 50
    with pytest.raises(ReviewError) as e:
        decide(conn, cid, "APPROVE", "a.analyst", "ANALYST")
    assert e.value.status == 403                                  # analyst limit £50
    with pytest.raises(ReviewError):
        decide(conn, cid, "APPROVE", "t.lead", "LEAD", final_redress=total + 10)   # override without justification
    out = decide(conn, cid, "APPROVE", "t.lead", "LEAD", final_redress=total + 10, justification="goodwill gesture")
    assert out["status"] == "RESOLVED_HUMAN"
    with pytest.raises(ReviewError) as e2:
        decide(conn, cid, "APPROVE", "t.lead", "LEAD")
    assert e2.value.status == 409                                 # already decided
    assert audit.verify(conn)["valid"]


def test_retriage_and_escalate(conn, as_of):
    a = _first(conn, vulnerable=1)
    run_pipeline(conn, a, as_of=as_of)
    out = decide(conn, a, "RETRIAGE", "a.analyst", "ANALYST", justification="check again")
    assert out["status"] == "PENDING_REVIEW"
    assert conn.execute("SELECT retriage_count FROM complaints WHERE id=?", (a,)).fetchone()[0] == 1
    assert decide(conn, a, "ESCALATE", "a.analyst", "ANALYST", justification="needs investigation")["status"] == "ESCALATED"


def test_contract_violation_fails_safe(conn, as_of, monkeypatch):
    from clearview import agents
    cid = _first(conn, intent="DUPLICATE_CHARGE", vulnerable=0)
    good = agents.policy
    monkeypatch.setattr(agents, "AGENTS", [("triage", agents.triage), ("evidence", agents.evidence),
                                           ("policy", lambda c, t: {**good(c, t), "outcome": "maybe"}), ("draft", agents.draft)])
    res = run_pipeline(conn, cid, as_of=as_of)
    assert res["status"] == "ERROR_HITL"
    assert conn.execute("SELECT status FROM complaints WHERE id=?", (cid,)).fetchone()[0] == "ERROR_HITL"


def test_demo_scenarios_behave_as_scripted(conn, as_of):
    from clearview import demo
    for s in demo.scenarios_with_state(conn):
        assert s["status"] == "RECEIVED"
        res = run_pipeline(conn, s["id"], as_of=as_of)
        assert res["status"] == s["expect"], (s["id"], res["status"])
    got = {s["key"]: conn.execute("SELECT vulnerable, legal_threat, outcome, redress_total, authority_required FROM complaints WHERE id=?", (s["id"],)).fetchone()
           for s in demo.SCENARIOS}
    assert got["B"]["vulnerable"] == 1 and got["B"]["redress_total"] == 37.0
    assert got["C"]["redress_total"] == 688.5 and got["C"]["authority_required"] == "cv:Authority/MANAGER"
    assert got["D"]["legal_threat"] == 1
    assert got["E"]["outcome"] == "reject"


def test_demo_reset_restores_clean_state(conn, as_of):
    from clearview import audit, demo
    run_pipeline(conn, "CMP-10009", as_of=as_of)
    assert conn.execute("SELECT COUNT(*) FROM audit_log").fetchone()[0] > 0
    assert demo.reset(conn) == 300
    assert conn.execute("SELECT COUNT(*) FROM audit_log").fetchone()[0] == 0
    assert conn.execute("SELECT COUNT(*) FROM complaints WHERE status='RECEIVED'").fetchone()[0] == 300
    assert audit.verify(conn)["valid"]
