"""Deterministic synthetic data: 300 complaints + simulated T24 / CAMS / Salesforce / Verint records
and a ground-truth table (labels derived from the scenario design, not from the agents).

    python -m clearview.seed [--reset]
"""
from __future__ import annotations

import argparse
import json
import random
import sqlite3
from datetime import datetime, timedelta, timezone

from . import config, db
from .tools import add_business_days, fmt_ts

ANCHOR = datetime(2026, 11, 5, 9, 0, tzinfo=timezone.utc)   # "now" for evaluation / seeded deadlines
INTENT_COUNTS = [("DUPLICATE_CHARGE", 84), ("ATM_PAYMENT_FAILURE", 66), ("UNAUTHORISED_TXN", 54),
                 ("MORTGAGE_LOAN_DISPUTE", 45), ("ACCOUNT_CLOSURE", 30), ("DATA_PRIVACY", 21)]
BASE_PRIORITY = {"DUPLICATE_CHARGE": "P3", "ATM_PAYMENT_FAILURE": "P2", "UNAUTHORISED_TXN": "P1",
                 "MORTGAGE_LOAN_DISPUTE": "P2", "ACCOUNT_CLOSURE": "P3", "DATA_PRIVACY": "P2"}
CHANNELS = (["Branch"] * 22 + ["Call Centre"] * 34 + ["Mobile App"] * 21 + ["Email"] * 14 + ["Social Media"] * 9)
FIRST = ["Olivia", "Amelia", "Isla", "Ava", "Grace", "Freya", "Harry", "Oliver", "George", "Noah", "Jack", "Leo", "Archie", "Fiona",
         "Callum", "Ewan", "Morag", "Kirsty", "Hamish", "Rory", "Aisha", "Priya", "Tariq", "Mei", "Sofia", "Daniel", "Chloe", "Ethan"]
LAST = ["Smith", "Campbell", "Stewart", "MacDonald", "Wilson", "Reid", "Murray", "Brown", "Taylor", "Clark", "Patel", "Khan",
        "Robertson", "Thomson", "Anderson", "Scott", "Ross", "Young", "Watson", "Fraser", "Henderson", "Morrison"]
PLACES = ["Princes Street", "Leith Walk", "Glasgow Central", "Aberdeen Union Street", "Dundee City Square", "Stirling Station"]
MERCHANTS_OK = ["Tesco", "Sainsbury's", "Amazon UK", "Boots", "Costa Coffee", "Shell", "Greggs", "Argos"]
MERCHANTS_RISK = ["QuickCash Online", "GlobalBet Ltd", "Zenith Electronics", "LuxWatch Direct", "CryptoNow"]

VULN_TEXT = ["I have been struggling to pay my rent since this happened.", "I am a full-time carer and cannot deal with this easily.",
             "My husband died last month and I am handling everything alone.", "I suffer from depression and this is making it worse.",
             "I am partially sighted and find the statements hard to check.", "I lost my job in September and every pound counts."]
LEGAL_TEXT = ["If this is not put right I will take legal action.", "I will be contacting my solicitor if you do not respond.",
              "I am prepared to take you to court over this."]
ANGRY = "I am furious and this is unacceptable."
MILD = "I am upset about this."

TEMPLATES = {
    "DUPLICATE_CHARGE": {
        "uphold": ["I was charged a monthly fee of £{a} twice on {d}. Please refund the duplicate fee.",
                   "My account shows a double charge. The same fee of £{a} came out two times and I want it put right.",
                   "You have taken a wrong fee from my current account. Can you check and correct it?"],
        "reject": ["I want to query the monthly fee of £{a} on my account. Please refund it.",
                   "There is a fee of £{a} on my statement and I believe it is a wrong fee. Please check it."],
    },
    "ATM_PAYMENT_FAILURE": {
        "uphold": ["I used the cash machine at {p} and it did not dispense the full £{a}, but my account was debited.",
                   "The ATM gave me less cash than the amount taken from my account. I asked for £{a}."],
        "reject": ["I used the cash machine at {p} and it did not dispense the full £{a}, but my account was debited.",
                   "My card payment failed at the shop yet the money has left my account."],
    },
    "UNAUTHORISED_TXN": {
        "uphold": ["There are transactions on my card that I did not make. Please investigate this fraud.",
                   "I do not recognise a payment of £{a} on my card statement. I think my card was stolen and used in a fraudulent way.",
                   "Someone used my card without permission - an unauthorised payment of £{a} was made. I think it is a scam."],
        "reject": ["There are transactions on my card that I did not make. Please investigate this fraud.",
                   "Someone used my card without permission - an unauthorised payment of £{a} was made. I think it is a scam."],
    },
    "MORTGAGE_LOAN_DISPUTE": {
        "uphold": ["I am querying an amount of £{a} taken on my mortgage account for early repayment. I believe it was not due.",
                   "My lender applied an admin cost of £{a} to my loan. I think this is not allowed under the contract."],
        "reject": ["I am querying an amount of £{a} taken on my mortgage account for early repayment. I believe it was not due.",
                   "My lender applied a cost of £{a} to my loan. I think this is not allowed under the contract."],
    },
    "ACCOUNT_CLOSURE": {
        "uphold": ["I asked you to close my account on {d} but it is still open and I keep paying for it.",
                   "I wrote to close my account weeks ago and the closure still has not happened."],
        "reject": ["I asked you to close my account on {d} but it is still open and I keep paying for it.",
                   "Please cancel my account and sort out my switching to another bank. It is taking too long."],
    },
    "DATA_PRIVACY": {
        "uphold": ["I made a subject access request about my personal data and have not had a reply.",
                   "I am concerned about my privacy. You shared my details with another company without asking me."],
        "reject": ["I made a subject access request about my personal data and have not had a reply.",
                   "I am concerned about my privacy. You shared my details with another company without asking me."],
    },
}
AMBIGUOUS = {   # short, clear base sentence + a competing-intent sentence => confidence < 0.90
    "DUPLICATE_CHARGE": "You have taken a wrong fee from my current account. I also asked about my mortgage and loan.",
    "ATM_PAYMENT_FAILURE": "The ATM did not dispense the cash. I was also charged a fee.",
    "UNAUTHORISED_TXN": "There are transactions I did not make. My fee was also wrong.",
    "MORTGAGE_LOAN_DISPUTE": "My lender took an amount for my loan. I also needed some cash that day.",
    "ACCOUNT_CLOSURE": "I asked to close my account weeks ago. Also a fee was taken.",
    "DATA_PRIVACY": "I have a concern about my personal data. I also have a question about my loan.",
}


def _comp(outcome: str, refund: float, intent: str, vulnerable: bool) -> float:
    if outcome == "reject":
        return 0.0
    if outcome == "partial_uphold":
        return 25.0
    if refund >= 1000:
        return 500.0
    if refund >= 250 or intent == "UNAUTHORISED_TXN" or (vulnerable and refund >= 100):
        return 200.0
    return 25.0


def _authority(total: float) -> str:
    return "cv:Authority/ANALYST" if total <= 50 else "cv:Authority/LEAD" if total <= 250 else \
        "cv:Authority/MANAGER" if total <= 1000 else "cv:Authority/EXECUTIVE"


def seed(conn: sqlite3.Connection, n_seed: int = 42, anchor: datetime = ANCHOR) -> int:
    rng = random.Random(n_seed)
    db.init_db(conn)
    plan: list[str] = [i for i, c in INTENT_COUNTS for _ in range(c)]
    rng.shuffle(plan)
    n = len(plan)
    idx = list(range(n))
    vuln = set(rng.sample(idx, 42))
    vuln_src = {i: k % 3 for k, i in enumerate(sorted(vuln))}       # 0 text, 1 crm flag, 2 age
    rest = [i for i in idx if i not in vuln]
    legal = set(rng.sample(rest, 15))
    deadline = set(rng.sample([i for i in rest if i not in legal], 8))
    ambiguous = set(rng.sample([i for i in rest if i not in legal and i not in deadline], 12))
    angry = set(rng.sample(idx, 20))
    mild = set(rng.sample([i for i in idx if i not in angry], 30))

    conn.execute("BEGIN")
    for i, intent in enumerate(plan):
        k = i + 1
        cid, cust, acct, cmp_id = f"CUS-{k:05d}", None, f"ACC-{k:05d}", f"CMP-{10000 + k}"
        cust = cid
        name = f"{rng.choice(FIRST)} {rng.choice(LAST)}"
        v, v_src = i in vuln, vuln_src.get(i)
        if v and v_src == 2:
            dob = datetime(rng.randint(1936, 1949), rng.randint(1, 12), rng.randint(1, 28))
        else:
            dob = datetime(rng.randint(1958, 2002), rng.randint(1, 12), rng.randint(1, 28))
        conn.execute("INSERT INTO customers VALUES (?,?,?,?,?,?,?)",
                     (cust, name, f"{name.split()[0].lower()}.{k}@example.com", rng.choice(["Standard"] * 6 + ["Premier"] * 2 + ["Wealth", "SME"]),
                      dob.strftime("%Y-%m-%d"), 1 if (v and v_src == 1) else 0,
                      "Vulnerability marker recorded by branch colleague" if (v and v_src == 1) else None))
        product = {"MORTGAGE_LOAN_DISPUTE": "Mortgage", "UNAUTHORISED_TXN": rng.choice(["Current Account", "Credit Card"])}.get(intent, "Current Account")
        conn.execute("INSERT INTO accounts VALUES (?,?,?,?)", (acct, cust, product, round(rng.uniform(-400, 9000), 2)))

        days_ago = 55 if i in deadline else rng.randint(0, 30)
        received = anchor - timedelta(days=days_ago, hours=rng.randint(0, 10), minutes=rng.randint(0, 59))
        received = received.replace(second=0, microsecond=0)

        def when(back_days: float) -> str:
            return fmt_ts(received - timedelta(days=back_days, hours=rng.randint(0, 8)))

        # background activity so evidence retrieval is realistic
        for t in range(rng.randint(6, 12)):
            conn.execute("INSERT INTO transactions VALUES (?,?,?,?,?,?,?,?,?,?)",
                         (f"TX-{k:05d}-B{t}", acct, when(rng.uniform(1, 88)), rng.choice(["CARD_PURCHASE", "DIRECT_DEBIT", "TRANSFER", "CREDIT"]),
                          round(rng.uniform(-150, 800), 2), rng.choice(MERCHANTS_OK), "POSTED", None, None, None))

        outcome = "uphold"
        r = rng.random()
        refund = 0.0
        ev_text = {"a": 0, "d": received.strftime("%d %B"), "p": rng.choice(PLACES)}
        if intent == "DUPLICATE_CHARGE":
            outcome = "reject" if r < 0.25 else "uphold"
            fee = rng.choice([5.0, 8.5, 12.0, 15.0, 20.0, 25.0, 35.0])
            cnt = rng.choice([1, 1, 1, 2, 2, 3]) if outcome == "uphold" else 1
            if outcome == "uphold" and rng.random() < 0.08:
                fee, cnt = rng.choice([30.0, 35.0]), rng.choice([4, 5, 6])
            for j in range(cnt):
                conn.execute("INSERT INTO transactions VALUES (?,?,?,?,?,?,?,?,?,?)",
                             (f"TX-{k:05d}-F{j}", acct, when(80 - j * 14 if outcome == "uphold" else 20 + j), "FEE", -fee, "Clearview", "POSTED", 1,
                              "MONTHLY_ACCOUNT_FEE", None))
                if outcome == "uphold":
                    conn.execute("INSERT INTO transactions VALUES (?,?,?,?,?,?,?,?,?,?)",
                                 (f"TX-{k:05d}-D{j}", acct, when(80 - j * 14 - 0.01), "FEE", -fee, "Clearview", "POSTED", 0, "DUPLICATE_FEE", f"TX-{k:05d}-F{j}"))
                    refund += fee
            ev_text["a"] = f"{fee:g}"
        elif intent == "ATM_PAYMENT_FAILURE":
            outcome = "reject" if r < 0.25 else "uphold"
            debited = float(rng.choice([20, 40, 50, 60, 80, 100, 150, 200, 250, 300]))
            short = min(debited, float(rng.choice([20, 40, 60, 100])) if rng.random() > 0.2 else float(rng.choice([150, 200, 250])))
            if short >= debited:
                short = debited / 2
            dispensed = debited - short if outcome == "uphold" else debited
            conn.execute("INSERT INTO transactions VALUES (?,?,?,?,?,?,?,?,?,?)",
                         (f"TX-{k:05d}-A", acct, when(rng.uniform(2, 20)), "ATM_WITHDRAWAL", -debited, rng.choice(PLACES), "POSTED", None, None, None))
            conn.execute("INSERT INTO card_disputes VALUES (?,?,?,?,?,?,?,?,?)",
                         (f"DSP-{k:05d}", acct, f"TX-{k:05d}-A", debited, dispensed, 0.05, 1, "LOW", "OPEN"))
            refund = short if outcome == "uphold" else 0.0
            ev_text["a"] = f"{debited:g}"
        elif intent == "UNAUTHORISED_TXN":
            outcome = "reject" if r < 0.2 else "partial_uphold" if r < 0.35 else "uphold"
            n_tx = rng.randint(1, 3)
            total = 0.0
            for j in range(n_tx):
                amt = round(rng.choice([29.99, 45.0, 89.5, 120.0, 250.0, 399.0, 640.0, 900.0]) if outcome != "reject" else rng.uniform(10, 60), 2)
                total += amt
                score, present, risk = {"uphold": (round(rng.uniform(0.65, 0.98), 2), 0, "HIGH"),
                                        "partial_uphold": (round(rng.uniform(0.35, 0.55), 2), 0, "LOW"),
                                        "reject": (round(rng.uniform(0.02, 0.2), 2), 1, "LOW")}[outcome]
                conn.execute("INSERT INTO transactions VALUES (?,?,?,?,?,?,?,?,?,?)",
                             (f"TX-{k:05d}-U{j}", acct, when(rng.uniform(1, 15)), "CARD_PURCHASE", -amt,
                              rng.choice(MERCHANTS_RISK if risk == "HIGH" else MERCHANTS_OK), "POSTED", None, None, None))
                conn.execute("INSERT INTO card_disputes VALUES (?,?,?,?,?,?,?,?,?)",
                             (f"DSP-{k:05d}-{j}", acct, f"TX-{k:05d}-U{j}", amt, None, score, present, risk, "OPEN"))
            total = round(total, 2)
            refund = total if outcome == "uphold" else round(total * 0.5, 2) if outcome == "partial_uphold" else 0.0
            ev_text["a"] = f"{total:g}"
        elif intent == "MORTGAGE_LOAN_DISPUTE":
            outcome = "reject" if r < 0.4 else "uphold"
            amt = float(rng.choice([45, 75, 120, 250, 395]))
            conn.execute("INSERT INTO transactions VALUES (?,?,?,?,?,?,?,?,?,?)",
                         (f"TX-{k:05d}-M", acct, when(rng.uniform(3, 40)), "FEE", -amt, "Clearview Mortgages", "POSTED",
                          0 if outcome == "uphold" else 1, "NO_CONTRACTUAL_BASIS" if outcome == "uphold" else "EARLY_REPAYMENT_CHARGE", None))
            refund = amt if outcome == "uphold" else 0.0
            ev_text["a"] = f"{amt:g}"
        elif intent == "ACCOUNT_CLOSURE":
            outcome = "reject" if r < 0.3 else "uphold"
            days_open = rng.randint(2, 5) if outcome == "reject" else rng.randint(9, 25)
            opened = received - timedelta(days=days_open, hours=1)
            conn.execute("INSERT INTO crm_cases VALUES (?,?,?,?,?,?)",
                         (f"CRM-{k:05d}", cust, "CLOSURE_REQUEST", fmt_ts(opened), None, "Customer requested account closure"))
            if outcome == "uphold":
                for j in range(rng.randint(0, 3)):
                    amt = float(rng.choice([5, 8, 12, 15]))
                    refund += amt
                    conn.execute("INSERT INTO transactions VALUES (?,?,?,?,?,?,?,?,?,?)",
                                 (f"TX-{k:05d}-C{j}", acct, fmt_ts(opened + timedelta(days=2 + j * 3)), "FEE", -amt, "Clearview", "POSTED", 0, "FEE_AFTER_CLOSURE_REQUEST", None))
            ev_text["d"] = opened.strftime("%d %B")
        else:  # DATA_PRIVACY
            outcome = "reject" if r < 0.3 else "uphold"
            days_open = rng.randint(8, 24) if outcome == "reject" else rng.randint(36, 60)
            conn.execute("INSERT INTO crm_cases VALUES (?,?,?,?,?,?)",
                         (f"CRM-{k:05d}", cust, "DSAR", fmt_ts(received - timedelta(days=days_open, hours=1)), None, "Subject access request"))
        # extra CRM + call history
        if rng.random() < 0.5:
            conn.execute("INSERT INTO crm_cases VALUES (?,?,?,?,?,?)",
                         (f"CRM-{k:05d}-S", cust, "SERVICE_REQUEST", when(rng.uniform(5, 80)), when(rng.uniform(1, 4)), "Address update"))
        for j in range(rng.randint(0, 2)):
            conn.execute("INSERT INTO call_transcripts VALUES (?,?,?,?)",
                         (f"CALL-{k:05d}-{j}", cust, when(rng.uniform(1, 30)), "Customer called regarding their account; agent logged the query and advised a written complaint."))

        # complaint text
        if i in ambiguous:
            text = AMBIGUOUS[intent]
        else:
            text = rng.choice(TEMPLATES[intent]["uphold" if outcome != "reject" else "reject"]).format(**ev_text)
        if v and v_src == 0:
            text += " " + rng.choice(VULN_TEXT)
        if i in legal:
            text += " " + rng.choice(LEGAL_TEXT)
        if i in angry:
            text += " " + ANGRY
        elif i in mild:
            text += " " + MILD
        channel = rng.choice(CHANNELS)
        sentiment_neg = 2 if i in angry else 1 if i in mild else 0
        deadline_risk = i in deadline

        src_due = add_business_days(received, 3)
        fca_deadline = received + timedelta(weeks=8)
        conn.execute("INSERT INTO complaints(id, customer_id, account_id, channel, text, received_at, src_due, fca_deadline, status) VALUES (?,?,?,?,?,?,?,?,?)",
                     (cmp_id, cust, acct, channel, text, fmt_ts(received), fmt_ts(src_due), fmt_ts(fca_deadline), "RECEIVED"))

        # ground truth -----------------------------------------------------------------------------
        refund = round(refund, 2)
        comp = _comp(outcome, refund, intent, v)
        redress = round(refund + comp, 2)
        pr = BASE_PRIORITY[intent]
        if pr == "P3" and (sentiment_neg == 2 or (sentiment_neg == 1 and channel == "Social Media")):
            pr = "P2"
        if v or i in legal or deadline_risk:
            pr = "P1"
        hitl = int(v or i in legal or deadline_risk or intent == "DATA_PRIVACY" or redress > config.HITL_REDRESS_LIMIT
                   or outcome == "reject" or i in ambiguous)
        conn.execute("INSERT INTO ground_truth VALUES (?,?,?,?,?,?,?,?)",
                     (cmp_id, intent, int(v), int(i in legal), pr, outcome, redress, hitl))
    conn.execute("COMMIT")
    return n


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--reset", action="store_true", help="delete existing database first")
    args = ap.parse_args()
    if args.reset and config.DB_PATH.exists():
        for suffix in ("", "-wal", "-shm"):
            p = config.DB_PATH.with_name(config.DB_PATH.name + suffix)
            p.unlink(missing_ok=True)
    conn = db.connect()
    existing = conn.execute("SELECT name FROM sqlite_master WHERE name='complaints'").fetchone()
    if existing and conn.execute("SELECT COUNT(*) FROM complaints").fetchone()[0]:
        print("database already seeded (use --reset to rebuild)")
        return
    print(f"seeded {seed(conn)} complaints into {config.DB_PATH}")


if __name__ == "__main__":
    main()

