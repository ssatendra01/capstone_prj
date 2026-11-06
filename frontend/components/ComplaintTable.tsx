"use client";
import { Button, Dropdown, Pagination, Search, Table, TableBody, TableCell, TableHead, TableHeader, TableRow, Tag } from "@carbon/react";
import { Complaint, INTENT_LABEL, STATUS_LABEL, gbp, sentimentBucket } from "@/lib/api";
import { PriorityTag, StatusTag, intentLabel } from "./tags";

export type Filters = { status: string; priority: string; channel: string; sentiment: string; vulnerable: string; q: string };
export const EMPTY_FILTERS: Filters = { status: "", priority: "", channel: "", sentiment: "", vulnerable: "", q: "" };

const opts = (all: string, pairs: [string, string][]) => [{ id: "", text: all }, ...pairs.map(([id, text]) => ({ id, text }))];
const STATUS = opts("All statuses", Object.entries(STATUS_LABEL));
const PRIORITY = opts("All priorities", [["P1", "P1 Urgent"], ["P2", "P2 High"], ["P3", "P3 Normal"]]);
const CHANNEL = opts("All channels", ["Branch", "Call Centre", "Mobile App", "Email", "Social Media"].map((c) => [c, c] as [string, string]));
const SENT = opts("Any sentiment", [["negative", "Negative"], ["neutral", "Neutral"], ["positive", "Positive"]]);
const VULN = opts("Vulnerable: any", [["true", "Vulnerable only"], ["false", "Not vulnerable"]]);

function DD({ label, items, value, onChange }: { label: string; items: { id: string; text: string }[]; value: string; onChange: (v: string) => void }) {
  return (
    <Dropdown id={`f-${label}`} titleText={label} label={label} size="sm" items={items} itemToString={(i: any) => i?.text ?? ""}
      selectedItem={items.find((i) => i.id === value) ?? items[0]} onChange={({ selectedItem }: any) => onChange(selectedItem?.id ?? "")} />
  );
}

export default function ComplaintTable(props: {
  items: Complaint[]; total: number; page: number; pageSize: number; selected: string | null; filters: Filters;
  onFilters: (f: Filters) => void; onPage: (page: number, size: number) => void; onSelect: (id: string) => void;
}) {
  const { filters: f, onFilters } = props;
  const set = (k: keyof Filters) => (v: string) => onFilters({ ...f, [k]: v });
  return (
    <div className="panel">
      <div className="filters">
        <Search size="sm" labelText="Search" placeholder="Search id, name, text" value={f.q} onChange={(e: any) => set("q")(e.target.value)} />
        <DD label="Status" items={STATUS} value={f.status} onChange={set("status")} />
        <DD label="Priority" items={PRIORITY} value={f.priority} onChange={set("priority")} />
        <DD label="Channel" items={CHANNEL} value={f.channel} onChange={set("channel")} />
        <DD label="Sentiment" items={SENT} value={f.sentiment} onChange={set("sentiment")} />
        <DD label="Vulnerability" items={VULN} value={f.vulnerable} onChange={set("vulnerable")} />
        <Button size="sm" kind="ghost" onClick={() => onFilters(EMPTY_FILTERS)}>Reset</Button>
      </div>
      <Table size="sm" aria-label="Complaints">
        <TableHead>
          <TableRow>
            {["ID", "Customer", "Channel", "Intent", "Pri", "Status", "Sentiment", "Redress", "Conf", "Flags"].map((h) => <TableHeader key={h}>{h}</TableHeader>)}
          </TableRow>
        </TableHead>
        <TableBody>
          {props.items.map((c) => (
            <TableRow key={c.id} className={`row-click ${props.selected === c.id ? "row-sel" : ""} ${c.vulnerable ? "row-vuln" : ""}`}
              onClick={() => props.onSelect(c.id)}>
              <TableCell className="mono">{c.id}</TableCell>
              <TableCell>{c.customer_name}</TableCell>
              <TableCell>{c.channel}</TableCell>
              <TableCell>{intentLabel(c.intent)}</TableCell>
              <TableCell><PriorityTag p={c.priority} /></TableCell>
              <TableCell><StatusTag s={c.status} /></TableCell>
              <TableCell>{sentimentBucket(c.sentiment)}</TableCell>
              <TableCell>{gbp(c.redress_total)}</TableCell>
              <TableCell>{c.confidence != null ? `${Math.round(c.confidence * 100)}%` : "-"}</TableCell>
              <TableCell className="tags">
                {c.vulnerable ? <Tag size="sm" type="red">Vulnerable</Tag> : null}
                {c.legal_threat ? <Tag size="sm" type="magenta">Legal</Tag> : null}
                {c.hours_to_deadline != null && c.hours_to_deadline < 48 && c.status !== "RESOLVED_STP" && c.status !== "RESOLVED_HUMAN"
                  ? <Tag size="sm" type="warm-gray">Deadline &lt;48h</Tag> : null}
              </TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
      {props.items.length === 0 && <div className="empty">No complaints match the filters.</div>}
      <Pagination page={props.page} pageSize={props.pageSize} pageSizes={[10, 25, 50]} totalItems={props.total}
        onChange={({ page, pageSize }: any) => props.onPage(page, pageSize)} />
    </div>
  );
}
