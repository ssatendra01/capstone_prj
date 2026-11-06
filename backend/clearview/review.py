"""Human-in-the-loop decisions with server-enforced delegated authority."""
from __future__ import annotations

import sqlite3

from . import audit as audit_mod
from .db import now_iso
from .graph import default_graph
from .tools import Tools

ROLES = {"ANALYST": "cv:Authority/ANALYST", "LEAD": "cv:Authority/LEAD", "MANAGER": "cv:Authority/MANAGER"}
ACTIONS = ("APPROVE", "RETRIAGE", "ESCALATE")


class ReviewError(Exception):
    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.status = status


def decide(conn: sqlite3.Connection, complaint_id: str, action: str, user: str, role: str,
           final_redress: float | None = None, justification: str | None = None, letter: str | None = None,
           graph=None) -> dict:
    graph = graph or default_graph()
    action, role = action.upper(), role.upper()
    if action not in ACTIONS:
        raise ReviewError(f"action must be one of {ACTIONS}")
    if role not in ROLES:
        raise ReviewError(f"role must be one of {tuple(ROLES)}")
    c = conn.execute("SELECT * FROM complaints WHERE id=?", (complaint_id,)).fetchone()
    if c is None:
        raise ReviewError("complaint not found", 404)
    if c["status"] not in ("PENDING_REVIEW", "ERROR_HITL", "ESCALATED"):
        raise ReviewError(f"complaint is {c['status']}; not awaiting review", 409)
    tools = Tools(conn, graph, complaint_id, c["retriage_count"] + 1)
    tools.agent = "human"

    if action == "RETRIAGE":
        conn.execute("UPDATE complaints SET status='RECEIVED', retriage_count=retriage_count+1 WHERE id=?", (complaint_id,))
        tools.audit(user, "HUMAN_RETRIAGE", {"role": role, "justification": justification})
        from .pipeline import run_pipeline
        return run_pipeline(conn, complaint_id, graph, actor=user)

    if action == "ESCALATE":
        conn.execute("UPDATE complaints SET status='ESCALATED', decided_by=?, decided_at=? WHERE id=?", (user, now_iso(), complaint_id))
        tools.audit(user, "HUMAN_ESCALATED", {"role": role, "justification": justification})
        return {"complaint_id": complaint_id, "status": "ESCALATED"}

    # APPROVE ------------------------------------------------------------------------------------------
    if c["status"] == "ERROR_HITL" or c["letter"] is None:
        raise ReviewError("no AI recommendation to approve; re-triage or escalate", 409)
    ai_total = float(c["redress_total"] or 0)
    redress = ai_total if final_redress is None else round(float(final_redress), 2)
    if redress < 0:
        raise ReviewError("redress cannot be negative")
    if abs(redress - ai_total) > 0.004 and not (justification and justification.strip()):
        raise ReviewError("a justification note is mandatory when overriding AI-calculated redress")
    limit = graph.get(ROLES[role])["limitGBP"]
    if redress > limit:
        raise ReviewError(f"redress £{redress:.2f} exceeds {role.title()} authority £{limit:.0f}; escalate to a higher level", 403)
    final_letter = letter if letter and letter.strip() else c["letter"]
    conn.execute("UPDATE complaints SET status='RESOLVED_HUMAN', final_redress=?, decided_by=?, decided_at=?, letter=? WHERE id=?",
                 (redress, user, now_iso(), final_letter, complaint_id))
    profile = conn.execute("SELECT email FROM customers WHERE id=?", (c["customer_id"],)).fetchone()
    tools.notify("EMAIL", profile["email"], f"Your complaint {complaint_id} - our response", final_letter)
    tools.audit(user, "HUMAN_APPROVED", {"role": role, "ai_redress": ai_total, "final_redress": redress,
                                         "override": abs(redress - ai_total) > 0.004, "justification": justification,
                                         "letter_edited": final_letter != c["letter"]})
    return {"complaint_id": complaint_id, "status": "RESOLVED_HUMAN", "final_redress": redress}
