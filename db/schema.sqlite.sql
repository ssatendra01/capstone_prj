-- Clearview complaints management – SQLite schema (runtime default).
-- A PostgreSQL 15 equivalent for production lives in db/schema.postgres.sql.

CREATE TABLE IF NOT EXISTS customers (
  id TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  email TEXT NOT NULL,
  tier TEXT NOT NULL CHECK (tier IN ('Standard','Premier','Wealth','SME')),
  date_of_birth TEXT NOT NULL,
  vulnerability_flag INTEGER NOT NULL DEFAULT 0,   -- Salesforce FSC CRM marker
  vulnerability_note TEXT
);

CREATE TABLE IF NOT EXISTS accounts (
  id TEXT PRIMARY KEY,
  customer_id TEXT NOT NULL REFERENCES customers(id),
  product TEXT NOT NULL,                            -- Current Account / Credit Card / Mortgage ...
  balance REAL NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_accounts_customer ON accounts(customer_id);

CREATE TABLE IF NOT EXISTS transactions (            -- Temenos T24 simulation
  id TEXT PRIMARY KEY,
  account_id TEXT NOT NULL REFERENCES accounts(id),
  posted_at TEXT NOT NULL,
  type TEXT NOT NULL,                               -- CARD_PURCHASE ATM_WITHDRAWAL FEE DIRECT_DEBIT TRANSFER CREDIT MORTGAGE_PAYMENT
  amount REAL NOT NULL,
  merchant TEXT,
  status TEXT NOT NULL DEFAULT 'POSTED',
  fee_valid INTEGER,                                -- NULL for non-fee rows
  fee_reason TEXT,
  related_tx_id TEXT
);
CREATE INDEX IF NOT EXISTS idx_tx_account_date ON transactions(account_id, posted_at);

CREATE TABLE IF NOT EXISTS card_disputes (           -- FIS CAMS simulation
  id TEXT PRIMARY KEY,
  account_id TEXT NOT NULL REFERENCES accounts(id),
  tx_id TEXT NOT NULL REFERENCES transactions(id),
  amount_disputed REAL NOT NULL,
  atm_dispensed REAL,
  fraud_score REAL NOT NULL DEFAULT 0,
  cardholder_present INTEGER NOT NULL DEFAULT 1,
  merchant_risk TEXT NOT NULL DEFAULT 'LOW',
  status TEXT NOT NULL DEFAULT 'OPEN'
);
CREATE INDEX IF NOT EXISTS idx_disputes_account ON card_disputes(account_id);

CREATE TABLE IF NOT EXISTS call_transcripts (        -- Verint IVR simulation
  id TEXT PRIMARY KEY,
  customer_id TEXT NOT NULL REFERENCES customers(id),
  call_at TEXT NOT NULL,
  text TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_calls_customer ON call_transcripts(customer_id);

CREATE TABLE IF NOT EXISTS crm_cases (               -- Salesforce FSC simulation
  id TEXT PRIMARY KEY,
  customer_id TEXT NOT NULL REFERENCES customers(id),
  case_type TEXT NOT NULL,                          -- CLOSURE_REQUEST DSAR SERVICE_REQUEST
  opened_at TEXT NOT NULL,
  closed_at TEXT,
  summary TEXT
);
CREATE INDEX IF NOT EXISTS idx_crm_customer ON crm_cases(customer_id);

CREATE TABLE IF NOT EXISTS complaints (
  id TEXT PRIMARY KEY,
  customer_id TEXT NOT NULL REFERENCES customers(id),
  account_id TEXT NOT NULL REFERENCES accounts(id),
  channel TEXT NOT NULL,
  text TEXT NOT NULL,
  received_at TEXT NOT NULL,
  src_due TEXT NOT NULL,
  fca_deadline TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'RECEIVED',
  -- triage
  intent TEXT, priority TEXT, sla_due TEXT, sentiment REAL,
  vulnerable INTEGER NOT NULL DEFAULT 0, legal_threat INTEGER NOT NULL DEFAULT 0, route_team TEXT,
  -- policy / draft
  outcome TEXT, refund_amount REAL, compensation_amount REAL, redress_total REAL,
  authority_required TEXT, confidence REAL, stp_eligible INTEGER,
  hitl_reasons TEXT, letter TEXT, letter_type TEXT,
  total_latency_ms INTEGER, retriage_count INTEGER NOT NULL DEFAULT 0, processed_at TEXT,
  -- human decision
  final_redress REAL, decided_by TEXT, decided_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_complaints_status ON complaints(status);
CREATE INDEX IF NOT EXISTS idx_complaints_priority ON complaints(priority);
CREATE INDEX IF NOT EXISTS idx_complaints_channel ON complaints(channel);
CREATE INDEX IF NOT EXISTS idx_complaints_received ON complaints(received_at);

CREATE TABLE IF NOT EXISTS agent_runs (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  complaint_id TEXT NOT NULL REFERENCES complaints(id),
  run_no INTEGER NOT NULL,
  agent TEXT NOT NULL,
  status TEXT NOT NULL,
  started_at TEXT NOT NULL,
  latency_ms INTEGER NOT NULL,
  confidence REAL,
  input_json TEXT,
  output_json TEXT,
  error TEXT
);
CREATE INDEX IF NOT EXISTS idx_runs_complaint ON agent_runs(complaint_id);

CREATE TABLE IF NOT EXISTS tool_calls (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  complaint_id TEXT,
  run_no INTEGER,
  agent TEXT,
  tool TEXT NOT NULL,
  args_json TEXT,
  summary TEXT,
  latency_ms INTEGER,
  called_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_tool_complaint ON tool_calls(complaint_id);

CREATE TABLE IF NOT EXISTS audit_log (               -- append-only, hash chained
  seq INTEGER PRIMARY KEY AUTOINCREMENT,
  ts TEXT NOT NULL,
  complaint_id TEXT,
  actor TEXT NOT NULL,
  event_type TEXT NOT NULL,
  payload TEXT NOT NULL,
  prev_hash TEXT NOT NULL,
  hash TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_audit_complaint ON audit_log(complaint_id);

CREATE TABLE IF NOT EXISTS outbox (                  -- notification-service
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  complaint_id TEXT,
  channel TEXT NOT NULL,
  recipient TEXT NOT NULL,
  subject TEXT NOT NULL,
  body TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'QUEUED',
  created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS ground_truth (            -- 300-case evaluation labels
  complaint_id TEXT PRIMARY KEY REFERENCES complaints(id),
  intent TEXT NOT NULL,
  vulnerable INTEGER NOT NULL,
  legal_threat INTEGER NOT NULL,
  priority TEXT NOT NULL,
  outcome TEXT NOT NULL,
  redress_total REAL NOT NULL,
  hitl_required INTEGER NOT NULL
);
