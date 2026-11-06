# COMPLAINTS-01 – Implementation Plan

Input: `spec.md`, `constitution.md`. Status: approved for implementation.

## Architecture
```
Channels -> FastAPI (/api) -> Orchestrator (pipeline.py)
   Triage -> Evidence -> Policy -> Draft      (each handshake validated against specs/contracts/schemas/*.json)
        |        |          |         |
        +--------+----MCP TOOL LAYER-+---------------------------+
          secure-query-executor | context-broker-hybrid-query | notification-service | audit-logger
        |                                   |
   SQLite (dev) / PostgreSQL 15 (prod)   Context Studio ontology (context-studio/ontology.jsonld)
        |
   Next.js 15 Monitoring Workbench (frontend/)  -- HITL: approve / re-triage / escalate
```

## Tech stack
| Layer | Choice | Reason |
|-------|--------|--------|
| Agents + tools | Python 3.11+, deterministic rules over knowledge graph | testable offline, 300-case ground truth |
| MCP | `mcp` SDK (stdio) – `.bob/mcp.json` | usable from IBM Bob / ICA Agentic Studio |
| API | FastAPI + Pydantic | typed contracts |
| DB | SQLite runtime default; `db/schema.postgres.sql` for PostgreSQL 15 | zero-setup dev, prod parity |
| Frontend | Next.js 15 (App Router), React 19, Carbon Design System (`@carbon/react`) | per mandate |
| Delivery | Docker Compose | `db`, `backend`, `frontend` |

## Components & decisions
1. **Knowledge graph** (`graph.py`): TF-IDF cosine retrieval + one-hop edge expansion over JSON-LD (`governedBy`, `routesTo`, `evidenceFrom`).
2. **Tools** (`tools.py`): allow-listed named queries only (no SQL accepted), every call logged to `tool_calls`.
3. **Agents** (`agents.py`): pure functions; output cites `cv:` ids. ICA LLM agents can replace them via `agents/ica/*.yaml` with the same schemas.
4. **Orchestrator** (`pipeline.py`): schema-validates each step; any failure ⇒ `ERROR_HITL` (fail safe, never auto-send).
5. **HITL** (`review.py`): delegated authority enforced server-side; override requires justification; re-triage increments `run_no`.
6. **Audit** (`audit.py`): SHA-256 hash chain, `BEGIN IMMEDIATE` serialisation; `/api/audit/verify`.
7. **Workbench**: KPI cards, filterable table, agent monitor, audit viewer, review panel, guardrail banners, intake form, knowledge-graph query console.

## MCP tool integrations (per task)
Triage: secure-query (customer_profile), hybrid-query. Evidence: secure-query x5. Policy: hybrid-query. Draft: secure-query, notification (STP only). All: audit-logger.

## Risks
| Risk | Mitigation |
|------|-----------|
| LLM drift if ICA agents replace rules | contracts validated at runtime; evaluate.py gate in CI |
| Vulnerable false negatives | multi-source detection (text, CRM flag, age); hard-stop invariant tested |
| Authority bypass in UI | enforced in API, tested |
