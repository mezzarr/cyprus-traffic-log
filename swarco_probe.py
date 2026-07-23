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
URL = "https://www.traffic4cyprus.org.cy/swarco3/api/Data/MeasuredDataPublication"


def main():
    now = datetime.now(timezone.utc)
    stamp = now.strftime("%Y-%m-%dT%H:%M:%SZ")
    try:
        req = urllib.request.Request(URL, headers={"User-Agent": "cyprus-traffic-log/1.0"})
        with urllib.request.urlopen(req, timeout=60) as r:
            x = r.read().decode("utf-8", "replace")
    except Exception as e:  # noqa: BLE001
        print(f"[{stamp}] swarco: unreachable ({type(e).__name__}) — fine, probe only")
        return 0
    flows = [int(v) for v in re.findall(r"vehicleFlowRate[^>]*>(-?\d+)<", x)]
    speeds = [int(v) for v in re.findall(r"<speed[^>]*>(-?\d+)<", x)]
    live_flows = sum(1 for v in flows if v > 0)
    live_speeds = sum(1 for v in speeds if v > 0)
    if live_flows or live_speeds:
        outdir = os.path.join(ROOT, "raw", "swarco")
        os.makedirs(outdir, exist_ok=True)
        path = os.path.join(outdir, now.strftime("%Y-%m-%d_%H%M") + "Z.xml")
        with open(path, "w", encoding="utf-8") as f:
            f.write(x)
        health = os.path.join(ROOT, "data", "health.csv")
        new = not os.path.exists(health)
        with open(health, "a", encoding="utf-8") as f:
            if new:
                f.write("utc,feed,error\n")
            f.write(f"{stamp},swarco,LIVE: {live_flows} flows / {live_speeds} speeds nonzero — start logging!\n")
        print(f"[{stamp}] swarco: *** LIVE DATA *** {live_flows} flows, {live_speeds} speeds — snapshot saved")
    else:
        print(f"[{stamp}] swarco: still hollow ({len(flows)} zero flows)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
