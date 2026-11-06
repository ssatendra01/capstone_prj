# COMPLAINTS-01 – Tasks

Each task = one code change / configuration, with acceptance criteria (AC). `[x]` = done and verified.

## Foundations
- [x] T01 Constitution, spec, plan – AC: reviewed, merged before code.
- [x] T02 Context Studio ontology JSON-LD (66 nodes: bank, systems, rules, intents, 13 vulnerability markers, SLA, authority, redress, precedents) – AC: 3 hybrid queries return DISP-1.6 / VULNERABLE-POLICY / REDRESS MODERATE (`test_hybrid_queries_three_use_cases`).
- [x] T03 DB schema (SQLite + PostgreSQL) – AC: indexed; FK enforced.
- [x] T04 Seed 300 synthetic complaints + ground truth – AC: deterministic; intent mix matches the 28/22/18/15/10/7 % distribution (scaled), 14 % vulnerable.

## Contracts (SDD gate – frozen before agent code)
- [x] T05 JSON schemas x5 (`specs/contracts/schemas/`) – AC: no placeholders; invariants (vulnerable ⇒ P1, STP ⇒ no HITL reasons).
- [x] T06 Prompt contracts x4 (`specs/contracts/prompts/`) – AC: ROLE/BOUNDARY/TASK/GUARDRAILS/OUTPUT FORMAT/Examples.
- [x] T07 MCP tool specs x4 + evaluation matrix (`specs/contracts/mcp_tools.md`, `evaluation_matrix.md`).

## Implementation
- [x] T08 Tools + allow-list – AC: free-form SQL rejected (test).
- [x] T09 Four agents + orchestrator – AC: <2 min/case (measured ≈30 ms), schema-valid, audit written.
- [x] T10 Audit hash chain – AC: tamper detected (test).
- [x] T11 HITL review service – AC: authority limits, override justification, re-triage, escalate (tests).
- [x] T12 FastAPI endpoints – AC: health, kpis, list/filter, detail, create, process, batch, review, audit, graph query, outbox.
- [x] T13 stdio MCP server + `.bob/mcp.json` – AC: 4 tools listed and callable by an MCP client.
- [x] T14 Evaluation harness – AC: intent/priority/outcome/redress ≥ 90 %, vulnerable recall 100 %, HITL recall 100 %.
- [x] T15 Next.js 15 Carbon Monitoring Workbench – AC: `next build` passes; dashboard, table filters, agent monitor, review panel, guardrails.
- [x] T16 Docker Compose + PostgreSQL schema + ICA agent configs.
- [x] T17 Process Studio documents (As-Is / To-Be / escalation / handshake payloads).
- [x] T18 End-to-end verification and README.

