"""
Loads normalized DataFrames into a local DuckDB warehouse file.

DuckDB is used here (rather than requiring a hosted Postgres/Snowflake)
so the project runs entirely locally with zero external services beyond
the public data APIs. 
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

def load_eia_hourly_demand(settings: Settings, df: pd.DataFrame) -> None:
    con = duckdb.connect(settings.duckdb_path)
    try:
        _write(con, "eia_hourly_demand", df)
    finally:
        con.close()


def load_eia_retail_price(settings: Settings, df: pd.DataFrame) -> None:
    con = duckdb.connect(settings.duckdb_path)
    try:
        _write(con, "eia_retail_price", df)
    finally:
        con.close()


def load_eia_retail_sales(settings: Settings, df: pd.DataFrame) -> None:
    con = duckdb.connect(settings.duckdb_path)
    try:
        _write(con, "eia_retail_sales", df)
    finally:
        con.close()


def load_epa_frs_facilities(settings: Settings, df: pd.DataFrame) -> None:
    con = duckdb.connect(settings.duckdb_path)
    try:
        _write(con, "epa_frs_facilities", df)
    finally:
        con.close()


def load_sustainability_metrics(settings: Settings, df: pd.DataFrame) -> None:
    con = duckdb.connect(settings.duckdb_path)
    try:
        _write(con, "sustainability_metrics", df)
    finally:
        con.close()
