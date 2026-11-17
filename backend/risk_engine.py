import salary_ai
from calculator import calculate


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
