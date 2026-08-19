#!/usr/bin/env python3
"""TomTom Traffic Flow Segment Data logger for the Strovolos corridor set.

Complements tomtom_logger.py (Routing API, 20K/month quota) with the SEPARATE
Traffic Flow Segment Data quota (also 20K/month): for the midpoint of each
corridor in routes.json it logs the current speed, free-flow speed and travel
times of the road segment TomTom snaps the point to. Same "what congestion
costs" signal, measured as segment speed instead of route time.

One row per corridor per round:
data/flow/fl_YYYY-MM.csv: fetched_utc, route_id, frc, cur_kmh, ff_kmh,
                          cur_s, ff_s, confidence, closed, snap_lat, snap_lon
frc + snap coords are kept so snapping to a wrong (side) road is detectable.

Budget guard: counts this month's rows; stops at MONTH_CAP so the quota can
never be exhausted by a runaway schedule. Schedule: weekdays only,
peaks every 20 min, off-peak hourly, night/weekend silent (~18K/month).
Requires TOMTOM_API_KEY. Stdlib only.
"""
import csv
import json
import os
import sys
import urllib.request
from datetime import datetime, timezone, timedelta

ROOT = os.path.dirname(os.path.abspath(__file__))
KEY = os.environ.get("TOMTOM_API_KEY", "").strip().strip("﻿")
CY = timezone(timedelta(hours=3))  # Cyprus summer time

PEAKS = [(6*60+30, 9*60), (13*60, 14*60+30), (16*60+45, 19*60+15)]
OFFPEAK = (9*60, 22*60)
MONTH_CAP = 19000  # requests; free tier is 20K/month, keep headroom


def should_run(now_local, force=False):
    if force:
        return True
    if now_local.weekday() >= 5:  # weekdays only, same rationale as routing
        return False
    m = now_local.hour * 60 + now_local.minute
    for s, e in PEAKS:
        if s <= m < e:
            return now_local.minute % 20 < 10  # every 20 min
    if OFFPEAK[0] <= m < OFFPEAK[1]:
        return now_local.minute < 10  # hourly off-peak
    return False


def month_rows(path):
    if not os.path.exists(path):
        return 0
    with open(path, encoding="utf-8") as f:
        return max(0, sum(1 for _ in f) - 1)


def fetch_flow(lat, lon, tries=2):
    url = (f"https://api.tomtom.com/traffic/services/4/flowSegmentData/"
           f"absolute/10/json?key={KEY}&point={lat},{lon}&unit=KMPH")
    last = None
    for _ in range(tries):
        try:
            with urllib.request.urlopen(url, timeout=30) as r:
                return json.load(r)["flowSegmentData"]
        except Exception as e:
            last = e
    raise last


def log_health(msg):
    hp = os.path.join(ROOT, "data", "health.csv")
    with open(hp, "a", newline="", encoding="utf-8") as f:
        csv.writer(f).writerow(
            [datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), "flow", msg])


def main():
    force = "--force" in sys.argv
    now = datetime.now(timezone.utc)
    if not KEY:
        print("flow: no TOMTOM_API_KEY, skipping")
        return
    if not should_run(now.astimezone(CY), force):
        print(f"flow: outside sampling window ({now.astimezone(CY):%H:%M} local), skipping")
        return

    outdir = os.path.join(ROOT, "data", "flow")
    os.makedirs(outdir, exist_ok=True)
    path = os.path.join(outdir, f"fl_{now:%Y-%m}.csv")
    used = month_rows(path)
    routes = json.load(open(os.path.join(ROOT, "routes.json"), encoding="utf-8"))
    if used + len(routes) > MONTH_CAP:
        print(f"flow: monthly budget reached ({used}/{MONTH_CAP}), skipping")
        return

    header = ["fetched_utc", "route_id", "frc", "cur_kmh", "ff_kmh",
              "cur_s", "ff_s", "confidence", "closed", "snap_lat", "snap_lon"]
    new = not os.path.exists(path)
    ts = now.strftime("%Y-%m-%dT%H:%M:%SZ")
    ok = err = 0
    with open(path, "a", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        if new:
            w.writerow(header)
        for r in routes:
            lat = (r["a"][0] + r["b"][0]) / 2
            lon = (r["a"][1] + r["b"][1]) / 2
            try:
                d = fetch_flow(lat, lon)
                c = d.get("coordinates", {}).get("coordinate", [{}])
                mid = c[len(c)//2] if c else {}
                w.writerow([ts, r["id"], d.get("frc", ""),
                            d.get("currentSpeed", ""), d.get("freeFlowSpeed", ""),
                            d.get("currentTravelTime", ""), d.get("freeFlowTravelTime", ""),
                            d.get("confidence", ""), d.get("roadClosure", ""),
                            round(mid.get("latitude", 0), 6), round(mid.get("longitude", 0), 6)])
                ok += 1
            except Exception as e:
                log_health(f"flow {r['id']}: {type(e).__name__}: {e}")
                err += 1
    print(f"flow: {ok} ok, {err} failed, month usage ~{used + ok + err}/{MONTH_CAP}")


if __name__ == "__main__":
    main()
