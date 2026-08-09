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

import duckdb
import pandas as pd
import plotly.express as px
import streamlit as st

from config.settings import get_settings

st.set_page_config(page_title="Data Center Energy & Water Footprint", layout="wide")

settings = get_settings(require_eia=False)  # dashboard never needs the API key
con = duckdb.connect(settings.duckdb_path, read_only=True)

st.title("⚡ Data Center Energy & Water Footprint Tracker")
st.caption(
    "Regional electricity demand, retail pricing, and industrial facility "
    "density -- built to explore the community impact of data center growth."
)

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
    fig = px.scatter_mapbox(
        facilities_df,
        lat="latitude83",
        lon="longitude83",
        hover_name="primary_name",
        hover_data=["city_name", "county_name"],
        zoom=6,
        height=500,
    )
    fig.update_layout(mapbox_style="open-street-map")
    st.plotly_chart(fig, use_container_width=True)

con.close()
