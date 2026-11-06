export const API = process.env.NEXT_PUBLIC_API ?? "http://localhost:8000";

export type Complaint = {
  id: string; channel: string; received_at: string; fca_deadline: string; status: string; intent: string | null;
  priority: "P1" | "P2" | "P3" | null; sentiment: number | null; vulnerable: boolean | null; legal_threat: boolean | null;
  outcome: string | null; redress_total: number | null; confidence: number | null; stp_eligible: boolean | null;
  hitl_reasons: string[]; total_latency_ms: number | null; customer_name: string; hours_to_deadline: number | null;
};
export type Kpis = {
  total: number; active_cases: number; in_flight: number; pending_review: number; p1_breach_risk: number; vulnerable_open: number;
  avg_redress: number; stp_rate: number; avg_pipeline_ms: number; by_status: { status: string; n: number }[];
};
export type AgentRun = {
  id: number; run_no: number; agent: string; status: string; latency_ms: number; confidence: number | null;
  error: string | null; output: Record<string, any> | null;
};
export type Detail = {
  complaint: Complaint & Record<string, any>;
  customer: { id: string; name: string; email: string; tier: string; date_of_birth: string; vulnerability_flag: number };
  agent_runs: AgentRun[];
  tool_calls: { id: number; run_no: number; agent: string; tool: string; summary: string; latency_ms: number; called_at: string }[];
  audit: { seq: number; ts: string; actor: string; event_type: string; payload: Record<string, any>; hash: string }[];
};

export class ApiError extends Error {
  constructor(public status: number, message: string) { super(message); }
}

export async function api<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API}${path}`, { ...init, cache: "no-store",
    headers: { "Content-Type": "application/json", ...(init?.headers ?? {}) } });
  if (!res.ok) {
    let msg = res.statusText;
    try { const j = await res.json(); msg = typeof j.detail === "string" ? j.detail : JSON.stringify(j.detail); } catch { /* keep statusText */ }
    throw new ApiError(res.status, msg);
  }
  return res.json() as Promise<T>;
}

export const STATUS_LABEL: Record<string, string> = {
  RECEIVED: "Received", IN_FLIGHT: "In flight", PENDING_REVIEW: "Pending review", RESOLVED_STP: "Resolved (STP)",
  RESOLVED_HUMAN: "Resolved (human)", ESCALATED: "Escalated", ERROR_HITL: "Error - review",
};
export const INTENT_LABEL: Record<string, string> = {
  DUPLICATE_CHARGE: "Duplicate charge / fee", ATM_PAYMENT_FAILURE: "ATM / payment failure", UNAUTHORISED_TXN: "Unauthorised transaction",
  MORTGAGE_LOAN_DISPUTE: "Mortgage / loan dispute", ACCOUNT_CLOSURE: "Account closure", DATA_PRIVACY: "Data & privacy", OTHER: "Other",
};
export const gbp = (n: number | null | undefined) => n == null ? "-" : `£${n.toLocaleString("en-GB", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
export const sentimentBucket = (s: number | null) => s == null ? "-" : s < -0.2 ? "Negative" : s > 0.2 ? "Positive" : "Neutral";
