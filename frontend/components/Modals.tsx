"use client";
import { useEffect, useState } from "react";
import { Button, InlineNotification, Modal, Select, SelectItem, TextArea, TextInput } from "@carbon/react";
import { api, ApiError } from "@/lib/api";

export function IntakeModal({ open, onClose, onCreated }: { open: boolean; onClose: () => void; onCreated: (id: string) => void }) {
  const [customer, setCustomer] = useState("CUS-00001");
  const [account, setAccount] = useState("ACC-00001");
  const [channel, setChannel] = useState("Call Centre");
  const [text, setText] = useState("");
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit() {
    setBusy(true); setErr(null);
    try {
      const r = await api<{ id: string }>("/api/complaints", { method: "POST", body: JSON.stringify({ customer_id: customer, account_id: account, channel, text, process: true }) });
      setText(""); onCreated(r.id);
    } catch (e) { setErr(e instanceof ApiError ? e.message : String(e)); } finally { setBusy(false); }
  }
  return (
    <Modal open={open} modalHeading="Log a new complaint" primaryButtonText={busy ? "Processing..." : "Submit & run agents"} secondaryButtonText="Cancel"
      primaryButtonDisabled={busy || text.trim().length < 10} onRequestClose={onClose} onRequestSubmit={submit}>
      <div className="stack">
        <TextInput id="ic" labelText="Customer id" value={customer} onChange={(e: any) => { setCustomer(e.target.value); setAccount(e.target.value.replace("CUS", "ACC")); }} />
        <TextInput id="ia" labelText="Account id" value={account} onChange={(e: any) => setAccount(e.target.value)} />
        <Select id="ich" labelText="Channel" value={channel} onChange={(e: any) => setChannel(e.target.value)}>
          {["Branch", "Call Centre", "Mobile App", "Email", "Social Media"].map((c) => <SelectItem key={c} value={c} text={c} />)}
        </Select>
        <TextArea id="itx" labelText="Complaint text" rows={5} value={text} onChange={(e: any) => setText(e.target.value)} />
        {err && <InlineNotification kind="error" lowContrast hideCloseButton title="Could not submit" subtitle={err} />}
      </div>
    </Modal>
  );
}

type Hit = { id: string; type: string; name: string; description: string; score: number };
export function ContextConsole({ open, onClose }: { open: boolean; onClose: () => void }) {
  const [q, setQ] = useState("vulnerable customer hard stop");
  const [res, setRes] = useState<{ hits: Hit[]; graph_context: Hit[] } | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const run = async () => {
    setErr(null);
    try { setRes(await api("/api/graph/query", { method: "POST", body: JSON.stringify({ query: q, top_k: 5 }) })); }
    catch (e) { setErr(String(e)); }
  };
  useEffect(() => { if (open && !res) void run(); /* eslint-disable-next-line */ }, [open]);
  return (
    <Modal open={open} passiveModal modalHeading="Context Studio - hybrid (vector + graph) query" onRequestClose={onClose} size="lg">
      <div className="toolbar">
        <TextInput id="gq" labelText="Query" value={q} onChange={(e: any) => setQ(e.target.value)} onKeyDown={(e: any) => e.key === "Enter" && run()} />
        <Button size="md" onClick={run} style={{ alignSelf: "flex-end" }}>Run</Button>
      </div>
      {err && <InlineNotification kind="error" lowContrast hideCloseButton title="Query failed" subtitle={err} />}
      {res?.hits.map((h) => (
        <div key={h.id} className="audit-item"><b>{h.name}</b> <span className="mono">{h.id} - {h.type} - score {h.score}</span><p style={{ fontSize: ".85rem" }}>{h.description}</p></div>
      ))}
      {!!res?.graph_context.length && <><h6>Graph neighbours</h6>
        {res.graph_context.map((g) => <div key={g.id} className="mono">{g.id} - {g.name}</div>)}</>}
    </Modal>
  );
}
