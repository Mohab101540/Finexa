import calendar
import json
from collections import Counter
from datetime import datetime
from pathlib import Path
from statistics import median

import numpy as np

from calculator import calculate
from config import TODAY
from salary_features import month_index, month_name
from sms_parser import parse_sms

ROOT = Path(__file__).resolve().parent.parent
SYNTH = ROOT / "data" / "synthetic"
OUT = ROOT / "data" / "samples" / "demo_users.json"
MODELS = Path(__file__).resolve().parent / "models"
SPLIT = MODELS / "salary_split.json"
REPORT = MODELS / "salary_report.txt"

LEVELS = {"high": (90, "High reliability"), "medium": (50, "Medium reliability"), "low": (15, "Low reliability")}
JOB_LOSS_TITLE = "Lost job (salary overdue)"

SELECTION_RULE = """\
DEMO USERS — illustrative users spanning the prediction range; evaluation uses the full test set.
  They are examples for the app's demo, not evidence of accuracy: the metrics above come from ALL test users.
  Rule (backend/demo_users.py):
  - Pool: the salary model's TEST users only (models/salary_split.json; never training or calibration users),
    each seen on the demo's today (Oct 20, 2026, in their own simulated timeline, no date change).
  - p = the AI's calibrated probability, worked out with the app's own pipeline (salary_ai.assess on the raw SMS).
  - Percentiles (90th, 50th, 15th) are taken over ALL test users' p (every test user the app can give a p, i.e.
    whose salary the app's rules find; the count is below). Candidates are the test users whose salary is
    not overdue (calculator safeguard), since an overdue user can't withdraw and shows nothing about the rate.
  - High / medium / low reliability = the candidate whose p is closest to the 90th / 50th / 15th percentile
    (ties: lowest user id; each user used once).
  - Plus one job-loss user to show the salary-overdue safeguard: the first job_loss test user (by id), on day 20 of
    the first month with no salary, with SMS dates moved by whole months so that day lands on Oct 20, 2026."""


def shift_months(iso, k):
    d = datetime.fromisoformat(iso)
    y, m = divmod(d.month - 1 + k, 12)
    y, m = d.year + y, m + 1
    return d.replace(year=y, month=m, day=min(d.day, calendar.monthrange(y, m)[1])).isoformat(timespec="minutes")


def load(path=OUT):
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def user_record(key, title, uid, persona, history, months, moment):
    k = month_index(TODAY) - month_index(moment)
    end = datetime.combine(moment, datetime.max.time())
    seen = [r for r in history if datetime.fromisoformat(r["date"]) <= end]
    salaries = [parse_sms(r)["amount"] for r in seen if r["label"] == "salary"]
    nxt = months.get((uid, month_name(month_index(moment) + 1)))
    return {
        "key": key, "title": title, "persona": persona, "source_user": uid, "source_today": str(moment),
        "months_moved": k, "tier": "Trusted", "hr_salary": round(median(salaries)) if salaries else 0,
        "next_month_truth": nxt and {f: nxt[f] for f in ("month", "salary_arrived", "days_late", "amount_ratio")},
        "sms": [{"id": f"{uid}-{i}", "sender": r["sender"], "date": shift_months(r["date"], k), "body": r["body"],
                 "true_label": r["label"]} for i, r in enumerate(seen)],
    }


def overdue(rec):
    return calculate(rec["sms"], hr_salary=rec["hr_salary"], tier=rec["tier"])["blocked"] == "salary_overdue"


def build():
    from salary_ai import assess

    split = json.loads(SPLIT.read_text(encoding="utf-8"))
    people = {u["user_id"]: u["persona"] for u in json.loads((SYNTH / "personas.json").read_text(encoding="utf-8"))["users"]}
    test = sorted(split["test"])
    assert not set(test) & (set(split["train"]) | set(split.get("calibration", []))), "a test user is also a train user"
    months, history = {}, {}
    for line in open(SYNTH / "user_months.jsonl", encoding="utf-8"):
        r = json.loads(line)
        months[(r["user_id"], r["month"])] = r
    for line in open(SYNTH / "sms_histories.jsonl", encoding="utf-8"):
        r = json.loads(line)
        if r["user_id"] in test:
            history.setdefault(r["user_id"], []).append(r)

    pool = []
    for uid in test:
        rec = user_record(None, None, uid, people[uid], history[uid], months, TODAY)
        ai = assess(rec["sms"])
        if ai is not None:
            pool.append((uid, ai["p"], overdue(rec), rec))
    targets = np.percentile([p for _, p, _, _ in pool], [pct for pct, _ in LEVELS.values()])

    users, used, lines = {}, set(), []
    for (key, (pct, title)), target in zip(LEVELS.items(), targets):
        uid, p, _, rec = min(((u, p, o, r) for u, p, o, r in pool if not o and u not in used),
                             key=lambda c: (abs(c[1] - target), c[0]))
        used.add(uid)
        users[key] = {**rec, "key": key, "title": title, "percentile": pct, "target_p": round(float(target), 4),
                      "p_at_build": round(p, 4)}
        lines.append(f"  {title}: {pct}th percentile of p = {target:.1%} → {uid} ({rec['persona']}), p = {p:.1%}")

    uid = next(u for u in test if people[u] == "job_loss")
    stop = min(k[1] for k, r in months.items() if k[0] == uid and not r["salary_arrived"])
    moment = datetime.strptime(stop + "-20", "%Y-%m-%d").date()
    users["job_loss"] = user_record("job_loss", JOB_LOSS_TITLE, uid, "job_loss", history[uid], months, moment)
    lines.append(f"  {JOB_LOSS_TITLE}: {uid}, seen on {moment} (moved {users['job_loss']['months_moved']} months)")

    no_salary = Counter(people[u] for u in test if u not in {u for u, _, _, _ in pool})
    summary = [f"  Test users: {len(test)}. The app finds a salary (keyword or same-payer pattern, payers.py) for "
               f"{len(pool)} of them" + (f"; not for {', '.join(f'{n} {k}' for k, n in no_salary.most_common())}, "
                                         "who have no p and are not in the pool." if no_salary else "."),
               f"  Pool: {len(pool)} users with a p; overdue on Oct 20, 2026 (not candidates): "
               f"{sum(o for _, _, o, _ in pool)}."] + lines
    print("\n".join(summary))
    OUT.write_text(json.dumps(users, ensure_ascii=False, indent=1), encoding="utf-8")
    write_report_section("\n".join([SELECTION_RULE, "  Picked (by the rule above, rebuilt after every retrain):"]
                                   + summary))
    print(f"Wrote {OUT} and the DEMO USERS section of {REPORT.name}")


def write_report_section(text):
    report = REPORT.read_text(encoding="utf-8")
    head = report.split("\nDEMO USERS")[0].rstrip("\n")
    REPORT.write_text(f"{head}\n\n{text}\n", encoding="utf-8")


if __name__ == "__main__":
    build()
