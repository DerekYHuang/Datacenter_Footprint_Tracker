"""
Starter Streamlit dashboard reading from the local DuckDB warehouse.

Run with: streamlit run dashboards/app.py

This intentionally reads only from the warehouse (never calls the EIA/EPA
APIs directly), so the dashboard never needs API keys at all -- only the
pipeline that populates the warehouse does. That's a good security
boundary to point out in an interview: the presentation layer has zero
credentials.
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
import streamlit as st
import pydeck as pdk

from config.settings import get_settings
from src.analysis.correlation import compute_demand_price_correlation
from src.analysis.forecast import forecast_retail_price

st.set_page_config(page_title="Data Center Energy & Water Footprint", layout="wide")

settings = get_settings(require_eia=False)  # dashboard never needs the API key
con = duckdb.connect(settings.duckdb_path, read_only=True)

st.title("⚡ Data Center Energy & Water Footprint Tracker")
st.caption(
    "Regional electricity demand, retail pricing, and industrial facility "
    "density -- built to explore the community impact of data center growth."
)

# ---------------------------------------------------------------------------
# KPI summary row
# ---------------------------------------------------------------------------
price_summary = con.execute(
    "SELECT MIN(price) AS min_p, MAX(price) AS max_p FROM eia_retail_price"
).fetchdf()
demand_summary = con.execute(
    "SELECT MAX(value) AS peak FROM eia_hourly_demand"
).fetchdf()
facility_count = con.execute(
    "SELECT COUNT(*) AS n FROM epa_frs_facilities WHERE latitude83 IS NOT NULL"
).fetchdf()

kpi1, kpi2, kpi3 = st.columns(3)
with kpi1:
    if not price_summary.empty and pd.notna(price_summary["max_p"].iloc[0]):
        min_p, max_p = price_summary["min_p"].iloc[0], price_summary["max_p"].iloc[0]
        pct_change = (max_p / min_p - 1) * 100 if min_p else 0
        st.metric("CA retail price growth (full history)", f"+{pct_change:.0f}%")
    else:
        st.metric("CA retail price growth", "—")
with kpi2:
    if not demand_summary.empty and pd.notna(demand_summary["peak"].iloc[0]):
        st.metric("Peak CISO demand (last 30 days)", f"{demand_summary['peak'].iloc[0]:,.0f} MWh")
    else:
        st.metric("Peak CISO demand", "—")
with kpi3:
    n = int(facility_count["n"].iloc[0]) if not facility_count.empty else 0
    st.metric("Mapped facilities, Santa Clara County", f"{n}")

st.divider()

col1, col2 = st.columns(2)

with col1:
    st.subheader("Hourly Electricity Demand")
    demand_df: pd.DataFrame = con.execute(
        "SELECT period, respondent, value FROM eia_hourly_demand ORDER BY period"
    ).fetchdf()
    if demand_df.empty:
        st.info("No demand data yet -- run `python run_pipeline.py` first.")
    else:
        fig = px.line(demand_df, x="period", y="value", color="respondent")
        st.plotly_chart(fig, use_container_width=True)

with col2:
    st.subheader("Retail Electricity Price Trend")
    price_df: pd.DataFrame = con.execute(
        "SELECT period, stateid, price FROM eia_retail_price ORDER BY period"
    ).fetchdf()
    if price_df.empty:
        st.info("No price data yet -- run `python run_pipeline.py` first.")
    else:
        fig = px.line(price_df, x="period", y="price", color="stateid")
        st.plotly_chart(fig, use_container_width=True)

st.divider()

# ---------------------------------------------------------------------------
# Correlation: consumption growth vs. price growth
# ---------------------------------------------------------------------------
st.subheader("Consumption Growth vs. Price Growth")
st.caption(
    "Both series indexed to % change from the first common month, so a "
    "million-kWh consumption figure and a cents-per-kWh price figure can "
    "be compared on the same axis. Chart shows monthly detail; the "
    "correlation statistic (right) is computed on annual averages instead, "
    "since consumption's seasonal swings would otherwise swamp the "
    "underlying trend relationship at monthly granularity."
)

corr_result = compute_demand_price_correlation(settings)
if corr_result is None:
    st.info(
        "Not enough overlapping consumption/price data yet -- run "
        "`python run_pipeline.py` first."
    )
else:
    corr_col1, corr_col2 = st.columns([3, 1])
    with corr_col1:
        fig = go.Figure()
        fig.add_trace(
            go.Scatter(
                x=corr_result.merged["period"],
                y=corr_result.merged["sales_pct_change"],
                name="Consumption (% change)",
                line=dict(color="#60a5fa"),
            )
        )
        fig.add_trace(
            go.Scatter(
                x=corr_result.merged["period"],
                y=corr_result.merged["price_pct_change"],
                name="Price (% change)",
                line=dict(color="#f97316"),
            )
        )
        fig.update_layout(yaxis_title="% change from first period", legend=dict(orientation="h"))
        st.plotly_chart(fig, use_container_width=True)
    with corr_col2:
        st.metric("Pearson correlation (r)", f"{corr_result.pearson_r:.2f}")
        st.metric("p-value", f"{corr_result.p_value:.4f}")
        st.metric("Total consumption change", f"{corr_result.sales_total_pct_change:+.1f}%")
        st.metric("Total price change", f"{corr_result.price_total_pct_change:+.1f}%")
        st.caption(
            f"Correlation computed on {corr_result.n_years} full years of "
            f"annual averages (to remove consumption's seasonal cycle); "
            f"chart above shows {corr_result.n_periods} months for detail."
        )
        if corr_result.p_value < 0.05:
            direction = "positively" if corr_result.pearson_r > 0 else "negatively"
            st.success(f"Statistically significant: consumption and price are {direction} correlated.")
        else:
            st.warning("Not statistically significant at p < 0.05 -- treat the r value with caution.")

st.divider()

# ---------------------------------------------------------------------------
# Forecast: projected retail price
# ---------------------------------------------------------------------------
st.subheader("Retail Price Forecast (next 24 months)")
st.caption(
    "Prophet time-series forecast fit on full monthly price history. "
    "Shaded band is the model's 80% uncertainty interval, not a guarantee."
)

with st.spinner("Fitting forecast model..."):
    forecast_result = forecast_retail_price(settings)

if forecast_result is None:
    st.info(
        "Not enough price history yet for a forecast (need 2+ years) -- "
        "run `python run_pipeline.py` first."
    )
else:
    fig = go.Figure()
    fig.add_trace(
        go.Scatter(
            x=forecast_result.forecast["ds"],
            y=forecast_result.forecast["yhat_upper"],
            line=dict(width=0),
            showlegend=False,
            hoverinfo="skip",
        )
    )
    fig.add_trace(
        go.Scatter(
            x=forecast_result.forecast["ds"],
            y=forecast_result.forecast["yhat_lower"],
            fill="tonexty",
            fillcolor="rgba(96,165,250,0.2)",
            line=dict(width=0),
            name="80% interval",
            hoverinfo="skip",
        )
    )
    fig.add_trace(
        go.Scatter(
            x=forecast_result.history["ds"],
            y=forecast_result.history["y"],
            name="Actual",
            line=dict(color="#e5e7eb"),
        )
    )
    fig.add_trace(
        go.Scatter(
            x=forecast_result.forecast["ds"],
            y=forecast_result.forecast["yhat"],
            name="Forecast",
            line=dict(color="#60a5fa", dash="dash"),
        )
    )
    fig.update_layout(yaxis_title="cents per kWh", legend=dict(orientation="h"))
    st.plotly_chart(fig, use_container_width=True)

st.divider()

st.subheader("Registered Industrial Facilities (EPA FRS)")
facilities_df: pd.DataFrame = con.execute(
    """
    SELECT primary_name, city_name, county_name, latitude83, longitude83
    FROM epa_frs_facilities
    WHERE latitude83 IS NOT NULL AND longitude83 IS NOT NULL
    """
).fetchdf()

if facilities_df.empty:
    st.info("No facility data yet -- run `python run_pipeline.py` first.")
else:
    # debugging for the map: st.write(map_df[["lat", "lon"]].describe())
    map_df = facilities_df.rename(columns={"latitude83": "lat", "longitude83": "lon"})
    map_df = map_df.dropna(subset=["lat", "lon"])

    if map_df.empty:
        st.warning("Facility data loaded, but none have usable coordinates yet.")
    else:
        layer = pdk.Layer(
            "ScatterplotLayer",
            data=map_df,
            get_position="[lon, lat]",
            get_radius=150,
            get_fill_color=[255, 90, 60, 180],
            pickable=True,
        )
        view_state = pdk.ViewState(
            latitude=map_df["lat"].mean(),
            longitude=map_df["lon"].mean(),
            zoom=9,
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
        st.caption(f"{len(map_df)} of {len(facilities_df)} facilities have mappable coordinates.")

    with st.expander("View facility list"):
        st.dataframe(
            facilities_df[["primary_name", "city_name", "county_name"]],
            use_container_width=True,
        )

con.close()