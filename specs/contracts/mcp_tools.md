# MCP Tool Interface Specifications (x4)

Server: `clearview-complaints-tools` (stdio, `python -m clearview.mcp_server`, registered in `.bob/mcp.json`).

## 1. `secure-query-executor`
Allow-listed, parameterised, read-only data access (T24 / CAMS / Salesforce / Verint / Postgres).
| Field | Type | Notes |
|-------|------|-------|
| `query_name` | string, required | one of `customer_profile`, `account_summary`, `account_transactions`, `card_disputes`, `call_transcripts`, `crm_cases`, `prior_complaints` |
| `params` | object, required | `customer_id`, `account_id`, `from_ts`, `to_ts`, `exclude_id` as required by the query |
| `complaint_id` | string, optional | for tool-call logging |

Returns `{query,row_count,rows[],source}`. Error: unknown name (including any SQL text) or missing parameter => tool error. No writes possible.

## 2. `context-broker-hybrid-query`
Vector (TF-IDF cosine) + one-hop graph expansion over `context-studio/ontology.jsonld`.
| Field | Type | Notes |
|-------|------|-------|
| `query` | string, required | natural language |
| `node_types` | string[], optional | e.g. `Intent`, `RegulatoryRule`, `PolicyRule`, `RedressBand`, `AuthorityLevel`, `VulnerabilityMarker`, `Precedent` |
| `top_k` | int, default 5 | |

Returns `{query,hits[{id,type,name,description,score,neighbours[]}],graph_context[]}`.

## 3. `notification-service`
| Field | Type | Notes |
|-------|------|-------|
| `channel` | `EMAIL`\|`SMS`\|`PUSH` | else tool error |
| `recipient`, `subject`, `body` | string | |
| `complaint_id` | string, optional | |

Queues a row in `outbox` (no real delivery). Returns `{notification_id,status:"QUEUED"}`. Only invoked for STP cases or after human approval.

## 4. `audit-logger`
| Field | Type | Notes |
|-------|------|-------|
| `actor` | string | agent or user id |
| `event_type` | string | e.g. `AGENT_OK`, `HUMAN_APPROVED` |
| `payload` | object | JSON evidence/decision |
| `complaint_id` | string, optional | |

Appends to a SHA-256 hash-chained ledger; returns `{seq,hash,prev_hash,ts,chain}`. `GET /api/audit/verify` re-validates the chain.
