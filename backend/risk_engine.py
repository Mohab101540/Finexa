from datetime import datetime, timedelta

import salary_ai
from calculator import calculate
from geofence import DEFAULT_SCHEDULE, WORKPLACE_RADIUS_M, distance_m, in_work_hours, looks_spoofed

ATTENDANCE_DAYS, MIN_CHECKS, MIN_INSIDE_SHARE = 14, 6, 0.70


def rules_engine(sms_list, employer, not_salary):
    return None


def ai_engine(sms_list, employer, not_salary):
    return salary_ai.assess(sms_list, employer=employer, not_salary=not_salary)


ENGINES = {"rules": rules_engine, "ai": ai_engine}


def decide(sms_list, hr_salary, tier="Starter", method="bank", mode="rules", employer=None, not_salary=(), **calc_args):
    if mode not in ENGINES:
        raise ValueError(f"unknown mode {mode!r}, expected one of {sorted(ENGINES)}")
    assessment = ENGINES[mode](sms_list, employer, not_salary)
    result = calculate(sms_list, hr_salary=hr_salary, tier=tier, method=method,
                       base_rate=assessment and assessment["rate"], employer=employer,
                       not_salary=not_salary, **calc_args)
    return result, assessment


def attendance(readings, workplace=None, radius_m=WORKPLACE_RADIUS_M, schedule=DEFAULT_SCHEDULE, remote=False,
               now=None):
    now = now or datetime.now()
    since = now - timedelta(days=ATTENDANCE_DAYS)
    counted = sorted((r for r in readings if since <= datetime.fromisoformat(r["time"]) <= now
                      and in_work_hours(datetime.fromisoformat(r["time"]), schedule)), key=lambda r: r["time"])
    out = {"checks": len(counted), "inside": 0, "share": None, "jumps": 0, "last": None,
           "work_hours_now": in_work_hours(now, schedule)}
    if remote:
        return {**out, "status": "skipped", "reason": "Remote worker: your location is not checked. "
                                                      "Your limit relies on your cash flow instead."}
    if not workplace:
        return {**out, "status": "skipped", "reason": "No workplace set yet, so there is no location check."}

    distances = [round(distance_m(r["lat"], r["lon"], workplace["lat"], workplace["lon"])) for r in counted]
    inside = sum(d <= radius_m for d in distances)
    jumps = sum(looks_spoofed(a, b) for a, b in zip(counted, counted[1:]))
    share = inside / len(counted) if counted else None
    out.update(inside=inside, share=share and round(share, 3), jumps=jumps,
               last=counted and {"time": counted[-1]["time"], "distance_m": distances[-1],
                                 "inside": distances[-1] <= radius_m} or None)
    record = (f"Inside your work area on {inside} of {len(counted)} checks ({share:.0%}) during your work hours "
              f"over the last {ATTENDANCE_DAYS} days.") if counted else ""
    if jumps:
        return {**out, "status": "needs_review",
                "reason": f"Your location jumped faster than a car can travel ({jumps} time{'s' * (jumps > 1)}). "
                          "Turn off any fake GPS app. A person will review your account; you can still withdraw."}
    if len(counted) < MIN_CHECKS:
        return {**out, "status": "not_enough_data",
                "reason": f"{len(counted)} of {MIN_CHECKS} work-time checks so far. Finexa needs a few more "
                          "before it judges your attendance."}
    if share < MIN_INSIDE_SHARE:
        return {**out, "status": "needs_review",
                "reason": f"{record} That is below {MIN_INSIDE_SHARE:.0%}, so a person will review your account. "
                          "You can still withdraw."}
    return {**out, "status": "ok", "reason": record}
