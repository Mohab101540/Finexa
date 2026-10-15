import json
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Annotated, Literal

from fastapi import FastAPI, HTTPException, Query
from fastapi.encoders import jsonable_encoder
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

import db
import demo_users
import salary_ai
from calculator import DEMO_TALABAT_SMS, TIERS, calculate
from classifier import ml_classify
from config import TODAY
from payers import classify_history, labels
from explainer import BOOSTER_LEVELS, NEXT_TIER, STREAK_NEEDED, explain
from health import health
from sms_parser import load_samples, parse_sms

app = FastAPI(title="Finexa")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

OFFLINE_PATH = Path(__file__).resolve().parent.parent / "app" / "src" / "data" / "demo-offline.json"

DEMO_HISTORY = [
    {"type": "withdrawal", "date": "2026-08-12", "amount": 1500, "method": "bank"},
    {"type": "repayment", "date": "2026-09-01", "amount": 1500, "on_time": True},
    {"type": "withdrawal", "date": "2026-09-15", "amount": 2000, "method": "bank"},
    {"type": "repayment", "date": "2026-10-01", "amount": 2000, "on_time": True},
]
DEMO_TIER = "Trusted"


class PastedSms(BaseModel):
    model_config = {"str_strip_whitespace": True}
    body: str = Field(min_length=1, max_length=1000)
    sender: str = Field("Unknown", max_length=50)
    date: str | None = None
    id: str | None = None


def to_sms(pasted):
    try:
        date = datetime.fromisoformat(pasted.date) if pasted.date else datetime(TODAY.year, TODAY.month, TODAY.day, 12)
    except ValueError:
        raise HTTPException(422, f'date "{pasted.date}" is not a date like 2026-10-20')
    return {"id": pasted.id, "sender": pasted.sender.strip() or "Unknown", "date": date.isoformat(),
            "body": pasted.body}


def parse_extra(extra):
    try:
        return [to_sms(PastedSms(**x)) for x in json.loads(extra)]
    except (ValueError, TypeError) as e:
        raise HTTPException(422, f"extra: {e}")


DEMO_REVIEW_SMS = [
    {"id": "transfer-demo", "sender": "BanK-AlAhly", "date": "2026-10-14T18:25:00", "body": "تم إضافة تحويل لحظي لبطاقتكم مسبقة الدفع بمبلغ 200.00 جم من مصطفى حسن عبد الله فؤاد رقم مرجعي 900000000101 يوم 14-10 الساعة 18:25 للمزيد اتصل بـ 19623"},
    {"id": "circular-in-demo", "sender": "BanK-AlAhly", "date": "2026-10-11T16:03:00", "body": "تم إضافة تحويل لحظي لبطاقتكم مسبقة الدفع بمبلغ 750.00 جم من مصطفى حسن عبد الله فؤاد رقم مرجعي 900000000102 يوم 11-10 الساعة 16:03 للمزيد اتصل بـ 19623"},
    {"id": "circular-out-demo", "sender": "BanK-AlAhly", "date": "2026-10-11T16:08:00", "body": "تم تنفيذ تحويل لحظي من بطاقتكم مسبقة الدفع بمبلغ 750.00 جم إلى Omar k* s** ******* رقم مرجعي 900000000103 يوم 11-10 الساعة 16:08 للمزيد اتصل بـ 19623"},
]


def demo_sms(with_talabat, extra=()):
    return load_samples() + DEMO_REVIEW_SMS + ([DEMO_TALABAT_SMS] if with_talabat else []) + list(extra)


EXTRA_USERS = demo_users.load()
USERS = {"main": {"key": "main", "title": "Main demo user", "persona": "main", "hr_salary": 15000, "tier": DEMO_TIER,
                  "employer": None},
         **EXTRA_USERS}
User = Literal[tuple(USERS)]
Mode = Literal["rules", "ai"]


def user_sms(with_talabat, extra=(), user="main"):
    if user == "main":
        sms_list = demo_sms(with_talabat, extra)
        return db.with_verified_gig(sms_list, db.reviews_for(sms_list)), db.family_payers()
    return EXTRA_USERS[user]["sms"] + ([DEMO_TALABAT_SMS] if with_talabat else []) + list(extra), ()


def demo_calc(with_talabat, method, withdrawn, withdrawals, extra=(), mode="rules", user="main"):
    sms_list, not_salary = user_sms(with_talabat, extra, user)
    u = USERS[user]
    employer = u.get("employer")
    ai = salary_ai.assess(sms_list, employer=employer, not_salary=not_salary) if mode == "ai" else None
    result = calculate(sms_list, hr_salary=u["hr_salary"], tier=u["tier"], method=method, withdrawn=withdrawn,
                       withdrawals_this_cycle=withdrawals, base_rate=ai and ai["rate"], employer=employer,
                       not_salary=not_salary)
    return result, ai


@app.get("/demo")
def demo(with_talabat: bool = False, method: Literal["bank", "wallet"] = "bank",
         withdrawn: Annotated[float, Query(ge=0)] = 0, withdrawals: Annotated[int, Query(ge=0)] = 0,
         extra: str = "[]", mode: Mode = "rules", user: User = "main"):
    extra = parse_extra(extra)
    result, ai = demo_calc(with_talabat, method, withdrawn, withdrawals, extra, mode, user)
    reviews = db.reviews_for(demo_sms(with_talabat, extra)) if user == "main" else {}
    reasons = explain(result)
    booster_next = BOOSTER_LEVELS.get(result.get("booster_points"))
    info = USERS[user]
    sms_list, not_salary = user_sms(with_talabat, extra, user)
    return {
        "available": result["available"],
        "tier": result.get("tier"),
        "reasons": reasons[:-1] if len(reasons) > 1 else reasons,
        "what_if": reasons[-1] if len(reasons) > 1 else None,
        "calc": jsonable_encoder(result),
        "booster_next": booster_next and dict(zip(["points", "egp", "weeks"], booster_next)),
        "to_review": sum(r["status"] == "needs_review" for r in reviews.values()),
        "mode": mode,
        "ai": salary_ai.api_block(ai, result),
        "health": health(sms_list, result, withdrawals, employer=info.get("employer"), not_salary=not_salary),
        "user": {k: info.get(k) for k in ("key", "title", "persona", "source_user", "source_today", "hr_salary")},
    }


@app.get("/inbox")
def inbox(with_talabat: bool = False, extra: str = "[]"):
    sms_list = demo_sms(with_talabat, parse_extra(extra))
    reviews = db.reviews_for(sms_list)
    rows = []
    for sms, label in zip(sms_list, labels(sms_list, not_salary=db.family_payers())):
        p = parse_sms(sms)
        rows.append({"id": sms.get("id") or "talabat-demo", "sender": sms["sender"], "date": sms["date"],
                     "body": sms["body"], "amount": p["amount"], "direction": p["direction"],
                     "label": label, "review": reviews.get(db.tx_id(sms))})
    return sorted(rows, key=lambda r: r["date"], reverse=True)


class AnalyzeRequest(PastedSms):
    added: list[PastedSms] = []
    with_talabat: bool = False
    method: Literal["bank", "wallet"] = "bank"
    withdrawn: float = Field(0, ge=0)
    withdrawals: int = Field(0, ge=0)
    mode: Mode = "rules"
    user: User = "main"


CHANGE_FIELDS = {
    "blocked": ("Blocked", "{}"),
    "salary_used": ("Salary used", "EGP {:,.0f}"),
    "last_payday": ("Last payday", "{}"),
    "days_passed": ("Days worked", "{}"),
    "earned": ("Earned so far", "EGP {:,.2f}"),
    "gig_income_30d": ("Gig income, last 30 days", "EGP {:,.0f}"),
    "booster_points": ("Gig booster", "+{} points"),
    "base_rate": ("AI rate", "{:g}%"),
    "cap": ("Cap", "EGP {:,.0f}"),
}


def effect(before, after):
    show = lambda fmt, v: "—" if v is None else fmt.format(v)
    changes = [f"{label}: {show(fmt, before.get(k))} → {show(fmt, after.get(k))}"
               for k, (label, fmt) in CHANGE_FIELDS.items() if before.get(k) != after.get(k)]
    return {"before": before["available"], "after": after["available"],
            "difference": round(after["available"] - before["available"], 2), "changes": changes}


@app.post("/analyze")
def analyze(req: AnalyzeRequest):
    sms = to_sms(req)
    p = parse_sms(sms)
    added = [to_sms(x) for x in req.added]
    history = (demo_sms(req.with_talabat, added) if req.user == "main"
               else EXTRA_USERS[req.user]["sms"] + added)
    known = [s for s in history if parse_sms(s)["date"] <= p["date"]] + [sms]
    label, why = classify_history(known, USERS[req.user].get("employer"),
                                  db.family_payers() if req.user == "main" else ())[-1]
    context = (req.with_talabat, req.method, req.withdrawn, req.withdrawals)
    before = demo_calc(*context, added, req.mode, req.user)[0]
    after = demo_calc(*context, added + [sms], req.mode, req.user)[0]
    if p["date"].date() > TODAY:
        why.append(f"dated after today ({TODAY}) → not counted in the limit")
    elif label in ("salary", "gig_income") and p["amount"] is None:
        why.append("no amount → not counted in the limit")
    review = (db.reviews_for(demo_sms(req.with_talabat, added + [sms])).get(db.tx_id(sms)) if req.user == "main"
              else None)
    return {"sender": sms["sender"], "date": sms["date"], "body": sms["body"], "amount": p["amount"],
            "direction": p["direction"], "label": label, "why": why, "effect": effect(before, after),
            "ml": ml_classify(sms),
            "review": review}


class SurveyAnswer(BaseModel):
    tx_id: str = Field(pattern=r"^[0-9a-f]{16}$")
    answer: Literal[tuple(db.ANSWERS)]
    details: str = Field("", max_length=500)
    evidence: Literal["now", "later", "none"]
    image: str | None = Field(None, max_length=7_000_000)


def review_call(action, *args):
    try:
        return action(*args)
    except LookupError as e:
        raise HTTPException(404, str(e))
    except ValueError as e:
        raise HTTPException(409, str(e))


@app.post("/survey")
def survey(req: SurveyAnswer):
    return review_call(db.answer_survey, req.tx_id, req.answer, req.details.strip(), req.evidence, req.image)


class VerifyRequest(BaseModel):
    tx_id: str = Field(pattern=r"^[0-9a-f]{16}$")


@app.post("/verify")
def verify(req: VerifyRequest):
    return review_call(db.verify, req.tx_id)


@app.get("/history")
def history():
    streak = 0
    for item in DEMO_HISTORY:
        if item["type"] == "repayment":
            streak = streak + 1 if item["on_time"] else 0
    nxt = NEXT_TIER.get(DEMO_TIER)
    return {
        "today": str(TODAY),
        "tier": DEMO_TIER,
        "items": DEMO_HISTORY[::-1],
        "on_time_streak": streak,
        "next_tier": nxt,
        "next_tier_streak": STREAK_NEEDED.get(nxt),
        "next_tier_rate": nxt and TIERS[nxt][0],
    }


def offline_snapshot():
    return {
        "demo": {f"{u}_{mode}_{m}_{t}".lower(): demo(t, m, mode=mode, user=u)
                 for u in USERS for mode in ["rules", "ai"] for m in ["bank", "wallet"] for t in [False, True]},
        "inbox": {str(t).lower(): inbox(t) for t in [False, True]},
        "history": history(),
    }


if __name__ == "__main__":
    db.DB_PATH = Path(tempfile.mkdtemp()) / "offline.db"
    with open(OFFLINE_PATH, "w", encoding="utf-8") as f:
        json.dump(offline_snapshot(), f, ensure_ascii=False, indent=2)
    print(f"Wrote {OFFLINE_PATH}")
