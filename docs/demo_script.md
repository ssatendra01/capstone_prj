# Demo Video Script (10–15 min) – Clearview Agentic Complaints Management

Reviewers assess **how** you used AI tools. Narrate decisions. Target runtime ≈ 14 min. Keep your face visible (picture-in-picture), 1080p, MP4.

## Before recording (checklist)
```powershell
cd backend
python -m clearview.seed --reset                 # fresh 300 complaints, none processed
uvicorn clearview.api:app --port 8000            # terminal 1
cd ../frontend; npm.cmd run dev                  # terminal 2  -> http://localhost:3000
```
Open in tabs: Workbench • `specs/COMPLAINTS-01/spec.md` • `specs/contracts/prompts/triage_agent.md` • `context-studio/ontology.jsonld` • `process-studio/process_design.md` • IBM Bob chat • ICA (Context Studio, Process Studio, Agentic Studio).
Do **not** click "Run agents on next 25" until section 5 (the table must be empty to show the pipeline live).

## Timeline
| # | Time | Section | What to show | What to say (key points) |
|---|------|---------|--------------|--------------------------|
| 1 | 0:00–1:00 | Business context | Slide 3 or README header | 50,000+ complaints/month, 7–10 day resolution, 40 % mis-routing, £48/case, 14 % vulnerable, £12M FCA fine exposure. Goal: <2 min agent time, 100 % vulnerable recall, 2× cost saving. |
| 2 | 1:00–3:00 | Context Studio (3 hybrid queries) | ICA Context Studio with the ontology imported; fallback: Workbench **Context Studio query** button | Grounding removes hallucination: agents may only cite `cv:` ids. Run: (1) **"DISP 1.6 eight week final response deadline"** → `cv:Rule/DISP-1.6`; (2) **"vulnerable customer hard stop human review"** → `cv:Rule/VULNERABLE-POLICY`; (3) **"redress scale moderate compensation"** → `cv:Redress/MODERATE` (£200). Point out graph neighbours (rule → intent → team). |
| 3 | 3:00–5:00 | Process Studio & spec | `process-studio/process_design.md` + the ICA-generated implementation spec | As-Is: 7–10 d, 40 % mis-routing, 60 % time on evidence. To-Be: 4 agents, STP criteria, escalation rules (vulnerable hard stop, redress > £150 HITL, authority £50/£250/£1,000). Show handshake JSON. Mention keywords used: *analyse using procedure eater*, *create blueprint*, *create implementation specifications*. |
| 4 | 5:00–8:00 | SDD contracts + IBM Bob | `constitution.md` → `spec.md` → `plan.md` → `tasks.md`; one JSON schema; one prompt contract (ROLE/BOUNDARY/TASK/GUARDRAILS/OUTPUT/Examples); `mcp_tools.md`; `.bob/mcp.json` | "Contracts were frozen before code." Show the schema invariants (vulnerable ⇒ P1; STP ⇒ no HITL reasons). In **Bob**: attach spec + MCP and run a synthesis prompt, e.g. *"Using the attached spec, add a `/api/…` endpoint / extend the Draft agent per draft_agent.md"*. In **ICA Agentic Studio**: New Agent → pick tools from the MCP catalogue (`agents/ica/agents.yaml`). Say what you'd verify after generation (tests, schema validation). |
| 5 | 8:00–11:00 | Live pipeline on 5 complaints | Workbench: **New complaint** x5 (texts below), or batch-run then open each | Show for each: Agent monitor tab (latency, confidence, MCP calls), citations, outcome. Run `python -m clearview.evaluate` for 10 s to show 300-case results (100 % vulnerable & HITL recall). |
| 6 | 11:00–14:00 | Workbench HITL + reflection | Review panel | Approve, escalate, vulnerable guardrail, authority block, override justification, audit verify. Reflection: what you would do differently (see end). |

## Five complaints for section 5 (vary intents)
Use **New complaint** with the customer/account ids shown (account id is `ACC-` + the customer number). The ids below come from the seeded data, so outcomes are reproducible. Alternatively select them from the table after **Run agents on next 25** (they are all in the first 100 ids, so use the search box).

| # | Seed id | Customer / account | Channel | Text (exact seed text) | Expected result |
|---|---------|--------------------|---------|-------------------------|-----------------|
| A | CMP-10009 | CUS-00009 / ACC-00009 | Branch | "I was charged a monthly fee of £5 twice on 16 October. Please refund the duplicate fee." | Duplicate charge, P3, **uphold £35.00** (refund £10 + £25), Analyst authority, **STP – auto-sent** (no human). Shows the happy path. |
| B | CMP-10030 | CUS-00030 / ACC-00030 | Email | "My account shows a double charge. The same fee of £12 came out two times and I want it put right." | **Vulnerable** (hard stop): the text has no vulnerability words; the flag comes from the customer's date of birth in the CRM KYC record (born 1946, so age 80, marker `cv:Vulnerability/AGE`; show `vulnerability_markers` in the Triage JSON). P1, red banner, `VULNERABLE_CUSTOMER`, redress £37 (£12 + £25), HITL even though the amount is small. **Guardrail demo.** |
| C | CMP-10020 | CUS-00020 / ACC-00020 | Call Centre | "There are transactions on my card that I did not make. Please investigate this fraud. I am upset about this." | Unauthorised txn, P1, **uphold £688.50** (refund £488.50 + £200), Manager authority, `REDRESS_OVER_150` → HITL. **Authority block demo** (Analyst blocked, Manager approves). |
| D | CMP-10005 | CUS-00005 / ACC-00005 | Email | "You have taken a wrong fee from my current account … I will be contacting my solicitor if you do not respond." | **Legal threat** → P1, `LEGAL_THREAT` → HITL. Use for **Escalate to Investigations**. |
| E | CMP-10014 | CUS-00014 / ACC-00014 | Branch | "I am querying an amount of £395 taken on my mortgage account for early repayment. I believe it was not due. I am upset about this." | Mortgage dispute, **reject £0** (valid early-repayment charge), `REJECTION_REQUIRES_APPROVAL` → HITL. Shows the agent does not just say yes. Use for **Request re-triage**. |

> The seeded complaints already exist (status RECEIVED). Easiest flow: search `CMP-10009` in the table, then use **Run agents on next 25 unprocessed** once, or `POST /api/complaints/{id}/process` in Swagger (`/docs`) to run exactly one case on camera. Using **New complaint** with the same text creates a new id (CMP-10301+). Case B only reproduces if you also use customer CUS-00030, because the flag is derived from that customer's date of birth.

## Section 6 – HITL walk-through (≈3 min)
1. **Vulnerable (B)**: open → red banner → Agent monitor shows triage markers → Review tab: approve as Analyst (£37 ≤ £50 so allowed) with a note offering tailored support → Approve & dispatch.
2. **Authority (C)**: Role = Analyst → Approve → *blocked: exceeds Analyst authority £50*. Switch to Manager → approve. Change redress to £600 without a note → button disabled until justification entered → approve with note.
3. **Escalate (D)**: Escalate to Investigations → status "Escalated".
4. **Re-triage (E)**: Request agent re-triage → run 2 appears in the Agent monitor.
5. **Audit**: open Audit trail tab → show every agent step + human decision with hashes; show header "audit chain: verified". Optional: Swagger `GET /api/audit/verify` → `valid: true`.

## Reflection – "what would I do differently" (talking points)
- Replace the rule-based agents with ICA LLM agents behind the same schemas and re-run the 300-case gate; keep guardrails in code, not prompts.
- Swap SQLite for PostgreSQL and add real SSO/RBAC (roles come from the login, not a form).
- Evaluate on real anonymised cases; the synthetic 100 % shows internal consistency only.
- Calibrate confidence (it is currently heuristic) and add drift monitoring.

## Rubric mapping
| Criterion (weight) | Evidence in the video |
|--------------------|-----------------------|
| Context Studio 20 % | Section 2 – ontology + 3 hybrid queries |
| Process Studio 20 % | Section 3 – As-Is/To-Be, STP, escalation, handshakes |
| SDD rigor 25 % | Section 4 – constitution → spec → plan → tasks, 5 schemas, 4 prompt contracts, 4 MCP specs, evaluation matrix |
| Implementation 20 % | Sections 5–6 – pipeline, MCP logs, audit trail, 300 seeded complaints, Next.js workbench |
| Demo quality 15 % | Narrated decisions, face visible, ≤ 15 min |
