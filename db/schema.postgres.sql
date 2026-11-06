-- PostgreSQL 15 schema (production equivalent of schema.sqlite.sql). Apply: psql -f db/schema.postgres.sql

CREATE TABLE IF NOT EXISTS customers (
  id TEXT PRIMARY KEY, name TEXT NOT NULL, email TEXT NOT NULL,
  tier TEXT NOT NULL CHECK (tier IN ('Standard','Premier','Wealth','SME')),
  date_of_birth DATE NOT NULL, vulnerability_flag BOOLEAN NOT NULL DEFAULT FALSE, vulnerability_note TEXT);

CREATE TABLE IF NOT EXISTS accounts (
  id TEXT PRIMARY KEY, customer_id TEXT NOT NULL REFERENCES customers(id), product TEXT NOT NULL, balance NUMERIC(14,2) NOT NULL DEFAULT 0);
CREATE INDEX IF NOT EXISTS idx_accounts_customer ON accounts(customer_id);

CREATE TABLE IF NOT EXISTS transactions (
  id TEXT PRIMARY KEY, account_id TEXT NOT NULL REFERENCES accounts(id), posted_at TIMESTAMPTZ NOT NULL, type TEXT NOT NULL,
  amount NUMERIC(14,2) NOT NULL, merchant TEXT, status TEXT NOT NULL DEFAULT 'POSTED', fee_valid BOOLEAN, fee_reason TEXT, related_tx_id TEXT);
CREATE INDEX IF NOT EXISTS idx_tx_account_date ON transactions(account_id, posted_at);

CREATE TABLE IF NOT EXISTS card_disputes (
  id TEXT PRIMARY KEY, account_id TEXT NOT NULL REFERENCES accounts(id), tx_id TEXT NOT NULL REFERENCES transactions(id),
  amount_disputed NUMERIC(14,2) NOT NULL, atm_dispensed NUMERIC(14,2), fraud_score NUMERIC(4,2) NOT NULL DEFAULT 0,
  cardholder_present BOOLEAN NOT NULL DEFAULT TRUE, merchant_risk TEXT NOT NULL DEFAULT 'LOW', status TEXT NOT NULL DEFAULT 'OPEN');
CREATE INDEX IF NOT EXISTS idx_disputes_account ON card_disputes(account_id);

CREATE TABLE IF NOT EXISTS call_transcripts (
  id TEXT PRIMARY KEY, customer_id TEXT NOT NULL REFERENCES customers(id), call_at TIMESTAMPTZ NOT NULL, text TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS idx_calls_customer ON call_transcripts(customer_id);

CREATE TABLE IF NOT EXISTS crm_cases (
  id TEXT PRIMARY KEY, customer_id TEXT NOT NULL REFERENCES customers(id), case_type TEXT NOT NULL,
  opened_at TIMESTAMPTZ NOT NULL, closed_at TIMESTAMPTZ, summary TEXT);
CREATE INDEX IF NOT EXISTS idx_crm_customer ON crm_cases(customer_id);

CREATE TABLE IF NOT EXISTS complaints (
  id TEXT PRIMARY KEY, customer_id TEXT NOT NULL REFERENCES customers(id), account_id TEXT NOT NULL REFERENCES accounts(id),
  channel TEXT NOT NULL, text TEXT NOT NULL, received_at TIMESTAMPTZ NOT NULL, src_due TIMESTAMPTZ NOT NULL, fca_deadline TIMESTAMPTZ NOT NULL,
  status TEXT NOT NULL DEFAULT 'RECEIVED',
  intent TEXT, priority TEXT, sla_due TIMESTAMPTZ, sentiment NUMERIC(4,2), vulnerable BOOLEAN NOT NULL DEFAULT FALSE,
  legal_threat BOOLEAN NOT NULL DEFAULT FALSE, route_team TEXT,
  outcome TEXT, refund_amount NUMERIC(14,2), compensation_amount NUMERIC(14,2), redress_total NUMERIC(14,2), authority_required TEXT,
  confidence NUMERIC(4,2), stp_eligible BOOLEAN, hitl_reasons JSONB, letter TEXT, letter_type TEXT,
  total_latency_ms INTEGER, retriage_count INTEGER NOT NULL DEFAULT 0, processed_at TIMESTAMPTZ,
  final_redress NUMERIC(14,2), decided_by TEXT, decided_at TIMESTAMPTZ);
CREATE INDEX IF NOT EXISTS idx_complaints_status ON complaints(status);
CREATE INDEX IF NOT EXISTS idx_complaints_priority ON complaints(priority);
CREATE INDEX IF NOT EXISTS idx_complaints_channel ON complaints(channel);
CREATE INDEX IF NOT EXISTS idx_complaints_received ON complaints(received_at);

CREATE TABLE IF NOT EXISTS agent_runs (
  id BIGSERIAL PRIMARY KEY, complaint_id TEXT NOT NULL REFERENCES complaints(id), run_no INTEGER NOT NULL, agent TEXT NOT NULL,
  status TEXT NOT NULL, started_at TIMESTAMPTZ NOT NULL, latency_ms INTEGER NOT NULL, confidence NUMERIC(4,2),
  input_json JSONB, output_json JSONB, error TEXT);
CREATE INDEX IF NOT EXISTS idx_runs_complaint ON agent_runs(complaint_id);

CREATE TABLE IF NOT EXISTS tool_calls (
  id BIGSERIAL PRIMARY KEY, complaint_id TEXT, run_no INTEGER, agent TEXT, tool TEXT NOT NULL, args_json JSONB, summary TEXT,
  latency_ms INTEGER, called_at TIMESTAMPTZ NOT NULL);
CREATE INDEX IF NOT EXISTS idx_tool_complaint ON tool_calls(complaint_id);

CREATE TABLE IF NOT EXISTS audit_log (
  seq BIGSERIAL PRIMARY KEY, ts TIMESTAMPTZ NOT NULL, complaint_id TEXT, actor TEXT NOT NULL, event_type TEXT NOT NULL,
  payload JSONB NOT NULL, prev_hash TEXT NOT NULL, hash TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS idx_audit_complaint ON audit_log(complaint_id);
-- append-only: block UPDATE / DELETE
CREATE OR REPLACE FUNCTION audit_immutable() RETURNS trigger AS $$ BEGIN RAISE EXCEPTION 'audit_log is append-only'; END; $$ LANGUAGE plpgsql;
DROP TRIGGER IF EXISTS audit_no_change ON audit_log;
CREATE TRIGGER audit_no_change BEFORE UPDATE OR DELETE ON audit_log FOR EACH ROW EXECUTE FUNCTION audit_immutable();

CREATE TABLE IF NOT EXISTS outbox (
  id BIGSERIAL PRIMARY KEY, complaint_id TEXT, channel TEXT NOT NULL, recipient TEXT NOT NULL, subject TEXT NOT NULL, body TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'QUEUED', created_at TIMESTAMPTZ NOT NULL);

CREATE TABLE IF NOT EXISTS ground_truth (
  complaint_id TEXT PRIMARY KEY REFERENCES complaints(id), intent TEXT NOT NULL, vulnerable BOOLEAN NOT NULL, legal_threat BOOLEAN NOT NULL,
  priority TEXT NOT NULL, outcome TEXT NOT NULL, redress_total NUMERIC(14,2) NOT NULL, hitl_required BOOLEAN NOT NULL);
