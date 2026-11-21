import json
import math
import time
import urllib.parse
import urllib.request
from contextlib import closing
from datetime import datetime, timedelta

import users
from geofence import distance_m
from payers import classify_history, employer_matches
from sms_parser import parse_sms

NOMINATIM = "https://nominatim.openstreetmap.org"
USER_AGENT = "Finexa-university-prototype/0.1"
SEARCH_BOX_M = 1500
NIGHT_HOURS = (1, 5)
NIGHT_DAYS, MIN_NIGHTS = 14, 3
SHARED_PIN_M, SHARED_PIN_MIN = 100, 3
HOME = {("building", t) for t in ("house", "residential", "apartments", "detached", "semidetached_house", "terrace")} \
    | {("place", "house"), ("landuse", "residential")}
BUSINESS_CATEGORIES = {"office", "shop", "amenity", "craft", "tourism", "industrial", "man_made", "healthcare"}
BUSINESS_TYPES = {"commercial", "office", "industrial", "retail", "warehouse", "hospital", "school", "university"}
RANK = {"needs_review": 3, "not_checked": 2, "ok": 1, "skipped": 0}

SCHEMA = """
CREATE TABLE IF NOT EXISTS place_cache (url TEXT PRIMARY KEY, body TEXT NOT NULL, fetched TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS night_checks (
    user_id INTEGER NOT NULL, night TEXT NOT NULL, inside INTEGER NOT NULL,
    PRIMARY KEY (user_id, night)
);
"""
_last_call = [0.0]


def connect():
    con = users.connect()
    con.executescript(SCHEMA)
    return con


def check(key, title, status, reason, **extra):
    return {"key": key, "title": title, "status": status, "reason": reason, **extra}


def fetch_json(path, params):
    url = f"{NOMINATIM}/{path}?{urllib.parse.urlencode(params)}"
    with closing(connect()) as con:
        row = con.execute("SELECT body FROM place_cache WHERE url = ?", (url,)).fetchone()
    if row:
        return json.loads(row["body"])
    time.sleep(max(0.0, 1.0 - (time.monotonic() - _last_call[0])))
    _last_call[0] = time.monotonic()
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept-Language": "en,ar"})
    with urllib.request.urlopen(request, timeout=8) as response:
        body = json.loads(response.read().decode("utf-8"))
    with closing(connect()) as con, con:
        con.execute("INSERT OR REPLACE INTO place_cache VALUES (?, ?, ?)",
                    (url, json.dumps(body), datetime.now().isoformat(timespec="seconds")))
    return body


def box_around(lat, lon, metres):
    dlat = metres / 111_320
    dlon = metres / (111_320 * math.cos(math.radians(lat)))
    return f"{lon - dlon},{lat + dlat},{lon + dlon},{lat - dlat}"


def places_near(name, lat, lon):
    found = fetch_json("search", {"q": name, "format": "jsonv2", "limit": 10, "countrycodes": "eg",
                                  "viewbox": box_around(lat, lon, SEARCH_BOX_M), "bounded": 1})
    places = [{"name": p.get("display_name", name).split(",")[0], "lat": float(p["lat"]), "lon": float(p["lon"])}
              for p in found]
    for p in places:
        p["distance_m"] = round(distance_m(lat, lon, p["lat"], p["lon"]))
    return sorted(places, key=lambda p: p["distance_m"])


def kind_of_spot(lat, lon):
    spot = fetch_json("reverse", {"lat": f"{lat:.5f}", "lon": f"{lon:.5f}", "format": "jsonv2", "zoom": 18})
    category, kind = spot.get("category"), spot.get("type")
    if (category, kind) in HOME:
        return "home"
    if category in BUSINESS_CATEGORIES or kind in BUSINESS_TYPES:
        return "business"
    return "unknown"


def place_check(employer, pin):
    title = "Employer on the map"
    if not employer:
        return check("place", title, "not_checked", "There is no employer name on your account, so the pin can't be "
                                                     "compared with it.")
    try:
        places = places_near(employer, pin["lat"], pin["lon"])
        spot = kind_of_spot(pin["lat"], pin["lon"])
    except (OSError, ValueError, KeyError):
        return check("place", title, "not_checked", "The map service could not be reached. Finexa will try again.")
    if places:
        best = places[0]
        return check("place", title, "ok", f'"{best["name"]}" is on the map {best["distance_m"]:,} m from your pin.',
                     place=best, spot=spot)
    home = " Your pin is on a home." if spot == "home" else ""
    return check("place", title, "needs_review",
                 f'"{employer}" was not found on the map within {SEARCH_BOX_M / 1000:g} km of your pin.{home} Many '
                 "companies are missing from the map, so a person will check. You can still withdraw.", spot=spot)


def payer_check(sms_list, employer):
    title = "Salary from your employer"
    if not employer:
        return check("payer", title, "not_checked", "There is no employer name on your account to compare with.")
    if not sms_list:
        return check("payer", title, "not_checked", "No SMS yet. This is checked when Finexa reads your salary SMS.")
    salary = [sms for sms, (label, _) in zip(sms_list, classify_history(sms_list)) if label == "salary"]
    if not salary:
        return check("payer", title, "not_checked", "No salary SMS found yet.")
    payers = {p["counterparty"] for p in map(parse_sms, salary) if p["counterparty"]}
    if not payers:
        return check("payer", title, "not_checked", "Your salary SMS don't name who paid, so the employer can't be "
                                                    "compared.")
    matching = sorted(p for p in payers if employer_matches(p, employer))
    if matching:
        return check("payer", title, "ok", f'Your salary comes from {matching[0]}, the employer on your account.')
    return check("payer", title, "needs_review",
                 f'Your salary comes from {", ".join(sorted(payers))}, not "{employer}". A person will check. '
                 "You can still withdraw.")


def is_night(t):
    return NIGHT_HOURS[0] <= t.hour < NIGHT_HOURS[1]


def night_shift(schedule):
    return schedule["end"] <= schedule["start"]


def save_night_reading(user_id, lat, lon, when, settings):
    pin = settings and settings["workplace"]
    if not (pin and settings["night_check"] and not settings["remote"] and not night_shift(settings["schedule"])
            and is_night(when)):
        return False
    inside = distance_m(lat, lon, pin["lat"], pin["lon"]) <= settings["radius_m"]
    keep_after = (when - timedelta(days=NIGHT_DAYS)).date().isoformat()
    with closing(connect()) as con, con:
        con.execute("INSERT OR REPLACE INTO night_checks VALUES (?, ?, ?)", (user_id, when.date().isoformat(), int(inside)))
        con.execute("DELETE FROM night_checks WHERE user_id = ? AND night < ?", (user_id, keep_after))
    return True


def night_check(user_id, settings, now):
    title = "Workplace is not your home"
    if not settings or settings["remote"] or not settings["workplace"]:
        return check("night", title, "skipped", "No workplace pin, so there is nothing to compare.")
    if night_shift(settings["schedule"]):
        return check("night", title, "skipped", "You work at night, so the night check is off.")
    if not settings["night_check"]:
        return check("night", title, "skipped", "Off. You can allow one location check a night to show your "
                                                "workplace is not your home.")
    since = (now - timedelta(days=NIGHT_DAYS)).date().isoformat()
    with closing(connect()) as con:
        nights = [r["inside"] for r in con.execute("SELECT inside FROM night_checks WHERE user_id = ? AND night >= ?",
                                                   (user_id, since))]
    if len(nights) < MIN_NIGHTS:
        return check("night", title, "not_checked", f"{len(nights)} of {MIN_NIGHTS} nights checked so far.")
    inside = sum(nights)
    if inside * 2 >= len(nights):
        return check("night", title, "needs_review",
                     f"Your phone was inside your workplace area at night on {inside} of {len(nights)} nights. If this "
                     "is your home, a person will check. You can still withdraw.")
    return check("night", title, "ok", f"Away from your workplace at night on {len(nights) - inside} of {len(nights)} "
                                       "nights.")


def shared_pin_check(user, pin, spot):
    title = "Pin shared with other accounts"
    others = [o for o in users.workplaces_near(pin["lat"], pin["lon"], SHARED_PIN_M, user["id"])
              if not (user["employer"] and o["employer"] and employer_matches(o["employer"], user["employer"]))]
    if len(others) < SHARED_PIN_MIN:
        return check("shared", title, "ok", "No unusual sharing of this spot.")
    if spot == "business":
        return check("shared", title, "ok", f"{len(others)} other accounts with other employers use this spot, but it "
                                            "is a business area, which is normal.")
    return check("shared", title, "needs_review",
                 f"{len(others)} other accounts with other employers use this same spot, and it is not a business. "
                 "A person will check. You can still withdraw.")


def run(user, sms_list=None, now=None):
    now = now or datetime.now()
    settings = users.workplace(user["id"])
    pin = settings and not settings["remote"] and settings["workplace"]
    checks = []
    if pin:
        place = place_check(user["employer"], pin)
        checks += [place, shared_pin_check(user, pin, place.get("spot", "unknown"))]
    else:
        reason = "Remote worker: there is no workplace pin." if settings and settings["remote"] else "No workplace set yet."
        checks.append(check("place", "Employer on the map", "skipped", reason))
    checks += [payer_check(sms_list or [], user["employer"]), night_check(user["id"], settings, now)]
    return {"status": max((c["status"] for c in checks), key=RANK.get), "checks": checks}
