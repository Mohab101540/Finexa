import re
from datetime import timedelta
from statistics import median

from classifier import classify_why
from sms_parser import parse_sms

FLAG_WINDOW = timedelta(minutes=60)
FLAG_TOLERANCE = 0.05

MONTHLY_GAP_DAYS = (25, 35)
SIMILAR_AMOUNT = 0.15
MIN_MEDIAN_GAP_DAYS = 20

ARABIC_FORMS = str.maketrans("أإآىة", "ااايه")
NAME_STOPWORDS = {"llc", "co", "company", "egypt", "eg", "ltd", "inc", "sae", "the", "for", "and",
                  "شركه", "مصر", "ش", "م", "للتجاره", "والتوزيع"}


def circular_pairs(parsed):
    outs = [(s, p) for s, p in parsed if p["direction"] == "out" and p["amount"]]
    for sms, p in parsed:
        if p["direction"] != "in" or not p["amount"]:
            continue
        for out_sms, o in outs:
            gap = o["date"] - p["date"]
            if timedelta(0) <= gap <= FLAG_WINDOW and abs(o["amount"] - p["amount"]) <= FLAG_TOLERANCE * p["amount"]:
                yield sms, p, out_sms, o
                break


def name_key(name):
    text = re.sub(r"[^\w\s]", " ", name.casefold().translate(ARABIC_FORMS))
    return " ".join(text.split())


def name_words(name):
    return {w for w in name_key(name).split() if len(w) > 1 and w not in NAME_STOPWORDS}


def employer_matches(payer, employer):
    names = [employer] if isinstance(employer, str) else list(employer or [])
    for name in names:
        a, b = name_words(payer), name_words(name)
        if a and b and (a <= b or b <= a):
            return name
    return None


def similar(a, b):
    return abs(a - b) <= SIMILAR_AMOUNT * max(a, b)


def salary_by_payer(items, employer=None, not_salary=()):
    payments = {}
    for sms, p in items:
        if p["direction"] == "in" and p["amount"] and p["counterparty"]:
            payments.setdefault(name_key(p["counterparty"]), []).append((sms, p))
    circular = {name_key(p["counterparty"]) for _, p, _, _ in circular_pairs(items) if p["counterparty"]}
    blocked = circular | {name_key(n) for n in not_salary}

    salary, never = {}, {}
    for key, pays in payments.items():
        pays.sort(key=lambda sp: sp[1]["date"])
        name = pays[0][1]["counterparty"]
        if match := employer_matches(name, employer):
            why = f'payer {name} matches the employer on your HR letter ("{match}") → salary'
            chosen = pays
        else:
            pairs = [(a, b) for a, b in zip(pays, pays[1:])
                     if MONTHLY_GAP_DAYS[0] <= (b[1]["date"] - a[1]["date"]).days <= MONTHLY_GAP_DAYS[1]
                     and similar(a[1]["amount"], b[1]["amount"])]
            gaps = [(b[1]["date"] - a[1]["date"]).days for a, b in zip(pays, pays[1:])]
            if not pairs or median(gaps) < MIN_MEDIAN_GAP_DAYS:
                continue
            usual = median([x[1]["amount"] for pair in pairs for x in pair])
            chosen = [sp for sp in pays if similar(sp[1]["amount"], usual)]
            why = (f"same payer {name}, monthly (25–35 days apart), similar amount (±15% of EGP {usual:,.0f}; "
                   f"{len(chosen)} payments so far) → salary")
        if key in blocked:
            reason = "its money went straight back out" if key in circular else "you said it is a friend or family"
            for sms, _ in chosen:
                never[id(sms)] = f"recurring payer {name}, but {reason} → never salary"
        else:
            for sms, _ in chosen:
                salary[id(sms)] = why
    return salary, never


def classify_history(sms_list, employer=None, not_salary=()):
    items = [(sms, parse_sms(sms)) for sms in sms_list]
    salary, never = salary_by_payer(items, employer, not_salary)
    out = []
    for sms, _ in items:
        label, why = classify_why(sms)
        if label == "ignore" and id(sms) in salary:
            label, why = "salary", why[:-1] + [salary[id(sms)]]
        elif id(sms) in never:
            why = why + [never[id(sms)]]
        out.append((label, why))
    return out


def labels(sms_list, employer=None, not_salary=()):
    return [label for label, _ in classify_history(sms_list, employer, not_salary)]
