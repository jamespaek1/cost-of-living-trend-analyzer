# Cost of Living Trend Analyzer

A self-contained, interactive dashboard tracking cost-of-living trends across the **US** (by category) and **globally** (by city and by country inflation), built for the TKH × Bloomberg Hackathon.

It ships with **real June 2026 data** baked in, so it works the instant you open it — and includes a script to refresh it with **live data** from the Federal Reserve and BLS APIs.

## Files

| File | What it is |
|---|---|
| `cost-of-living-trend-analyzer.html` | The dashboard. Zero dependencies — open it in any browser. |
| `fetch_cost_of_living.py` | Pulls live US CPI data from FRED/BLS and regenerates the dashboard data. |
| `README.md` | This file. |

## Run it (instant)

Double-click `cost-of-living-trend-analyzer.html`, or drop it on any static host (GitHub Pages, Netlify, Vercel). No build step, no server required for the demo.

## Run it with live data

1. Get a free FRED API key: https://fredaccount.stlouisfed.org/apikeys
2. Install the one dependency and set your key:
   ```bash
   pip install requests
   export FRED_API_KEY=your_key_here
   ```
3. Generate live data, then serve the folder:
   ```bash
   python fetch_cost_of_living.py
   python -m http.server 8000
   ```
4. Open http://localhost:8000/cost-of-living-trend-analyzer.html

The script writes `data.js` (`window.COL_DATA`); the dashboard auto-detects it and replaces the seed data. A local server is needed only because browsers block reading local files over `file://` — without it the dashboard simply uses its seed data.

## What's in it

- **Hero** — current US headline inflation, an 18-month sparkline, a **next-CPI-release** indicator, and a **live auto-refresh ticker** (last checked / countdown to next check).
- **My location · live** — pick any of ~200 economies (list itself fetched live from the World Bank). The moment you choose, the app fetches your country's inflation history, price level vs the US (PPP), and GNI per capita — and runs the damped-trend forecaster on *your* country's series. Your selection is encoded in the URL (`#c=FRA&city=Paris`) so links are shareable, and shared links open straight to this tab. City is a display label (data resolution is country-level; see notes).
- **US · by category** — trend line with a **computed statistical forecast** (damped-trend Holt smoothing, ~80% band), category bars, and a **metro drill-down** against the national average.
- **Global · by city** — cost-of-living index (NYC = 100) plus a **pay-equivalence calculator**.
- **Global · inflation extremes** — 2026 inflation on a log scale, **live from the World Bank API** with a live/snapshot status line.
- **Global · purchasing power** — cost-vs-purchasing-power scatter with a toggle between **city wage proxies** and **live World Bank GNI (PPP)**.
- **Toolkit · models & export** — personal inflation calculator (defaults reproduce the official 4.2%), energy scenario simulator, CSV export. All computed client-side.

## Real-time behavior (honest version)

Cost-of-living statistics publish on schedules — US CPI monthly, World Bank series annually — so no app can show tick-by-tick living costs. What this project does instead:

1. **In-browser polling** — the page re-checks every live source (World Bank inflation, GNI, and your selected country) every 15 minutes, and immediately when you return to the tab. A ticker in the header shows last-checked time and a countdown; the moment a source publishes new data, it appears without a reload.
2. **Self-updating deployment** — `refresh-data.yml` is a ready GitHub Actions workflow that runs the fetcher daily and commits a fresh `data.js` only when data changed. With GitHub Pages on, the public site updates itself with zero human involvement. Setup instructions are at the top of the workflow file (move it to `.github/workflows/` and add a `FRED_API_KEY` repo secret).

## The demo narrative (for judges)

The model-vs-news tension is your strongest 30 seconds: the damped-trend forecast, seeing only momentum, projects inflation rising toward ~4.6%; the scenario tool, fed the June energy reversal, shows headline falling toward ~2.6% if energy fully normalizes. Two rigorous methods, two answers — and the dashboard makes the disagreement explicit instead of hiding it. Then personalize: drag the "My inflation" sliders to show a renter with a long commute lives in a different inflation reality than the headline number.

## Data sources

- **US prices/inflation** — U.S. Bureau of Labor Statistics CPI; Federal Reserve (FRED). FRED's `units=pc1` returns year-over-year change directly, which is why it's the easiest starting point.
- **Country inflation** — **live from the free, key-less World Bank Open Data API** (`FP.CPI.TOTL.ZG`), in two places: the dashboard fetches it in-browser, and `fetch_cost_of_living.py` merges it server-side (`merge_worldbank_inflation`). Countries the World Bank has no recent value for fall back to IMF World Economic Outlook (April 2026) forecasts.
- **Global cities** — Numbeo Cost of Living Index 2026 (NYC = 100). The World Bank has no city-level cost index, so this stays a curated snapshot; wire Numbeo's API for live city values.
- **Purchasing power** — average net wage ÷ cost of living, rebased to NYC = 100. Wages are approximate net-salary proxies; `fetch_gni_ppp()` in the script shows how to pull live GNI-per-capita (PPP) from the World Bank as an income proxy.

Headline, core, energy, and shelter figures are the reported BLS values (May 2026, released June 10); other US category values and the pre-2026 trend are approximate placeholders until you run the live fetch. See each panel's "Data notes."

## Extend it (ideas for the hackathon)

- **City-level live cost data** — wire the cities panel to the Numbeo API (the World Bank only goes to country level). Country inflation and the GNI income proxy are already live via World Bank.
- **Live metro CPI** — swap the placeholder metro values for live BLS regional CPI-U series (one series ID per metro; see the note in `CURATED_METROS`). New York's 5.1% is already a reported figure.
- **Upgrade the forecaster** — damped-trend Holt smoothing is built in and runs in-browser; a server-side ARIMA or Prophet model could add seasonality and exogenous energy inputs.
- **Persist scenarios** — save "My inflation" profiles and comparisons (artifact storage API or a small backend).
- **Auto-refresh** — schedule `fetch_cost_of_living.py` (cron / GitHub Action) so the deployed dashboard updates monthly when new CPI prints.

## Design notes

All quantitative values render in a monospace face with tabular alignment — a small nod to financial readouts — and the inflation "heat" is encoded consistently across every view so the eye can scan severity at a glance.
