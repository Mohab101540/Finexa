import random

from calculator import fee_for

SEED = 7
USERS = 1000
MONTHS = 12
TIER_MIX = {"Starter": 0.70, "Trusted": 0.20, "Strong": 0.10}
TIER_CAP = {"Starter": 2000, "Trusted": 4000, "Strong": 6000}
DEFAULT_RATE = {"Starter": 0.05, "Trusted": 0.02, "Strong": 0.01}
ADVANCE_SHARE = (0.50, 1.00)


def simulate(seed=SEED, users=USERS, months=MONTHS, fee=None):
    rng = random.Random(seed)
    rows = {t: {"users": 0, "advances": 0, "lent": 0.0, "fees": 0.0, "lost": 0.0, "repaid_count": 0} for t in TIER_MIX}
    for _ in range(users):
        tier = rng.choices(list(TIER_MIX), weights=TIER_MIX.values())[0]
        row = rows[tier]
        row["users"] += 1
        for _ in range(months):
            amount = round(TIER_CAP[tier] * rng.uniform(*ADVANCE_SHARE), 2)
            row["advances"] += 1
            row["lent"] += amount
            if rng.random() < DEFAULT_RATE[tier]:
                row["lost"] += amount
            else:
                row["fees"] += fee_for(amount) if fee is None else fee
                row["repaid_count"] += 1
    return rows


def break_even_fee(rows):
    return sum(r["lost"] for r in rows.values()) / sum(r["repaid_count"] for r in rows.values())


def main():
    rows = simulate()
    print(f"{USERS:,} simulated users x {MONTHS} months, fee bands (calculator.FEE_BANDS)\n")
    print(f"{'Tier':<9}{'Users':>7}{'Advances':>10}{'Lent EGP':>14}{'Fees EGP':>12}{'Lost EGP':>12}{'Net EGP':>12}")
    for tier, r in list(rows.items()) + [("Total", {k: sum(r[k] for r in rows.values()) for k in rows["Starter"]})]:
        net = r["fees"] - r["lost"]
        print(f"{tier:<9}{r['users']:>7,}{r['advances']:>10,}{r['lent']:>14,.0f}{r['fees']:>12,.0f}{r['lost']:>12,.0f}{net:>12,.0f}")
    print(f"\nBreak-even flat fee: EGP {break_even_fee(rows):,.2f} per advance (net result exactly 0)")


if __name__ == "__main__":
    main()
