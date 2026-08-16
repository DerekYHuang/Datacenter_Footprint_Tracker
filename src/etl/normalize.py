"""
Normalization layer: maps raw API response columns (whatever EIA/EPA
happen to call them) into the stable warehouse schema defined in
src/models/schema.sql. Keeping this separate from the API clients means
if EIA renames a field, you fix it in exactly one place.
"""

from __future__ import annotations

import logging

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


def _coalesce(df: pd.DataFrame, candidates: list[str]):
    """
    Row-by-row fallback across candidate columns -- e.g. prefer
    PREF_LATITUDE but fill in from FAC_LATITUDE wherever PREF_LATITUDE is
    blank for that row. TRI's PREF_* fields are sparsely populated, so
    just grabbing "the first column that exists" (rather than falling
    back per-row) silently drops most of the coordinates.
    """
    normalized_cols = {c.replace("_", "").upper(): c for c in df.columns}
    result = None
    for candidate in candidates:
        key = candidate.replace("_", "").upper()
        if key in normalized_cols:
            col = df[normalized_cols[key]]
            result = col if result is None else result.combine_first(col)
    return result


def normalize_epa_frs_facilities(raw: pd.DataFrame) -> pd.DataFrame:
    """
    Maps EPA TRI_FACILITY columns into the stable warehouse schema.
    Uses row-wise coalescing (see _coalesce) so sparse "preferred"
    coordinate columns fall back to raw coordinate columns per-row
    instead of dropping rows where only one of the two is populated.
    """
    if raw.empty:
        return raw

    out = pd.DataFrame()
    field_map = {
        "registry_id": ["EPA_REGISTRY_ID", "TRI_FACILITY_ID", "REGISTRY_ID"],
        "primary_name": ["FACILITY_NAME", "PRIMARY_NAME"],
        "location_address": ["STREET_ADDRESS", "LOCATION_ADDRESS"],
        "city_name": ["CITY_NAME"],
        "county_name": ["COUNTY_NAME"],
        "state_code": ["STATE_ABBR", "STATE_CODE"],
        # Prefer PREF_LATITUDE/LONGITUDE (EPA's cleaned-up "best available"
        # coordinate), fall back row-by-row to FAC_LATITUDE/LONGITUDE
        # wherever PREF_* is blank.
        "latitude83": ["PREF_LATITUDE", "FAC_LATITUDE"],
        "longitude83": ["PREF_LONGITUDE", "FAC_LONGITUDE"],
    }

    missing = []
    for target, candidates in field_map.items():
        col = _coalesce(raw, candidates)
        if col is None:
            missing.append(target)
            out[target] = None
        else:
            out[target] = col

    if missing:
        logging.getLogger(__name__).warning(
            "Could not find columns for %s in FRS response (available: %s). "
            "Update field_map in normalize_epa_frs_facilities once you've "
            "inspected a real payload.",
            missing,
            list(raw.columns),
        )

    out["latitude83"] = pd.to_numeric(out["latitude83"], errors="coerce")
    out["longitude83"] = pd.to_numeric(out["longitude83"], errors="coerce")
    # TRI stores US longitude as an unsigned magnitude (e.g. 121.83 instead
    # of -121.83). Every TRI facility is in the Western hemisphere, so any
    # positive value here is a sign error, not a real eastern-hemisphere
    # coordinate -- negate it. (This is what put facilities in China/Korea
    # on the map instead of California.)
    out["longitude83"] = out["longitude83"].abs() * -1
    out["pulled_at"] = raw.get("PULLED_AT", raw.get("pulled_at"))
    return out