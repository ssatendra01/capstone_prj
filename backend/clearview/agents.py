"""The four agents: Triage -> Evidence -> Policy -> Draft.

Each agent is a pure function `run(ctx, tools) -> dict` whose output must satisfy the JSON schema in
`specs/contracts/schemas/` (enforced by the orchestrator). Agents are deterministic and grounded:
every decision cites ontology `@id`s returned by Context Studio (hybrid query / graph) or rows returned
by `secure-query-executor`. An ICA Agentic Studio LLM agent can replace any of these behind the same
contract (see agents/ica/).
"""
from __future__ import annotations

import re
from datetime import datetime, timedelta

from . import config
from .tools import Tools, fmt_ts, parse_ts

INTENTS = ["DUPLICATE_CHARGE", "ATM_PAYMENT_FAILURE", "UNAUTHORISED_TXN", "MORTGAGE_LOAN_DISPUTE",
           "ACCOUNT_CLOSURE", "DATA_PRIVACY", "OTHER"]
PRIORITY_ORDER = ["P1", "P2", "P3"]
NEGATIVE_SENTIMENT_BUMP = -0.6

# Required evidence sources per intent (system node ids from the ontology).
REQUIRED_SOURCES = {
    "DUPLICATE_CHARGE": ["T24"], "ATM_PAYMENT_FAILURE": ["T24", "CAMS"], "UNAUTHORISED_TXN": ["T24", "CAMS"],
    "MORTGAGE_LOAN_DISPUTE": ["T24"], "ACCOUNT_CLOSURE": ["SFDC"], "DATA_PRIVACY": ["SFDC"], "OTHER": [],
}


def _norm(text: str) -> str:
    return text.lower().replace("\u2019", "'").replace("\u2018", "'")


def _matches(text_l: str, keywords: list[str]) -> list[str]:
    found = []
    for kw in keywords:
        if re.search(r"(?<![a-z])" + re.escape(kw.lower()) + r"(?:s|es|ed|d|ing)?(?![a-z])", text_l):
            found.append(kw)
    return found


def _round(x: float) -> float:
    return round(float(x) + 1e-9, 2)


# =============================================================================== 1. TRIAGE
def triage(ctx: dict, tools: Tools) -> dict:
    c, g = ctx["complaint"], tools.graph
    text_l = _norm(c["text"])
    received = parse_ts(c["received_at"])
    as_of = ctx["as_of"]
    profile = tools.secure_query("customer_profile", {"customer_id": c["customer_id"]})["rows"][0]

    # --- intent (keyword evidence from ontology Intent nodes, weighted by phrase length) -------
    scores: dict[str, float] = {}
    for node in g.of_type("Intent"):
        key = node["@id"].split("/")[-1]
        hits = _matches(text_l, node.get("keywords", []))
        scores[key] = float(sum(1 + len(k.split()) for k in hits))
    ranked = sorted(scores.items(), key=lambda kv: kv[1], reverse=True)
    top_key, top = ranked[0]
    second = ranked[1][1] if len(ranked) > 1 else 0.0
    if top <= 0:
        intent, conf = "OTHER", 0.30
    else:
        intent = top_key
        conf = 0.70 + 0.28 * ((top - second) / top) * min(1.0, top / 4.0)
    # Grounding call: retrieve the governing graph nodes for the selected intent.
    grounding = tools.hybrid_query(c["text"], ["Intent"], top_k=3)
    intent_node = g.get(f"cv:Intent/{intent}") if intent != "OTHER" else None
    citations = [f"cv:Intent/{intent}"] if intent_node else []
    if intent_node:
        citations += [e for e in g.edges(intent_node) if e.startswith("cv:Rule/")]

    # --- vulnerability (text markers + CRM flag + age) -----------------------------------------
    markers: list[dict] = []
    for node in g.of_type("VulnerabilityMarker"):
        if node["@id"] == "cv:Vulnerability/AGE":
            continue
        if _matches(text_l, node.get("keywords", [])):
            markers.append({"id": node["@id"], "source": "complaint_text"})
    dob = datetime.fromisoformat(profile["date_of_birth"] + "T00:00:00+00:00")
    age = (received - dob).days // 365
    age_limit = g.get("cv:Vulnerability/AGE").get("ageThreshold", 75)
    if age >= age_limit:
        markers.append({"id": "cv:Vulnerability/AGE", "source": "crm_dob"})
    if profile["vulnerability_flag"]:
        markers.append({"id": "cv:Vulnerability/CRM_FLAG", "source": "crm_flag"})
    vulnerable = bool(markers)

    # --- legal threat, sentiment -----------------------------------------------------------------
    legal_hits = _matches(text_l, g.get("cv:Legal/THREAT").get("keywords", []))
    legal = bool(legal_hits)
    lex = g.get("cv:Sentiment/LEXICON")
    neg, pos = len(_matches(text_l, lex["negative"])), len(_matches(text_l, lex["positive"]))
    sentiment = _round(max(-1.0, min(1.0, (pos - neg) / (pos + neg + 1))))

    # --- deadlines, priority, SLA ------------------------------------------------------------------
    fca_deadline = parse_ts(c["fca_deadline"])
    hours_left = _round((fca_deadline - as_of).total_seconds() / 3600)
    deadline_risk = hours_left < 48
    base = intent_node["defaultPriority"] if intent_node else "P3"
    channel_node = next((n for n in g.of_type("Channel") if n["name"] == c["channel"]), None)
    channel_weight = channel_node.get("weight", 0.0) if channel_node else 0.0
    priority = base
    if base == "P3" and (sentiment <= NEGATIVE_SENTIMENT_BUMP or (channel_weight > 0 and sentiment < 0)):
        priority = "P2"
    if vulnerable or legal or deadline_risk:
        priority = "P1"
    sla_hours = g.get(f"cv:SLA/{priority}")["hours"]
    sla_due = fmt_ts(received + timedelta(hours=sla_hours))
    route = ""
    if intent_node:
        route = intent_node["routesTo"]["@id"].split("/")[-1]
    route_name = g.get(intent_node["routesTo"]["@id"])["name"] if intent_node else "Manual Triage"

    reasoning = (f"Intent {intent} from {int(top)} weighted keyword points (runner-up {int(second)}). "
                 f"Priority {priority}: base {base}"
                 f"{', vulnerable customer hard-stop' if vulnerable else ''}{', legal threat' if legal else ''}"
                 f"{', FCA deadline < 48h' if deadline_risk else ''}.")
    return {
        "complaint_id": c["id"], "intent": intent, "confidence": _round(conf), "intent_scores": scores,
        "priority": priority, "sla_hours": sla_hours, "sla_due": sla_due, "sentiment": sentiment,
        "vulnerable": vulnerable, "vulnerability_markers": markers, "legal_threat": legal,
        "legal_markers": legal_hits, "route_team": route or "MANUAL", "route_team_name": route_name,
        "channel_weight": channel_weight, "hours_to_fca_deadline": hours_left, "deadline_risk": deadline_risk,
        "citations": citations + [m["id"] for m in markers if m["id"].startswith("cv:Vulnerability/") and m["source"] != "crm_flag"],
        "grounding_hits": [h["id"] for h in grounding["hits"]], "reasoning": reasoning,
    }


# =============================================================================== 2. EVIDENCE
def evidence(ctx: dict, tools: Tools) -> dict:
    c, tri = ctx["complaint"], ctx["triage"]
    intent = tri["intent"]
    received = parse_ts(c["received_at"])
    window = {"from_ts": fmt_ts(received - timedelta(days=90)), "to_ts": fmt_ts(received)}
    cust, acct = c["customer_id"], c["account_id"]

    sources: list[dict] = []

    def fetch(system: str, name: str, params: dict) -> list[dict]:
        res = tools.secure_query(name, params)
        sources.append({"system": system, "query": name, "row_count": res["row_count"],
                        "required": system in REQUIRED_SOURCES.get(intent, [])})
        return res["rows"]

    txs = fetch("T24", "account_transactions", {"account_id": acct, **window})
    disputes = fetch("CAMS", "card_disputes", {"account_id": acct})
    calls = fetch("VERINT", "call_transcripts", {"customer_id": cust, **window})
    crm = fetch("SFDC", "crm_cases", {"customer_id": cust})
    prior = fetch("POSTGRES", "prior_complaints", {"customer_id": cust, "exclude_id": c["id"]})

    findings: dict = {"transactions_90d": len(txs), "call_transcripts": len(calls), "crm_cases": len(crm),
                      "prior_complaints": len(prior)}
    refund = 0.0
    if intent == "DUPLICATE_CHARGE":
        bad = [t for t in txs if t["type"] == "FEE" and t["fee_valid"] == 0]
        refund = sum(abs(t["amount"]) for t in bad)
        findings.update({"invalid_fees": [{"tx_id": t["id"], "amount": abs(t["amount"]), "reason": t["fee_reason"]} for t in bad],
                         "invalid_fee_total": _round(refund)})
        has_data = len([t for t in txs if t["type"] == "FEE"]) > 0
    elif intent == "ATM_PAYMENT_FAILURE":
        by_tx = {t["id"]: t for t in txs}
        short = [{"dispute_id": d["id"], "tx_id": d["tx_id"], "debited": d["amount_disputed"], "dispensed": d["atm_dispensed"],
                  "shortfall": _round(d["amount_disputed"] - d["atm_dispensed"])}
                 for d in disputes if d["atm_dispensed"] is not None and d["tx_id"] in by_tx
                 and d["amount_disputed"] > d["atm_dispensed"]]
        refund = sum(s["shortfall"] for s in short)
        findings.update({"shortfalls": short, "shortfall_total": _round(refund)})
        has_data = any(d["atm_dispensed"] is not None for d in disputes)
    elif intent == "UNAUTHORISED_TXN":
        findings.update({"disputed_transactions": [
            {"dispute_id": d["id"], "tx_id": d["tx_id"], "amount": d["amount_disputed"], "fraud_score": d["fraud_score"],
             "cardholder_present": bool(d["cardholder_present"]), "merchant_risk": d["merchant_risk"]} for d in disputes],
            "max_fraud_score": max([d["fraud_score"] for d in disputes], default=0.0),
            "all_cardholder_present": bool(disputes) and all(d["cardholder_present"] for d in disputes),
            "high_risk_merchant": any(d["merchant_risk"] == "HIGH" for d in disputes)})
        refund = sum(d["amount_disputed"] for d in disputes)
        has_data = bool(disputes)
    elif intent == "MORTGAGE_LOAN_DISPUTE":
        fees = [t for t in txs if t["type"] == "FEE"]
        bad = [t for t in fees if t["fee_valid"] == 0]
        refund = sum(abs(t["amount"]) for t in bad)
        findings.update({"fees_reviewed": len(fees), "invalid_fee_total": _round(refund),
                         "invalid_fees": [{"tx_id": t["id"], "amount": abs(t["amount"]), "reason": t["fee_reason"]} for t in bad],
                         "valid_fees": [{"tx_id": t["id"], "amount": abs(t["amount"]), "reason": t["fee_reason"]} for t in fees if t["fee_valid"] == 1]})
        has_data = bool(fees)
    elif intent == "ACCOUNT_CLOSURE":
        req = next((x for x in crm if x["case_type"] == "CLOSURE_REQUEST"), None)
        if req:
            opened = parse_ts(req["opened_at"])
            after = [t for t in txs if t["type"] == "FEE" and t["posted_at"] >= req["opened_at"]]
            refund = sum(abs(t["amount"]) for t in after)
            findings.update({"closure_request_id": req["id"], "days_open": (received - opened).days,
                             "fees_after_request": [{"tx_id": t["id"], "amount": abs(t["amount"])} for t in after],
                             "fees_after_request_total": _round(refund)})
        has_data = req is not None
    elif intent == "DATA_PRIVACY":
        dsar = next((x for x in crm if x["case_type"] == "DSAR"), None)
        if dsar:
            end = parse_ts(dsar["closed_at"]) if dsar["closed_at"] else received
            findings.update({"dsar_case_id": dsar["id"], "dsar_days_open": (end - parse_ts(dsar["opened_at"])).days,
                             "dsar_closed": bool(dsar["closed_at"])})
        has_data = dsar is not None
    else:
        has_data = False

    required = [s for s in sources if s["required"]]
    if intent in ("OTHER",):
        completeness = 0.0
    else:
        covered = [s for s in required if (s["row_count"] > 0)]
        completeness = len(covered) / len(required) if required else 0.0
        if not has_data:
            completeness = min(completeness, 0.4)
    return {
        "complaint_id": c["id"], "intent": intent, "sources": sources, "completeness": _round(completeness),
        "confidence": _round(0.6 + 0.4 * completeness), "refund_candidate": _round(refund), "findings": findings,
        "citations": [f"cv:System/{s['system']}" for s in sources if s["row_count"] > 0],
        "summary": f"{sum(s['row_count'] for s in sources)} rows from {len(sources)} sources; completeness {completeness:.2f}.",
    }


# =============================================================================== 3. POLICY
def _compensation(outcome: str, refund: float, intent: str, vulnerable: bool) -> str | None:
    if outcome == "reject":
        return None
    if outcome == "partial_uphold":
        return "MINOR"
    if refund >= 1000:
        return "SEVERE"
    if refund >= 250 or intent == "UNAUTHORISED_TXN" or (vulnerable and refund >= 100):
        return "MODERATE"
    return "MINOR"


def _authority(total: float, tools_graph) -> str:
    levels = sorted(tools_graph.of_type("AuthorityLevel"), key=lambda n: n["rank"])
    for lv in levels:
        if total <= lv["limitGBP"]:
            return lv["@id"]
    return levels[-1]["@id"]


def policy(ctx: dict, tools: Tools) -> dict:
    tri, ev, g = ctx["triage"], ctx["evidence"], tools.graph
    intent, f = tri["intent"], ev["findings"]
    refund, outcome, pconf, why = 0.0, "reject", 0.60, "No policy applicable; manual review required."

    if intent == "DUPLICATE_CHARGE":
        if f["invalid_fee_total"] > 0:
            outcome, refund, pconf = "uphold", f["invalid_fee_total"], 0.95
            why = f"{len(f['invalid_fees'])} fee(s) found without contractual basis or duplicated; refund in full."
        else:
            outcome, pconf, why = "reject", (0.92 if f["transactions_90d"] else 0.60), "All fees in the last 90 days are valid and applied once."
    elif intent == "ATM_PAYMENT_FAILURE":
        if f["shortfall_total"] > 0:
            outcome, refund, pconf = "uphold", f["shortfall_total"], 0.95
            why = "ATM dispensed less than the account was debited; shortfall refunded."
        else:
            outcome, pconf, why = "reject", (0.92 if f["shortfalls"] == [] and ev["completeness"] >= 1 else 0.60), "ATM records show the full amount was dispensed."
    elif intent == "UNAUTHORISED_TXN":
        refund_all = ev["refund_candidate"]
        if not f["disputed_transactions"]:
            outcome, pconf, why = "reject", 0.60, "No disputed card transactions found."
        elif f["max_fraud_score"] >= 0.6 or (f["high_risk_merchant"] and not f["all_cardholder_present"]):
            outcome, refund, pconf = "uphold", refund_all, 0.95
            why = "High fraud score / cardholder not present at high-risk merchant; payer refunded (PSR 2017 reg 76)."
        elif f["max_fraud_score"] < 0.3 and f["all_cardholder_present"]:
            outcome, pconf, why = "reject", 0.92, "Low fraud score and cardholder present; payments appear authorised."
        else:
            outcome, refund, pconf = "partial_uphold", refund_all * 0.5, 0.80
            why = "Indicators inconclusive; 50% goodwill refund pending investigation."
    elif intent == "MORTGAGE_LOAN_DISPUTE":
        if f["invalid_fee_total"] > 0:
            outcome, refund, pconf = "uphold", f["invalid_fee_total"], 0.95
            why = "Fee has no basis under the mortgage contract; refunded."
        else:
            outcome, pconf, why = "reject", (0.92 if f["fees_reviewed"] else 0.60), "Charges are contractual and correctly applied."
    elif intent == "ACCOUNT_CLOSURE":
        if "days_open" not in f:
            outcome, pconf, why = "reject", 0.60, "No closure request found in CRM."
        elif f["days_open"] > 7:
            outcome, refund, pconf = "uphold", f["fees_after_request_total"], 0.95
            why = f"Closure request open {f['days_open']} days (limit 7); post-request fees refunded."
        else:
            outcome, pconf, why = "reject", 0.92, f"Closure request is within the 7-day window ({f['days_open']} days)."
    elif intent == "DATA_PRIVACY":
        if "dsar_days_open" not in f:
            outcome, pconf, why = "reject", 0.60, "No subject access request found in CRM; DPO to review."
        elif f["dsar_days_open"] > 30:
            outcome, pconf, why = "uphold", 0.93, f"DSAR open {f['dsar_days_open']} days, exceeding one month (UK GDPR Art. 15)."
        else:
            outcome, pconf, why = "reject", 0.92, "DSAR is within the statutory month."

    refund = _round(refund)
    band_key = _compensation(outcome, refund, intent, tri["vulnerable"])
    band = g.get(f"cv:Redress/{band_key}") if band_key else None
    comp = float(band["amountGBP"]) if band else 0.0
    total = _round(refund + comp)
    authority = _authority(total, g)

    # grounding: governing rules from the intent node + precedents via hybrid query
    intent_node = g.get(f"cv:Intent/{intent}")
    rules = [e for e in g.edges(intent_node) if e.startswith("cv:Rule/")] if intent_node else []
    prec_res = tools.hybrid_query(f"{intent} {outcome} refund precedent", ["Precedent"], top_k=3)
    precedents = [h["id"] for h in prec_res["hits"] if g.get(h["id"]).get("intent") == intent][:2]
    if tri["vulnerable"]:
        rules.append("cv:Rule/VULNERABLE-POLICY")
    cites = rules + ([band["@id"]] if band else []) + [authority]
    return {
        "complaint_id": ctx["complaint"]["id"], "outcome": outcome, "refund_amount": refund, "compensation_amount": comp,
        "redress_total": total, "redress_band": band["@id"] if band else None, "authority_required": authority,
        "rules_cited": rules, "precedents": precedents, "citations": cites,
        "confidence": _round(min(pconf, ev["confidence"])), "reasoning": why,
    }


# =============================================================================== 4. DRAFT
def render_letter(name: str, complaint: dict, outcome: str, refund: float, comp: float, vulnerable: bool,
                  letter_type: str, rules: list[str], reasoning: str) -> str:
    first = name.split()[0]
    total = _round(refund + comp)
    received = complaint["received_at"][:10]
    lines = [f"Dear {first},", "", f"Our reference: {complaint['id']}", "",
             f"Thank you for getting in touch on {received}. We are sorry that you have had cause to complain, and we have looked into what happened carefully."]
    if outcome == "uphold":
        lines += ["", "We have upheld your complaint. " + reasoning]
    elif outcome == "partial_uphold":
        lines += ["", "We have partly upheld your complaint. " + reasoning]
    else:
        lines += ["", "Having reviewed your account and the records available to us, we have not been able to uphold your complaint. " + reasoning
                  + " We understand this is not the answer you were hoping for and we would like to explain how we reached it."]
    if total > 0:
        parts = []
        if refund > 0:
            parts.append(f"£{refund:,.2f} refund")
        if comp > 0:
            parts.append(f"£{comp:,.2f} to recognise the inconvenience caused")
        lines += ["", f"We will credit your account with {' and '.join(parts)}, a total of £{total:,.2f}. You do not need to do anything."]
    if vulnerable:
        lines += ["", "We want to make sure you get the support you need. Please tell us if you would like us to communicate in a different way or if "
                      "there is anything that would make this easier for you; a named colleague can call you at a time that suits you."]
    refs = ", ".join(r.split("/")[-1] for r in rules if r.startswith("cv:Rule/")) or "our complaints procedure"
    lines += ["", f"This response is based on {refs}.",
              "", "If you are not satisfied with this response you can refer your complaint to the Financial Ombudsman Service (www.financial-ombudsman.org.uk), "
                  "free of charge, within six months of the date of this letter. We will provide the details you need on request."
              if letter_type != "SUMMARY_RESOLUTION" else
              "", ]
    if letter_type == "SUMMARY_RESOLUTION":
        lines[-1] = ("This is a summary resolution communication. If you are not satisfied you can ask us to reopen your complaint or refer it to the "
                     "Financial Ombudsman Service (www.financial-ombudsman.org.uk), free of charge, within six months.")
    lines += ["", "Yours sincerely,", "Complaints Resolution Team", "Clearview Retail Bank plc"]
    return "\n".join(lines)


def draft(ctx: dict, tools: Tools) -> dict:
    c, tri, ev, pol = ctx["complaint"], ctx["triage"], ctx["evidence"], ctx["policy"]
    profile = tools.secure_query("customer_profile", {"customer_id": c["customer_id"]})["rows"][0]
    final_conf = _round(min(tri["confidence"], ev["confidence"], pol["confidence"]))

    reasons, guardrails = [], []
    if tri["vulnerable"]:
        reasons.append("VULNERABLE_CUSTOMER")
        guardrails.append({"type": "VULNERABLE_CUSTOMER", "severity": "critical", "message": "Vulnerable customer detected - mandatory human review."})
    if tri["legal_threat"]:
        reasons.append("LEGAL_THREAT")
        guardrails.append({"type": "LEGAL_THREAT", "severity": "high", "message": "Legal / ombudsman threat detected."})
    if tri["deadline_risk"]:
        reasons.append("FCA_DEADLINE_RISK")
        guardrails.append({"type": "FCA_DEADLINE", "severity": "high", "message": f"FCA final-response deadline in {tri['hours_to_fca_deadline']}h."})
    if pol["redress_total"] > config.HITL_REDRESS_LIMIT:
        reasons.append("REDRESS_OVER_150")
    if tri["intent"] == "DATA_PRIVACY":
        reasons.append("DATA_PRIVACY_DPO_REVIEW")
    if tri["intent"] == "OTHER":
        reasons.append("UNKNOWN_INTENT")
    if pol["outcome"] == "reject":
        reasons.append("REJECTION_REQUIRES_APPROVAL")
    if final_conf < config.STP_CONFIDENCE:
        reasons.append("LOW_CONFIDENCE")
    stp = not reasons
    letter_type = "SUMMARY_RESOLUTION" if stp else "FINAL_RESPONSE_DRAFT"
    letter = render_letter(profile["name"], c, pol["outcome"], pol["refund_amount"], pol["compensation_amount"],
                           tri["vulnerable"], letter_type, pol["rules_cited"], pol["reasoning"])
    action = "SEND" if stp else "HOLD_FOR_REVIEW"
    return {
        "complaint_id": c["id"], "letter_type": letter_type, "letter": letter, "stp_eligible": stp,
        "hitl_required": not stp, "hitl_reasons": reasons, "guardrails": guardrails, "final_confidence": final_conf,
        "dispatch": {"action": action, "channel": "EMAIL", "recipient": profile["email"],
                     "subject": f"Your complaint {c['id']} - our response"},
        "audit_summary": (f"{tri['intent']} / {tri['priority']} / vulnerable={tri['vulnerable']} -> {pol['outcome']} "
                          f"£{pol['redress_total']:.2f} (conf {final_conf}); {action}; rules {','.join(pol['rules_cited'])}"),
    }


AGENTS = [("triage", triage), ("evidence", evidence), ("policy", policy), ("draft", draft)]
