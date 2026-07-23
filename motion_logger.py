#!/usr/bin/env python3
"""GTFS-realtime bus delay logger (MOTION / NPT Nicosia).

Snapshots TripUpdates from the national GTFS-RT feed and logs one row per
active Nicosia (NPT) trip: the delay at its latest estimated stop. Powers
the bus-vs-car comparison on the ΙΑ11/ΙΑ12 corridors (bus lanes case).
Same peak-focused gating as the TomTom logger.
Requires: gtfs-realtime-bindings (pip). Fails soft without it.
"""
import csv
import json
import os
import sys
import urllib.request
from datetime import datetime, timezone, timedelta

ROOT = os.path.dirname(os.path.abspath(__file__))
URL = "http://20.19.98.194:8328/Api/api/gtfs-realtime"
CY = timezone(timedelta(hours=3))
PEAKS = [(6*60+30, 9*60), (13*60, 14*60+30), (16*60+45, 19*60+15)]
OFFPEAK = (9*60, 22*60)


def should_run(now_local, force=False):
    if force:
        return True
    m = now_local.hour * 60 + now_local.minute
    for s, e in PEAKS:
        if s <= m < e:
            return True
    if OFFPEAK[0] <= m < OFFPEAK[1]:
        return now_local.minute < 10
    return False


def main():
    force = "--force" in sys.argv
    now = datetime.now(timezone.utc)
    if not should_run(now.astimezone(CY), force):
        print(f"motion: outside sampling window, skipping")
        return 0
    try:
        from google.transit import gtfs_realtime_pb2
    except ImportError:
        print("motion: gtfs-realtime-bindings not installed, skipping")
        return 0
    stamp = now.strftime("%Y-%m-%dT%H:%M:%SZ")
    month = now.strftime("%Y-%m")
    npt = set(json.load(open(os.path.join(ROOT, "npt_routes.json"), encoding="utf-8"))["route_ids"])
    try:
        req = urllib.request.Request(URL, headers={"User-Agent": "cyprus-traffic-log/1.0"})
        with urllib.request.urlopen(req, timeout=60) as r:
            data = r.read()
        feed = gtfs_realtime_pb2.FeedMessage()
        feed.ParseFromString(data)
    except Exception as e:  # noqa: BLE001
        path = os.path.join(ROOT, "data", "health.csv")
        new = not os.path.exists(path)
        with open(path, "a", encoding="utf-8") as f:
            if new:
                f.write("utc,feed,error\n")
            f.write(f"{stamp},motion_gtfsrt,{type(e).__name__}: {str(e)[:200]}\n")
        print(f"[{stamp}] motion: feed error, logged to health.csv")
        return 0
    rows = []
    for ent in feed.entity:
        if not ent.HasField("trip_update"):
            continue
        tu = ent.trip_update
        rid = tu.trip.route_id
        if rid not in npt:
            continue
        delay = last_seq = ""
        for stu in tu.stop_time_update:
            ev = stu.arrival if stu.HasField("arrival") else (stu.departure if stu.HasField("departure") else None)
            if ev is not None and ev.HasField("delay"):
                delay, last_seq = ev.delay, stu.stop_sequence
        if delay == "":
            continue
        rows.append([stamp, rid, tu.trip.trip_id, last_seq, delay])
    if rows:
        path = os.path.join(ROOT, "data", "motion", f"delays_{month}.csv")
        os.makedirs(os.path.dirname(path), exist_ok=True)
        new = not os.path.exists(path)
        with open(path, "a", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            if new:
                w.writerow(["fetched_utc", "route_id", "trip_id", "last_stop_seq", "delay_s"])
            w.writerows(rows)
    print(f"[{stamp}] motion: {len(rows)} NPT trips with delay logged")
    return 0


if __name__ == "__main__":
    sys.exit(main())
