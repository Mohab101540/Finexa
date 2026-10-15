import base64
import binascii
import hashlib
import json
import os
import sqlite3
from contextlib import closing
from pathlib import Path

from classifier import ml_classify
from payers import FLAG_TOLERANCE, FLAG_WINDOW, circular_pairs, classify_history
from sms_parser import parse_sms

BACKEND = Path(__file__).resolve().parent
DB_PATH = Path(os.environ.get("FINEXA_DB", BACKEND / "finexa.db"))
EVIDENCE_DIR = BACKEND / "evidence"
VERIFIED_EXAMPLES = BACKEND.parent / "data" / "private" / "verified_examples.jsonl"

STATUSES = ["needs_review", "user_reported", "awaiting_evidence", "verified", "flagged", "reversed"]
ANSWERS = {
    "gig": "Gig work or delivery earnings",
    "freelance": "Freelance work or a client",
    "atm_cash": "Cash earnings deposited through an ATM",
    "customer": "Payment from a customer or business",
    "family": "Transfer from a friend or family member",
    "own_accounts": "Refund, savings, or transfer between my own accounts",
    "other": "Something else",
}
INCOME_ANSWERS = {"gig", "freelance", "atm_cash", "customer"}
CAN_ANSWER = {"needs_review", "user_reported", "awaiting_evidence"}
MAX_IMAGE_BYTES = 5_000_000
IMAGE_TYPES = {b"\xff\xd8\xff": "jpg", b"\x89PNG": "png", b"RIFF": "webp"}

SCHEMA = """
CREATE TABLE IF NOT EXISTS transactions (
    id TEXT PRIMARY KEY,          -- tx_id(): fingerprint of sender + date + text
    sender TEXT, date TEXT, body TEXT, amount REAL,
    counterparty TEXT,            -- the person who sent the money, if the SMS names them
    ml_label TEXT, ml_confidence REAL,
    status TEXT NOT NULL,
    answer TEXT, details TEXT, evidence TEXT, evidence_file TEXT,
    remembered INTEGER DEFAULT 0, -- 1 = answer copied from an earlier payment by the same person
    flag_reason TEXT
);
CREATE TABLE IF NOT EXISTS senders (
    counterparty TEXT PRIMARY KEY,
    answer TEXT, details TEXT, status TEXT
);
"""


def connect():
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    con.executescript(SCHEMA)
    return con


def tx_id(sms):
    return hashlib.sha1(f"{sms['sender']}|{sms['date']}|{sms['body']}".encode()).hexdigest()[:16]


def family_payers():
    with closing(connect()) as con:
        return {row["counterparty"] for row in con.execute("SELECT counterparty FROM senders WHERE answer = 'family'")}


def circular_flags(sms_list):
    flags = {}
    for sms, p, _, o in circular_pairs([(sms, parse_sms(sms)) for sms in sms_list]):
        gap = o["date"] - p["date"]
        flags[tx_id(sms)] = (f"EGP {p['amount']:,.0f} came in at {p['date']:%H:%M} and EGP {o['amount']:,.0f} "
                             f"went out {int(gap.total_seconds() // 60)} minutes later → looks like money "
                             "passing through, not income")
    return flags


def needs_survey(label, ml):
    return label not in ("salary", "gig_income") and (ml["label"] == "needs_review" or ml["best_guess"] == "transfer_in")


def review_dict(row):
    return {"tx_id": row["id"], "status": row["status"], "answer": row["answer"], "details": row["details"],
            "evidence": row["evidence"], "remembered": bool(row["remembered"]), "flag_reason": row["flag_reason"],
            "amount": row["amount"], "counterparty": row["counterparty"]}


def reviews_for(sms_list):
    flags = circular_flags(sms_list)
    labels = classify_history(sms_list, not_salary=family_payers())
    reviews = {}
    with closing(connect()) as con, con:
        for sms, (label, _) in zip(sms_list, labels):
            p = parse_sms(sms)
            if p["direction"] != "in" or p["amount"] is None:
                continue
            tid = tx_id(sms)
            row = con.execute("SELECT * FROM transactions WHERE id = ?", (tid,)).fetchone()
            if row is None:
                ml = ml_classify(sms)
                known = p["counterparty"] and con.execute("SELECT * FROM senders WHERE counterparty = ?",
                                                          (p["counterparty"],)).fetchone()
                if tid in flags:
                    status, answer, details = "flagged", None, None
                elif known:
                    status = "verified" if known["status"] == "verified" else "user_reported"
                    answer, details = known["answer"], known["details"]
                elif needs_survey(label, ml):
                    status, answer, details = "needs_review", None, None
                else:
                    continue
                con.execute("INSERT INTO transactions (id, sender, date, body, amount, counterparty, ml_label, "
                            "ml_confidence, status, answer, details, remembered, flag_reason) "
                            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                            (tid, sms["sender"], sms["date"], sms["body"], p["amount"], p["counterparty"],
                             ml["best_guess"], ml["confidence"], status, answer, details, int(bool(known)),
                             flags.get(tid)))
            elif tid in flags and row["status"] != "flagged":
                con.execute("UPDATE transactions SET status = 'flagged', flag_reason = ? WHERE id = ?",
                            (flags[tid], tid))
            reviews[tid] = review_dict(con.execute("SELECT * FROM transactions WHERE id = ?", (tid,)).fetchone())
    return reviews


def with_verified_gig(sms_list, reviews):
    def counts(sms):
        r = reviews.get(tx_id(sms))
        return r and r["status"] == "verified" and r["answer"] in INCOME_ANSWERS
    return [{**sms, "verified_gig": True} if counts(sms) else sms for sms in sms_list]


def save_image(tid, image_b64):
    try:
        data = base64.b64decode(image_b64, validate=True)
    except binascii.Error:
        raise ValueError("image is not valid base64")
    if len(data) > MAX_IMAGE_BYTES:
        raise ValueError("image is larger than 5 MB")
    ext = next((e for magic, e in IMAGE_TYPES.items() if data.startswith(magic)), None)
    if ext is None:
        raise ValueError("image must be a JPEG, PNG or WebP")
    EVIDENCE_DIR.mkdir(exist_ok=True)
    path = EVIDENCE_DIR / f"{tid}.{ext}"
    path.write_bytes(data)
    return path.name


def answer_survey(tid, answer, details, evidence, image_b64=None):
    with closing(connect()) as con, con:
        row = con.execute("SELECT * FROM transactions WHERE id = ?", (tid,)).fetchone()
        if row is None:
            raise LookupError("unknown payment")
        if row["status"] not in CAN_ANSWER:
            raise ValueError(f"a {row['status']} payment can't be answered again")
        if evidence == "now" and not image_b64:
            raise ValueError('"I can submit proof now" needs an image')
        evidence_file = save_image(tid, image_b64) if evidence == "now" else None
        status = "awaiting_evidence" if evidence == "later" else "user_reported"
        con.execute("UPDATE transactions SET status = ?, answer = ?, details = ?, evidence = ?, evidence_file = ?, "
                    "remembered = 0 WHERE id = ?", (status, answer, details, evidence, evidence_file, tid))
        if row["counterparty"]:
            con.execute("INSERT OR REPLACE INTO senders VALUES (?, ?, ?, ?)",
                        (row["counterparty"], answer, details, status))
        return review_dict(con.execute("SELECT * FROM transactions WHERE id = ?", (tid,)).fetchone())


def verify(tid):
    with closing(connect()) as con, con:
        row = con.execute("SELECT * FROM transactions WHERE id = ?", (tid,)).fetchone()
        if row is None:
            raise LookupError("unknown payment")
        if row["status"] not in ("user_reported", "awaiting_evidence"):
            raise ValueError(f"only an answered payment can be verified (this one is {row['status']})")
        con.execute("UPDATE transactions SET status = 'verified' WHERE id = ?", (tid,))
        if row["counterparty"]:
            con.execute("UPDATE senders SET status = 'verified' WHERE counterparty = ?", (row["counterparty"],))
        VERIFIED_EXAMPLES.parent.mkdir(parents=True, exist_ok=True)
        with open(VERIFIED_EXAMPLES, "a", encoding="utf-8") as f:
            label = "gig_income" if row["answer"] in INCOME_ANSWERS else "transfer_in"
            f.write(json.dumps({"tx_id": tid, "sender": row["sender"], "date": row["date"], "body": row["body"],
                                "label": label, "answer": row["answer"]}, ensure_ascii=False) + "\n")
        return review_dict(con.execute("SELECT * FROM transactions WHERE id = ?", (tid,)).fetchone())
