"use client";
import { useState } from "react";
import { Button, InlineNotification, NumberInput, Select, SelectItem, Tab, TabList, TabPanel, TabPanels, Tabs, Tag, TextArea, TextInput } from "@carbon/react";
import { Detail, api, gbp, ApiError } from "@/lib/api";
import { PriorityTag, StatusTag, intentLabel } from "./tags";

const REASON_LABEL: Record<string, string> = {
  VULNERABLE_CUSTOMER: "Vulnerable customer", LEGAL_THREAT: "Legal threat", FCA_DEADLINE_RISK: "FCA deadline < 48h",
  REDRESS_OVER_150: "Redress > £150", DATA_PRIVACY_DPO_REVIEW: "Data privacy - DPO review", UNKNOWN_INTENT: "Unknown intent",
  REJECTION_REQUIRES_APPROVAL: "Rejection needs approval", LOW_CONFIDENCE: "Confidence < 90%", PIPELINE_ERROR: "Pipeline error",
};
const LIMIT: Record<string, number> = { ANALYST: 50, LEAD: 250, MANAGER: 1000 };

function Guardrails({ d }: { d: Detail }) {
  const c = d.complaint;
  const out = [];
  if (c.vulnerable) out.push(<InlineNotification key="v" kind="error" lowContrast hideCloseButton title="Vulnerable customer detected"
    subtitle="Hard stop: priority P1 and mandatory human review. Offer tailored support." />);
  if (c.legal_threat) out.push(<InlineNotification key="l" kind="warning" lowContrast hideCloseButton title="Legal threat flag" subtitle="Customer mentions legal action or the Ombudsman." />);
  if (c.hours_to_deadline != null && c.hours_to_deadline < 48 && !String(c.status).startsWith("RESOLVED"))
    out.push(<InlineNotification key="d" kind="warning" lowContrast hideCloseButton title="FCA deadline in < 48h" subtitle={`${c.hours_to_deadline}h left to the 8-week final response deadline (DISP 1.6).`} />);
  return <>{out}</>;
}

function AgentMonitor({ d }: { d: Detail }) {
  const lastRun = Math.max(0, ...d.agent_runs.map((r) => r.run_no));
  const runs = d.agent_runs.filter((r) => r.run_no === lastRun);
  const [open, setOpen] = useState<string | null>(null);
  if (!runs.length) return <div className="empty">Not processed yet.</div>;
  return (
    <div>
      <div className="pipeline">
        {runs.map((r) => (
          <div key={r.id} className={`step ${r.status}`} onClick={() => setOpen(open === r.agent ? null : r.agent)} style={{ cursor: "pointer" }}>
            <h5>{r.agent}</h5>
            <small>{r.status} - {r.latency_ms} ms</small>
            <small>confidence {r.confidence != null ? `${Math.round(r.confidence * 100)}%` : "-"}</small>
          </div>
        ))}
      </div>
      {open && <pre className="letter mono">{JSON.stringify(runs.find((r) => r.agent === open)?.output ?? { error: runs.find((r) => r.agent === open)?.error }, null, 2)}</pre>}
      <h6 style={{ marginTop: "1rem" }}>MCP tool calls (run {lastRun})</h6>
      <table className="mono" style={{ width: "100%", fontSize: ".75rem" }}>
        <tbody>
          {d.tool_calls.filter((t) => t.run_no === lastRun).map((t) => (
            <tr key={t.id}><td>{t.agent}</td><td>{t.tool}</td><td>{t.summary}</td><td>{t.latency_ms} ms</td></tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function ReviewPanel({ d, onDone }: { d: Detail; onDone: (msg: string) => void }) {
  const c = d.complaint;
  const [user, setUser] = useState("a.analyst");
  const [role, setRole] = useState("ANALYST");
  const [redress, setRedress] = useState<number>(c.redress_total ?? 0);
  const [note, setNote] = useState("");
  const [letter, setLetter] = useState<string>(c.letter ?? "");
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const awaiting = ["PENDING_REVIEW", "ERROR_HITL", "ESCALATED"].includes(c.status);
  const override = Math.abs(redress - (c.redress_total ?? 0)) > 0.004;

  async function act(action: "APPROVE" | "RETRIAGE" | "ESCALATE") {
    setBusy(true); setErr(null);
    try {
      await api(`/api/complaints/${c.id}/review`, { method: "POST", body: JSON.stringify({
        action, user, role, justification: note || null,
        ...(action === "APPROVE" ? { final_redress: redress, letter } : {}) }) });
      onDone(`${c.id}: ${action.toLowerCase()} recorded`);
    } catch (e) { setErr(e instanceof ApiError ? e.message : String(e)); } finally { setBusy(false); }
  }

  if (!c.outcome && c.status !== "ERROR_HITL") return <div className="empty">No AI recommendation yet. Process the complaint first.</div>;
  return (
    <div className="stack">
      <div>
        <h6>AI recommendation</h6>
        <Tag type={c.outcome === "reject" ? "red" : "green"}>{String(c.outcome ?? "n/a").replace("_", " ")}</Tag>{" "}
        <Tag type="blue">Confidence {c.confidence != null ? Math.round(c.confidence * 100) : "-"}%</Tag>{" "}
        <Tag type="gray">Redress {gbp(c.redress_total)}</Tag>{" "}
        <Tag type="cool-gray">{String(c.authority_required ?? "").replace("cv:Authority/", "")} authority</Tag>
        <p style={{ marginTop: ".5rem", fontSize: ".875rem" }}>
          {d.agent_runs.filter((r) => r.agent === "policy").slice(-1)[0]?.output?.reasoning}
        </p>
        <p className="mono">Rules: {(d.agent_runs.filter((r) => r.agent === "policy").slice(-1)[0]?.output?.rules_cited ?? []).join(", ")}</p>
        <div className="tags">{c.hitl_reasons.map((r: string) => <Tag key={r} size="sm" type="purple">{REASON_LABEL[r] ?? r}</Tag>)}</div>
      </div>
      {awaiting ? (
        <>
          <div style={{ display: "flex", gap: "1rem" }}>
            <TextInput id="user" labelText="Reviewer" size="sm" value={user} onChange={(e: any) => setUser(e.target.value)} />
            <Select id="role" labelText="Authority role" size="sm" value={role} onChange={(e: any) => setRole(e.target.value)}>
              {Object.entries(LIMIT).map(([r, l]) => <SelectItem key={r} value={r} text={`${r} (up to £${l})`} />)}
            </Select>
          </div>
          <NumberInput id="redress" label="Final redress (£) - accept AI value or override" min={0} step={5} size="sm" value={redress}
            onChange={(_e: any, { value }: any) => setRedress(Number(value) || 0)} />
          <TextArea id="note" labelText={override ? "Justification (mandatory - redress overridden)" : "Note / justification"} rows={2} value={note}
            invalid={override && !note.trim()} invalidText="Required when overriding AI redress" onChange={(e: any) => setNote(e.target.value)} />
          <TextArea id="letter" labelText="Customer letter (editable before dispatch)" rows={12} value={letter} onChange={(e: any) => setLetter(e.target.value)} />
          {err && <InlineNotification kind="error" lowContrast title="Action blocked" subtitle={err} onCloseButtonClick={() => setErr(null)} />}
          <div className="toolbar">
            <Button size="md" disabled={busy || (override && !note.trim())} onClick={() => act("APPROVE")}>Approve &amp; dispatch</Button>
            <Button size="md" kind="tertiary" disabled={busy} onClick={() => act("RETRIAGE")}>Request agent re-triage</Button>
            <Button size="md" kind="danger--tertiary" disabled={busy} onClick={() => act("ESCALATE")}>Escalate to Investigations</Button>
          </div>
        </>
      ) : (
        <>
          <div className="letter">{c.letter}</div>
          <p>Decision: <b>{c.status}</b>{c.decided_by ? ` by ${c.decided_by}` : ""}{c.final_redress != null ? ` - final redress ${gbp(c.final_redress)}` : ""}</p>
        </>
      )}
    </div>
  );
}

function AuditTrail({ d }: { d: Detail }) {
  return (
    <div>
      {d.audit.map((a) => (
        <div key={a.seq} className="audit-item">
          <b>#{a.seq}</b> {a.event_type} <Tag size="sm" type="gray">{a.actor}</Tag> <span className="mono">{a.ts}</span>
          <pre>{JSON.stringify(a.payload)}</pre>
          <pre>hash {a.hash.slice(0, 20)}...</pre>
        </div>
      ))}
    </div>
  );
}

export default function CaseDetail({ d, onChanged }: { d: Detail; onChanged: (msg: string) => void }) {
  const c = d.complaint;
  return (
    <div className="panel stack">
      <div>
        <h4>{c.id} <PriorityTag p={c.priority} /> <StatusTag s={c.status} /></h4>
        <p className="mono">{d.customer.name} ({d.customer.tier}) - {c.channel} - {intentLabel(c.intent)} - route {c.route_team ?? "-"}</p>
      </div>
      <Guardrails d={d} />
      <div className="letter" style={{ maxHeight: 120 }}>{c.text}</div>
      <Tabs>
        <TabList aria-label="Case tabs">
          <Tab>Human review</Tab><Tab>Agent monitor</Tab><Tab>Audit trail</Tab>
        </TabList>
        <TabPanels>
          <TabPanel><ReviewPanel key={`${c.id}-${c.status}-${c.retriage_count}`} d={d} onDone={onChanged} /></TabPanel>
          <TabPanel><AgentMonitor d={d} /></TabPanel>
          <TabPanel><AuditTrail d={d} /></TabPanel>
        </TabPanels>
      </Tabs>
    </div>
  );
}
