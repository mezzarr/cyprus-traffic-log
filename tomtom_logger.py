#!/usr/bin/env python3
"""TomTom travel-time logger for the Strovolos corridor set.

Polls the TomTom Routing API (traffic=true) for each corridor in routes.json,
both directions, and appends one CSV row per direction: real travel time,
free-flow travel time and delay. Complements the Waze jam logger: Waze says
WHERE congestion is reported, this measures WHAT IT COSTS in minutes.

Free tier is 20,000 requests/MONTH (not per day — learned the hard way,
quota exhausted 14/08/2026). Schedule: WEEKDAYS ONLY, AM/PM peaks every
20 min plus one midday round; hard budget guard on this month's row count.
Requires TOMTOM_API_KEY in the environment. Stdlib only.
"""
import csv
import json
import os
import sys
import time
import urllib.request
from datetime import datetime, timezone, timedelta

ROOT = os.path.dirname(os.path.abspath(__file__))
KEY = os.environ.get("TOMTOM_API_KEY", "").strip().strip("﻿")
CY = timezone(timedelta(hours=3))  # Cyprus summer time

# local-time windows: (start_minute_of_day, end_minute_of_day)
PEAKS = [(6*60+30, 9*60), (13*60, 14*60+30), (16*60+45, 19*60+15)]
OFFPEAK = (9*60, 22*60)  # (unused by routing now, kept for reference)
MONTH_CAP = 19000  # free tier 20K/month, keep headroom


def should_run(now_local, force=False):
    if force:
        return True
    if now_local.weekday() >= 5:  # school-term comparison: weekdays only
        return False
    m = now_local.hour * 60 + now_local.minute
    for s, e in PEAKS:
        if s <= m < e:
            return now_local.minute % 20 < 10  # every 20 min (loop is 10-min)
    if 13*60+30 <= m < 13*60+40:  # single midday reference round
        return True
    return False


def month_budget_left(month):
    """Rows already written this month = requests spent (1 row per request)."""
    path = os.path.join(ROOT, "data", "tomtom", f"tt_{month}.csv")
    if not os.path.exists(path):
        return MONTH_CAP
    with open(path, encoding="utf-8") as f:
        used = max(0, sum(1 for _ in f) - 1)
    return MONTH_CAP - used


def fetch_route(a, b, tries=2):
    url = (f"https://api.tomtom.com/routing/1/calculateRoute/"
           f"{a[0]},{a[1]}:{b[0]},{b[1]}/json?key={KEY}"
           f"&traffic=true&computeTravelTimeFor=all&routeType=fastest&travelMode=car")
    last = None
    for i in range(tries):
        try:
            with urllib.request.urlopen(url, timeout=30) as r:
                d = json.load(r)
            s = d["routes"][0]["summary"]
            return (s["lengthInMeters"], s["travelTimeInSeconds"],
                    s.get("noTrafficTravelTimeInSeconds", ""),
                    s.get("trafficDelayInSeconds", ""))
        except Exception as e:  # noqa: BLE001
            last = e
            time.sleep(3 * (i + 1))
    raise RuntimeError(f"tomtom {a}->{b}: {type(last).__name__}: {last}")


def append_rows(path, header, rows):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    new = not os.path.exists(path)
    with open(path, "a", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        if new:
            w.writerow(header)
        w.writerows(rows)


def main():
    force = "--force" in sys.argv
    limit = None
    for arg in sys.argv[1:]:
        if arg.startswith("--limit="):
            limit = int(arg.split("=")[1])
    now = datetime.now(timezone.utc)
    if not KEY:
        print("tomtom: no TOMTOM_API_KEY, skipping")
        return 0
    if not should_run(now.astimezone(CY), force):
        print(f"tomtom: outside sampling window ({now.astimezone(CY):%H:%M} local), skipping")
        return 0
    stamp = now.strftime("%Y-%m-%dT%H:%M:%SZ")
    month = now.strftime("%Y-%m")
    routes = json.load(open(os.path.join(ROOT, "routes.json"), encoding="utf-8"))
    if month_budget_left(month) < 2 * len(routes):
        print(f"tomtom: monthly budget spent, skipping until next month")
        return 0
    if limit:
        routes = routes[:limit]
    rows, failed = [], 0
    for r in routes:
        for direction, (p, q) in (("ab", (r["a"], r["b"])), ("ba", (r["b"], r["a"]))):
            try:
                length, tt, fft, delay = fetch_route(p, q)
                rows.append([stamp, r["id"], direction, length, tt, fft, delay])
            except RuntimeError as e:
                failed += 1
                append_rows(os.path.join(ROOT, "data", "health.csv"),
                            ["utc", "feed", "error"],
                            [[stamp, f"tomtom:{r['id']}:{direction}", str(e)[:300]]])
            time.sleep(0.35)
    if rows:
        append_rows(os.path.join(ROOT, "data", "tomtom", f"tt_{month}.csv"),
                    ["fetched_utc", "route_id", "direction", "length_m",
                     "travel_s", "freeflow_s", "delay_s"], rows)
    print(f"[{stamp}] tomtom: {len(rows)} measurements, {failed} failed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
