#!/usr/bin/env python3
"""SWARCO / PWD detector-loop logger (CyNAP MeasuredDataPublication, DATEX II v3).

Companion to swarco_probe.py. The probe runs ONCE per workflow run and only
shouts in health.csv when the feed wakes up; that is how we learned the loops
went live 2026-08-20..22 (40-48 nonzero values) and then went hollow again —
and why we only kept 7 snapshots of a 3-day window. This logger runs inside the
10-minute loop instead, so if the loops come back on (e.g. during the school
term, the peak our summer data lacks) we capture the whole series, not samples.

Feed: 100 q1:siteMeasurements blocks; ~33 carry vehicleFlowRate (veh/h) and
speed (km/h) under a measurementSiteReference id. Hollow state = all 0 / -1.

Writes ONLY rows with a real value (flow>0 or speed>0), so the CSV stays
meaningful and the repo does not grow while the feed sleeps:
data/swarco/sw_YYYY-MM.csv: fetched_utc, publication_time, site_id, flow_vph, speed_kmh

No API key, no quota — the endpoint is public. Stdlib only.
"""
import csv
import os
import re
import urllib.request
from datetime import datetime, timezone

ROOT = os.path.dirname(os.path.abspath(__file__))
URL = "https://www.traffic4cyprus.org.cy/swarco3/api/Data/MeasuredDataPublication"

RE_BLOCK = re.compile(r"<q1:siteMeasurements>(.*?)</q1:siteMeasurements>", re.S)
RE_SITE = re.compile(r"measurementSiteReference[^>]*\bid=\"([^\"]+)\"")
RE_FLOW = re.compile(r"<vehicleFlowRate[^>]*>(-?[\d.]+)</vehicleFlowRate>")
RE_SPEED = re.compile(r"<speed[^>]*>(-?[\d.]+)</speed>")
RE_PUBTIME = re.compile(r"<publicationTime[^>]*>([^<]+)</publicationTime>")


def log_health(msg):
    hp = os.path.join(ROOT, "data", "health.csv")
    with open(hp, "a", newline="", encoding="utf-8") as f:
        csv.writer(f).writerow(
            [datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), "swarco", msg])


def main():
    now = datetime.now(timezone.utc)
    ts = now.strftime("%Y-%m-%dT%H:%M:%SZ")
    try:
        req = urllib.request.Request(URL, headers={"User-Agent": "cyprus-traffic-log/1.0"})
        with urllib.request.urlopen(req, timeout=60) as r:
            xml = r.read().decode("utf-8", "replace")
    except Exception as e:  # noqa: BLE001
        log_health(f"{URL}: {type(e).__name__}: {e}")
        print(f"swarco: unreachable ({type(e).__name__})")
        return

    pub = RE_PUBTIME.search(xml)
    pub = pub.group(1) if pub else ""
    rows = []
    for b in RE_BLOCK.findall(xml):
        site = RE_SITE.search(b)
        flow = RE_FLOW.search(b)
        spd = RE_SPEED.search(b)
        fv = float(flow.group(1)) if flow else None
        sv = float(spd.group(1)) if spd else None
        if (fv is not None and fv > 0) or (sv is not None and sv > 0):
            rows.append([ts, pub, site.group(1) if site else "",
                         "" if fv is None else fv, "" if sv is None else sv])

    if not rows:
        print(f"swarco: hollow ({len(RE_BLOCK.findall(xml))} sites, no positive values)")
        return

    outdir = os.path.join(ROOT, "data", "swarco")
    os.makedirs(outdir, exist_ok=True)
    path = os.path.join(outdir, f"sw_{now:%Y-%m}.csv")
    new = not os.path.exists(path)
    with open(path, "a", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        if new:
            w.writerow(["fetched_utc", "publication_time", "site_id", "flow_vph", "speed_kmh"])
            log_health(f"LIVE: first rows written this month ({len(rows)} sites)")
        w.writerows(rows)
    print(f"swarco: *** LIVE *** {len(rows)} sites with values written")


if __name__ == "__main__":
    main()
