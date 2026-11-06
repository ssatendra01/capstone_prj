"use client";
import { useCallback, useEffect, useRef, useState } from "react";
import { Button, Header, HeaderName, InlineNotification, Loading } from "@carbon/react";
import { Complaint, Detail, Kpis, api } from "@/lib/api";
import KpiCards from "@/components/KpiCards";
import ComplaintTable, { EMPTY_FILTERS, Filters } from "@/components/ComplaintTable";
import CaseDetail from "@/components/CaseDetail";
import { ContextConsole, IntakeModal } from "@/components/Modals";
import DemoBar from "@/components/DemoBar";

export default function Page() {
  const [kpis, setKpis] = useState<Kpis | null>(null);
  const [items, setItems] = useState<Complaint[]>([]);
  const [total, setTotal] = useState(0);
  const [filters, setFilters] = useState<Filters>(EMPTY_FILTERS);
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(10);
  const [selected, setSelected] = useState<string | null>(null);
  const [detail, setDetail] = useState<Detail | null>(null);
  const [msg, setMsg] = useState<{ kind: "success" | "error"; text: string } | null>(null);
  const [auditOk, setAuditOk] = useState<boolean | null>(null);
  const [intake, setIntake] = useState(false);
  const [graph, setGraph] = useState(false);
  const [busy, setBusy] = useState(false);
  const [demoKey, setDemoKey] = useState(0);
  const reqId = useRef(0);

  const load = useCallback(async () => {
    const id = ++reqId.current;
    const p = new URLSearchParams({ limit: String(pageSize), offset: String((page - 1) * pageSize) });
    (Object.entries(filters) as [string, string][]).forEach(([k, v]) => v && p.set(k, v));
    try {
      const [k, list, av] = await Promise.all([api<Kpis>("/api/kpis"), api<{ total: number; items: Complaint[] }>(`/api/complaints?${p}`),
        api<{ valid: boolean }>("/api/audit/verify")]);
      if (id !== reqId.current) return;           // ignore stale responses
      setKpis(k); setItems(list.items); setTotal(list.total); setAuditOk(av.valid);
    } catch (e) { if (id === reqId.current) setMsg({ kind: "error", text: `API unreachable: ${e}` }); }
  }, [filters, page, pageSize]);

  const loadDetail = useCallback(async (id: string) => {
    try { setDetail(await api<Detail>(`/api/complaints/${id}`)); } catch (e) { setMsg({ kind: "error", text: String(e) }); }
  }, []);

  useEffect(() => { void load(); const t = setInterval(load, 15000); return () => clearInterval(t); }, [load]);
  useEffect(() => { if (selected) void loadDetail(selected); }, [selected, loadDetail]);

  async function processBatch() {
    setBusy(true);
    try {
      const r = await api<{ processed: number }>("/api/process-batch?limit=25", { method: "POST" });
      setMsg({ kind: "success", text: `Agent pipeline ran on ${r.processed} complaints` });
      await load();
    } catch (e) { setMsg({ kind: "error", text: String(e) }); } finally { setBusy(false); }
  }
  const changed = async (text: string) => { setMsg({ kind: "success", text }); await load(); setDemoKey((k) => k + 1); if (selected) await loadDetail(selected); };
  const onError = useCallback((m: string) => setMsg({ kind: "error", text: m }), []);
  async function openScenario(id: string, ranNow: boolean) {
    setSelected(id); await loadDetail(id); await load(); setDemoKey((k) => k + 1);
    setMsg({ kind: "success", text: ranNow ? `${id}: agents ran - review the result on the right` : `${id}: opened` });
  }
  async function afterReset() {
    setSelected(null); setDetail(null); setFilters(EMPTY_FILTERS); setPage(1); await load(); setDemoKey((k) => k + 1);
    setMsg({ kind: "success", text: "Demo data reset: 300 complaints, none processed" });
  }

  return (
    <>
      <Header aria-label="Clearview">
        <HeaderName prefix="Clearview">Complaints Monitoring Workbench</HeaderName>
      </Header>
      <main className="shell">
        <div className="toolbar">
          <Button size="md" onClick={() => setIntake(true)}>New complaint</Button>
          <Button size="md" kind="secondary" disabled={busy} onClick={processBatch}>{busy ? "Running agents..." : "Run agents on next 25 unprocessed"}</Button>
          <Button size="md" kind="tertiary" onClick={() => setGraph(true)}>Context Studio query</Button>
          <Button size="md" kind="ghost" onClick={load}>Refresh</Button>
          <span style={{ alignSelf: "center", marginLeft: "auto" }} className="mono">
            audit chain: {auditOk == null ? "..." : auditOk ? "verified" : "BROKEN"}
          </span>
        </div>
        {msg && <InlineNotification kind={msg.kind} lowContrast title={msg.text} onCloseButtonClick={() => setMsg(null)} />}
        <DemoBar refreshKey={demoKey} onOpen={openScenario} onReset={afterReset} onError={onError} />
        <KpiCards k={kpis} />
        <div className="layout">
          <ComplaintTable items={items} total={total} page={page} pageSize={pageSize} selected={selected} filters={filters}
            onFilters={(f) => { setFilters(f); setPage(1); }} onPage={(pg, sz) => { setPage(pg); setPageSize(sz); }}
            onSelect={(id) => { setSelected(id); }} />
          {detail && selected ? <CaseDetail d={detail} onChanged={changed} /> :
            <div className="panel empty">{selected ? <Loading withOverlay={false} small /> : "Select a complaint to review the agents' work."}</div>}
        </div>
      </main>
      <IntakeModal open={intake} onClose={() => setIntake(false)} onCreated={(id) => { setIntake(false); setSelected(id); void changed(`${id} created and processed`); }} />
      <ContextConsole open={graph} onClose={() => setGraph(false)} />
    </>
  );
}
