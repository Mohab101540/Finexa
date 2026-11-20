import salary_ai
from calculator import calculate
from geofence import WORKPLACE_RADIUS_M, distance_m, looks_spoofed


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


def location_check(location, workplace=None, remote=False, previous=None, radius_m=WORKPLACE_RADIUS_M):
    def out(status, reason, distance=None):
        return {"status": status, "reason": reason, "distance_m": distance}

    if remote:
        return out("skipped", "Remote worker: the location check is off.")
    if not workplace:
        return out("skipped", "No workplace on file, so there is no location check.")
    if not location:
        return out("failed", "Share your location to withdraw.")
    if previous and looks_spoofed(previous, location):
        return out("failed", "Your location jumped faster than a car can travel. Turn off any fake GPS app.")
    distance = round(distance_m(location["lat"], location["lon"], workplace["lat"], workplace["lon"]))
    if distance > radius_m:
        return out("failed", f"You are {distance:,} m from your workplace. Withdraw when you are at work.", distance)
    return out("passed", f"You are at your workplace ({distance:,} m away).", distance)
