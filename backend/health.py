import json
import re
from datetime import timedelta
from pathlib import Path
from statistics import mean, pstdev

from config import TODAY
from payers import circular_pairs, labels
from salary_ai import end_of, user_rows
from salary_features import features, month_index
from sms_parser import parse_sms

WINDOW_DAYS = 30
FINEXA = re.compile(r"finexa|فينكسا", re.IGNORECASE)

CATEGORIES = [
    ("cash", "Cash withdrawal", r"\bATM|سحب"),
    ("transfers", "Transfers to people", r"تحويل"),
    ("eating_out", "Eating out", r"MCDONALDS|KFC|HARDEES|SUSHI|WINGS|DAWGS|BATATES|CHILL\s?OUT|PIZZA|CAFE|كافيه|مطعم"),
    ("food_delivery", "Food delivery", r"TALABAT|طلبات|BREADFAST|ELMENUS"),
    ("groceries", "Groceries", r"MART\b|MARKET|HYPER|CARREFOUR|SPINNEYS|SEOUDI|KAZYON|OSCAR|JZAR|ماركت|سوبر"),
    ("bills", "Bills", r"FAWRY|\bWE\b|فاتورة|الكهرباء|عداد|ORANGE|ETISALAT|VODAFONE BILL"),
    ("transport", "Transport", r"UBER|أوبر|CAREEM|كريم\s+مصر|SWVL|SHELL|ADNOC|رحلت?ك|رحلة"),
    ("shopping", "Shopping", r"AMAZON|NOON|DEFACTO|B\.TECH|ZARA|H&M"),
]
CATEGORY_RULES = [(key, re.compile(pattern, re.IGNORECASE)) for key, _, pattern in CATEGORIES]
CATEGORY_LABELS = {key: label for key, label, _ in CATEGORIES} | {"other": "Other"}
ESSENTIALS = {"groceries", "bills", "transport"}
EXTRAS = {"eating_out", "food_delivery", "shopping"}
NOT_DAY_TO_DAY = {"bills", "cash", "transfers"}

BANDS = [(80, "Excellent"), (60, "Good"), (40, "Fair"), (0, "Needs attention")]
MERCHANT = re.compile(r"(?:عند|لدى|لـ)\s*(.+?)(?:\s{2}|\s+يوم|\s+بتاريخ|\.\s|$)")


def category(sms):
    return next((key for key, rule in CATEGORY_RULES if rule.search(sms["body"])), "other")


def merchant(sms):
    found = MERCHANT.search(sms["body"])
    return found.group(1).strip() if found else None


def line(x, full_at, zero_at, max_points):
    t = (zero_at - x) / (zero_at - full_at)
    return max_points * min(max(t, 0), 1)


def spending_items(sms_list, today, employer=None, not_salary=()):
    known = [(sms, p) for sms in sms_list if (p := parse_sms(sms))["date"].date() <= today]
    end = max((p["date"].date() for _, p in known), default=today)
    circular = {id(out) for _, _, out, _ in circular_pairs(known)}
    found = labels([sms for sms, _ in known], employer, not_salary)
    in_window = [(sms, p, label) for (sms, p), label in zip(known, found)
                 if p["amount"] and (end - p["date"].date()).days < WINDOW_DAYS]
    items = [(p["date"].date(), p["amount"], category(sms)) for sms, p, label in in_window
             if label == "spending" and id(sms) not in circular
             and not FINEXA.search(sms["sender"] + " " + sms["body"])]
    gig = sum(p["amount"] for sms, p, label in in_window if label == "gig_income" or sms.get("verified_gig"))
    return end, items, gig


def balance_pct(sms_list, today, employer=None, not_salary=()):
    notes = []
    f = features(user_rows(sms_list, today, employer, not_salary), month_index(today), end_of(today), notes)
    return None if f is None or "no_balance" in notes else f["pre_payday_balance_pct"]


def inputs(sms_list, calc, withdrawals=0, today=TODAY, employer=None, not_salary=()):
    end, items, gig = spending_items(sms_list, today, employer, not_salary)
    by_cat = {}
    for _, amount, cat in items:
        by_cat[cat] = by_cat.get(cat, 0) + amount
    weeks = [0.0] * 4
    for d, amount, cat in items:
        if cat not in NOT_DAY_TO_DAY and (end - d).days < 28:
            weeks[(end - d).days // 7] += amount
    paid = calc.get("last_payday") and (end - calc["last_payday"]).days < WINDOW_DAYS
    salary = calc.get("salary_used") if paid and calc.get("blocked") != "salary_overdue" else None
    return {"end": end, "salary": salary, "spent": sum(a for _, a, _ in items), "by_cat": by_cat,
            "balance_pct": balance_pct(sms_list, today, employer, not_salary), "weeks": weeks,
            "advances": withdrawals, "bills": sum(cat == "bills" for _, _, cat in items),
            "gig": gig}


def factors(x):
    out = []
    def add(key, label, max_points, points, reason):
        out.append({"key": key, "label": label, "points": round(points), "max": max_points, "reason": reason})

    salary, spent, gig = x["salary"], x["spent"], x["gig"]
    if salary:
        ratio = spent / (salary + gig)
        income = (f"of your income (salary EGP {salary:,.0f} + gig EGP {gig:,.0f})" if gig
                  else f"of your salary (EGP {salary:,.0f})")
        add("spending", "Spending vs income", 25, line(ratio, 0.5, 1.2, 25),
            f"You spent EGP {spent:,.0f} in the last 30 days, {ratio:.0%} {income}. Full points at 50% or less.")
    else:
        add("spending", "Spending vs income", 25, 0, "No salary received in the last 30 days.")

    pct = x["balance_pct"]
    if pct is None:
        add("balance", "Cushion before payday", 20, 10, "No balance seen in your salary account's SMS, so this "
            "factor gets half points.")
    else:
        add("balance", "Cushion before payday", 20, line(pct, 0.30, 0, 20),
            f"Your lowest balance in the 5 days before payday was {pct:.0%} of your salary. "
            "Full points at 30% or more.")

    essentials = sum(x["by_cat"].get(c, 0) for c in ESSENTIALS)
    extras = sum(x["by_cat"].get(c, 0) for c in EXTRAS)
    if essentials + extras:
        share = extras / (essentials + extras)
        add("extras", "Essentials vs extras", 15, line(share, 0.30, 0.70, 15),
            f"EGP {extras:,.0f} on eating out, delivery and shopping = {share:.0%} of your purchases "
            f"(EGP {essentials:,.0f} on groceries, bills and transport). Full points at 30% or less.")
    else:
        add("extras", "Essentials vs extras", 15, 15, "No purchases in the last 30 days.")

    weeks = x["weeks"]
    if mean(weeks):
        spread = pstdev(weeks) / mean(weeks)
        add("stability", "Steady week to week", 15, line(spread, 0.25, 1.0, 15),
            "Day-to-day spending by week (newest first, bills, cash and transfers left out): "
            + " · ".join(f"EGP {w:,.0f}" for w in weeks)
            + f". It moves {spread:.0%} around its average. Full points at 25% or less.")
    else:
        add("stability", "Steady week to week", 15, 15, "No day-to-day spending in the last 4 weeks.")

    n = x["advances"]
    add("advances", "Finexa advances", 15, max(0, 15 - 5 * max(0, n - 1)),
        f"{n} Finexa advance{'' if n == 1 else 's'} in the last 30 days. Full points for 0–1, minus 5 for each extra advance.")

    b = x["bills"]
    if b:
        add("bills", "Bills paid", 10, 5 * min(b, 2),
            f"{b} bill payment{'' if b == 1 else 's'} seen in the last 30 days. 5 points per bill, full points at 2 bills.")
    else:
        add("bills", "Bills paid", 10, 5, "No bills seen in your SMS yet, so this factor gets half points.")
    return out


def total(x):
    return sum(f["points"] for f in factors(x))


def tip(x):
    now, options = total(x), []
    extras = {c: x["by_cat"].get(c, 0) for c in EXTRAS if x["by_cat"].get(c)}
    if extras:
        cut = 0.20 * sum(extras.values())
        by_cat = {**x["by_cat"], **{c: v * 0.8 for c, v in extras.items()}}
        top = [CATEGORY_LABELS[c].lower() for c in sorted(extras, key=extras.get, reverse=True)[:2]]
        options.append((total({**x, "spent": x["spent"] - cut, "by_cat": by_cat}),
                        f"Spend EGP {cut:,.0f} less on {' and '.join(top)} over the next 30 days (a fifth of your "
                        f"EGP {sum(extras.values()):,.0f} on extras)"))
    if x["salary"] and x["balance_pct"] is not None:
        more = 0.10 * x["salary"]
        options.append((total({**x, "balance_pct": min(x["balance_pct"] + 0.10, 1.0)}),
                        f"Keep EGP {more:,.0f} more in your account in the 5 days before payday (10% of your salary)"))
    if x["advances"] >= 2:
        options.append((total({**x, "advances": x["advances"] - 1}), "Take one Finexa advance fewer this month"))
    best = max(options, default=(now, ""))
    if best[0] <= now:
        return {"text": "Nothing quick to improve: keep spending the way you do.", "gain": 0}
    return {"text": f"{best[1]}.", "gain": best[0] - now}


def health(sms_list, calc, withdrawals=0, today=TODAY, employer=None, not_salary=()):
    x = inputs(sms_list, calc, withdrawals, today, employer, not_salary)
    fs = factors(x)
    score = sum(f["points"] for f in fs)
    band = next(name for low, name in BANDS if score >= low) if x["salary"] else "Needs attention"
    return {
        "score": score,
        "band": band,
        "window_end": x["end"].isoformat(),
        "spent_30d": round(x["spent"], 2),
        "categories": [{"key": c, "label": CATEGORY_LABELS[c], "egp": round(v, 2)}
                       for c, v in sorted(x["by_cat"].items(), key=lambda kv: -kv[1])],
        "factors": fs,
        "tip": tip(x),
    }


ROOT = Path(__file__).resolve().parent.parent
SIM_TAGS = {"food_out": "eating_out", "cash_withdrawal": "cash"}


def coverage_report():
    with open(ROOT / "data" / "samples" / "real_sms_anon.json", encoding="utf-8") as f:
        real = [s for s in json.load(f) if s["expected"]["label"] == "spending"]
    named = [s for s in real if category(s) != "other"]
    print(f"REAL SMS: {len(named)} of {len(real)} spending SMS get a category other than \"other\" "
          f"({len(named) / len(real):.0%}).")
    for s in real:
        print(f"  {category(s):<14} {merchant(s) or s['body'][:50]!s}")

    path = ROOT / "data" / "synthetic" / "sms_histories.jsonl"
    if not path.exists():
        print("Simulated SMS: data/synthetic not found (run simulate_sms.py to check against them).")
        return
    right = wrong = 0
    mistakes = {}
    with open(path, encoding="utf-8") as f:
        for row in map(json.loads, f):
            if row["label"] != "spending" or not row["tag"]:
                continue
            want, got = SIM_TAGS.get(row["tag"], row["tag"]), category(row)
            if want == got:
                right += 1
            else:
                wrong += 1
                mistakes[(want, got)] = mistakes.get((want, got), 0) + 1
    print(f"SIMULATED SMS: {right} of {right + wrong} tagged spending SMS match the simulator's category "
          f"({right / (right + wrong):.1%}).")
    for (want, got), n in sorted(mistakes.items(), key=lambda kv: -kv[1]):
        print(f"  simulator {want} → ours {got}: {n}")


if __name__ == "__main__":
    coverage_report()
