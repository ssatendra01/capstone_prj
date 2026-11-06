"""Run the 4-agent pipeline over the 300-case ground truth and report quality metrics.

    python -m clearview.evaluate            # exit code 1 if any target is missed
"""
from __future__ import annotations

import json
import sys
from collections import Counter

from . import db
from .pipeline import run_pipeline
from .seed import ANCHOR

TARGETS = {"intent_accuracy": 0.90, "vulnerable_recall": 1.0, "hitl_recall": 1.0, "priority_accuracy": 0.90,
           "outcome_accuracy": 0.90, "redress_accuracy": 0.90}


def evaluate(conn, limit: int | None = None, verbose: bool = False) -> dict:
    gts = db.rows(conn, "SELECT * FROM ground_truth ORDER BY complaint_id" + (f" LIMIT {int(limit)}" if limit else ""))
    hits = Counter()
    vuln_total = hitl_total = stp = 0
    total_ms = max_ms = 0
    misses: list[dict] = []
    for g in gts:
        res = run_pipeline(conn, g["complaint_id"], as_of=ANCHOR)
        if "error" in res:
            misses.append({"id": g["complaint_id"], "error": res["error"]})
            continue
        tri, pol, dr = res["triage"], res["policy"], res["draft"]
        checks = {"intent": tri["intent"] == g["intent"], "priority": tri["priority"] == g["priority"],
                  "outcome": pol["outcome"] == g["outcome"], "redress": abs(pol["redress_total"] - g["redress_total"]) < 0.015}
        for k, ok in checks.items():
            hits[k] += ok
        if g["vulnerable"]:
            vuln_total += 1
            hits["vuln"] += tri["vulnerable"]
        elif tri["vulnerable"]:
            hits["vuln_false_pos"] += 1
        if g["hitl_required"]:
            hitl_total += 1
            hits["hitl"] += dr["hitl_required"]
        stp += dr["stp_eligible"]
        total_ms += res["total_latency_ms"]
        max_ms = max(max_ms, res["total_latency_ms"])
        if not all(checks.values()) or (g["hitl_required"] and not dr["hitl_required"]):
            misses.append({"id": g["complaint_id"], "gt": {k: g[k] for k in ("intent", "priority", "outcome", "redress_total", "hitl_required")},
                           "got": {"intent": tri["intent"], "priority": tri["priority"], "outcome": pol["outcome"],
                                   "redress_total": pol["redress_total"], "hitl": dr["hitl_required"]}, "conf": tri["confidence"]})
    n = len(gts)
    m = {"cases": n, "intent_accuracy": hits["intent"] / n, "priority_accuracy": hits["priority"] / n,
         "outcome_accuracy": hits["outcome"] / n, "redress_accuracy": hits["redress"] / n,
         "vulnerable_recall": hits["vuln"] / vuln_total if vuln_total else 1.0, "vulnerable_false_positives": hits["vuln_false_pos"],
         "hitl_recall": hits["hitl"] / hitl_total if hitl_total else 1.0, "stp_rate": stp / n,
         "avg_pipeline_ms": total_ms / n, "max_pipeline_ms": max_ms}
    m["errors"] = sum(1 for x in misses if "error" in x)
    m["passed"] = m["errors"] == 0 and all(m[k] >= t for k, t in TARGETS.items())
    if verbose:
        m["misses"] = misses
    return m


if __name__ == "__main__":
    conn = db.connect()
    result = evaluate(conn, verbose="-v" in sys.argv)
    print(json.dumps(result, indent=2))
    sys.exit(0 if result["passed"] else 1)

