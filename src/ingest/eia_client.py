"""
Client for the U.S. Energy Information Administration (EIA) API v2.

Docs: https://www.eia.gov/opendata/documentation.php
Free API key: https://www.eia.gov/opendata/register.php

SECURITY NOTES:
- The API key is read from Settings (which reads from .env), never
  hardcoded, never logged.
- We send the key as a query parameter (that's how EIA's API works) but we
  strip it out before logging any URL -- see `_safe_url_for_logging`.
- We use a timeout on every request so a hung connection can't stall the
  pipeline indefinitely.
- We use tenacity for bounded retries with backoff, so transient network
  errors don't turn into silent data gaps, but we also don't hammer EIA's
  servers -- max 4 attempts, exponential backoff.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

import pandas as pd
import requests
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

from config.settings import Settings
from src.utils.logging_config import get_logger

EIA_BASE_URL = "https://api.eia.gov/v2"
REQUEST_TIMEOUT_SECONDS = 20


def _safe_url_for_logging(url: str) -> str:
    """Strip api_key query param before this URL ever touches a log line."""
    return re.sub(r"(api_key=)[^&]+", r"\1***REDACTED***", url)


class EIAClientError(RuntimeError):
    pass


@dataclass
class EIAClient:
    settings: Settings
    session: requests.Session = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        if self.session is None:
            self.session = requests.Session()
        self.logger = get_logger(__name__, self.settings.log_level)

    @retry(
        reraise=True,
        stop=stop_after_attempt(4),
        wait=wait_exponential(multiplier=1, min=2, max=20),
        retry=retry_if_exception_type((requests.ConnectionError, requests.Timeout)),
    )
    def _get(self, path: str, params: dict[str, Any]) -> dict[str, Any]:
        url = f"{EIA_BASE_URL}{path}"
        request_params = {**params, "api_key": self.settings.eia_api_key}

        self.logger.debug("GET %s", _safe_url_for_logging(url))

        response = self.session.get(
            url, params=request_params, timeout=REQUEST_TIMEOUT_SECONDS
        )

        if response.status_code == 401:
            # Deliberately don't include response body -- some APIs echo
            # back the invalid key in error messages.
            raise EIAClientError(
                "EIA API returned 401 Unauthorized. Check that EIA_API_KEY "
                "in your .env is valid (get one at eia.gov/opendata/register.php)."
            )
        if response.status_code == 429:
            raise EIAClientError(
                "EIA API rate limit hit (429). Slow down request frequency."
            )

        response.raise_for_status()
        return response.json()

    def get_hourly_demand(
        self,
        balancing_authority: str,
        start: str,
        end: str,
    ) -> pd.DataFrame:
        """
        Pull hourly electricity demand for a given balancing authority
        (e.g. "CISO" for California ISO).

        start/end format: "YYYY-MM-DDTHH" per EIA v2 conventions.
        """
        params = {
            "frequency": "hourly",
            "data[0]": "value",
            "facets[respondent][]": balancing_authority,
            "start": start,
            "end": end,
            "sort[0][column]": "period",
            "sort[0][direction]": "asc",
            "offset": 0,
            "length": 5000,
        }
        payload = self._get("/electricity/rto/region-data/data/", params)
        rows = payload.get("response", {}).get("data", [])
        if not rows:
            self.logger.warning(
                "No rows returned for %s between %s and %s",
                balancing_authority,
                start,
                end,
            )
        df = pd.DataFrame(rows)
        if not df.empty:
            df["pulled_at"] = pd.Timestamp.now('UTC')
        return df

    def get_retail_price(
        self,
        state: str,
        sector: str = "ALL",
    ) -> pd.DataFrame:
        """
        Monthly retail electricity price by state/sector (e.g. state="CA").
        Useful for correlating data center buildout with rate changes.
        """
        params = {
            "frequency": "monthly",
            "data[0]": "price",
            "facets[stateid][]": state,
            "facets[sectorid][]": sector,
            "sort[0][column]": "period",
            "sort[0][direction]": "asc",
            "offset": 0,
            "length": 5000,
        }
        payload = self._get("/electricity/retail-sales/data/", params)
        rows = payload.get("response", {}).get("data", [])
        df = pd.DataFrame(rows)
        if not df.empty:
            df["pulled_at"] = pd.Timestamp.now('UTC')
        return df


if __name__ == "__main__":
    # Small manual smoke test. Run with: python -m src.ingest.eia_client
    from config.settings import get_settings

    settings = get_settings(require_eia=True)
    client = EIAClient(settings=settings)
    demo = client.get_retail_price(state="CA")
    print(demo.head())
