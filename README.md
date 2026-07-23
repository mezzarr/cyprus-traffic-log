# cyprus-traffic-log

Continuous logger of the open **Waze traffic & alerts feeds for Cyprus**, published by the
Cyprus National Access Point ([traffic4cyprus.org.cy](https://www.traffic4cyprus.org.cy/),
Public Works Department / KIOS CoE) in DATEX II v3 format, licence **CC BY 4.0**.

A GitHub Action fetches both feeds every ~10 minutes and appends compact CSV observations.
Raw XML snapshots are kept once per hour (gzipped) as parsing insurance.

## Why

Collected to build an empirical congestion time-series for the greater Nicosia area
(with a summer-holiday baseline vs school-term comparison) in support of urban planning
analysis for the new Nicosia Local Plan (Τοπικό Σχέδιο Λευκωσίας) — positions of the
Municipality of Strovolos, prepared by MELOUAR (Mesaritis & Loizou Associates LLC).

## Layout

```
data/traffic/obs_YYYY-MM.csv    one row per road segment per fetch:
                                fetched_utc, publication_time, record_id, geom_hash,
                                street_from, street_to, jam_level (0-5)
data/traffic/geometries.csv     geom_hash -> WKT LINESTRING (WGS84), street from/to
data/alerts/alerts_YYYY-MM.csv  one row per NEW alert id:
                                first_seen_utc, alert_id, type, subtype, street,
                                report_time, wkt
raw/<feed>/YYYY/MM/DD_HH00Z.xml.gz   hourly raw DATEX II snapshots
data/health.csv                 feed outages (utc, feed, error) — appended when a
                                feed stays unreachable/unparseable after retries
```

Note: up to 2026-07-23 the cron ran ~7x/day due to GitHub schedule throttling
(gaps of 1–12 h); from 2026-07-23 the workflow loops internally, giving true
~10-minute sampling with a short (~20 min) predictable gap every 3 hours.

Jam levels (per feed documentation): 0 = free flow … 4 = standstill, 5 = road closed.
Coordinates are WGS84 (EPSG:4326); reproject to CGRS93 / LTM (EPSG:6312) for Cyprus work.

## Licence & attribution

- Source data: © Public Works Department / Cyprus National Access Point / Waze — CC BY 4.0.
- This repository's logs: CC BY 4.0, attribution "cyprus-traffic-log (MELOUAR), source CyNAP/PWD/Waze".
- Code: MIT.
