import math
from datetime import datetime
from zoneinfo import ZoneInfo

CAIRO = ZoneInfo("Africa/Cairo")
DEFAULT_SCHEDULE = {"days": [0, 1, 2, 3, 4], "start": "09:00", "end": "17:00"}

EARTH_RADIUS_M = 6_371_000
WORKPLACE_RADIUS_M = 200
MAX_SPEED_KMH = 150


def distance_m(lat1, lon1, lat2, lon2):
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * EARTH_RADIUS_M * math.asin(math.sqrt(a))


def inside_workplace(point, workplace, radius_m=WORKPLACE_RADIUS_M, remote=False):
    if remote:
        return True
    return distance_m(point["lat"], point["lon"], workplace["lat"], workplace["lon"]) <= radius_m


def speed_kmh(previous_point, new_point):
    hours = (datetime.fromisoformat(new_point["time"]) - datetime.fromisoformat(previous_point["time"])).total_seconds() / 3600
    km = distance_m(previous_point["lat"], previous_point["lon"], new_point["lat"], new_point["lon"]) / 1000
    return km / hours if hours > 0 else None


def looks_spoofed(previous_point, new_point, max_kmh=MAX_SPEED_KMH):
    speed = speed_kmh(previous_point, new_point)
    if speed is None:
        return distance_m(previous_point["lat"], previous_point["lon"], new_point["lat"], new_point["lon"]) > WORKPLACE_RADIUS_M
    return speed > max_kmh


def cairo_time(time):
    return time.astimezone(CAIRO).replace(tzinfo=None) if time.tzinfo else time


def minutes(hhmm):
    hours, mins = hhmm.split(":")
    return int(hours) * 60 + int(mins)


def in_work_hours(time, schedule):
    day = (time.weekday() + 1) % 7
    now, start, end = time.hour * 60 + time.minute, minutes(schedule["start"]), minutes(schedule["end"])
    if start < end:
        return day in schedule["days"] and start <= now < end
    return (day in schedule["days"] and now >= start) or ((day - 1) % 7 in schedule["days"] and now < end)


if __name__ == "__main__":
    tahrir = {"lat": 30.0444, "lon": 31.2357, "time": "2026-10-20T09:00"}
    smart_village = {"lat": 30.0711, "lon": 31.0178, "time": "2026-10-20T09:05"}
    km = distance_m(tahrir["lat"], tahrir["lon"], smart_village["lat"], smart_village["lon"]) / 1000
    print(f"Tahrir -> Smart Village: {km:.1f} km in 5 minutes, spoofed: {looks_spoofed(tahrir, smart_village)}")
