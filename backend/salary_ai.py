import math
import pickle
from datetime import datetime, time, timedelta
from functools import cache
from pathlib import Path

import pandas as pd

from config import TODAY
from payers import labels
from salary_features import (FEATURES, MIN_HISTORY, CalibratedEBM, contributions, features, history_rows,
                             month_index, recent_gig_income)
from sms_parser import parse_sms

MODEL_PATH = Path(__file__).resolve().parent / "models" / "salary_model.pkl"

P_REVIEW, P_FULL = 0.70, 0.95
MIN_RATE, MAX_RATE = 20, 50


def ai_rate(p):
    rate = MIN_RATE + (MAX_RATE - MIN_RATE) * (p - P_REVIEW) / (P_FULL - P_REVIEW)
    return round(min(max(rate, MIN_RATE), MAX_RATE), 1), p < P_REVIEW


@cache
def load_model():
    with open(MODEL_PATH, "rb") as f:
        saved = pickle.load(f)
    return CalibratedEBM(saved["ebm"], saved["platt_a"], saved["platt_b"]), saved["fallbacks"]


def app_label(sms, parsed, label):
    label = "gig_income" if sms.get("verified_gig") else label
    return "transfer_in" if label == "ignore" and parsed["direction"] == "in" else label


def user_rows(sms_list, today=TODAY, employer=None, not_salary=()):
    known = [(sms, p) for sms in sms_list if (p := parse_sms(sms))["date"].date() <= today]
    found = labels([sms for sms, _ in known], employer, not_salary)
    return history_rows([(sms, p, app_label(sms, p, label)) for (sms, p), label in zip(known, found)])[0]


def end_of(today):
    return datetime.combine(today + timedelta(days=1), time.min)


def features_from_rows(rows, today=TODAY):
    notes = []
    f = features(rows, month_index(today), end_of(today), notes)
    if f and f["pre_payday_balance_pct"] is None:
        f["pre_payday_balance_pct"] = load_model()[1]["pre_payday_balance_pct"]
    return f, notes


def user_features(sms_list, today=TODAY, employer=None, not_salary=()):
    return features_from_rows(user_rows(sms_list, today, employer, not_salary), today)


def predict(f):
    start, parts, score = contributions(load_model()[0], pd.DataFrame([f])[list(FEATURES)].astype(float))
    return start, {k: float(v) for k, v in parts.items()}, score, 1 / (1 + math.exp(-score))


NOTES = {
    "balance_from_salary_sms": "No balance SMS from your salary account in the 5 days before payday, so the balance "
                               "just before your salary landed was used (from the salary SMS).",
    "no_balance": "No balance seen in any SMS from your salary account, so an average user's pre-payday balance "
                  "({:.0%} of the salary) was used.",
    "short_history": "Only {} of salary seen; the AI was trained on users with at least 3, so the minimum rate applies.",
}


def months(n):
    return f"{n:g} month{'' if n == 1 else 's'}"


def assess(sms_list, today=TODAY, employer=None, not_salary=()):
    rows = user_rows(sms_list, today, employer, not_salary)
    f, notes = features_from_rows(rows, today)
    if f is None:
        return None
    has_gig = recent_gig_income(rows, month_index(today), end_of(today)) > 0
    start, parts, score, p = predict(f)
    rate, needs_review = ai_rate(p)
    if f["salary_months"] < MIN_HISTORY:
        rate, needs_review = MIN_RATE, True
        notes.append("short_history")
    fallback = load_model()[1]["pre_payday_balance_pct"]
    return {"p": p, "rate": rate, "needs_review": needs_review, "features": f, "start": start,
            "contributions": parts, "score": score,
            "notes": [NOTES[n].format(months(f["salary_months"]) if n == "short_history" else fallback) for n in notes],
            "short_history": "short_history" in notes, "has_gig": has_gig}


STEADY = 0.05
def spending_base(f, has_gig):
    if not has_gig:
        return "the money that comes in"
    return "your salary" + (" and transfers in" if f["transfer_in_share"] >= 0.005 else "")


def fact(name, f, has_gig=False):
    v = f[name]
    plural = lambda n, word: f"{n:g} {word}{'' if n == 1 else 's'}"
    gig_note = "not counting your gig income, " if has_gig else ""
    return {
        "payday_spread_days": lambda: "your salary arrives on the same day every month" if v < 0.5
                                      else f"your salary day varies by about {plural(round(v), 'day')}",
        "salary_months": lambda: f"{plural(v, 'month')} of salary history",
        "late_days_3m": lambda: "no late salary in the last 3 months" if v == 0
                                else f"your salary was {plural(v, 'day')} late in total over the last 3 paydays",
        "missed_months": lambda: "no missed paydays" if v == 0 else f"{plural(v, 'payday')} passed with no salary",
        "months_since_last_salary": lambda: "this month's salary has arrived" if v == 0
                                            else f"no salary for {plural(v, 'month')} (a missed payday)",
        "consecutive_missed": lambda: "no missed paydays in a row" if v == 0 else f"{plural(v, 'missed payday')} in a row",
        "amount_change": lambda: "your salary amount is steady" if abs(v) < STEADY
                                 else f"your last salary was {abs(v):.0%} {'higher' if v > 0 else 'lower'} than your "
                                      "earlier average",
        "pre_payday_balance_pct": lambda: f"you kept {v:.0%} of your salary in the days before payday" if v >= 0
                                          else f"your balance went below zero before payday ({v:.0%} of your salary)",
        "spend_income_ratio": lambda: f"{gig_note}you spend {v:.0%} of {spending_base(f, has_gig)}",
        "transfer_in_share": lambda: "almost none of your money comes from personal transfers" if v < 0.005
                                     else f"{v:.0%} of your money in comes from personal transfers",
    }[name]()


SAME_REASON = {"consecutive_missed": "months_since_last_salary"}


def reason_scores(parts):
    out = {}
    for name, c in parts.items():
        key = SAME_REASON.get(name, name)
        out[key] = out.get(key, 0.0) + c
    return out


def join(parts):
    return parts[0] if len(parts) == 1 else ", ".join(parts[:-1]) + " and " + parts[-1]


def amount(earned, rate, cap):
    return min(earned * rate / 100, cap, earned)


BALANCE_STEP = 0.10
SPEND_STEP = 0.10


def what_if(ai, calc):
    if ai["short_history"]:
        return "Once a 3rd monthly salary arrives, the AI can set your rate from your own history.", 0.0
    if ai["rate"] >= MAX_RATE and calc["earned"] * calc["rate"] / 100 < calc["cap"]:
        return (f"What-if: your AI rate is already the maximum ({MAX_RATE}%); keep your salary on time to stay "
                "there.", 0.0)
    f, earned, cap = ai["features"], calc["earned"], calc["cap"]
    now = amount(earned, calc["rate"], cap)
    kept = f["pre_payday_balance_pct"]
    options = [("pre_payday_balance_pct", kept + BALANCE_STEP,
                f"keep {kept + BALANCE_STEP:.0%} of your salary instead of {kept:.0%} in your account in the 5 days "
                "before payday")]
    if f["spend_income_ratio"] > SPEND_STEP:
        new = f["spend_income_ratio"] - SPEND_STEP
        options.append(("spend_income_ratio", new,
                        f"spend {new:.0%} of {spending_base(f, ai['has_gig'])} instead of {f['spend_income_ratio']:.0%}"
                        + (" (not counting your gig income)" if ai["has_gig"] else "")))
    best = None
    for name, value, text in options:
        p = predict({**f, name: value})[3]
        rate = ai_rate(p)[0]
        gain = amount(earned, calc["rate"] - ai["rate"] + rate, cap) - now
        if best is None or gain > best[0]:
            best = (gain, p, rate, text)
    gain, p, rate, text = best
    if gain >= 1:
        return (f"What-if: if you {text}, the chance would rise from {ai['p']:.1%} to {p:.1%}, your rate to "
                f"{rate:g}% and you could withdraw EGP {gain:,.0f} more.", gain)
    if now >= cap:
        return (f"What-if: your amount is limited by your tier's cap (EGP {cap:,.0f}), not by the AI; on-time "
                "repayments move you up a tier and raise the cap.", 0.0)
    return ("What-if: nothing you control would raise your rate right now; every salary that arrives on time "
            "and in full will.", 0.0)


def paragraph(ai, calc):
    f, parts = ai["features"], ai["contributions"]
    if ai["short_history"]:
        first = (f"We have seen only {months(f['salary_months'])} of your salary and the AI needs at least 3, so your "
                 f"rate is the minimum {ai['rate']:g}% and your account needs review: upload a recent payslip to "
                 f"unlock more (the model alone would say {ai['p']:.0%}).")
    elif ai["needs_review"]:
        first = (f"The AI model gives only a {ai['p']:.0%} chance that your next salary arrives on time and in full. "
                 f"That is below the 70% it needs, so your rate is the minimum {ai['rate']:g}% and your account needs "
                 "review: upload a recent payslip to unlock more.")
    else:
        article = "an" if f"{ai['p']:.0%}".startswith(("8", "11", "18")) else "a"
        first = (f"The AI model gives {article} {ai['p']:.0%} chance that your next salary arrives on time and in full, "
                 f"which sets your advance rate at {ai['rate']:g}% (the AI's range is 20–50%).")
    ranked = sorted(reason_scores(parts).items(), key=lambda kv: -abs(kv[1]))
    ups = [fact(n, f, ai["has_gig"]) for n, c in ranked if c > 0.005][:2]
    downs = [(n, c) for n, c in ranked if c < -0.005][:2]
    downs = [fact(n, f, ai["has_gig"]) for i, (n, c) in enumerate(downs) if i == 0 or abs(c) >= 0.05]
    last = ("Withdrawals are paused anyway until your overdue salary arrives." if calc.get("blocked") == "salary_overdue"
            else what_if(ai, calc)[0])
    sentences = [first,
                 f"In your favour: {join(ups)}." if ups else "Nothing in your history raises the chance much.",
                 f"Against you: {join(downs)}." if downs else "Nothing counts noticeably against you.",
                 last]
    return " ".join(s[0].upper() + s[1:] for s in sentences)


def api_block(ai, calc):
    if ai is None:
        return None
    no_numbers = calc.get("blocked") in ("no_salary_seen", "unpaid_last_cycle")
    gain = None if calc.get("blocked") else what_if(ai, calc)[1]
    return {"p": round(ai["p"], 4), "rate": ai["rate"],
            "needs_review": ai["needs_review"] or bool(calc.get("needs_review")),
            "paragraph": None if no_numbers else paragraph(ai, calc),
            "what_if_egp": gain and round(gain, 2), "notes": ai["notes"],
            "contributions": [{"feature": n, "label": FEATURES[n][0], "value": ai["features"][n], "score": round(c, 4)}
                              for n, c in sorted(ai["contributions"].items(), key=lambda kv: -abs(kv[1]))],
            "start": round(ai["start"], 4), "score": round(ai["score"], 4)}
