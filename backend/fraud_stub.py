import json
import statistics
from collections import defaultdict
from pathlib import Path

from sklearn.ensemble import IsolationForest

DATA = Path(__file__).resolve().parent.parent / "data" / "synthetic" / "user_months.jsonl"
SEED = 42
TOP = 10
FEATURES = ["salary_share", "late_share", "avg_days_late", "max_days_late", "amount_spread", "lowest_amount"]


def load_months(path=DATA):
    users = defaultdict(list)
    with open(path, encoding="utf-8") as f:
        for line in f:
            row = json.loads(line)
            users[row["user_id"]].append(row)
    return users


def user_features(months):
    expected = [m for m in months if m["salary_expected"]] or months
    arrived = [m for m in expected if m["salary_arrived"]]
    late = [m["days_late"] or 0 for m in arrived]
    ratios = [m["amount_ratio"] or 0 for m in arrived] or [0]
    return {
        "salary_share": len(arrived) / len(expected),
        "late_share": sum(d > 3 for d in late) / max(len(arrived), 1),
        "avg_days_late": statistics.mean(late) if late else 0,
        "max_days_late": max(late, default=0),
        "amount_spread": statistics.pstdev(ratios),
        "lowest_amount": min(ratios),
    }


def rank(users):
    ids = sorted(users)
    feats = [user_features(users[u]) for u in ids]
    X = [[f[k] for k in FEATURES] for f in feats]
    model = IsolationForest(n_estimators=200, random_state=SEED).fit(X)
    scores = model.score_samples(X)
    return sorted(zip(scores, ids, (users[u][0]["persona"] for u in ids), feats))


def main():
    if not DATA.exists():
        print(f"No data at {DATA}. Make it first:\n  python backend\\simulate_sms.py --users-per-persona 30 --months 18 --seed 7")
        return
    ranked = rank(load_months())
    print(f"Isolation Forest on {len(ranked)} simulated users. Top {TOP} most unusual:\n")
    print(f"{'#':>2}  {'User':<8}{'Persona':<20}{'Score':>7}  {'Salary seen':>11}{'Late':>6}{'Max late':>9}{'Lowest pay':>11}")
    for i, (score, uid, persona, f) in enumerate(ranked[:TOP], 1):
        print(f"{i:>2}  {uid:<8}{persona:<20}{score:>7.3f}  {f['salary_share']:>11.0%}{f['late_share']:>6.0%}"
              f"{f['max_days_late']:>9}{f['lowest_amount']:>11.0%}")


if __name__ == "__main__":
    main()
