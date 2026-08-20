"""
Correlation analysis: does electricity CONSUMPTION growth (a proxy for
grid load, which data center buildout drives) move together with retail
PRICE growth over the same period?

We use monthly retail-sales "sales" (consumption, million kWh) rather
than the hourly demand series, because hourly demand only covers ~30
days of recent history -- not enough to say anything about a multi-year
trend. Sales and price come from the same EIA endpoint/geography/months,
so they're already aligned for a fair comparison.

Both series are converted to an indexed "% change from the first common
period" before comparing, since sales (million kWh) and price (cents per
kWh) are on totally different scales -- comparing raw correlation of the
levels would be misleading (e.g. seasonal swings in consumption would
dominate over the slow price trend). Pearson correlation is computed on
these normalized growth series.
"""

from __future__ import annotations

from dataclasses import dataclass

import duckdb
import pandas as pd
from scipy import stats

from config.settings import Settings


@dataclass
class CorrelationResult:
    merged: pd.DataFrame  # period, sales_pct_change, price_pct_change
    pearson_r: float
    p_value: float
    n_periods: int
    sales_total_pct_change: float
    price_total_pct_change: float


def load_demand_price_series(settings: Settings, state: str = "CA", sector: str = "ALL") -> pd.DataFrame:
    con = duckdb.connect(settings.duckdb_path, read_only=True)
    try:
        df = con.execute(
            """
            SELECT
                s.period AS period,
                s.sales AS sales,
                p.price AS price
            FROM eia_retail_sales s
            JOIN eia_retail_price p
                ON s.period = p.period
                AND s.stateid = p.stateid
                AND s.sectorid = p.sectorid
            WHERE s.stateid = ? AND s.sectorid = ?
            ORDER BY s.period
            """,
            [state, sector],
        ).fetchdf()
    finally:
        con.close()
    return df


def compute_demand_price_correlation(
    settings: Settings, state: str = "CA", sector: str = "ALL"
) -> CorrelationResult | None:
    df = load_demand_price_series(settings, state=state, sector=sector)
    df = df.dropna(subset=["sales", "price"])

    if len(df) < 3:
        return None  # not enough overlapping data to say anything meaningful

    df = df.sort_values("period").reset_index(drop=True)

    base_sales = df["sales"].iloc[0]
    base_price = df["price"].iloc[0]
    df["sales_pct_change"] = (df["sales"] / base_sales - 1) * 100
    df["price_pct_change"] = (df["price"] / base_price - 1) * 100

    r, p_value = stats.pearsonr(df["sales_pct_change"], df["price_pct_change"])

    return CorrelationResult(
        merged=df[["period", "sales_pct_change", "price_pct_change"]],
        pearson_r=r,
        p_value=p_value,
        n_periods=len(df),
        sales_total_pct_change=df["sales_pct_change"].iloc[-1],
        price_total_pct_change=df["price_pct_change"].iloc[-1],
    )


if __name__ == "__main__":
    from config.settings import get_settings

    settings = get_settings(require_eia=False)
    result = compute_demand_price_correlation(settings)
    if result is None:
        print("Not enough overlapping data yet -- run run_pipeline.py first.")
    else:
        print(f"n periods: {result.n_periods}")
        print(f"Pearson r: {result.pearson_r:.3f} (p={result.p_value:.4f})")
        print(f"Total consumption change: {result.sales_total_pct_change:.1f}%")
        print(f"Total price change: {result.price_total_pct_change:.1f}%")
