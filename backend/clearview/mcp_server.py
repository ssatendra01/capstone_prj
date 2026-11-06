"""stdio MCP server exposing the four Clearview tools (register in .bob/mcp.json).

    python -m clearview.mcp_server
"""
from __future__ import annotations

import json
import sys

from mcp.server.mcpserver import MCPServer

from . import audit as audit_mod
from . import db
from .graph import default_graph
from .tools import ALLOWED_QUERIES, Tools

mcp = MCPServer("clearview-complaints-tools",
                instructions="Tools for the Clearview complaints agents: read-only evidence queries, Context Studio hybrid "
                             "(vector+graph) queries, notifications and a tamper-evident audit ledger.")


def _tools(complaint_id: str | None) -> tuple[Tools, object]:
    conn = db.connect()
    db.init_db(conn)
    return Tools(conn, default_graph(), complaint_id, None), conn


@mcp.tool(name="secure-query-executor",
          description="Run an allow-listed, parameterised, READ-ONLY query against the bank data (T24/CAMS/Salesforce/Verint simulation). "
                      "query_name must be one of: " + ", ".join(ALLOWED_QUERIES) + ". Free-form SQL is rejected.")
def secure_query_executor(query_name: str, params: dict, complaint_id: str | None = None) -> str:
    t, conn = _tools(complaint_id)
    try:
        return json.dumps(t.secure_query(query_name, params), default=str)
    finally:
        conn.close()


@mcp.tool(name="context-broker-hybrid-query")
def context_broker_hybrid_query(query: str, node_types: list[str] | None = None, top_k: int = 5) -> str:
    """Hybrid (vector + one-hop graph) query over the Clearview Context Studio ontology (bank profile, FCA DISP rules,
    IT landscape, vulnerability markers, redress bands, precedents). Returns scored hits with ids to cite."""
    t, conn = _tools(None)
    try:
        return json.dumps(t.hybrid_query(query, node_types, top_k))
    finally:
        conn.close()


@mcp.tool(name="notification-service")
def notification_service(channel: str, recipient: str, subject: str, body: str, complaint_id: str | None = None) -> str:
    """Queue a customer notification (channel EMAIL, SMS or PUSH) in the outbox."""
    t, conn = _tools(complaint_id)
    try:
        return json.dumps(t.notify(channel, recipient, subject, body))
    finally:
        conn.close()


@mcp.tool(name="audit-logger")
def audit_logger(actor: str, event_type: str, payload: dict, complaint_id: str | None = None) -> str:
    """Append an entry to the hash-chained audit ledger and return its sequence number and hash."""
    t, conn = _tools(complaint_id)
    try:
        res = t.audit(actor, event_type, payload)
        res["chain"] = audit_mod.verify(conn)["valid"]
        return json.dumps(res)
    finally:
        conn.close()


if __name__ == "__main__":
    print("clearview MCP server starting on stdio", file=sys.stderr)
    mcp.run("stdio")

