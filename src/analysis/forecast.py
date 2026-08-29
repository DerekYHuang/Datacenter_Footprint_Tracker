"""
Forecast: project CA retail electricity price forward using Prophet.

Price is used (rather than demand/sales) because it has 25 years of
clean monthly history in this warehouse, which is enough for Prophet to
pick up trend and yearly seasonality. The hourly demand series only
covers ~30 days, which isn't enough history to forecast meaningfully --
extending that would require pulling a much longer hourly window from
EIA, which is a reasonable next step but out of scope for this pass.
"""

from __future__ import annotations

from dataclasses import dataclass

import duckdb
import pandas as pd

from config.settings import Settings


@dataclass
class ForecastResult:
    history: pd.DataFrame  # ds, y (actuals)
    forecast: pd.DataFrame  # ds, yhat, yhat_lower, yhat_upper (history + future)
    periods_forecasted: int


def load_price_series(settings: Settings, state: str = "CA", sector: str = "ALL") -> pd.DataFrame:
    con = duckdb.connect(settings.duckdb_path, read_only=True)
    try:
        df = con.execute(
            """
            SELECT period AS ds, price AS y
            FROM eia_retail_price
            WHERE stateid = ? AND sectorid = ?
            ORDER BY period
            """,
            [state, sector],
        ).fetchdf()
    finally:
        con.close()
    return df


def forecast_retail_price(
    settings: Settings,
    state: str = "CA",
    sector: str = "ALL",
    periods_months: int = 24,
) -> ForecastResult | None:
    history = load_price_series(settings, state=state, sector=sector).dropna()

    if len(history) < 24:
        return None  # need at least ~2 years of monthly data for a sane fit

    from prophet import Prophet

    model = Prophet(yearly_seasonality=True, weekly_seasonality=False, daily_seasonality=False)
    model.fit(history)

    future = model.make_future_dataframe(periods=periods_months, freq="MS")
    forecast = model.predict(future)

    return ForecastResult(
        history=history,
        forecast=forecast[["ds", "yhat", "yhat_lower", "yhat_upper"]],
        periods_forecasted=periods_months,
    )


if __name__ == "__main__":
    from config.settings import get_settings

    settings = get_settings(require_eia=False)
    result = forecast_retail_price(settings)
    if result is None:
        print("Not enough price history yet -- run run_pipeline.py first.")
    else:
        print(result.forecast.tail(result.periods_forecasted))
