"""
Entry point: run the full ingest -> normalize -> load pipeline.

Usage:
    python run_pipeline.py

Make sure you've copied .env.example to .env and filled in EIA_API_KEY
first (see README.md).
"""

from __future__ import annotations

import datetime as dt

from config.settings import get_settings
from src.etl.load_warehouse import (
    init_schema,
    load_eia_hourly_demand,
    load_eia_retail_price,
    load_epa_frs_facilities,
    load_sustainability_metrics,
)
from src.etl.normalize import (
    normalize_eia_hourly_demand,
    normalize_eia_retail_price,
    normalize_epa_frs_facilities,
)
from src.ingest.eia_client import EIAClient
from src.ingest.envirofacts_client import EnvirofactsClient
from src.ingest.sustainability_reports import load_sustainability_entries
from src.utils.logging_config import get_logger

# California ISO -- swap in "PJM" or "ERCOT" to compare against the
# Virginia/Texas data center clusters mentioned in the research.
DEFAULT_BALANCING_AUTHORITY = "CISO"
DEFAULT_STATE = "CA"


def main() -> None:
    settings = get_settings(require_eia=True)
    logger = get_logger("pipeline", settings.log_level)

    logger.info("Initializing warehouse schema...")
    init_schema(settings)

    end = dt.datetime.utcnow()
    start = end - dt.timedelta(days=30)
    start_str = start.strftime("%Y-%m-%dT%H")
    end_str = end.strftime("%Y-%m-%dT%H")

    logger.info("Pulling EIA hourly demand for %s...", DEFAULT_BALANCING_AUTHORITY)
    eia = EIAClient(settings=settings)
    raw_demand = eia.get_hourly_demand(DEFAULT_BALANCING_AUTHORITY, start_str, end_str)
    load_eia_hourly_demand(settings, normalize_eia_hourly_demand(raw_demand))
    logger.info("Loaded %d hourly demand rows", len(raw_demand))

    logger.info("Pulling EIA retail price for %s...", DEFAULT_STATE)
    raw_price = eia.get_retail_price(DEFAULT_STATE)
    load_eia_retail_price(settings, normalize_eia_retail_price(raw_price))
    logger.info("Loaded %d retail price rows", len(raw_price))

    logger.info("Pulling EPA FRS facilities for %s...", DEFAULT_STATE)
    envirofacts = EnvirofactsClient(settings=settings)
    raw_facilities = envirofacts.get_facilities_by_state(DEFAULT_STATE, rows=500)
    load_epa_frs_facilities(settings, normalize_epa_frs_facilities(raw_facilities))
    logger.info("Loaded %d facility rows", len(raw_facilities))

    logger.info("Loading manually-curated sustainability report entries...")
    sustainability_df = load_sustainability_entries()
    load_sustainability_metrics(settings, sustainability_df)
    logger.info("Loaded %d sustainability metric rows", len(sustainability_df))

    logger.info("Pipeline complete. Warehouse at: %s", settings.duckdb_path)


if __name__ == "__main__":
    main()
