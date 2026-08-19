# Data Center Energy & Water Footprint Tracker

Pulls public electricity demand/pricing data (EIA) and industrial facility
registry data (EPA) to explore how data center growth in a region relates
to grid load, retail electricity prices, and community-facing concerns
(water use, rising bills, local opposition) that have been driving real
backlash against new data center projects nationally.

## Why I'm looking at this problem

Data centers are one of the most contested infrastructure topics
happening right now: roughly 7 in 10 Americans oppose new data centers
in their area, largely over water use and rising electricity costs, and
dozens of proposed projects nationally have been delayed or killed by
local opposition. At the same time, companies report efficiency metrics
(like "90% less water per facility") that can obscure rising *total*
consumption as they build more facilities. I wanted to build the kind of
transparency tool that communities are actually asking for in these
fights, and test with real numbers whether the "data centers are driving
up my electric bill" narrative holds up — starting with Santa Clara
County and California as a concrete case study.

## Why I chose this data

- **EIA hourly demand + retail price data** — because "is the grid under
  more strain" and "are prices actually rising" are testable claims, not
  just talking points, and EIA publishes exactly the numbers needed to
  test them at the regional level (CAISO for California).
- **EPA TRI facility registry data** — to ground the "which industrial
  facilities are actually here" question in something more concrete than
  news anecdotes, scoped to Santa Clara County to keep it locally
  relevant to where I live and where I'm job hunting.
- **Company sustainability reports** (in progress) — because the water
  side of this story is the part specifically missing from most public
  dashboards, and it only exists in inconsistent PDF disclosures, which
  is itself part of the story worth showing.

## My approach

1. Start narrow and correct (one region, one county) rather than wide
   and wrong — better to have clean data for Santa Clara County/CAISO
   than sloppy data for the whole country.
2. Treat every data source as something to verify, not trust blindly —
   EPA and EIA field names, units, and even coordinate sign conventions
   turned out to have real inconsistencies (see below).
3. Build the pipeline to be re-runnable and idempotent, not a one-off
   script, so the dashboard reflects the current pull, not an
   accumulation of every debugging run.
4. Get the foundation fully correct before adding scope — forecasting,
   more regions, and the water-use layer come after the current three
   panels are verifiably accurate.

## How I actually cleaned and ran everything

Almost none of this worked on the first try, which is typical of working
with real public data rather than a sign something was done wrong. A
rundown of what came up and how it was handled:

- **EIA's `region-data` endpoint mixes demand, generation, interchange,
  and forecast values in one response**, distinguished only by a `type`
  facet. Without filtering to `type=D`, total interchange (which swings
  negative) was getting plotted as if it were part of electricity demand
  — explaining an early chart with impossible-looking negative demand.
- **EPA's facility data required three different attempts** before
  landing on something reliable: a generic Envirofacts table-join
  endpoint returned intermittent 500 errors, EPA's dedicated FRS search
  API returned intermittent 503 errors, and TRI (Toxics Release
  Inventory) — chosen because EPA's own docs show a confirmed-working
  example against it — finally worked consistently.
- **TRI's coordinate fields aren't fully reliable either**: the
  "preferred" latitude/longitude columns are sparsely populated (most
  rows only have the raw `FAC_LATITUDE`/`FAC_LONGITUDE` fields, not the
  cleaned-up `PREF_*` ones), longitude is stored as an unsigned
  magnitude rather than signed (so every value needed negating), and a
  handful of rows contained clearly invalid coordinates (values in the
  hundreds of thousands) that had to be filtered out with a plausibility
  bounding box before the map was usable.
- **The warehouse load logic originally just appended on every run**,
  which meant re-running the pipeline during debugging silently mixed
  old (buggy) data with new (fixed) data in the same table — a subtle
  bug that looked like the code fixes weren't working, when really the
  old contaminated rows were still sitting in the database. Fixed by
  clearing each table before every load, so each run is a clean replace.

## Setup

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1        # Mac/Linux: source .venv/bin/activate
pip install -r requirements.txt

cp .env.example .env
# Edit .env and set EIA_API_KEY (free, instant signup):
# https://www.eia.gov/opendata/register.php
```

**Every time you re-run the pipeline** (e.g. after pulling code changes),
clear the warehouse first so old and new data don't mix:

```powershell
Remove-Item data\processed\warehouse.duckdb   # Mac/Linux: rm data/processed/warehouse.duckdb
python run_pipeline.py
python -m streamlit run dashboards/app.py     # Mac/Linux: streamlit run dashboards/app.py
```

## Running tests

```bash
pytest
```

Tests use the `responses` library to mock all HTTP calls — no real API
key or network access is needed to run the suite, and no secrets are
required in CI.

## Architecture

```
EIA API ──────┐
              ├──► ingest/ ──► etl/normalize.py ──► etl/load_warehouse.py ──► DuckDB ──► dashboards/app.py
EPA TRI (Envirofacts) ┘
Sustainability reports (manual) ──────────────────────────┘
```

- **`src/ingest/`** — API clients (EIA, EPA TRI) + a manually curated
  module for sustainability report figures, since those exist only as
  inconsistent PDFs with no API.
- **`src/etl/normalize.py`** — maps each source's raw field names into a
  single stable schema, with resilient column-matching and row-wise
  coalescing (see above) so upstream field-naming quirks are handled in
  one place instead of breaking downstream code.
- **`src/etl/load_warehouse.py`** + **`src/models/schema.sql`** — clears
  and reloads normalized data into a local DuckDB file (zero external
  services required to run this end to end).
- **`dashboards/app.py`** — Streamlit dashboard (line charts + a pydeck
  map with hover tooltips) that reads *only* from DuckDB, never calls
  external APIs directly (see Security below).

## Results so far

*(This section will fill in further as the correlation/forecasting work
lands — current state below.)*

- **CA retail electricity prices have nearly tripled since 2005**, with
  a visibly steeper climb in the last few years — the era coinciding
  with the recent wave of hyperscale data center buildout nationally.
  The next step is quantifying this correlation directly (regional
  demand growth vs. price growth, not just two charts sitting side by
  side) rather than relying on visual coincidence.
- **CISO hourly demand shows the expected daily double-peak pattern**
  once correctly filtered to actual demand (`type=D`) — a clean baseline
  to measure future growth against.
- **358 TRI-reporting facilities are registered in Santa Clara County**,
  visibly clustered around San Jose/Santa Clara/Sunnyvale — the same
  geography as the historical semiconductor manufacturing footprint and
  current data center siting pressure.
- **Open question I still want to answer**: whether the water-use side
  of the story (currently unpopulated) shows the same "efficiency
  improving while absolute consumption rises" pattern that's been
  reported anecdotally at the company level.

## Security

This project handles a real (free, low-sensitivity, but still personal)
API key, so it follows a few practices worth calling out explicitly:

1. **Secrets never touch the codebase.** `EIA_API_KEY` is loaded from a
   local `.env` file at runtime via `config/settings.py`. `.env` is
   gitignored; only `.env.example` (with placeholder values) is committed.
2. **Fail fast, don't fail silently.** `config/settings.py` validates
   that required keys are actually set (and not left as the placeholder
   text) before any pipeline code runs, so a missing key throws a clear
   error instead of an obscure 401 deep in a stack trace.
3. **Keys never appear in logs.** `src/utils/logging_config.py` installs
   a `RedactingFilter` that scrubs `api_key=...`, `Bearer ...`, and
   similar patterns from every log line before it's written anywhere.
   The EIA client also strips the key from any URL before logging it
   directly (`_safe_url_for_logging`). See
   `tests/test_logging_redaction.py` for the tests that enforce this.
4. **Least privilege by layer.** The dashboard (`dashboards/app.py`)
   reads only from the local DuckDB file — it never calls EIA/EPA
   directly and therefore never needs a credential at all. Only the
   ingestion layer holds the key.
5. **Network hygiene.** Every external request sets an explicit timeout
   and uses bounded retries with exponential backoff (via `tenacity`),
   so a hung or flaky upstream API can't stall or infinitely hammer the
   pipeline.
6. **Optional: automated secret scanning.** `.pre-commit-config.yaml`
   wires up [gitleaks](https://github.com/gitleaks/gitleaks) to scan
   every commit for accidentally-staged secrets, as a backstop beyond
   `.gitignore`. Install with `pip install pre-commit && pre-commit install`.

If you ever want to demo this project live or deploy the dashboard
publicly (e.g. Streamlit Community Cloud), use that platform's secrets
manager for `EIA_API_KEY` rather than committing any `.env` file — never
put real keys in a public repo, including in commit history.

## Roadmap / how this scales

- Quantify the demand-vs-price correlation directly instead of showing
  two separate charts.
- Add a forecasting layer (Prophet is already in `requirements.txt`) to
  project regional grid load under different data center growth
  scenarios.
- Fill in `src/ingest/sustainability_reports.py` with real, cited
  water-use/PUE figures from company sustainability reports.
- Swap `DEFAULT_BALANCING_AUTHORITY` in `run_pipeline.py` from `CISO`
  (California) to `PJM` or `ERCOT` to compare against the Virginia/Texas
  data center clusters driving most of the national opposition headlines.
- Migrate `load_warehouse.py` from DuckDB to Snowflake/Postgres — the
  schema is already written in portable SQL, so this is mostly a
  connection-string change.
- Add a scraper for the [Data Center Watch](https://datacenterwatch.org)
  tracker to quantify opposition project counts/dollar values by region.

## Data sources

| Source | Used for |
|---|---|
| [EIA API](https://www.eia.gov/opendata/) | Hourly electricity demand, monthly retail prices |
| [EPA TRI via Envirofacts](https://www.epa.gov/enviro/envirofacts-data-service-api) | Registered industrial facilities reporting toxic releases |
| Company sustainability reports | Water use / PUE figures (manually curated, see `src/ingest/sustainability_reports.py`) |