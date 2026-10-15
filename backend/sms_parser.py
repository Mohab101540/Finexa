import json
import re
from datetime import datetime
from pathlib import Path

SAMPLES_PATH = Path(__file__).resolve().parent.parent / "data" / "samples" / "sms_samples.json"

ARABIC_TO_NORMAL = str.maketrans("٠١٢٣٤٥٦٧٨٩٫٬", "0123456789.,")

CURRENCY = r"(?:جنيه|ج\.?م\b|EGP|\bL\.?E\b)"
NUMBER = r"(\d[\d,]*(?:\.\d+)?)"
AMOUNT = re.compile(rf"{CURRENCY}\s*{NUMBER}|{NUMBER}\s*{CURRENCY}")

DONE = r"\bتم\s+(?:تنفيذ\s+)?"

MONEY_IN = re.compile(DONE + r"(?:إيداع|استلام|إضافة|اضافة|تحويل\s+(?:مستحقاتك|أرباحك))")

MONEY_OUT = re.compile(DONE + r"(?:خصم|تحويل|دفع|شحن|سحب)")


BALANCE = re.compile(r"(?:المتاح|رصيدك|الرصيد)\D{0,35}?(-?\d[\d,]*(?:\.\d+)?)")


COUNTERPARTY_IN = [re.compile(r"المسجل بإسم\s+(.+?)\s+على"), re.compile(r"\sمن\s+(.+?)\s+رقم مرجعي")]


def normalize_digits(text):
    return text.translate(ARABIC_TO_NORMAL)


def parse_sms(sms):
    body = normalize_digits(sms["body"])

    why = []

    match = AMOUNT.search(body)
    amount = float((match.group(1) or match.group(2)).replace(",", "")) if match else None
    why.append(f'found "{match.group()}" → amount {amount:,.2f}' if match
               else "no amount with جنيه / جم / EGP found → amount unknown")

    if found := MONEY_IN.search(body):
        direction = "in"
        why.append(f'found "{found.group()}" → money in')
    elif found := MONEY_OUT.search(body):
        direction = "out"
        why.append(f'found "{found.group()}" → money out')
    else:
        direction = None
        why.append('no "تم + deposit/received/paid…" wording found → direction unknown')

    found = direction == "in" and next((m for p in COUNTERPARTY_IN if (m := p.search(body))), None)
    balance = BALANCE.search(body)

    return {
        "counterparty": found.group(1).strip() if found else None,
        "id": sms.get("id"),
        "sender": sms["sender"],
        "date": datetime.fromisoformat(sms["date"]),
        "amount": amount,
        "direction": direction,
        "balance": float(balance.group(1).replace(",", "")) if balance else None,
        "why": why,
    }


def load_samples(path=SAMPLES_PATH):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


if __name__ == "__main__":
    for sms in load_samples():
        p = parse_sms(sms)
        print(f"{p['id']:>2}  {p['date']:%Y-%m-%d}  {p['sender']:<14} {str(p['direction']):<5} {p['amount']}")
