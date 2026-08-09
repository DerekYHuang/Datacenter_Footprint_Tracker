"""
Normalization layer: maps raw API response columns (whatever EIA/EPA
happen to call them) into the stable warehouse schema defined in
src/models/schema.sql. Keeping this separate from the API clients means
if EIA renames a field, you fix it in exactly one place.
"""

from __future__ import annotations

import pandas as pd


def normalize_eia_hourly_demand(raw: pd.DataFrame) -> pd.DataFrame:
    if raw.empty:
        return raw

    out = pd.DataFrame()
    out["period"] = pd.to_datetime(raw.get("period"))
    out["respondent"] = raw.get("respondent")
    out["respondent_name"] = raw.get("respondent-name", raw.get("respondent_name"))
    out["value"] = pd.to_numeric(raw.get("value"), errors="coerce")
    out["value_units"] = raw.get("value-units", raw.get("value_units", "megawatthours"))
    out["pulled_at"] = raw.get("pulled_at")
    return out


def normalize_eia_retail_price(raw: pd.DataFrame) -> pd.DataFrame:
    if raw.empty:
        return raw

    out = pd.DataFrame()
    out["period"] = pd.to_datetime(raw.get("period"), format="%Y-%m", errors="coerce")
    out["stateid"] = raw.get("stateid")
    out["sectorid"] = raw.get("sectorid")
    out["price"] = pd.to_numeric(raw.get("price"), errors="coerce")
    out["pulled_at"] = raw.get("pulled_at")
    return out


def normalize_epa_frs_facilities(raw: pd.DataFrame) -> pd.DataFrame:
    if raw.empty:
        return raw

    out = pd.DataFrame()
    out["registry_id"] = raw.get("REGISTRY_ID")
    out["primary_name"] = raw.get("PRIMARY_NAME")
    out["location_address"] = raw.get("LOCATION_ADDRESS")
    out["city_name"] = raw.get("CITY_NAME")
    out["county_name"] = raw.get("COUNTY_NAME")
    out["state_code"] = raw.get("STATE_CODE")
    out["latitude83"] = pd.to_numeric(raw.get("LATITUDE83"), errors="coerce")
    out["longitude83"] = pd.to_numeric(raw.get("LONGITUDE83"), errors="coerce")
    out["pulled_at"] = raw.get("pulled_at")
    return out
