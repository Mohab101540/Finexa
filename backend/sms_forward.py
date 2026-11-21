import hashlib
import secrets
from contextlib import closing
from datetime import datetime, timedelta

import users
from sms_parser import parse_sms

KEEP_DAYS = 120
MAX_PER_USER = 1000

SCHEMA = """
CREATE TABLE IF NOT EXISTS forward_keys (key_hash TEXT PRIMARY KEY, user_id INTEGER NOT NULL UNIQUE);
CREATE TABLE IF NOT EXISTS forwarded_sms (
    id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL, sender TEXT NOT NULL, date TEXT NOT NULL, body TEXT NOT NULL
);
"""


def connect():
    con = users.connect()
    con.executescript(SCHEMA)
    return con


def key_hash(key):
    return hashlib.sha256(key.encode()).hexdigest()


def new_key(user_id):
    key = "fx_" + secrets.token_urlsafe(24)
    with closing(connect()) as con, con:
        con.execute("DELETE FROM forward_keys WHERE user_id = ?", (user_id,))
        con.execute("INSERT INTO forward_keys VALUES (?, ?)", (key_hash(key), user_id))
    return key


def user_for_key(key):
    with closing(connect()) as con:
        row = con.execute("SELECT user_id FROM forward_keys WHERE key_hash = ?", (key_hash(key or ""),)).fetchone()
    return row and row["user_id"]


def save(user_id, sender, body, when):
    sms = {"id": None, "sender": sender or "Unknown", "date": when.isoformat(timespec="seconds"), "body": body}
    parsed = parse_sms(sms)
    if not (parsed["amount"] and parsed["direction"]):
        return None
    with closing(connect()) as con, con:
        con.execute("INSERT INTO forwarded_sms (user_id, sender, date, body) VALUES (?, ?, ?, ?)",
                    (user_id, sms["sender"], sms["date"], body))
        con.execute("DELETE FROM forwarded_sms WHERE user_id = ? AND date < ?",
                    (user_id, (when - timedelta(days=KEEP_DAYS)).isoformat(timespec="seconds")))
        con.execute("DELETE FROM forwarded_sms WHERE user_id = ? AND id NOT IN "
                    "(SELECT id FROM forwarded_sms WHERE user_id = ? ORDER BY date DESC LIMIT ?)",
                    (user_id, user_id, MAX_PER_USER))
    return parsed


def messages(user_id):
    with closing(connect()) as con:
        rows = con.execute("SELECT id, sender, date, body FROM forwarded_sms WHERE user_id = ? ORDER BY date",
                           (user_id,)).fetchall()
    return [{"id": f"fwd{r['id']}", "sender": r["sender"], "date": r["date"], "body": r["body"]} for r in rows]


def delete_all(user_id):
    with closing(connect()) as con, con:
        return con.execute("DELETE FROM forwarded_sms WHERE user_id = ?", (user_id,)).rowcount
