#!/usr/bin/env python3
"""Probe the CyNAP/SWARCO measured-traffic feed (PWD detector loops).

As of 2026-07-23 the MeasuredDataPublication endpoint is structurally live
but hollow: all sites report vehicleFlowRate=0 / speed=-1. This probe runs
once per workflow run; the day real values appear it saves the raw snapshot
and logs a LIVE line to data/health.csv so we notice immediately.
Stdlib only.
"""
import os
import re
import sys
import urllib.request
from datetime import datetime, timezone

ROOT = os.path.dirname(os.path.abspath(__file__))
FEEDS = {
    "swarco_loops": ("https://www.traffic4cyprus.org.cy/swarco3/api/Data/MeasuredDataPublication",
                     r"vehicleFlowRate[^>]*>(-?[\d.]+)<|<speed[^>]*>(-?[\d.]+)<"),
    "swarco_bt": ("https://www.traffic4cyprus.org.cy/swarco3/api/Data/PredefinedLocationDataPublication",
                  r"travelTime[^>]*>(-?[\d.]+)<|<speed[^>]*>(-?[\d.]+)<"),
}


def main():
    now = datetime.now(timezone.utc)
    stamp = now.strftime("%Y-%m-%dT%H:%M:%SZ")
    for feed, (url, pattern) in FEEDS.items():
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "cyprus-traffic-log/1.0"})
            with urllib.request.urlopen(req, timeout=60) as r:
                x = r.read().decode("utf-8", "replace")
        except Exception as e:  # noqa: BLE001
            print(f"[{stamp}] {feed}: unreachable ({type(e).__name__}) — fine, probe only")
            continue
        vals = [float(a or b) for a, b in re.findall(pattern, x)]
        live = sum(1 for v in vals if v > 0)
        if live:
            outdir = os.path.join(ROOT, "raw", feed)
            os.makedirs(outdir, exist_ok=True)
            path = os.path.join(outdir, now.strftime("%Y-%m-%d_%H%M") + "Z.xml")
            with open(path, "w", encoding="utf-8") as f:
                f.write(x)
            health = os.path.join(ROOT, "data", "health.csv")
            new = not os.path.exists(health)
            with open(health, "a", encoding="utf-8") as f:
                if new:
                    f.write("utc,feed,error\n")
                f.write(f"{stamp},{feed},LIVE: {live} nonzero values — start logging!\n")
            print(f"[{stamp}] {feed}: *** LIVE DATA *** {live} nonzero values — snapshot saved")
        else:
            print(f"[{stamp}] {feed}: still hollow ({len(vals)} values, all zero/absent)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
