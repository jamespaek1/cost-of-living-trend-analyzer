#!/usr/bin/env python3
"""
fetch_cost_of_living.py
-----------------------
Pulls LIVE US cost-of-living data from the Federal Reserve (FRED) API and writes
`data.js` next to the dashboard. The dashboard (cost-of-living-trend-analyzer.html)
auto-detects `window.COL_DATA` and uses it instead of the built-in seed data.

USAGE
    1. Get a free FRED API key:  https://fredaccount.stlouisfed.org/apikeys
    2. pip install requests
    3. export FRED_API_KEY=your_key_here      (or paste it into FRED_API_KEY below)
    4. python fetch_cost_of_living.py
    5. Serve the folder so the browser can load data.js:
           python -m http.server 8000
       then open  http://localhost:8000/cost-of-living-trend-analyzer.html

WHY A LOCAL SERVER?  Browsers block reading local files via file:// for security.
Serving over http:// lets the page load data.js. Without it, the dashboard still
works on its seed data.

The global side (cities, country inflation) can be wired the same way using the
Numbeo API (https://www.numbeo.com/common/api.jsp) or the free, key-less
World Bank Open Data API (https://api.worldbank.org/v2/country/all/indicator/FP.CPI.TOTL.ZG).
Hooks are stubbed at the bottom.
"""

import os
import json
import datetime as dt

try:
    import requests
except ImportError:
    raise SystemExit("Missing dependency. Run:  pip install requests")

# ---------------------------------------------------------------------------
FRED_API_KEY = os.environ.get("FRED_API_KEY", "PASTE_YOUR_KEY_HERE")
FRED_BASE = "https://api.stlouisfed.org/fred/series/observations"

# FRED series IDs -> label shown in the dashboard.
# units=pc1 asks FRED for the year-over-year percent change directly.
HEADLINE_SERIES = "CPIAUCSL"          # CPI, All items
CATEGORY_SERIES = {
    "Energy":                 "CPIENGSL",
    "Shelter":                "CUSR0000SAH1",
    "Medical care":           "CPIMEDSL",
    "Core (ex food/energy)":  "CPILFESL",
    "Food":                   "CPIUFDSL",
    "Apparel":                "CPIAPPSL",
    "Used cars & trucks":     "CUSR0000SETA02",
    "New vehicles":           "CUSR0000SETA01",
}
REPORTED = {"Energy", "Shelter", "Core (ex food/energy)"}  # flag as headline-reported

MONTHS_BACK = 18  # length of the trend line


def fred_yoy(series_id, start):
    """Return list of (YYYY-MM-DD, value%) year-over-year observations since `start`."""
    params = {
        "series_id": series_id,
        "api_key": FRED_API_KEY,
        "file_type": "json",
        "units": "pc1",                 # percent change from a year ago
        "observation_start": start,
        "sort_order": "asc",
    }
    r = requests.get(FRED_BASE, params=params, timeout=30)
    r.raise_for_status()
    obs = r.json().get("observations", [])
    out = []
    for o in obs:
        if o["value"] not in (".", "", None):
            out.append((o["date"], round(float(o["value"]), 1)))
    return out


def label_month(date_str):
    d = dt.date.fromisoformat(date_str)
    return d.strftime("%b '%y").replace("'0", "'")  # e.g. May '26


def build_payload():
    if FRED_API_KEY in ("", "PASTE_YOUR_KEY_HERE"):
        raise SystemExit(
            "No FRED API key set.\n"
            "Get one free at https://fredaccount.stlouisfed.org/apikeys "
            "then `export FRED_API_KEY=...` and re-run."
        )

    start = (dt.date.today().replace(day=1) -
             dt.timedelta(days=31 * (MONTHS_BACK + 2))).isoformat()

    print(f"Fetching headline CPI ({HEADLINE_SERIES}) ...")
    headline = fred_yoy(HEADLINE_SERIES, start)[-MONTHS_BACK:]
    trend = [{"m": label_month(d), "v": v, "est": False} for d, v in headline]

    latest = headline[-1][1]
    prev = headline[-2][1] if len(headline) > 1 else latest

    print("Fetching categories ...")
    categories = []
    core_val = latest
    for name, sid in CATEGORY_SERIES.items():
        try:
            series = fred_yoy(sid, start)
            val = series[-1][1] if series else None
            if val is None:
                continue
            if name.startswith("Core"):
                core_val = val
            categories.append({"name": name, "yoy": val,
                               **({"reported": True} if name in REPORTED else {})})
            print(f"  {name:24s} {val:+.1f}%")
        except Exception as e:
            print(f"  ! skipped {name}: {e}")

    # 2026 energy-shock band starts roughly at the dip before the run-up;
    # keep it at the third-to-last point as a sensible default.
    shock_idx = max(0, len(trend) - 6)

    print("Fetching live country inflation (World Bank) ...")
    countries = merge_worldbank_inflation(CURATED_COUNTRIES)

    print("Fetching live GNI per capita, PPP (World Bank) ...")
    cities = attach_live_gni(CURATED_CITIES)
    purchasing = compute_purchasing_power(cities)

    payload = {
        "asOf": dt.date.today().strftime("%B %-d, %Y"),
        "us": {
            "headline": latest,
            "headlinePrev": prev,
            "core": core_val,
            "catMonth": label_month(headline[-1][0]),
            "metaNote": f"FRED live · pulled {dt.date.today().isoformat()}",
            "trend": trend,
            "shockFromIndex": shock_idx,
            "categories": categories,
            "nextCpi": NEXT_CPI,
            "metroNational": latest,
            "outlook": OUTLOOK,
            "metros": CURATED_METROS,
        },
        "cities": cities,                         # carries salary + live GNI
        "countries": countries,                   # live World Bank where available
        "purchasingPower": purchasing,            # precomputed, for other consumers
        "global": {"growth": 3.1, "headline": 3.8},
    }
    return payload


# --- curated global snapshot (live World Bank merged in below) ----------------
CURATED_CITIES = [
    {"city": "Zurich", "country": "Switzerland", "cc": "CHE", "idx": 122, "salary": 7800, "gni": 90000},
    {"city": "Geneva", "country": "Switzerland", "cc": "CHE", "idx": 120, "salary": 7300, "gni": 90000},
    {"city": "New York", "country": "United States", "cc": "USA", "idx": 100, "salary": 6200, "gni": 81000},
    {"city": "San Francisco", "country": "United States", "cc": "USA", "idx": 97.6, "salary": 7000, "gni": 81000},
    {"city": "Singapore", "country": "Singapore", "cc": "SGP", "idx": 88, "salary": 4200, "gni": 127000},
    {"city": "Hong Kong", "country": "Hong Kong", "cc": "HKG", "idx": 83, "salary": 3300, "gni": 75000},
    {"city": "Boston", "country": "United States", "cc": "USA", "idx": 82.4, "salary": 5200, "gni": 81000},
    {"city": "Sydney", "country": "Australia", "cc": "AUS", "idx": 80.5, "salary": 4300, "gni": 62000},
    {"city": "Miami", "country": "United States", "cc": "USA", "idx": 80.1, "salary": 4100, "gni": 81000},
    {"city": "London", "country": "United Kingdom", "cc": "GBR", "idx": 78, "salary": 3900, "gni": 58000},
    {"city": "Chicago", "country": "United States", "cc": "USA", "idx": 73.2, "salary": 4600, "gni": 81000},
    {"city": "Dubai", "country": "UAE", "cc": "ARE", "idx": 62, "salary": 3800, "gni": 88000},
    {"city": "Paris", "country": "France", "cc": "FRA", "idx": 58, "salary": 3100, "gni": 60000},
    {"city": "Tokyo", "country": "Japan", "cc": "JPN", "idx": 55, "salary": 2600, "gni": 49000},
]
CURATED_COUNTRIES = [
    {"country": "Venezuela", "code": "VEN", "v": 685},
    {"country": "South Sudan", "code": "SSD", "v": 113},
    {"country": "Iran", "code": "IRN", "v": 50},
    {"country": "Argentina", "code": "ARG", "v": 33},
    {"country": "Turkey", "code": "TUR", "v": 31},
    {"country": "United States", "code": "USA", "v": 4.2, "here": True},
    {"country": "Euro area", "code": "EMU", "v": 3.2},
    {"country": "Switzerland", "code": "CHE", "v": 0.6},
]
NEXT_CPI = "July 14, 2026"
# Near-term OUTLOOK scenario (not a forecast) reflecting the mid-June energy reversal.
OUTLOOK = [
    {"m": "Jun '26", "v": 4.0},
    {"m": "Jul '26", "v": 3.6},
    {"m": "Aug '26", "v": 3.3},
]
# Metro CPI. New York (5.1%) is reported; others are placeholders.
# To make these live, look up BLS regional CPI-U series IDs (one per metro) at
# https://www.bls.gov/cpi/regional-resources.htm and fetch via fred_yoy()/BLS API.
CURATED_METROS = [
    {"name": "New York–Newark–Jersey City", "yoy": 5.1, "reported": True},
    {"name": "Miami–Fort Lauderdale", "yoy": 4.8},
    {"name": "San Diego", "yoy": 4.6},
    {"name": "Boston", "yoy": 4.4},
    {"name": "Los Angeles", "yoy": 4.3},
    {"name": "Seattle", "yoy": 4.1},
    {"name": "Atlanta", "yoy": 4.0},
    {"name": "Chicago", "yoy": 3.9},
    {"name": "Dallas–Fort Worth", "yoy": 3.8},
    {"name": "Houston", "yoy": 3.7},
    {"name": "Phoenix", "yoy": 3.6},
]


# --- LIVE: merge World Bank country inflation into the curated list -----------
WB_INFLATION = "FP.CPI.TOTL.ZG"   # inflation, consumer prices, annual %


def merge_worldbank_inflation(countries):
    """Override each country's value with the latest World Bank actual where available.
    Free, no API key. Countries with no recent value keep their IMF forecast."""
    codes = ";".join(c["code"] for c in countries if c.get("code"))
    url = (f"https://api.worldbank.org/v2/country/{codes}/indicator/"
           f"{WB_INFLATION}?format=json&per_page=400&mrnev=1")
    out = [dict(c) for c in countries]
    by_code = {c["code"]: c for c in out}
    try:
        rows = requests.get(url, timeout=30).json()[1] or []
        hits, years = 0, []
        for r in rows:
            if r.get("value") is None:
                continue
            code = r.get("countryiso3code") or (r.get("country") or {}).get("id")
            if code in by_code:
                by_code[code]["v"] = round(float(r["value"]), 1)
                by_code[code]["live"] = True
                years.append(r["date"])
                hits += 1
        if hits:
            print(f"World Bank: merged {hits} live inflation values "
                  f"({min(years)}-{max(years)})")
        else:
            print("World Bank: no live values returned; keeping IMF forecasts")
    except Exception as e:
        print(f"World Bank fetch failed ({e}); keeping IMF forecasts")
    return out


def compute_purchasing_power(cities):
    """Wages / cost, indexed so New York = 100 (higher = more affordable for locals)."""
    ny = next((c for c in cities if c["city"] == "New York"), cities[0])
    base = ny["salary"] / ny["idx"]
    out = []
    for c in cities:
        aff = round((c["salary"] / c["idx"]) / base * 100, 1)
        out.append({"city": c["city"], "idx": c["idx"],
                    "salary": c["salary"], "affordability": aff})
    return sorted(out, key=lambda x: -x["affordability"])


# --- OPTIONAL: GNI per capita (PPP) as a live income proxy --------------------
def fetch_gni_ppp(country_codes=("CHE", "USA", "SGP", "GBR", "FRA", "JPN")):
    """Latest GNI per capita, PPP (current international $) per country, no key."""
    codes = ";".join(country_codes)
    url = (f"https://api.worldbank.org/v2/country/{codes}/indicator/"
           f"NY.GNP.PCAP.PP.CD?format=json&per_page=400&mrnev=1")
    out = {}
    try:
        for r in requests.get(url, timeout=20).json()[1] or []:
            if r.get("value") is not None:
                code = r.get("countryiso3code") or (r.get("country") or {}).get("id")
                out[code] = round(float(r["value"]))
    except Exception as e:
        print(f"  ! GNI fetch: {e}")
    return out


def attach_live_gni(cities):
    """Override each city's GNI with the latest World Bank GNI per capita (PPP)."""
    codes = sorted({c["cc"] for c in cities if c.get("cc")})
    live = fetch_gni_ppp(tuple(codes)) if codes else {}
    out = [dict(c) for c in cities]
    n = 0
    for c in out:
        if c.get("cc") and c["cc"] in live:
            c["gni"] = live[c["cc"]]
            n += 1
    print(f"World Bank: merged {n} live GNI values" if n
          else "World Bank: no live GNI returned; keeping snapshot")
    return out


def main():
    payload = build_payload()
    js = "window.COL_DATA = " + json.dumps(payload, indent=2) + ";\n"
    with open("data.js", "w", encoding="utf-8") as f:
        f.write(js)
    print("\n✓ Wrote data.js")
    print("  Now run:  python -m http.server 8000")
    print("  Open:     http://localhost:8000/cost-of-living-trend-analyzer.html")


if __name__ == "__main__":
    main()
