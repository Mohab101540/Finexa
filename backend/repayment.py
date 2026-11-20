from datetime import date, timedelta

from calculator import fee_for


def amount_due(withdrawals, fee=None):
    return round(sum(w + (fee_for(w) if fee is None else fee) for w in withdrawals), 2)


def settle(balance_due, incoming, share=0.2):
    paid = round(min(balance_due, max(incoming, 0) * share), 2)
    return paid, round(balance_due - paid, 2)


def is_late(due_date, today, grace_days=0):
    due_date, today = (date.fromisoformat(d) if isinstance(d, str) else d for d in (due_date, today))
    return today > due_date + timedelta(days=grace_days)
