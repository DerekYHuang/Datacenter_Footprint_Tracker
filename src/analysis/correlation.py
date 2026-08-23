"""
Correlation analysis: does electricity CONSUMPTION growth (a proxy for
grid load, which data center buildout drives) move together with retail
PRICE growth over the same period?

We use monthly retail-sales "sales" (consumption, million kWh) rather
than the hourly demand series, because hourly demand only covers ~30
days of recent history -- not enough to say anything about a multi-year
trend. Sales and price come from the same EIA endpoint/geography/months,
so they're already aligned for a fair comparison.

AGGREGATION: consumption has a strong 12-month seasonal cycle (AC/heating
load) that price does not. Correlating the two series at raw monthly
granularity lets that seasonal noise swamp the actual trend relationship
we care about -- verified directly: a synthetic series with a genuine
built-in upward trend in both consumption and price still only produced
r=0.17 at monthly granularity, versus r=1.0 once aggregated to annual
means. So this aggregates to annual averages before computing Pearson
correlation, which is what the reported r/p values below reflect. The
monthly, non-aggregated series is still returned (in `merged`) for the
chart, since showing month-to-month texture is still useful visually --
just not for the correlation statistic itself.
"""

from __future__ import annotations

from dataclasses import dataclass

import duckdb
import pandas as pd
from scipy import stats

from config.settings import Settings


@dataclass
class CorrelationResult:
    merged: pd.DataFrame          # monthly: period, sales_pct_change, price_pct_change (for charting)
    annual: pd.DataFrame          # annual: year, sales_mean, price_mean (what the stats are based on)
    pearson_r: float              # computed on annual-aggregated data, not raw monthly
    p_value: float
    n_periods: int                # monthly periods available (for the chart)
    n_years: int                  # annual periods used for the correlation stat
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
    df["period"] = pd.to_datetime(df["period"])

    base_sales = df["sales"].iloc[0]
    base_price = df["price"].iloc[0]
    df["sales_pct_change"] = (df["sales"] / base_sales - 1) * 100
    df["price_pct_change"] = (df["price"] / base_price - 1) * 100

    # Aggregate to annual means to remove consumption's seasonal cycle
    # before computing correlation (see module docstring).
    df["year"] = df["period"].dt.year
    annual = df.groupby("year").agg(
        sales_mean=("sales", "mean"),
        price_mean=("price", "mean"),
        n_months=("sales", "count"),
    ).reset_index()
    # Drop any year with fewer than 12 months of data (partial first/last
    # year), since a partial-year average isn't comparable to full-year
    # averages and would bias the trend.
    annual = annual[annual["n_months"] == 12].reset_index(drop=True)

    if len(annual) < 3:
        return None  # not enough full years to correlate annually

    r, p_value = stats.pearsonr(annual["sales_mean"], annual["price_mean"])

    return CorrelationResult(
        merged=df[["period", "sales_pct_change", "price_pct_change"]],
        annual=annual,
        pearson_r=r,
        p_value=p_value,
        n_periods=len(df),
        n_years=len(annual),
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
        print(f"n years (correlation basis): {result.n_years}")
        print(f"n months (chart basis): {result.n_periods}")
        print(f"Pearson r (annual): {result.pearson_r:.3f} (p={result.p_value:.4f})")
        print(f"Total consumption change: {result.sales_total_pct_change:.1f}%")
        print(f"Total price change: {result.price_total_pct_change:.1f}%")