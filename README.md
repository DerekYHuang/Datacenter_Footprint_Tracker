# Data Center Energy & Water Footprint Tracker

Pulls public electricity demand/pricing data (EIA) and industrial facility
registry data (EPA) to explore how data center growth in a region relates
to grid load, retail electricity prices, and community-facing concerns
(water use, rising bills, local opposition) that have been driving
real backlash against new data center projects nationally.

## Why this project exists

Data centers are one of the most contested infrastructure topics right
now — 7 in 10 Americans oppose new data centers in their area, largely
over water use and electricity costs, and dozens of projects have been
delayed or canceled by local opposition. Meanwhile companies report
efficiency metrics (like "90% less water per facility") that can obscure
rising *total* consumption as they build more facilities. This project
builds the kind of transparency tooling that communities are asking for
and that companies haven't fully provided yet.

## Architecture

```
EIA API ──────┐
              ├──► ingest/ ──► etl/normalize.py ──► etl/load_warehouse.py ──► DuckDB ──► dashboards/app.py
EPA Envirofacts┘
Sustainability reports (manual) ──────────────────────────┘
```

- **`src/ingest/`** — API clients (EIA, EPA Envirofacts) + a manually
  curated module for sustainability report figures, since those exist
  only as inconsistent PDFs with no API.
- **`src/etl/normalize.py`** — maps each source's raw field names into a
  single stable schema, so upstream API changes only require edits here.
- **`src/etl/load_warehouse.py`** + **`src/models/schema.sql`** — loads
  normalized data into a local DuckDB file (zero external services
  required to run this end to end).
- **`dashboards/app.py`** — Streamlit dashboard that reads *only* from
  DuckDB, never calls external APIs directly (see Security below).

## Setup

```bash
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt

cp .env.example .env
# Edit .env and set EIA_API_KEY (free, instant signup):
# https://www.eia.gov/opendata/register.php

python run_pipeline.py           # populates data/processed/warehouse.duckdb
streamlit run dashboards/app.py  # view the dashboard
```

## Running tests

```bash
pytest
```

Tests use the `responses` library to mock all HTTP calls — no real API
key or network access is needed to run the suite, and no secrets are
required in CI.

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
manager for `EIA_API_KEY` rather than committing any `.env` file —
never put real keys in a public repo, including in commit history.

## Roadmap / how this scales

- Swap `DEFAULT_BALANCING_AUTHORITY` in `run_pipeline.py` from `CISO`
  (California) to `PJM` or `ERCOT` to compare against the Virginia/Texas
  data center clusters driving most of the national opposition headlines.
- Add a forecasting notebook (Prophet is already in `requirements.txt`)
  to project regional grid load under different data center growth
  scenarios.
- Migrate `load_warehouse.py` from DuckDB to Snowflake/Postgres — the
  schema is already written in portable SQL, so this is mostly a
  connection-string change.
- Add a scraper for the [Data Center Watch](https://datacenterwatch.org)
  tracker to quantify opposition project counts/dollar values by region.

## Data sources

| Source | Used for |
|---|---|
| [EIA API](https://www.eia.gov/opendata/) | Hourly electricity demand, monthly retail prices |
| [EPA Envirofacts](https://www.epa.gov/enviro/envirofacts-data-service-api) | Registered industrial/large-load facilities (FRS) |
| Company sustainability reports | Water use / PUE figures (manually curated, see `src/ingest/sustainability_reports.py`) |
