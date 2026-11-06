# AGENTS.md – repository architecture for coding agents (IBM Bob / Kiro / Cursor)

Project: Clearview Retail Bank – Agentic Complaints Management. Read `constitution.md` first; it is binding.

## Workflow (SDD)
`constitution.md → specs/COMPLAINTS-01/spec.md → plan.md → tasks.md → code`. Never change behaviour without updating the matching spec/contract first.

## Layout
| Path | Purpose |
|------|---------|
| `specs/` | spec, plan, tasks; `contracts/schemas` (JSON Schema), `contracts/prompts` (4 prompt contracts), `contracts/mcp_tools.md`, `contracts/evaluation_matrix.md` |
| `context-studio/ontology.jsonld` | Context Studio knowledge graph – single source of truth for rules, thresholds, keywords |
| `process-studio/` | As-Is/To-Be, escalation rules, handshake payloads |
| `backend/clearview/` | `agents.py`, `pipeline.py`, `tools.py`, `graph.py`, `audit.py`, `review.py`, `api.py`, `mcp_server.py`, `seed.py`, `evaluate.py` |
| `backend/tests/` | pytest suite (10+ tests incl. 300-case evaluation) |
| `db/` | `schema.sqlite.sql` (runtime), `schema.postgres.sql` (production) |
| `agents/ica/` | ICA Agentic Studio agent definitions mirroring the prompt contracts |
| `frontend/` | Next.js 15 + Carbon Monitoring Workbench |
| `.bob/mcp.json` | Registers the `clearview-complaints-tools` MCP server |

## Commands
```
cd backend
pip install -r requirements.txt
python -m clearview.seed --reset        # 300 synthetic complaints + ground truth
python -m clearview.evaluate -v         # quality gate (exit 1 if targets missed)
python -m pytest -q
uvicorn clearview.api:app --port 8000
python -m clearview.mcp_server          # stdio MCP server
cd ../frontend && npm install && npm run dev   # http://localhost:3000
```

## Rules for agents modifying code
- Thresholds/keywords live in the ontology; do not hardcode new ones in agents.
- Any agent output change requires a schema change + `evaluate` run at 100 % vulnerable & HITL recall.
- Never add a way to run arbitrary SQL; add a named query to `ALLOWED_QUERIES` instead.
- Audit every state change through `audit.append`.
- No secrets in the repo; use env vars (`CLEARVIEW_DB`, `CLEARVIEW_ONTOLOGY`, `NEXT_PUBLIC_API`).
