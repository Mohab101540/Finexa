import calendar
from datetime import date, timedelta
from statistics import median

from classifier import gig_app
from config import TODAY
from payers import labels
from sms_parser import load_samples, parse_sms

TIERS = {"Starter": (30, 2000), "Trusted": (40, 4000), "Strong": (50, 6000)}
TIER_BELOW = {"Strong": "Trusted", "Trusted": "Starter", "Starter": "Starter"}
WALLET_ADJUSTMENT = -5
OVERUSE_AT = 5
OVERDUE_AFTER_DAYS = 5
OTHER_GIG = "Verified side"

DEMO_TALABAT_SMS = {"sender": "talabat", "date": f"{TODAY - timedelta(days=1)}T21:00:00",
                    "body": "تم تحويل مستحقاتك الأسبوعية بقيمة 400.00 جنيه إلى محفظة فودافون كاش"}


def booster_points(gigs, today=TODAY):
    recent = [(d, amount) for d, amount in gigs if 0 <= (today - d).days < 30]
    total = sum(amount for _, amount in recent)
    weeks = len({(today - d).days // 7 for d, _ in recent})

    if total >= 3000 and weeks >= 3:
        return 10
    if total >= 1000 and weeks >= 2:
        return 5
    return 0


def expected_payday(salary_dates):
    day = int(median(d.day for d in salary_dates))
    last = max(salary_dates)
    year, month = last.year, last.month
    while True:
        candidate = date(year, month, min(day, calendar.monthrange(year, month)[1]))
        if (candidate - last).days > 15:
            return candidate
        year, month = (year + 1, 1) if month == 12 else (year, month + 1)


def calculate(sms_list, hr_salary, tier="Starter", method="bank", withdrawn=0,
              last_cycle_unpaid=False, fee=0, withdrawals_this_cycle=0, late_last_repayment=False,
              today=TODAY, base_rate=None, employer=None, not_salary=()):
    salaries, gigs, gig_apps = [], [], set()
    known = [sms for sms in sms_list if parse_sms(sms)["date"].date() <= today]
    for sms, label in zip(known, labels(known, employer, not_salary)):
        label, p = "gig_income" if sms.get("verified_gig") else label, parse_sms(sms)
        d = p["date"].date()
        if d > today or p["amount"] is None:
            continue
        if label == "salary":
            salaries.append((d, p["amount"]))
        elif label == "gig_income":
            gigs.append((d, p["amount"]))
            if (today - d).days < 30:
                gig_apps.add(OTHER_GIG if sms.get("verified_gig") else gig_app(sms))
    salaries.sort()
    recent_gigs = [(d, a) for d, a in gigs if (today - d).days < 30]

    if not salaries:
        return {"available": 0, "blocked": "no_salary_seen"}
    if last_cycle_unpaid:
        return {"available": 0, "blocked": "unpaid_last_cycle"}

    last_three = [amount for _, amount in salaries[-3:]]
    salary_used = min(hr_salary, median(last_three))

    payday = salaries[-1][0]
    days_in_cycle = calendar.monthrange(payday.year, payday.month)[1]
    days_passed = min((today - payday).days, days_in_cycle)
    earned = salary_used * days_passed / days_in_cycle

    if late_last_repayment:
        tier = TIER_BELOW[tier]
    tier_rate, tier_cap = TIERS[tier]
    booster = 0 if late_last_repayment else booster_points(gigs, today)
    wallet = WALLET_ADJUSTMENT if method == "wallet" else 0
    base = tier_rate if base_rate is None else base_rate
    rate = round(base + booster + wallet, 1)
    cap = tier_cap * (1 + booster * 2 / 100)

    available = max(0, min(earned * rate / 100, cap, earned) - withdrawn - fee)

    expected = expected_payday([d for d, _ in salaries])
    overdue_days = max(0, (today - expected).days)
    overdue = overdue_days > OVERDUE_AFTER_DAYS
    if overdue:
        available = 0

    return {
        "available": round(available, 2),
        "blocked": "salary_overdue" if overdue else None,
        "expected_payday": expected,
        "overdue_days": overdue_days,
        "needs_review": overdue,
        "hr_salary": hr_salary,
        "salary_deposits": last_three,
        "salary_used": salary_used,
        "last_payday": payday,
        "days_passed": days_passed,
        "days_in_cycle": days_in_cycle,
        "earned": round(earned, 2),
        "tier": tier,
        "tier_rate": tier_rate,
        "rate_source": "rules" if base_rate is None else "ai",
        "base_rate": base,
        "booster_points": booster,
        "gig_income_30d": sum(a for _, a in recent_gigs),
        "gig_weeks_30d": len({(today - d).days // 7 for d, _ in recent_gigs}),
        "gig_apps": sorted(gig_apps),
        "wallet_adjustment": wallet,
        "rate": rate,
        "cap": cap,
        "withdrawn": withdrawn,
        "fee": fee,
        "late_last_repayment": late_last_repayment,
        "overuse_warning": withdrawals_this_cycle + 1 >= OVERUSE_AT,
    }


if __name__ == "__main__":
    before = calculate(load_samples(), hr_salary=15000, tier="Trusted")
    after = calculate(load_samples() + [DEMO_TALABAT_SMS], hr_salary=15000, tier="Trusted")
    print(f"{'':<20} {'before':>12} {'after':>12}")
    for key in before:
        print(f"{key:<20} {str(before[key]):>12} {str(after[key]):>12}")
