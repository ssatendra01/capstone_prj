# Clearview – Agentic Complaints Management

Capstone implementation for Clearview Retail Bank: a 4-agent swarm (**Triage → Evidence → Policy → Draft**) grounded in a Context Studio knowledge graph, exposed through 4 MCP tools, with a Next.js 15 / Carbon **Monitoring Workbench** for human-in-the-loop governance. Built spec-first (see `constitution.md`, `specs/`).

## What is where
| Capstone deliverable | Location |
|----------------------|----------|
| 1. Context Studio ontology (JSON-LD, 66 nodes) | `context-studio/ontology.jsonld` (3 hybrid-query checks in `backend/tests`) |
| 2. Process Studio documentation | `process-studio/process_design.md` |
| 3. SDD: spec → plan → tasks, 5 JSON schemas, 4 prompt contracts, 4 MCP tool specs, 300-case evaluation matrix | `specs/COMPLAINTS-01/`, `specs/contracts/` |
| 4. Implementation: agents, MCP server, API, DB, Workbench | `backend/`, `db/`, `frontend/`, `.bob/mcp.json`, `agents/ica/` |
| 5. Governing docs for coding agents | `constitution.md`, `AGENTS.md` |

## Run it
```powershell
# backend (Python 3.11+)
cd backend
pip install -r requirements.txt
python -m clearview.seed --reset          # 300 synthetic complaints + ground truth (SQLite)
python -m clearview.evaluate              # quality gate
python -m pytest -q                       # 10 tests
uvicorn clearview.api:app --port 8000

# frontend (Node 20+)
cd ../frontend
npm install
npm run dev                               # http://localhost:3000   (NEXT_PUBLIC_API defaults to http://localhost:8000)
```
In the Workbench click **Run agents on next 25 unprocessed** (or **New complaint**), then select a row to review.
Docker: `docker compose up --build` (backend seeds SQLite on start; `db/schema.postgres.sql` is the PostgreSQL 15 equivalent, loaded into the `db` service).

## Using it from IBM Bob / ICA
- `.bob/mcp.json` registers `clearview-complaints-tools` (stdio): `secure-query-executor`, `context-broker-hybrid-query`, `notification-service`, `audit-logger`.
- `agents/ica/agents.yaml` describes the 4 ICA Agentic Studio agents that mirror `specs/contracts/prompts/*.md`; export them as MCP endpoints / Agent Cards.
- Import `context-studio/ontology.jsonld` into Context Studio (ICA › Context Studio Schema Builder can be used to extend it). The local `graph.py` implements the same hybrid query contract so everything runs offline.
- Process Studio keywords from the briefing (`analyse using procedure eater`, `create blueprint`, `create implementation specifications`) must be run in the ICA tenant; `process-studio/process_design.md` is the design to compare against.

## Guarantees (enforced in code and tested)
- Vulnerable customer ⇒ P1 + mandatory human review (text, CRM flag or age ≥ 75). Recall 100 % on 300-case ground truth.
- Redress > £150, legal threat, DATA_PRIVACY, rejections, confidence < 0.90 ⇒ human review. Only the rest are STP.
- Delegated authority Analyst £50 / Lead £250 / Manager £1,000 enforced by the API; overrides need a justification.
- Agents can only run allow-listed named queries; every handshake is JSON-schema validated; any failure ⇒ `ERROR_HITL`.
- SHA-256 hash-chained audit log, verifiable at `GET /api/audit/verify`.

## Latest evaluation (300 cases)
Intent / priority / outcome / redress accuracy 100 %, vulnerable recall 100 % (0 false positives), HITL recall 100 %, STP rate ≈ 34 %, avg pipeline ≈ 30 ms.
The cases are synthetic and the agents are rule-based over the ontology, so these figures show internal consistency, not production accuracy; real LLM agents would need re-evaluation with `evaluate.py`.

## Known limitations
- T24 / CAMS / Salesforce / Verint are simulated in one database behind the real MCP contract; email/SMS go to an outbox table.
- No authentication: reviewer identity and role are supplied by the caller (SSO/RBAC is out of scope; authority limits are still enforced).
- SQLite is the runtime store; the PostgreSQL schema is provided but the Python data layer is not yet switched to a Postgres driver.
- Demo video, IBM GitHub push and the ICA/Context Studio/Process Studio tenant steps must be done by you.
