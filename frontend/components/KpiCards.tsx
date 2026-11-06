"use client";
import { Kpis, gbp } from "@/lib/api";

export default function KpiCards({ k }: { k: Kpis | null }) {
  const c = (label: string, value: string | number, cls = "") => (
    <div className={`kpi ${cls}`} key={label}><div className="label">{label}</div><div className="value">{value}</div></div>
  );
  if (!k) return <div className="kpis">{c("Loading", "...")}</div>;
  return (
    <div className="kpis">
      {c("Total active cases", k.active_cases)}
      {c("In-flight pipeline", k.in_flight)}
      {c("Awaiting human review", k.pending_review, k.pending_review ? "warn" : "good")}
      {c("P1 breach risk", k.p1_breach_risk, k.p1_breach_risk ? "danger" : "good")}
      {c("Vulnerable open", k.vulnerable_open, k.vulnerable_open ? "danger" : "good")}
      {c("Avg redress payout", gbp(k.avg_redress))}
      {c("STP rate", `${(k.stp_rate * 100).toFixed(1)}%`, "good")}
      {c("Avg agent time", `${k.avg_pipeline_ms} ms`)}
    </div>
  );
}
