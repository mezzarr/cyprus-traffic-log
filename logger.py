#!/usr/bin/env python3
"""Cyprus Waze feed logger (CyNAP / traffic4cyprus, DATEX II v3).

Fetches the open Waze traffic + alerts feeds every run and appends compact
CSV observations. Raw XML snapshots are kept once per hour as insurance.

Data source: Cyprus National Access Point (https://www.traffic4cyprus.org.cy/),
Public Works Department / Waze — licence CC BY 4.0. Stdlib only.
"""
import csv
import gzip
import hashlib
import os
import sys
import time
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone

ROOT = os.path.dirname(os.path.abspath(__file__))
FEEDS = {
    "traffic": "https://fixcyprus.cy/gnosis/open/api/nap/datasets/waze_traffic/",
    "alerts": "https://fixcyprus.cy/gnosis/open/api/nap/datasets/waze_alerts/",
}
UA = {"User-Agent": "cyprus-traffic-log/1.0 (research logger; CC BY 4.0 source)"}


def local(tag):
    return tag.split("}")[-1]


def fetch(url, tries=3):
    last = None
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers=UA)
            with urllib.request.urlopen(req, timeout=90) as r:
                return r.read()
        except Exception as e:  # noqa: BLE001 - log-and-retry by design
            last = e
            time.sleep(10 * (i + 1))
    raise RuntimeError(f"fetch failed for {url}: {last}")


def walk_comments(elem):
    """Return {commentType: value} from a generalPublicComment block."""
    out = {}
    for c in elem.iter():
        if local(c.tag) == "comment":
            ctype = value = None
            for ch in c:
                if local(ch.tag) == "commentType":
                    ctype = (ch.text or "").strip()
                elif local(ch.tag) == "value":
                    value = (ch.text or "").strip()
            if ctype:
                out[ctype] = value or ""
    return out


def coords_of(elem):
    """Ordered (lon, lat) list: start, intermediates..., end. Points too."""
    start = end = None
    mids, pts = [], []
    for node in elem.iter():
        name = local(node.tag)
        if name in ("startPointCoordinates", "endPointCoordinates",
                    "intermediatePointCoordinates", "pointCoordinates"):
            lat = lon = None
            for ch in node:
                if local(ch.tag) == "latitude":
                    lat = ch.text
                elif local(ch.tag) == "longitude":
                    lon = ch.text
            if lat is None or lon is None:
                continue
            p = (float(lon), float(lat))
            if name == "startPointCoordinates":
                start = p
            elif name == "endPointCoordinates":
                end = p
            elif name == "intermediatePointCoordinates":
                mids.append(p)
            else:
                pts.append(p)
    if start or end:
        return ([start] if start else []) + mids + ([end] if end else [])
    return pts


def wkt_of(coords):
    if not coords:
        return ""
    if len(coords) == 1:
        return f"POINT({coords[0][0]:.6f} {coords[0][1]:.6f})"
    body = ", ".join(f"{lon:.6f} {lat:.6f}" for lon, lat in coords)
    return f"LINESTRING({body})"


def parse(xml_bytes):
    root = ET.fromstring(xml_bytes)
    pub_time = ""
    for node in root.iter():
        if local(node.tag) == "publicationTime":
            pub_time = (node.text or "").strip()
            break
    records = []
    for el in root.iter():
        if local(el.tag) != "trafficElement":
            continue
        rec_id = ""
        comments = {}
        for ch in el:
            if local(ch.tag) == "id":
                rec_id = (ch.text or "").strip()
            elif local(ch.tag) == "generalPublicComment":
                comments.update(walk_comments(ch))
        records.append({
            "id": rec_id,
            "comments": comments,
            "wkt": wkt_of(coords_of(el)),
        })
    return pub_time, records


def append_rows(path, header, rows):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    new = not os.path.exists(path)
    with open(path, "a", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        if new:
            w.writerow(header)
        w.writerows(rows)


def known_column(path, col_idx):
    if not os.path.exists(path):
        return set()
    with open(path, newline="", encoding="utf-8") as f:
        return {row[col_idx] for row in csv.reader(f) if row}


def save_raw_hourly(feed, xml_bytes, now):
    hour_dir = os.path.join(ROOT, "raw", feed, now.strftime("%Y"), now.strftime("%m"))
    os.makedirs(hour_dir, exist_ok=True)
    path = os.path.join(hour_dir, now.strftime("%d_%H") + "00Z.xml.gz")
    if os.path.exists(path):
        return False
    with gzip.open(path, "wb") as f:
        f.write(xml_bytes)
    return True


def main():
    now = datetime.now(timezone.utc)
    stamp = now.strftime("%Y-%m-%dT%H:%M:%SZ")
    month = now.strftime("%Y-%m")
    summary = []

    # --- traffic ---
    xml_t = fetch(FEEDS["traffic"])
    raw_saved = save_raw_hourly("traffic", xml_t, now)
    pub, recs = parse(xml_t)
    geom_path = os.path.join(ROOT, "data", "traffic", "geometries.csv")
    obs_path = os.path.join(ROOT, "data", "traffic", f"obs_{month}.csv")
    known_geoms = known_column(geom_path, 0)
    geom_rows, obs_rows = [], []
    for r in recs:
        h = hashlib.md5(r["wkt"].encode()).hexdigest()[:12]
        c = r["comments"]
        if r["wkt"] and h not in known_geoms:
            known_geoms.add(h)
            geom_rows.append([h, c.get("from", ""), c.get("to", ""),
                              max(1, r["wkt"].count(",") + 1), r["wkt"]])
        obs_rows.append([stamp, pub, r["id"], h,
                         c.get("from", ""), c.get("to", ""), c.get("jamLevel", "")])
    if geom_rows:
        append_rows(geom_path, ["geom_hash", "street_from", "street_to", "n_points", "wkt"], geom_rows)
    append_rows(obs_path, ["fetched_utc", "publication_time", "record_id", "geom_hash",
                           "street_from", "street_to", "jam_level"], obs_rows)
    summary.append(f"traffic: {len(obs_rows)} obs ({len(geom_rows)} new geoms, raw={'y' if raw_saved else 'n'})")

    # --- alerts (append only newly seen alert ids) ---
    xml_a = fetch(FEEDS["alerts"])
    save_raw_hourly("alerts", xml_a, now)
    pub_a, recs_a = parse(xml_a)
    alerts_path = os.path.join(ROOT, "data", "alerts", f"alerts_{month}.csv")
    seen = known_column(alerts_path, 1)
    new_alerts = []
    for r in recs_a:
        if not r["id"] or r["id"] in seen:
            continue
        seen.add(r["id"])
        c = r["comments"]
        new_alerts.append([stamp, r["id"], c.get("type", ""), c.get("subtype", ""),
                           c.get("street", ""), c.get("report_time", ""), r["wkt"]])
    if new_alerts:
        append_rows(alerts_path, ["first_seen_utc", "alert_id", "type", "subtype",
                                  "street", "report_time", "wkt"], new_alerts)
    summary.append(f"alerts: {len(recs_a)} in feed, {len(new_alerts)} new")

    print(f"[{stamp}] " + " | ".join(summary))
    return 0


if __name__ == "__main__":
    sys.exit(main())
