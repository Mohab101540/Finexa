import json
import tempfile
from datetime import datetime, timedelta
from pathlib import Path
from typing import Annotated, Literal

from fastapi import Depends, FastAPI, Header, HTTPException, Query
from fastapi.encoders import jsonable_encoder
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field, StringConstraints

import db
import demo_users
import identity
import risk_engine
import salary_ai
import sms_forward
import users
import workplace_checks
from calculator import DEMO_TALABAT_SMS, FEE_BANDS, TIERS, fee_for, max_withdrawal
from classifier import ml_classify
from config import TODAY
from geofence import CAIRO, DEFAULT_SCHEDULE, WORKPLACE_RADIUS_M, cairo_time, in_work_hours
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
    return risk_engine.decide(sms_list, u["hr_salary"], u["tier"], method, mode, employer, not_salary,
                              withdrawn=withdrawn, withdrawals_this_cycle=withdrawals)


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


class PhoneBatch(BaseModel):
    messages: list[PastedSms] = Field(max_length=200)


@app.post("/classify")
def classify_phone(req: PhoneBatch):
    sms_list = [to_sms(m) for m in req.messages]
    rows = []
    for i, (sms, label) in enumerate(zip(sms_list, labels(sms_list))):
        p = parse_sms(sms)
        rows.append({"id": sms["id"] or f"phone-{i}", "sender": sms["sender"], "date": sms["date"], "body": sms["body"],
                     "amount": p["amount"], "direction": p["direction"], "label": label})
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


class Login(BaseModel):
    phone: str = Field(pattern=r"^01[0125][0-9]{8}$")
    password: str = Field(min_length=8, max_length=128)


class Signup(Login):
    name: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]
    hr_salary: float | None = Field(None, gt=0, le=1_000_000)
    employer: str | None = Field(None, max_length=100)
    method: Literal["bank", "wallet"] = "bank"


def current_user(authorization: Annotated[str | None, Header()] = None):
    scheme, _, token = (authorization or "").partition(" ")
    user = scheme.lower() == "bearer" and users.user_for(token)
    if not user:
        raise HTTPException(401, "log in first")
    return user


@app.post("/signup", status_code=201)
def signup(req: Signup):
    try:
        return users.signup(req.phone, req.name, req.password, req.hr_salary, req.employer, req.method)
    except ValueError as e:
        raise HTTPException(409, str(e))


@app.post("/login")
def login(req: Login):
    try:
        token, user = users.login(req.phone, req.password)
    except users.TooManyAttempts as e:
        raise HTTPException(429, str(e))
    except PermissionError as e:
        raise HTTPException(401, str(e))
    return {"token": token, "user": user}


@app.get("/me")
def me(user: Annotated[dict, Depends(current_user)]):
    tier, streak = users.standing(users.ledger(user["id"]))
    return {**user, "tier": tier, "on_time_streak": streak}


class LimitRequest(BaseModel):
    messages: list[PastedSms] = Field(max_length=500)
    mode: Mode = "rules"


def user_messages(user, messages):
    return [to_sms(m) for m in messages] if messages else sms_forward.messages(user["id"])


def user_limit(user, req):
    items = users.ledger(user["id"])
    tier = users.standing(items)[0]
    args = (user_messages(user, req.messages),user["hr_salary"] or float("inf"), tier, user["method"], req.mode,
            user["employer"])
    personal = users.personal_cap(items)
    result, ai = risk_engine.decide(*args, personal_cap=personal)
    payday = result.get("last_payday")
    if payday:
        owed = [i for i in items if i["type"] in ("withdrawal", "fee")]
        this_cycle = [i for i in owed if i["date"] >= str(payday)]
        unpaid = sum(i["amount"] for i in owed if i["date"] < str(payday)) \
            > sum(i["amount"] for i in items if i["type"] == "repayment")
        result, ai = risk_engine.decide(
            *args, personal_cap=personal, last_cycle_unpaid=unpaid,
            withdrawn=sum(i["amount"] for i in this_cycle if i["type"] == "withdrawal"),
            fee=sum(i["amount"] for i in this_cycle if i["type"] == "fee"),
            withdrawals_this_cycle=sum(i["type"] == "withdrawal" for i in this_cycle))
    return result, ai, tier


@app.post("/limit")
def limit(req: LimitRequest, user: Annotated[dict, Depends(current_user)]):
    result, ai, tier = user_limit(user, req)
    return {"available": result["available"], "max_withdrawal": max_withdrawal(result["available"]),
            "fee_bands": FEE_BANDS, "tier": tier, "mode": req.mode, "reasons": explain(result),
            "calc": result, "ai": salary_ai.api_block(ai, result), "attendance": attendance_for(user["id"])}


def account_id(authorization):
    return current_user(authorization)["id"] if authorization else users.DEMO_USER_ID


def cairo_now():
    return datetime.now(CAIRO).replace(tzinfo=None)


def attendance_for(user_id):
    settings = users.workplace(user_id) or {}
    return risk_engine.attendance(users.locations(user_id), settings.get("workplace"),
                                  settings.get("radius_m", WORKPLACE_RADIUS_M), settings.get("schedule", DEFAULT_SCHEDULE),
                                  settings.get("remote", False), now=cairo_now())


Clock = Annotated[str, StringConstraints(pattern=r"^([01]\d|2[0-3]):[0-5]\d$")]


class Schedule(BaseModel):
    days: list[Annotated[int, Field(ge=0, le=6)]] = Field(min_length=1, max_length=7)
    start: Clock
    end: Clock


class Location(BaseModel):
    lat: float = Field(ge=-90, le=90)
    lon: float = Field(ge=-180, le=180)
    time: datetime | None = None


class WorkplaceRequest(BaseModel):
    workplace: Location | None = None
    radius_m: int = Field(WORKPLACE_RADIUS_M, ge=50, le=2000)
    schedule: Schedule = Schedule(**DEFAULT_SCHEDULE)
    remote: bool = False
    night_check: bool = False


@app.get("/workplace")
def get_workplace(authorization: Annotated[str | None, Header()] = None):
    return users.workplace(account_id(authorization)) or {
        "workplace": None, "radius_m": WORKPLACE_RADIUS_M, "schedule": DEFAULT_SCHEDULE, "remote": False,
        "night_check": False}


@app.post("/workplace")
def workplace(req: WorkplaceRequest, authorization: Annotated[str | None, Header()] = None):
    if not req.remote and not req.workplace:
        raise HTTPException(422, "send a workplace, or remote=true")
    loc = req.workplace
    users.save_workplace(account_id(authorization), loc and loc.lat, loc and loc.lon, req.radius_m,
                         req.schedule.model_dump(), req.remote, req.night_check)
    return get_workplace(authorization)


class Readings(BaseModel):
    readings: list[Location] = Field(min_length=1, max_length=200)


@app.post("/locations")
def add_locations(req: Readings, authorization: Annotated[str | None, Header()] = None):
    user_id, now = account_id(authorization), cairo_now()
    schedule = (users.workplace(user_id) or {}).get("schedule", DEFAULT_SCHEDULE)
    since = now - timedelta(days=risk_engine.ATTENDANCE_DAYS)
    points = [{"lat": r.lat, "lon": r.lon, "time": t.isoformat(timespec="seconds")}
              for r in req.readings for t in [cairo_time(r.time) if r.time else now]
              if since <= t <= now + timedelta(minutes=5) and in_work_hours(t, schedule)]
    users.add_locations(user_id, points, since.isoformat(timespec="seconds"))
    return {"saved": len(points), "attendance": attendance_for(user_id)}


@app.get("/attendance")
def attendance(authorization: Annotated[str | None, Header()] = None):
    return attendance_for(account_id(authorization))


@app.post("/night-check")
def night_reading(req: Location, authorization: Annotated[str | None, Header()] = None):
    user_id = account_id(authorization)
    when = cairo_time(req.time) if req.time else cairo_now()
    return {"saved": workplace_checks.save_night_reading(user_id, req.lat, req.lon, when, users.workplace(user_id))}


class ChecksRequest(BaseModel):
    messages: list[PastedSms] = Field([], max_length=500)


@app.post("/workplace/checks")
def workplace_check(req: ChecksRequest, authorization: Annotated[str | None, Header()] = None):
    user = current_user(authorization) if authorization else {"id": users.DEMO_USER_ID, "employer": None}
    sms = user_messages(user, req.messages) if authorization else [to_sms(m) for m in req.messages]
    return workplace_checks.run(user, sms, now=cairo_now())


class ForwardedSms(BaseModel):
    model_config = {"str_strip_whitespace": True}
    body: str = Field(min_length=1, max_length=1000)
    sender: str = Field("Unknown", max_length=50)


@app.post("/sms/forward-key")
def forward_key(user: Annotated[dict, Depends(current_user)]):
    return {"key": sms_forward.new_key(user["id"]), "path": "/sms/forward", "header": "X-Finexa-Key"}


@app.post("/sms/forward")
def forward_sms(req: ForwardedSms, x_finexa_key: Annotated[str | None, Header()] = None):
    user_id = sms_forward.user_for_key(x_finexa_key)
    if not user_id:
        raise HTTPException(401, "unknown forwarding key: make a new one in the Finexa app")
    parsed = sms_forward.save(user_id, req.sender, req.body, cairo_now())
    if not parsed:
        return {"kept": False, "reason": "not a money SMS (no amount or no in/out), so it was not saved"}
    return {"kept": True, "amount": parsed["amount"], "direction": parsed["direction"]}


@app.get("/sms/forwarded")
def forwarded(user: Annotated[dict, Depends(current_user)]):
    rows = [parse_sms(s) for s in sms_forward.messages(user["id"])]
    return {"count": len(rows), "messages": [{"date": p["date"].isoformat(), "sender": p["sender"],
                                              "amount": p["amount"], "direction": p["direction"]} for p in rows[-20:]]}


@app.delete("/sms/forwarded")
def delete_forwarded(user: Annotated[dict, Depends(current_user)]):
    return {"deleted": sms_forward.delete_all(user["id"])}


REQUIRE_BACKUP_CARD_FOR_WALLET = False
REQUIRE_VERIFIED_IDENTITY = False


@app.get("/onboarding")
def onboarding(user: Annotated[dict, Depends(current_user)]):
    return identity.refresh(user["id"])


class NationalId(BaseModel):
    number: str = Field(min_length=14, max_length=20)


@app.post("/onboarding/national-id")
def national_id(req: NationalId, user: Annotated[dict, Depends(current_user)]):
    try:
        return identity.save_national_id(user["id"], req.number)
    except identity.AlreadyUsed as e:
        raise HTTPException(409, str(e))
    except ValueError as e:
        raise HTTPException(422, str(e))


class Document(BaseModel):
    kind: Literal[tuple(identity.KINDS)]
    image: str = Field(max_length=7_000_000)


@app.post("/onboarding/document")
def document(req: Document, user: Annotated[dict, Depends(current_user)]):
    try:
        return identity.save_document(user["id"], req.kind, req.image)
    except ValueError as e:
        raise HTTPException(422, str(e))


@app.post("/onboarding/verify")
def verify_identity(user: Annotated[dict, Depends(current_user)]):
    try:
        return identity.verify(user["id"])
    except ValueError as e:
        raise HTTPException(409, str(e))


class WithdrawRequest(LimitRequest):
    amount: float = Field(gt=0, le=1_000_000)
    confirm_overuse: bool = False


@app.post("/withdraw")
def withdraw(req: WithdrawRequest, user: Annotated[dict, Depends(current_user)]):
    result, _, _ = user_limit(user, req)
    if result.get("blocked"):
        raise HTTPException(409, f"withdrawals are paused: {result['blocked']}")
    if REQUIRE_VERIFIED_IDENTITY and identity.refresh(user["id"])["status"] != "verified":
        raise HTTPException(409, "your ID and documents are still being checked")
    if REQUIRE_BACKUP_CARD_FOR_WALLET and user["method"] == "wallet" and not user["backup_card"]:
        raise HTTPException(409, "wallet users need a backup Visa or Mastercard saved before withdrawing")
    amount, fee = round(req.amount, 2), fee_for(req.amount)
    if amount + fee > result["available"]:
        raise HTTPException(409, f"the most you can withdraw now is EGP {max_withdrawal(result['available']):,.2f} "
                                 f"(plus its fee)")
    if result["overuse_warning"] and not req.confirm_overuse:
        raise HTTPException(409, "this would be your 5th withdrawal this cycle: send confirm_overuse=true to continue")
    users.withdraw(user["id"], str(TODAY), amount, user["method"])
    users.charge_fee(user["id"], str(TODAY), fee)
    return {"withdrawn": amount, "fee": fee, "total_owed": amount + fee,
            "available_after": round(result["available"] - amount - fee, 2)}


@app.get("/history")
def history(authorization: Annotated[str | None, Header()] = None):
    if authorization:
        items = users.ledger(current_user(authorization)["id"])
        tier, streak = users.standing(items)
    else:
        items, tier, streak = DEMO_HISTORY, DEMO_TIER, users.standing(DEMO_HISTORY)[1]
    nxt = NEXT_TIER.get(tier)
    return {
        "today": str(TODAY),
        "tier": tier,
        "items": items[::-1],
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
    with tempfile.TemporaryDirectory() as tmp:
        db.DB_PATH = Path(tmp) / "offline.db"
        with open(OFFLINE_PATH, "w", encoding="utf-8") as f:
            json.dump(offline_snapshot(), f, ensure_ascii=False, indent=2)
    print(f"Wrote {OFFLINE_PATH}")
