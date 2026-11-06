"use client";
import { useEffect, useState } from "react";
import { Button, Tag } from "@carbon/react";
import { api } from "@/lib/api";

type Scenario = { id: string; key: string; title: string; show: string; expect: string; status: string };

export default function DemoBar({ refreshKey, onOpen, onReset, onError }: {
  refreshKey: number; onOpen: (id: string, ranNow: boolean) => void; onReset: () => void; onError: (m: string) => void;
}) {
  const [items, setItems] = useState<Scenario[]>([]);
  const [busy, setBusy] = useState<string | null>(null);

  useEffect(() => { api<Scenario[]>("/api/demo/scenarios").then(setItems).catch((e) => onError(String(e))); }, [refreshKey, onError]);

  async function run(s: Scenario) {
    setBusy(s.id);
    try {
      let ran = false;
      if (s.status === "RECEIVED") { await api(`/api/complaints/${s.id}/process`, { method: "POST" }); ran = true; }
      onOpen(s.id, ran);
    } catch (e) { onError(String(e)); } finally { setBusy(null); }
  }
  async function reset() {
    if (!window.confirm("Reset all demo data? This deletes decisions and the audit log, then re-seeds 300 complaints.")) return;
    setBusy("reset");
    try { await api("/api/demo/reset", { method: "POST" }); onReset(); } catch (e) { onError(String(e)); } finally { setBusy(null); }
  }

  return (
    <div className="panel" style={{ marginBottom: "1.5rem" }}>
      <div className="toolbar" style={{ marginBottom: ".5rem", alignItems: "center" }}>
        <h5 style={{ margin: 0 }}>Demo scenarios</h5>
        <Button size="sm" kind="danger--ghost" disabled={busy !== null} onClick={reset} style={{ marginLeft: "auto" }}>Reset demo data</Button>
      </div>
      <div className="kpis" style={{ marginBottom: 0 }}>
        {items.map((s) => (
          <div key={s.id} className="kpi">
            <div className="label">Scenario {s.key} - {s.id}</div>
            <div style={{ fontWeight: 600, margin: ".25rem 0" }}>{s.title}</div>
            <div style={{ fontSize: ".8rem", color: "var(--cds-text-secondary)", minHeight: "3.6em" }}>{s.show}</div>
            <div style={{ margin: ".5rem 0" }}>
              <Tag size="sm" type={s.status === "RECEIVED" ? "gray" : "green"}>{s.status === "RECEIVED" ? "Not run yet" : s.status.replace("_", " ").toLowerCase()}</Tag>
            </div>
            <Button size="sm" disabled={busy !== null} onClick={() => run(s)}>
              {busy === s.id ? "Running agents..." : s.status === "RECEIVED" ? "Run agents" : "Open case"}
            </Button>
          </div>
        ))}
      </div>
    </div>
  );
}
