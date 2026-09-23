"""
Loads normalized DataFrames into a local DuckDB warehouse file.

Each load clears the target table before inserting, so re-running the
pipeline replaces the data rather than appending to it. Without this,
repeated runs during development silently accumulate duplicate/stale rows
(including data from before a bug fix), which looks like a fix "isn't
working" when really old contaminated rows are still sitting in the table.
"""

from __future__ import annotations

from pathlib import Path

import duckdb
import pandas as pd

from config.settings import Settings
from src.utils.logging_config import get_logger

SCHEMA_PATH = Path(__file__).resolve().parent.parent / "models" / "schema.sql"


def init_schema(settings: Settings) -> None:
    logger = get_logger(__name__, settings.log_level)
    Path(settings.duckdb_path).parent.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect(settings.duckdb_path)
    try:
        con.execute(SCHEMA_PATH.read_text())
        logger.info("Schema initialized at %s", settings.duckdb_path)
    finally:
        con.close()


def _write(con: duckdb.DuckDBPyConnection, table: str, df: pd.DataFrame) -> None:
    if df.empty:
        return
    con.execute(f"DELETE FROM {table}")  # clear stale data from prior runs first
    con.register("tmp_df", df)
    con.execute(f"INSERT INTO {table} SELECT * FROM tmp_df")
    con.unregister("tmp_df")


def load_table(settings: Settings, table: str, df: pd.DataFrame) -> None:
    """Clear-and-replace load for a single warehouse table. All the named
    load_* functions below are thin wrappers around this, so the
    connect/write/close boilerplate exists in exactly one place."""
    con = duckdb.connect(settings.duckdb_path)
    try:
        _write(con, table, df)
    finally:
        con.close()


# Named wrappers -- kept so call sites stay explicit about which table
# they're loading (and so existing imports elsewhere don't need to change),
# without each one repeating the connect/write/close pattern.
def load_eia_hourly_demand(settings: Settings, df: pd.DataFrame) -> None:
    load_table(settings, "eia_hourly_demand", df)


def load_eia_retail_price(settings: Settings, df: pd.DataFrame) -> None:
    load_table(settings, "eia_retail_price", df)


def load_eia_retail_sales(settings: Settings, df: pd.DataFrame) -> None:
    load_table(settings, "eia_retail_sales", df)


def load_epa_frs_facilities(settings: Settings, df: pd.DataFrame) -> None:
    load_table(settings, "epa_frs_facilities", df)


def load_sustainability_metrics(settings: Settings, df: pd.DataFrame) -> None:
    load_table(settings, "sustainability_metrics", df)