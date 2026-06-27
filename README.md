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

- **Hero** — current US headline inflation with an 18-month sparkline marking the 2026 reversal, plus a **next-CPI-release** indicator (Jul 14) reinforcing the real-time framing.
- **US · by category** — a trend line with a dashed **near-term outlook** (the mid-June energy reversal, labeled as a scenario), a year-over-year category bar chart, and a **metro drill-down** showing inflation across US metro areas against the national average.
- **Global · by city** — cost-of-living index with New York = 100, plus a **pay-equivalence calculator**: enter a salary and two cities to see what you'd need to keep the same lifestyle ("a $80,000 New York lifestyle needs ~$97,600 in Zurich").
- **Global · inflation extremes** — 2026 inflation on a log scale. **Live from the World Bank API** when online (with a live/snapshot status line); IMF snapshot offline.
- **Global · purchasing power** — the reframe that lands with judges: a cost-vs-purchasing-power scatter and a ranked bar showing a city can top the cost charts yet stay livable on local wages. A toggle switches the income basis between **city wage proxies** and **live World Bank GNI per capita (PPP)** — the two methodologies tell different stories, which is itself a talking point.

## Data sources

- **US prices/inflation** — U.S. Bureau of Labor Statistics CPI; Federal Reserve (FRED). FRED's `units=pc1` returns year-over-year change directly, which is why it's the easiest starting point.
- **Country inflation** — **live from the free, key-less World Bank Open Data API** (`FP.CPI.TOTL.ZG`), in two places: the dashboard fetches it in-browser, and `fetch_cost_of_living.py` merges it server-side (`merge_worldbank_inflation`). Countries the World Bank has no recent value for fall back to IMF World Economic Outlook (April 2026) forecasts.
- **Global cities** — Numbeo Cost of Living Index 2026 (NYC = 100). The World Bank has no city-level cost index, so this stays a curated snapshot; wire Numbeo's API for live city values.
- **Purchasing power** — average net wage ÷ cost of living, rebased to NYC = 100. Wages are approximate net-salary proxies; `fetch_gni_ppp()` in the script shows how to pull live GNI-per-capita (PPP) from the World Bank as an income proxy.

Headline, core, energy, and shelter figures are the reported BLS values (May 2026, released June 10); other US category values and the pre-2026 trend are approximate placeholders until you run the live fetch. See each panel's "Data notes."

## Extend it (ideas for the hackathon)

- **City-level live cost data** — wire the cities panel to the Numbeo API (the World Bank only goes to country level). Country inflation and the GNI income proxy are already live via World Bank.
- **Live metro CPI** — swap the placeholder metro values for live BLS regional CPI-U series (one series ID per metro; see the note in `CURATED_METROS`). New York's 5.1% is already a reported figure.
- **Turn the outlook into a real forecast** — the dashed line is a hand-set scenario; replace it with an ARIMA/regression on the FRED series.
- **Persist comparisons** — let users save salary-comparison scenarios (use the artifact storage API or a backend).
- **Auto-refresh** — schedule `fetch_cost_of_living.py` (cron / GitHub Action) so the deployed dashboard updates monthly when new CPI prints.

## Design notes

All quantitative values render in a monospace face with tabular alignment — a small nod to financial readouts — and the inflation "heat" is encoded consistently across every view so the eye can scan severity at a glance.
