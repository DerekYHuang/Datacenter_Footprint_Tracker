"""
Entry point: run the full ingest -> normalize -> load pipeline.

Usage:
    python run_pipeline.py

Make sure you've copied .env.example to .env and filled in EIA_API_KEY
first (see README.md).
"""

from __future__ import annotations

import datetime as dt
from logging import Logger
from typing import Callable

import pandas as pd

from config.settings import Settings, get_settings
from src.etl.load_warehouse import (
    init_schema,
    load_eia_hourly_demand,
    load_eia_retail_price,
    load_eia_retail_sales,
    load_epa_frs_facilities,
    load_sustainability_metrics,
)
from src.etl.normalize import (
    normalize_eia_hourly_demand,
    normalize_eia_retail_price,
    normalize_eia_retail_sales,
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
DEFAULT_COUNTY = "Santa Clara"


def _pull_and_load(
    logger: Logger,
    label: str,
    fetch: Callable[[], pd.DataFrame],
    normalize: Callable[[pd.DataFrame], pd.DataFrame],
    load: Callable[[Settings, pd.DataFrame], None],
    settings: Settings,
) -> None:
    """Fetch -> normalize -> load one source, with consistent logging.
    Every source in this pipeline follows this exact shape, so this
    replaces five near-identical fetch/normalize/load/log blocks."""
    logger.info("Pulling %s...", label)
    raw = fetch()
    load(settings, normalize(raw))
    logger.info("Loaded %d %s rows", len(raw), label)


def main() -> None:
    settings = get_settings(require_eia=True)
    logger = get_logger("pipeline", settings.log_level)

    logger.info("Initializing warehouse schema...")
    init_schema(settings)

    end = dt.datetime.now(dt.timezone.utc)
    start = end - dt.timedelta(days=30)
    start_str, end_str = start.strftime("%Y-%m-%dT%H"), end.strftime("%Y-%m-%dT%H")

    eia = EIAClient(settings=settings)
    envirofacts = EnvirofactsClient(settings=settings)

    _pull_and_load(
        logger, f"hourly demand for {DEFAULT_BALANCING_AUTHORITY}",
        lambda: eia.get_hourly_demand(DEFAULT_BALANCING_AUTHORITY, start_str, end_str),
        normalize_eia_hourly_demand, load_eia_hourly_demand, settings,
    )
    _pull_and_load(
        logger, f"retail price for {DEFAULT_STATE}",
        lambda: eia.get_retail_price(DEFAULT_STATE),
        normalize_eia_retail_price, load_eia_retail_price, settings,
    )
    _pull_and_load(
        logger, f"retail sales (consumption) for {DEFAULT_STATE}",
        lambda: eia.get_retail_sales(DEFAULT_STATE),
        normalize_eia_retail_sales, load_eia_retail_sales, settings,
    )
    _pull_and_load(
        logger, f"TRI facilities for {DEFAULT_COUNTY} County, {DEFAULT_STATE}",
        lambda: envirofacts.get_facilities(state_abbr=DEFAULT_STATE, county_name=DEFAULT_COUNTY),
        normalize_epa_frs_facilities, load_epa_frs_facilities, settings,
    )
    _pull_and_load(
        logger, "sustainability report entries",
        load_sustainability_entries,
        lambda df: df,  # already in warehouse shape, nothing to normalize
        load_sustainability_metrics, settings,
    )

    logger.info("Pipeline complete. Warehouse at: %s", settings.duckdb_path)


if __name__ == "__main__":
    main()