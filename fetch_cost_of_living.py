#!/usr/bin/env python3
"""
fetch_cost_of_living.py
-----------------------
Pulls live U.S. CPI data from keyless FRED CSV exports of BLS series and writes
`data.js` next to the dashboard. The dashboard (`index.html`)
auto-detects `window.COL_DATA` and uses it instead of the built-in seed data.

USAGE
    1. python fetch_cost_of_living.py
    2. Serve the folder so the browser can load data.js:
           python -m http.server 8000
       then open  http://localhost:8000/

WHY A LOCAL SERVER?  Browsers block reading local files via file:// for security.
Serving over http:// lets the page load data.js. Without it, the dashboard still
works on its seed data.

The global side (cities, country inflation) can be wired the same way using the
Numbeo API (https://www.numbeo.com/common/api.jsp) or the free, key-less
World Bank Open Data API (https://api.worldbank.org/v2/country/all/indicator/FP.CPI.TOTL.ZG).
Hooks are stubbed at the bottom.
"""

import json
import datetime as dt
import csv
import time
from io import StringIO
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

# ---------------------------------------------------------------------------
FRED_CSV = "https://fred.stlouisfed.org/graph/fredgraph.csv"

# FRED series IDs sourced from BLS -> label shown in the dashboard.
# Use not-seasonally-adjusted CPI indexes so calculated 12-month changes match
# the headline figures published in the BLS CPI release.
HEADLINE_SERIES = "CPIAUCNS"          # CPI-U, all items
CATEGORY_SERIES = {
    "Energy":                 "CPIENGNS",
    "Shelter":                "CUUR0000SAH1",
    "Medical care services":  "CUUR0000SAM2",
    "Core (ex food/energy)":  "CPILFENS",
    "Food":                   "CPIUFDNS",
    "Apparel":                "CPIAPPNS",
    "Used cars & trucks":     "CUUR0000SETA02",
    "New vehicles":           "CUUR0000SETA01",
}
REPORTED = set(CATEGORY_SERIES)

MONTHS_BACK = 18  # length of the trend line


def request_bytes(request, timeout=30, attempts=5):
    """Fetch a URL with bounded retries for transient public-API failures."""
    for attempt in range(1, attempts + 1):
        try:
            with urlopen(request, timeout=timeout) as response:
                return response.read()
        except (HTTPError, URLError, TimeoutError) as exc:
            retryable = not isinstance(exc, HTTPError) or exc.code in {
                408, 429, 500, 502, 503, 504
            }
            if not retryable or attempt == attempts:
                raise
            delay = 2 ** (attempt - 1)
            print(
                f"Public API request failed ({exc}); retrying in {delay}s "
                f"[{attempt}/{attempts}] ..."
            )
            time.sleep(delay)


def fetch_text(url, params=None, timeout=30):
    """Fetch UTF-8 text using only the Python standard library."""
    if params:
        url = f"{url}?{urlencode(params)}"
    request = Request(url, headers={"User-Agent": "cost-of-living-trend-analyzer/1.0"})
    return request_bytes(request, timeout=timeout).decode("utf-8")


def fetch_json(url, timeout=30):
    return json.loads(fetch_text(url, timeout=timeout))


def fred_yoy(series_ids, start_year, end_year):
    """Return monthly year-over-year changes from keyless FRED CSV exports."""
    text = fetch_text(
        FRED_CSV,
        params={
            "id": ",".join(series_ids),
            "cosd": f"{start_year}-01-01",
            "coed": f"{end_year}-12-31",
        },
        timeout=45,
    )
    reader = csv.DictReader(StringIO(text))
    if not reader.fieldnames or "observation_date" not in reader.fieldnames:
        raise RuntimeError("FRED returned an invalid CSV response")

    levels = {series_id: {} for series_id in series_ids}
    for row in reader:
        try:
            observed = dt.date.fromisoformat(row["observation_date"])
        except (TypeError, ValueError):
            continue
        for series_id in series_ids:
            value = row.get(series_id)
            if value in (None, "", "."):
                continue
            try:
                levels[series_id][(observed.year, observed.month)] = float(value)
            except ValueError:
                continue

    output = {}
    for series_id, observations in levels.items():
        changes = []
        for (year, month), level in sorted(observations.items()):
            prior = observations.get((year - 1, month))
            if prior:
                date_text = dt.date(year, month, 1).isoformat()
                changes.append((date_text, round((level / prior - 1) * 100, 1)))
        output[series_id] = changes
    return output


def label_month(date_str):
    d = dt.date.fromisoformat(date_str)
    return d.strftime("%b '%y").replace("'0", "'")  # e.g. May '26


def label_long_month(date_str):
    return dt.date.fromisoformat(date_str).strftime("%B %Y")


def build_payload():
    today = dt.date.today()
    print("Fetching BLS CPI series from keyless FRED CSV exports ...")
    all_series = [HEADLINE_SERIES, *CATEGORY_SERIES.values()]
    live = fred_yoy(all_series, today.year - 3, today.year)
    headline = live.get(HEADLINE_SERIES, [])[-MONTHS_BACK:]
    if not headline:
        raise SystemExit("FRED returned no usable headline CPI observations.")
    trend = [{"m": label_month(d), "v": v, "est": False} for d, v in headline]

    latest = headline[-1][1]
    prev = headline[-2][1] if len(headline) > 1 else latest

    print("Fetching categories ...")
    categories = []
    core_val = latest
    for name, sid in CATEGORY_SERIES.items():
        try:
            series = live.get(sid, [])
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
            "catMonth": label_long_month(headline[-1][0]),
            "metaNote": f"BLS · {label_long_month(headline[-1][0])}",
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
    {"country": "United States", "code": "USA", "v": 3.4, "here": True},
    {"country": "Euro area", "code": "EMU", "v": 3.2},
    {"country": "Switzerland", "code": "CHE", "v": 0.6},
]
NEXT_CPI = "September 11, 2026"
# Fallback outlook only: the dashboard now computes its own damped-trend
# forecast from the trend series in-browser; these values are used only if
# that computation can't run (series shorter than 6 points).
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
        rows = fetch_json(url, timeout=30)[1] or []
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
        for r in fetch_json(url, timeout=20)[1] or []:
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
    print("  Open:     http://localhost:8000/")


if __name__ == "__main__":
    main()
