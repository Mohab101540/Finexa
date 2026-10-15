import math
from collections import defaultdict
from datetime import date, datetime, timedelta
from statistics import mean, pstdev

import numpy as np
from sklearn.linear_model import LogisticRegression

from payers import circular_pairs

MIN_HISTORY = 3
MAX_RATIO = 5.0
PRE_PAYDAY_DAYS = 5
MAX_BALANCE_PCT = 1.0

FEATURES = {
    "payday_spread_days": ("Spread of salary arrival days", -1),
    "salary_months": ("Months of salary history", +1),
    "late_days_3m": ("Late days in the last 3 paydays", -1),
    "missed_months": ("Paydays passed with no salary (yet)", -1),
    "months_since_last_salary": ("Months since the last salary", -1),
    "consecutive_missed": ("Missed paydays in a row (up to now)", -1),
    "amount_change": ("Last salary vs earlier average", 0),
    "pre_payday_balance_pct": ("Lowest balance in 5 days before payday, as a share of the average salary", +1),
    "spend_income_ratio": ("Money out ÷ money in, last 3 months", -1),
    "transfer_in_share": ("Share of money in from personal transfers", 0),
}


def month_index(d):
    return d.year * 12 + d.month - 1

def month_start(m):
    return date(m // 12, m % 12 + 1, 1)

def month_name(m):
    return f"{m // 12}-{m % 12 + 1:02d}"


def history_rows(items):
    kept = [(s, p, label) for s, p, label in items if label != "ignore"]
    flagged = set()
    for s_in, _, s_out, _ in circular_pairs([(s, p) for s, p, _ in kept]):
        flagged |= {id(s_in), id(s_out)}
    removed = [(s, label) for s, _, label in kept if id(s) in flagged]
    rows = sorted(({"date": p["date"], "label": label, "amount": p["amount"], "sender": s["sender"],
                    "balance": p["balance"]}
                   for s, p, label in kept if id(s) not in flagged and p["amount"] is not None),
                  key=lambda r: r["date"])
    return rows, removed


def pay_cycle(d, late_payer):
    return month_index(d - timedelta(days=14)) if late_payer else month_index(d)

def recent_gig_income(user_sms, m, cutoff):
    return sum(s["amount"] for s in user_sms
               if s["label"] == "gig_income" and s["date"] < cutoff and month_index(s["date"]) >= m - 2)


def features(user_sms, m, cutoff=None, notes=None):
    cutoff = cutoff or datetime.combine(month_start(m + 1), datetime.min.time())
    seen = [s for s in user_sms if s["date"] < cutoff]
    deposits = [s for s in seen if s["label"] == "salary"]
    if not deposits:
        return None
    late_payer = sum(s["date"].day >= 20 for s in deposits) * 2 > len(deposits)
    cycles = {}
    for s in deposits:
        cycles.setdefault(pay_cycle(s["date"], late_payer), s)
    offset = {c: (s["date"].date() - month_start(c)).days for c, s in cycles.items()}
    payday = min(offset.values())
    late = {c: o - payday for c, o in offset.items()}
    payday_passed = [c for c in range(min(cycles), m + 1) if month_start(c) + timedelta(days=payday) < cutoff.date()]
    missed = sum(1 for c in payday_passed if c not in cycles)

    order = sorted(cycles)
    in_a_row = sum(1 for c in payday_passed if c > order[-1])
    last = cycles[order[-1]]
    earlier = [cycles[c]["amount"] for c in order[:-1]]
    average_salary = mean(s["amount"] for s in cycles.values())

    window = [s["balance"] for s in seen if s["sender"] == last["sender"] and s["balance"] is not None
              and last["date"] - timedelta(days=PRE_PAYDAY_DAYS) <= s["date"] < last["date"]]
    just_before = None if last["balance"] is None else last["balance"] - last["amount"]
    balances = window + ([just_before] if just_before is not None else [])
    if notes is not None and not window:
        notes.append("balance_from_salary_sms" if balances else "no_balance")

    recent = defaultdict(float)
    for s in seen:
        if month_index(s["date"]) >= m - 2:
            recent[s["label"]] += s["amount"]
    money_in = recent["salary"] + recent["transfer_in"]
    money_out = recent["spending"] + recent["transfer_out"]
    return {
        "payday_spread_days": pstdev(late.values()),
        "salary_months": len(cycles),
        "late_days_3m": sum(v for c, v in late.items() if c >= m - 2),
        "missed_months": missed,
        "months_since_last_salary": m - order[-1],
        "consecutive_missed": in_a_row,
        "amount_change": last["amount"] / mean(earlier) - 1 if earlier else 0.0,
        "pre_payday_balance_pct": min(min(balances) / average_salary, MAX_BALANCE_PCT) if balances else None,
        "spend_income_ratio": min(money_out / money_in, MAX_RATIO) if money_in else MAX_RATIO,
        "transfer_in_share": recent["transfer_in"] / money_in if money_in else 0.0,
    }


class CalibratedEBM:
    def __init__(self, ebm, a=1.0, b=0.0):
        self.ebm, self.a, self.b = ebm, a, b

    @classmethod
    def fit(cls, ebm, X_cal, y_cal):
        platt = LogisticRegression(C=1e6).fit(ebm.decision_function(X_cal).reshape(-1, 1), y_cal)
        return cls(ebm, float(platt.coef_[0, 0]), float(platt.intercept_[0]))

    def decision_function(self, X):
        return self.a * self.ebm.decision_function(X) + self.b

    def predict_proba(self, X):
        p = 1 / (1 + np.exp(-self.decision_function(X)))
        return np.column_stack([1 - p, p])

def contributions(model, x):
    parts = model.a * model.ebm.eval_terms(x)[0]
    start = model.a * float(np.ravel(model.ebm.intercept_)[0]) + model.b
    score = float(model.decision_function(x)[0])
    assert abs(start + parts.sum() - score) < 1e-6, "contributions don't add up to the model's score"
    assert abs(1 / (1 + math.exp(-score)) - model.predict_proba(x)[0, 1]) < 1e-6, "score doesn't match the probability"
    return start, dict(zip(model.ebm.term_names_, parts)), score
