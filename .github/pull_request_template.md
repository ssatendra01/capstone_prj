## Summary
Agentic Complaints Management for Clearview Retail Bank (COMPLAINTS-01): 4-agent swarm (Triage, Evidence, Policy, Draft), 4 MCP tools, Context Studio ontology, Process Studio design, Next.js 15 Monitoring Workbench.

## SDD artefacts
- [ ] constitution.md, specs/COMPLAINTS-01/{spec,plan,tasks}.md
- [ ] specs/contracts: 5 schemas, 4 prompt contracts, mcp_tools.md, evaluation_matrix.md
- [ ] context-studio/ontology.jsonld, process-studio/process_design.md

## Verification
- [ ] `python -m pytest -q` (10 passed)
- [ ] `python -m clearview.evaluate` (300 cases, passed)
- [ ] `npm run typecheck && npm run build` in frontend/

## Known limitations
SQLite runtime (Postgres schema provided), no auth, simulated T24/CAMS/Salesforce/Verint. See README.