import re
from functools import cache
from pathlib import Path

import joblib

from sms_parser import load_samples, normalize_digits, parse_sms

MODEL_PATH = Path(__file__).resolve().parent / "models" / "sms_classifier.joblib"
REVIEW_BELOW = 0.7

SALARY_WORDS = re.compile(r"مرتب|راتب")

GIG_WORDS = re.compile(r"talabat|طلبات|uber|أوبر|careem|كريم\s+مصر|indrive|upwork|payoneer", re.IGNORECASE)
GIG_APP_NAMES = {"talabat": "Talabat", "طلبات": "Talabat", "uber": "Uber", "أوبر": "Uber", "careem": "Careem",
                 "كريم مصر": "Careem", "indrive": "InDrive", "upwork": "Upwork", "payoneer": "Payoneer"}


def app_name(word):
    return GIG_APP_NAMES[" ".join(word.lower().split())]


def gig_app(sms):
    return app_name(GIG_WORDS.search(sms["sender"] + " " + sms["body"]).group())


IGNORE_HINTS = [
    (re.compile(r"رمز التحقق|كود التفعيل|OTP", re.IGNORECASE), "a one-time code (OTP)"),
    (re.compile(r"لم تتم|رفض|فشل"), "a failed or rejected payment"),
    (re.compile(r"رصيد"), "a balance message"),
    (re.compile(r"عرض|خصم|اشترك|قسّط"), "a promotion"),
]


def classify(sms):
    return classify_why(sms)[0]


def classify_why(sms):
    p = parse_sms(sms)
    why = list(p["why"])
    text = sms["sender"] + " " + sms["body"]

    if p["direction"] == "out":
        return "spending", why + ["money out → spending"]
    if p["direction"] == "in":
        if found := SALARY_WORDS.search(text):
            return "salary", why + [f'mentions "{found.group()}" → salary']
        if found := GIG_WORDS.search(text):
            return "gig_income", why + [f'mentions "{found.group()}" ({app_name(found.group())}) → gig income']
        return "ignore", why + ["money in, but no salary or gig app word → ignored (unknown source)"]
    for pattern, kind in IGNORE_HINTS:
        if found := pattern.search(text):
            return "ignore", why + [f'found "{found.group()}" → looks like {kind}, ignored']
    return "ignore", why + ["no known wording → ignored"]


def ml_text(sms):
    return re.sub(r"\d", "0", normalize_digits(sms["sender"] + " " + sms["body"]))


@cache
def load_model():
    return joblib.load(MODEL_PATH)


def ml_classify(sms):
    model = load_model()
    probs = model.predict_proba([ml_text(sms)])[0]
    best = probs.argmax()
    guess, confidence = str(model.classes_[best]), float(probs[best])
    return {"label": guess if confidence >= REVIEW_BELOW else "needs_review",
            "confidence": round(confidence, 3), "best_guess": guess}


if __name__ == "__main__":
    samples = load_samples()
    correct = 0
    for sms in samples:
        label = classify(sms)
        ok = label == sms["label"]
        correct += ok
        print(f"{sms['id']:>2}  {sms['sender']:<14} {label:<11} {'OK' if ok else 'WRONG, expected ' + sms['label']}")
    print(f"\n{correct}/{len(samples)} correct")
