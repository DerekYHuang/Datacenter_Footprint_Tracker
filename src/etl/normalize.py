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
    """
    The FRS Facility Search API's exact field names aren't fully pinned
    down in public docs and can vary in casing/format. This picks the
    first matching column (case-insensitive, ignoring underscores) for
    each target field rather than assuming one exact name, and logs any
    field it can't find so the mapping can be corrected once you've seen
    a real response (`python -m src.ingest.envirofacts_client`).
    """
    if raw.empty:
        return raw

    def _find(df: pd.DataFrame, candidates: list[str]):
        normalized_cols = {c.replace("_", "").upper(): c for c in df.columns}
        for candidate in candidates:
            key = candidate.replace("_", "").upper()
            if key in normalized_cols:
                return df[normalized_cols[key]]
        return None

    out = pd.DataFrame()
    field_map = {
        "registry_id": ["EPA_REGISTRY_ID", "TRI_FACILITY_ID", "REGISTRY_ID"],
        "primary_name": ["FACILITY_NAME", "PRIMARY_NAME"],
        "location_address": ["STREET_ADDRESS", "LOCATION_ADDRESS"],
        "city_name": ["CITY_NAME"],
        "county_name": ["COUNTY_NAME"],
        "state_code": ["STATE_ABBR", "STATE_CODE"],
        # Prefer PREF_LATITUDE/LONGITUDE (EPA's cleaned-up "best available"
        # coordinate), fall back to raw FAC_LATITUDE/LONGITUDE if missing.
        "latitude83": ["PREF_LATITUDE", "FAC_LATITUDE"],
        "longitude83": ["PREF_LONGITUDE", "FAC_LONGITUDE"],
    }

    missing = []
    for target, candidates in field_map.items():
        col = _find(raw, candidates)
        if col is None:
            missing.append(target)
            out[target] = None
        else:
            out[target] = col

    if missing:
        import logging

        logging.getLogger(__name__).warning(
            "Could not find columns for %s in FRS response (available: %s). "
            "Update field_map in normalize_epa_frs_facilities once you've "
            "inspected a real payload.",
            missing,
            list(raw.columns),
        )

    out["latitude83"] = pd.to_numeric(out["latitude83"], errors="coerce")
    out["longitude83"] = pd.to_numeric(out["longitude83"], errors="coerce")
    out["pulled_at"] = raw.get("PULLED_AT", raw.get("pulled_at"))
    return out
