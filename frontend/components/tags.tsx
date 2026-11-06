"use client";
import { Tag } from "@carbon/react";
import { INTENT_LABEL, STATUS_LABEL } from "@/lib/api";

const prioColor = { P1: "red", P2: "magenta", P3: "cool-gray" } as const;
const statusColor: Record<string, any> = {
  PENDING_REVIEW: "purple", RESOLVED_STP: "green", RESOLVED_HUMAN: "teal", ESCALATED: "red", ERROR_HITL: "red", RECEIVED: "gray", IN_FLIGHT: "blue",
};

export function PriorityTag({ p }: { p: string | null }) {
  return p ? <Tag size="sm" type={prioColor[p as "P1"]}>{p}</Tag> : <span>-</span>;
}
export function StatusTag({ s }: { s: string }) {
  return <Tag size="sm" type={statusColor[s] ?? "gray"}>{STATUS_LABEL[s] ?? s}</Tag>;
}
export function intentLabel(i: string | null) {
  return i ? INTENT_LABEL[i] ?? i : "-";
}
