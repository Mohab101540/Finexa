from calculator import DEMO_TALABAT_SMS, TIERS, calculate
from sms_parser import load_samples

TIER_AR = {"Starter": "مبتدئ", "Trusted": "موثوق", "Strong": "ممتاز"}
APP_AR = {"Verified side": "عمل جانبي موثّق", "Talabat": "طلبات","Uber": "أوبر", "Careem": "كريم", "InDrive": "إن درايف",
          "Upwork": "أب وورك", "Payoneer": "بايونير"}
NEXT_TIER = {"Starter": "Trusted", "Trusted": "Strong"}
STREAK_NEEDED = {"Starter": 0, "Trusted": 2, "Strong": 5}
BOOSTER_LEVELS = {0: (5, 1000, 2), 5: (10, 3000, 3)}

HEALTH_TIPS = [
    ("Set a weekly spending limit so your salary lasts until payday.",
     "حدد سقفاً أسبوعياً لمصروفاتك حتى يكفي مرتبك حتى يوم القبض."),
    ("Withdraw only for real needs: every withdrawal is repaid from your next salary.",
     "اسحب فقط للاحتياجات الضرورية: كل سحب يُسدد من مرتبك القادم."),
]


def amount(earned, rate, cap):
    return min(earned * rate / 100, cap, earned)


def egp(x):
    return f"{abs(x):,.0f}"


def reason(type_, en, ar, effect=None):
    return {"type": type_, "en": en, "ar": ar, "egp": None if effect is None else round(effect, 2)}


def explain(r, on_time_streak=None):
    if r["blocked"] == "no_salary_seen":
        return [reason("red", "No salary deposit seen in your SMS yet, so you can't withdraw.",
                       "لم نجد إيداع مرتب في رسائلك بعد، لذلك لا يمكنك السحب.")]
    if r["blocked"] == "unpaid_last_cycle":
        return [reason("red", "Settle last cycle's balance to unlock withdrawals.",
                       "سدّد المبلغ المتبقي من الشهر الماضي لتتمكن من السحب.")]
    if r["blocked"] == "salary_overdue":
        days, due = r["overdue_days"], r["expected_payday"]
        return [reason("red", f"Your salary is {days} days overdue (expected {due:%b} {due.day}); withdrawals pause "
                              "until it arrives.",
                       f"مرتبك متأخر {days} يوماً (كان متوقعاً يوم {due:%d/%m})؛ السحب متوقف حتى يصل."),
                reason("info", "Needs review: upload a recent payslip or a letter from your employer to resume.",
                       "يحتاج إلى مراجعة: ارفع آخر قسيمة مرتب أو خطاباً من جهة عملك لاستئناف السحب.")]

    earned, tier, rate, cap = r["earned"], r["tier"], r["rate"], r["cap"]
    booster, wallet = r["booster_points"], r["wallet_adjustment"]
    tier_rate, tier_cap = TIERS[tier]
    current = amount(earned, rate, cap)

    reasons = [
        reason("green", f"Days worked: {r['days_passed']} of {r['days_in_cycle']} → earned EGP {egp(earned)}",
               f"أيام العمل: {r['days_passed']} من {r['days_in_cycle']} ← استحققت {egp(earned)} جنيه", earned),
    ]
    if r.get("rate_source") == "ai":
        reasons += [
            reason("info", f"AI salary model: {r['base_rate']:g}%", f"نموذج الذكاء الاصطناعي للمرتب: {r['base_rate']:g}%"),
            reason("info", f"{tier} tier: cap EGP {egp(tier_cap)}", f"مستوى {TIER_AR[tier]}: حد أقصى {egp(tier_cap)} جنيه"),
        ]
    else:
        reasons.append(reason("info", f"{tier} tier: {tier_rate}%", f"مستوى {TIER_AR[tier]}: {tier_rate}%"))
    if booster:
        gain = current - amount(earned, rate - booster, tier_cap)
        apps = ", ".join(r["gig_apps"])
        apps_ar = "، ".join(APP_AR.get(a, a) for a in r["gig_apps"])
        reasons.append(reason("green", f"{apps} income detected: +{booster}% (+EGP {egp(gain)})",
                              f"تم رصد دخل من {apps_ar}: +{booster}% (+{egp(gain)} جنيه)", gain))
    if wallet:
        loss = current - amount(earned, rate - wallet, cap)
        reasons.append(reason("red", f"Wallet repayment: −{-wallet}% (−EGP {egp(loss)})",
                              f"السداد من المحفظة: −{-wallet}% (−{egp(loss)} جنيه)", loss))
    if earned * rate / 100 > cap:
        reasons.append(reason("red", f"Capped at EGP {egp(cap)}", f"الحد الأقصى {egp(cap)} جنيه",
                              cap - earned * rate / 100))
    if r["withdrawn"]:
        reasons.append(reason("red", f"Already withdrawn this cycle: −EGP {egp(r['withdrawn'])}",
                              f"سحبت بالفعل هذا الشهر: −{egp(r['withdrawn'])} جنيه", -r["withdrawn"]))
    if r["fee"]:
        reasons.append(reason("red", f"Withdrawal fee: −EGP {egp(r['fee'])}",
                              f"رسوم السحب: −{egp(r['fee'])} جنيه", -r["fee"]))
    if r["late_last_repayment"]:
        reasons.append(reason("red", f"Late repayment: dropped to {tier} tier and lost the gig booster",
                              f"تأخرت في السداد: نزلت إلى مستوى {TIER_AR[tier]} وفقدت زيادة الدخل الإضافي"))
    if r["overuse_warning"]:
        reasons.append(reason("red", "This is your 5th or more withdrawal this cycle. Take a moment before withdrawing again.",
                              "هذا سحبك الخامس أو أكثر هذا الشهر. فكّر قليلاً قبل السحب مرة أخرى."))
        reasons += [reason("info", en, ar) for en, ar in HEALTH_TIPS]

    reasons.append(what_if(r, current, on_time_streak))
    return reasons


def what_if(r, current, on_time_streak):
    earned, tier, rate, booster = r["earned"], r["tier"], r["rate"], r["booster_points"]
    tips = []

    if tier in NEXT_TIER:
        nxt = NEXT_TIER[tier]
        if on_time_streak is None:
            on_time_streak = 0 if r["late_last_repayment"] else STREAK_NEEDED[tier]
        more = max(1, STREAK_NEEDED[nxt] - on_time_streak)
        ai = r.get("rate_source") == "ai"
        new_rate = rate if ai else rate - TIERS[tier][0] + TIERS[nxt][0]
        gain = amount(earned, new_rate, TIERS[nxt][1] * (1 + booster * 2 / 100)) - current
        step, step_ar = ((f"cap EGP {egp(TIERS[nxt][1])}", f"حد أقصى {egp(TIERS[nxt][1])} جنيه") if ai
                         else (f"{TIERS[nxt][0]}%", f"{TIERS[nxt][0]}%"))
        tips.append((gain, f"{more} more on-time repayments → {nxt} tier, {step} (+EGP {egp(gain)})",
                     f"{more} عمليات سداد أخرى في موعدها ← مستوى {TIER_AR[nxt]}، {step_ar} (+{egp(gain)} جنيه)"))

    if booster in BOOSTER_LEVELS and not r["late_last_repayment"]:
        points, needed, weeks = BOOSTER_LEVELS[booster]
        more = max(0, needed - r["gig_income_30d"])
        gain = amount(earned, rate - booster + points, TIERS[tier][1] * (1 + points * 2 / 100)) - current
        if more:
            en, ar = f"EGP {egp(more)} more gig income", f"{egp(more)} جنيه دخل إضافي آخر"
        else:
            en, ar = "Gig income", "دخل إضافي"
        tips.append((gain, f"{en} across {weeks} different weeks → +{points}% (+EGP {egp(gain)})",
                     f"{ar} على مدار {weeks} أسابيع مختلفة ← +{points}% (+{egp(gain)} جنيه)"))

    if not tips:
        return reason("info", "You've unlocked the maximum: Strong tier and +10% booster.",
                      "وصلت إلى الحد الأقصى: مستوى ممتاز وزيادة +10%.")
    gain, en, ar = max(tips)
    return reason("info", en, ar, gain)


if __name__ == "__main__":
    for title, sms in [("BEFORE", load_samples()), ("AFTER one Talabat SMS", load_samples() + [DEMO_TALABAT_SMS])]:
        r = calculate(sms, hr_salary=15000, tier="Trusted")
        print(f"\n{title}: available EGP {r['available']:,.2f}")
        for x in explain(r):
            print(f"  [{x['type']:<5}] {x['en']}\n          {x['ar']}")
