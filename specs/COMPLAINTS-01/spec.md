# COMPLAINTS-01 – Agentic Complaints Management (Feature Specification)

## 1. Why
Clearview Retail Bank receives 50,000+ complaints/month, handled manually: 7–10 day average
resolution, 40 % first-triage mis-routing, 60 %+ analyst time spent gathering evidence, £48/case,
~14 % vulnerable customers not consistently identified, and £12M FCA fine exposure in 2026.

## 2. What (outcomes)
| # | Target | Measure |
|---|--------|---------|
| O1 | End-to-end agent processing < 2 min / complaint | `agent_runs` latency sum |
| O2 | Triage accuracy (intent) ≥ 90 % on 300-case ground truth | `backend/evaluate.py` |
| O3 | 100 % of vulnerable customers flagged and human-reviewed | recall = 1.0 on ground truth |
| O4 | 100 % of cases requiring HITL are routed to HITL | HITL recall = 1.0 |
| O5 | Every decision carries a rule citation, evidence references and audit trail | audit chain verifies |
| O6 | 30–50 % cycle-time reduction, 2× cost saving | STP rate KPI, avg handling time |

## 3. User stories & acceptance criteria
**US-1 Intake.** As a complaints handler I submit a complaint (channel, customer, account, text) and it is stored with FCA deadlines (SRC = 3 business days, final response = 8 weeks).
- AC: `POST /api/complaints` returns id; `received_at`, `src_due`, `fca_deadline` set.

**US-2 Triage.** The Triage Agent extracts intent (6 intents), P1/P2/P3 priority and SLA, sentiment (-1..1), vulnerability flag (13 FCA markers + CRM flag + age ≥ 75), legal-threat flag, channel weighting.
- AC: JSON conforms to `specs/contracts/schemas/triage_output.schema.json`; vulnerable ⇒ P1.

**US-3 Evidence.** The Evidence Agent gathers 90-day transactions, card disputes, call transcripts, CRM history and prior complaints through `secure-query-executor`, and derives intent-specific findings.
- AC: output lists each source with row counts and `completeness` 0..1; no free-form SQL.

**US-4 Policy.** The Policy Agent maps findings to FCA DISP / bank policy nodes (via `context-broker-hybrid-query`), adjudicates liability (uphold / partial_uphold / reject), calculates redress (refund + compensation band) and checks delegated authority.
- AC: every outcome cites ≥1 ontology `@id`; redress ≤ evidence-justified refund + band amount.

**US-5 Draft.** The Draft Agent writes the customer letter, packages redress, decides STP eligibility and dispatch trigger, and writes the audit summary.
- AC: letter includes outcome, redress, FOS rights; STP only if confidence ≥ 0.90, redress ≤ £150, outcome ≠ reject, not vulnerable, no legal threat, intent ≠ DATA_PRIVACY.

**US-6 Monitoring Workbench.** A supervisor sees live KPIs, filters complaints, inspects agent steps (latency, confidence), audit trail, and reviews cases.
- AC: approve / request re-triage / escalate; override redress with justification; edit letter; role-based authority; guardrail banners for vulnerable, legal threat, FCA deadline < 48 h.

**US-7 Audit.** Every agent step, tool call and decision is appended to a hash-chained log.
- AC: `GET /api/audit/verify` returns `valid: true`; tampering is detected.

## 4. Escalation rules
- Vulnerable ⇒ hard stop → human review, P1.
- Redress > £150 ⇒ mandatory HITL. Legal threat ⇒ HITL. DATA_PRIVACY ⇒ HITL + DPO route.
- Authority: Analyst ≤ £50, Lead ≤ £250, Manager ≤ £1,000; above ⇒ must escalate.

## 5. Out of scope
Real T24/CAMS/Salesforce/Verint connectivity (simulated in the seeded database behind the same MCP contract); production auth/SSO; real email/SMS delivery (notification-service writes to an outbox).

## 6. Constraints
Constitution applies. Contracts in `specs/contracts/` are frozen before implementation. See `plan.md`.
