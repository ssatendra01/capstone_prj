# Constitution – Clearview Agentic Complaints Management

Governing principles. Every spec, plan, task and line of code must comply.

1. **Specification first.** No code is written until the relevant contract in `specs/` is approved.
   Chain: `constitution.md → specs/COMPLAINTS-01/spec.md → plan.md → tasks.md → code`.
2. **Grounded, never guessed.** Every agent decision (intent, vulnerability, rule, redress band,
   authority limit) is derived from the Context Studio knowledge graph (`context-studio/ontology.jsonld`)
   or from data returned by an MCP tool. Agents must cite the node `@id` / table row they relied on.
3. **Vulnerable customers are a hard stop.** A vulnerable flag from *any* source (text, CRM, age)
   forces human review, priority P1 and a visible guardrail alert. This can never be overridden by confidence.
4. **Humans own money and rejections.** Redress > £150, legal threats, data/privacy complaints,
   confidence < 0.90 and every *rejection* require human approval. Only upheld / partially-upheld
   cases with redress ≤ £150 may be straight-through-processed (STP).
5. **Delegated authority is enforced server-side.** Analyst £50, Lead £250, Manager £1,000.
   Overriding AI redress requires a written justification.
6. **Everything is auditable.** Every agent step, MCP tool call and human decision writes an
   append-only, hash-chained audit record. The chain must be verifiable.
7. **Least privilege tools.** The query tool executes only allow-listed, parameterised, read-only queries.
   No agent can run free-form SQL.
8. **Deterministic by default, LLM-pluggable.** Agents run offline with rule-based logic over the graph so the
   system is testable (300-case ground truth). LLM calls (e.g. ICA agents) may enhance, never bypass, the guardrails above.
9. **Customer voice.** Letters are empathic, legally precise, non-defensive, and always state Financial
   Ombudsman Service (FOS) referral rights.
10. **No secrets in the repo.** Configuration via environment variables only.
