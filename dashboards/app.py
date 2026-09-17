"""
Streamlit dashboard reading from the local DuckDB warehouse.

Run with: streamlit run dashboards/app.py

Reads only from DuckDB, never calls the EIA/EPA APIs directly -- so this
file never needs API keys at all. Only the ingestion layer (run_pipeline.py)
holds credentials.

Layout: each section below is a `get_*` function (pure data, no Streamlit
calls -- testable in isolation) followed by the `st.*` calls that render
it. Keeping those separate makes each section's logic checkable without
spinning up the app.
"""

from __future__ import annotations

import sys
from pathlib import Path

# Streamlit only adds this script's own folder (dashboards/) to sys.path,
# not the project root -- so "config" and "src" aren't importable unless
# we add the root ourselves. This must happen before the local imports below.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import duckdb
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import pydeck as pdk
import streamlit as st

from config.settings import get_settings
from src.analysis.correlation import CorrelationResult, compute_demand_price_correlation
from src.analysis.forecast import ForecastResult, forecast_retail_price

st.set_page_config(page_title="Data Center Energy & Water Footprint", layout="wide")

settings = get_settings(require_eia=False)  # dashboard never needs the API key
con = duckdb.connect(settings.duckdb_path, read_only=True)


# ---------------------------------------------------------------------------
# Data access (pure -- no st.* calls, so these are unit-testable on their own)
# ---------------------------------------------------------------------------
def get_kpis(con: duckdb.DuckDBPyConnection) -> dict:
    price = con.execute(
        "SELECT MIN(price) AS min_p, MAX(price) AS max_p FROM eia_retail_price"
    ).fetchdf()
    demand = con.execute("SELECT MAX(value) AS peak FROM eia_hourly_demand").fetchdf()
    facilities = con.execute(
        "SELECT COUNT(*) AS n FROM epa_frs_facilities WHERE latitude83 IS NOT NULL"
    ).fetchdf()

    price_growth_pct = None
    if not price.empty and pd.notna(price["max_p"].iloc[0]) and price["min_p"].iloc[0]:
        price_growth_pct = (price["max_p"].iloc[0] / price["min_p"].iloc[0] - 1) * 100

    peak_demand = (
        demand["peak"].iloc[0] if not demand.empty and pd.notna(demand["peak"].iloc[0]) else None
    )
    facility_count = int(facilities["n"].iloc[0]) if not facilities.empty else 0

    return {
        "price_growth_pct": price_growth_pct,
        "peak_demand": peak_demand,
        "facility_count": facility_count,
    }


def get_hourly_demand(con: duckdb.DuckDBPyConnection) -> pd.DataFrame:
    return con.execute(
        "SELECT period, respondent, value FROM eia_hourly_demand ORDER BY period"
    ).fetchdf()


def get_retail_price(con: duckdb.DuckDBPyConnection) -> pd.DataFrame:
    return con.execute(
        "SELECT period, stateid, price FROM eia_retail_price ORDER BY period"
    ).fetchdf()


def get_mappable_facilities(con: duckdb.DuckDBPyConnection) -> pd.DataFrame:
    df = con.execute(
        """
        SELECT primary_name, city_name, county_name, latitude83, longitude83
        FROM epa_frs_facilities
        WHERE latitude83 IS NOT NULL AND longitude83 IS NOT NULL
        """
    ).fetchdf()
    return df.rename(columns={"latitude83": "lat", "longitude83": "lon"}).dropna(
        subset=["lat", "lon"]
    )


# ---------------------------------------------------------------------------
# Rendering (st.* calls only -- assembles the page from the data above)
# ---------------------------------------------------------------------------
def render_kpis(kpis: dict) -> None:
    col1, col2, col3 = st.columns(3)
    with col1:
        value = f"+{kpis['price_growth_pct']:.0f}%" if kpis["price_growth_pct"] is not None else "—"
        st.metric("CA retail price growth (full history)", value)
    with col2:
        value = f"{kpis['peak_demand']:,.0f} MWh" if kpis["peak_demand"] is not None else "—"
        st.metric("Peak CISO demand (last 30 days)", value)
    with col3:
        st.metric("Mapped facilities, Santa Clara County", str(kpis["facility_count"]))


def render_operational_charts(demand_df: pd.DataFrame, price_df: pd.DataFrame) -> None:
    col1, col2 = st.columns(2)
    with col1:
        st.subheader("Hourly Electricity Demand")
        if demand_df.empty:
            st.info("No demand data yet -- run `python run_pipeline.py` first.")
        else:
            st.plotly_chart(
                px.line(demand_df, x="period", y="value", color="respondent"),
                use_container_width=True,
            )
    with col2:
        st.subheader("Retail Electricity Price Trend")
        if price_df.empty:
            st.info("No price data yet -- run `python run_pipeline.py` first.")
        else:
            st.plotly_chart(
                px.line(price_df, x="period", y="price", color="stateid"),
                use_container_width=True,
            )


def render_correlation_section(result: CorrelationResult | None) -> None:
    st.subheader("Consumption Growth vs. Price Growth")
    st.caption(
        "Both series indexed to % change from the first common month, so a "
        "million-kWh consumption figure and a cents-per-kWh price figure can "
        "be compared on the same axis. Chart shows monthly detail; the "
        "correlation statistic (right) is computed on annual averages instead, "
        "since consumption's seasonal swings would otherwise swamp the "
        "underlying trend relationship at monthly granularity."
    )

    if result is None:
        st.info(
            "Not enough overlapping consumption/price data yet -- run "
            "`python run_pipeline.py` first."
        )
        return

    chart_col, stats_col = st.columns([3, 1])
    with chart_col:
        fig = go.Figure()
        fig.add_trace(go.Scatter(
            x=result.merged["period"], y=result.merged["sales_pct_change"],
            name="Consumption (% change)", line=dict(color="#60a5fa"),
        ))
        fig.add_trace(go.Scatter(
            x=result.merged["period"], y=result.merged["price_pct_change"],
            name="Price (% change)", line=dict(color="#f97316"),
        ))
        fig.update_layout(yaxis_title="% change from first period", legend=dict(orientation="h"))
        st.plotly_chart(fig, use_container_width=True)

    with stats_col:
        st.metric("Pearson correlation (r)", f"{result.pearson_r:.2f}")
        st.metric("p-value", f"{result.p_value:.4f}")
        st.metric("Total consumption change", f"{result.sales_total_pct_change:+.1f}%")
        st.metric("Total price change", f"{result.price_total_pct_change:+.1f}%")
        st.caption(
            f"Correlation computed on {result.n_years} full years of annual "
            f"averages (to remove consumption's seasonal cycle); chart above "
            f"shows {result.n_periods} months for detail."
        )
        if result.p_value < 0.05:
            direction = "positively" if result.pearson_r > 0 else "negatively"
            st.success(f"Statistically significant: consumption and price are {direction} correlated.")
        else:
            st.warning("Not statistically significant at p < 0.05 -- treat the r value with caution.")


def render_forecast_section(result: ForecastResult | None) -> None:
    st.subheader("Retail Price Forecast (next 24 months)")
    st.caption(
        "Prophet time-series forecast fit on full monthly price history. "
        "Shaded band is the model's 80% uncertainty interval, not a guarantee."
    )

    if result is None:
        st.info(
            "Not enough price history yet for a forecast (need 2+ years) -- "
            "run `python run_pipeline.py` first."
        )
        return

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=result.forecast["ds"], y=result.forecast["yhat_upper"],
        line=dict(width=0), showlegend=False, hoverinfo="skip",
    ))
    fig.add_trace(go.Scatter(
        x=result.forecast["ds"], y=result.forecast["yhat_lower"],
        fill="tonexty", fillcolor="rgba(96,165,250,0.2)", line=dict(width=0),
        name="80% interval", hoverinfo="skip",
    ))
    fig.add_trace(go.Scatter(
        x=result.history["ds"], y=result.history["y"],
        name="Actual", line=dict(color="#e5e7eb"),
    ))
    fig.add_trace(go.Scatter(
        x=result.forecast["ds"], y=result.forecast["yhat"],
        name="Forecast", line=dict(color="#60a5fa", dash="dash"),
    ))
    fig.update_layout(yaxis_title="cents per kWh", legend=dict(orientation="h"))
    st.plotly_chart(fig, use_container_width=True)


def render_facility_map(map_df: pd.DataFrame, total_facility_count: int) -> None:
    st.subheader("Registered Industrial Facilities (EPA FRS)")

    if total_facility_count == 0:
        st.info("No facility data yet -- run `python run_pipeline.py` first.")
        return
    if map_df.empty:
        st.warning("Facility data loaded, but none have usable coordinates yet.")
        return

    layer = pdk.Layer(
        "ScatterplotLayer",
        data=map_df,
        get_position="[lon, lat]",
        get_radius=150,
        get_fill_color=[255, 90, 60, 180],
        pickable=True,
    )
    view_state = pdk.ViewState(
        latitude=map_df["lat"].mean(), longitude=map_df["lon"].mean(), zoom=9,
    )
    deck = pdk.Deck(
        layers=[layer],
        initial_view_state=view_state,
        map_style="dark",
        tooltip={
            "html": "<b>{primary_name}</b><br/>{city_name}, {county_name}",
            "style": {"backgroundColor": "steelblue", "color": "white"},
        },
    )
    st.pydeck_chart(deck)
    st.caption(f"{len(map_df)} of {total_facility_count} facilities have mappable coordinates.")

    with st.expander("View facility list"):
        st.dataframe(
            map_df[["primary_name", "city_name", "county_name"]],
            use_container_width=True,
        )


# ---------------------------------------------------------------------------
# Page assembly
# ---------------------------------------------------------------------------
st.title("⚡ Data Center Energy & Water Footprint Tracker")
st.caption(
    "Regional electricity demand, retail pricing, and industrial facility "
    "density -- built to explore the community impact of data center growth."
)

kpis = get_kpis(con)
render_kpis(kpis)
st.divider()

render_operational_charts(get_hourly_demand(con), get_retail_price(con))
st.divider()

render_correlation_section(compute_demand_price_correlation(settings))
st.divider()

with st.spinner("Fitting forecast model..."):
    render_forecast_section(forecast_retail_price(settings))
st.divider()

render_facility_map(get_mappable_facilities(con), kpis["facility_count"])

con.close()