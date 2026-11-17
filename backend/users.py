import hashlib
import hmac
import os
import secrets
import sqlite3
from contextlib import closing
from datetime import datetime, timedelta

import db
from explainer import NEXT_TIER, STREAK_NEEDED

SESSION_DAYS = 30
MAX_FAILED_LOGINS, LOCKOUT_MINUTES = 5, 15


class TooManyAttempts(Exception):
    pass


def now():
    return datetime.now()

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY,
    phone TEXT UNIQUE NOT NULL,
    name TEXT NOT NULL,
    password_hash TEXT NOT NULL, salt TEXT NOT NULL,
    hr_salary REAL, employer TEXT,
    method TEXT NOT NULL DEFAULT 'bank',
    created TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS sessions (
    token_hash TEXT PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id),
    expires TEXT
);
CREATE TABLE IF NOT EXISTS failed_logins (
    phone TEXT NOT NULL,
    at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS ledger (
    id INTEGER PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id),
    type TEXT NOT NULL,
    date TEXT NOT NULL, amount REAL NOT NULL,
    method TEXT,
    on_time INTEGER
);
"""
PUBLIC = ("id", "phone", "name", "hr_salary", "employer", "method")


def connect():
    con = db.connect()
    con.executescript(SCHEMA)
    if "expires" not in [r[1] for r in con.execute("PRAGMA table_info(sessions)")]:
        con.execute("ALTER TABLE sessions ADD COLUMN expires TEXT")
    return con


def hash_password(password, salt):
    return hashlib.scrypt(password.encode(), salt=salt, n=2 ** 14, r=8, p=1).hex()


def token_hash(token):
    return hashlib.sha256(token.encode()).hexdigest()


def public(row):
    return {k: row[k] for k in PUBLIC}


def signup(phone, name, password, hr_salary=None, employer=None, method="bank"):
    salt = os.urandom(16)
    with closing(connect()) as con, con:
        try:
            cur = con.execute("INSERT INTO users (phone, name, password_hash, salt, hr_salary, employer, method, created) "
                              "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                              (phone, name, hash_password(password, salt), salt.hex(), hr_salary, employer, method,
                               datetime.now().isoformat(timespec="seconds")))
        except sqlite3.IntegrityError:
            raise ValueError("this phone number already has an account")
        return public(con.execute("SELECT * FROM users WHERE id = ?", (cur.lastrowid,)).fetchone())


def login(phone, password):
    stamp = lambda t: t.isoformat(timespec="seconds")
    with closing(connect()) as con, con:
        recent = con.execute("SELECT COUNT(*) FROM failed_logins WHERE phone = ? AND at > ?",
                             (phone, stamp(now() - timedelta(minutes=LOCKOUT_MINUTES)))).fetchone()[0]
        if recent >= MAX_FAILED_LOGINS:
            raise TooManyAttempts(f"too many wrong attempts, try again in {LOCKOUT_MINUTES} minutes")
        row = con.execute("SELECT * FROM users WHERE phone = ?", (phone,)).fetchone()
        salt = bytes.fromhex(row["salt"]) if row else bytes(16)
        good = hmac.compare_digest(hash_password(password, salt), row["password_hash"] if row else "0" * 128)
        if not (row and good):
            con.execute("INSERT INTO failed_logins (phone, at) VALUES (?, ?)", (phone, stamp(now())))
            con.commit()
            raise PermissionError("wrong phone or password")
        con.execute("DELETE FROM failed_logins WHERE phone = ?", (phone,))
        token = secrets.token_urlsafe(32)
        con.execute("INSERT INTO sessions (token_hash, user_id, expires) VALUES (?, ?, ?)",
                    (token_hash(token), row["id"], stamp(now() + timedelta(days=SESSION_DAYS))))
        return token, public(row)


def user_for(token):
    with closing(connect()) as con:
        row = con.execute("SELECT u.* FROM users u JOIN sessions s ON s.user_id = u.id "
                          "WHERE s.token_hash = ? AND s.expires > ?",
                          (token_hash(token), now().isoformat(timespec="seconds"))).fetchone()
    return row and public(row)


def add_entry(user_id, type, date, amount, method=None, on_time=None):
    with closing(connect()) as con, con:
        con.execute("INSERT INTO ledger (user_id, type, date, amount, method, on_time) VALUES (?, ?, ?, ?, ?, ?)",
                    (user_id, type, date, amount, method, None if on_time is None else int(on_time)))


def withdraw(user_id, date, amount, method):
    add_entry(user_id, "withdrawal", date, amount, method=method)


def repay(user_id, date, amount, on_time):
    add_entry(user_id, "repayment", date, amount, on_time=on_time)


def ledger(user_id):
    with closing(connect()) as con:
        rows = con.execute("SELECT * FROM ledger WHERE user_id = ? ORDER BY date, id", (user_id,)).fetchall()
    return [{"type": r["type"], "date": r["date"], "amount": r["amount"],
             **({"method": r["method"]} if r["type"] == "withdrawal" else {"on_time": bool(r["on_time"])})}
            for r in rows]


def tier_for(streak):
    return max((t for t, n in STREAK_NEEDED.items() if streak >= n), key=STREAK_NEEDED.get)


def standing(items):
    tier, streak = "Starter", 0
    lower = {v: k for k, v in NEXT_TIER.items()}
    for item in items:
        if item["type"] != "repayment":
            continue
        if item["on_time"]:
            streak += 1
            tier = max(tier, tier_for(streak), key=STREAK_NEEDED.get)
        else:
            streak, tier = 0, lower.get(tier, tier)
    return tier, streak
