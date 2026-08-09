"""
Client for EPA's Envirofacts Data Service API.

Docs: https://www.epa.gov/enviro/envirofacts-data-service-api
No API key required -- this is fully open data. We still apply the same
timeout/retry discipline as the EIA client for reliability, and keep the
base URL configurable via settings in case EPA changes endpoints.

We use this primarily to pull facility registry (FRS) records for
identifying industrial/data-center-adjacent facilities by state/county,
which we then join against EIA regional demand data.
"""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd
import requests
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

from config.settings import Settings
from src.utils.logging_config import get_logger

REQUEST_TIMEOUT_SECONDS = 20


class EnvirofactsClientError(RuntimeError):
    pass


@dataclass
class EnvirofactsClient:
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
    def _get_json(self, path: str) -> list[dict]:
        url = f"{self.settings.envirofacts_base_url}{path}"
        self.logger.debug("GET %s", url)
        response = self.session.get(url, timeout=REQUEST_TIMEOUT_SECONDS)

        if response.status_code == 429:
            raise EnvirofactsClientError("Envirofacts rate limit hit (429).")
        response.raise_for_status()

        try:
            return response.json()
        except ValueError as exc:
            raise EnvirofactsClientError(
                f"Envirofacts returned non-JSON response for {path}"
            ) from exc

    def get_facilities_by_state(self, state_code: str, rows: int = 1000) -> pd.DataFrame:
        """
        Pull registered facilities (FRS) for a state, e.g. "CA".
        Used to identify industrial / large-load facilities by county for
        cross-referencing against EIA regional demand data.
        """
        path = f"/FRS_PROGRAM_FACILITY/STATE_CODE/{state_code}/rows/0:{rows}/JSON"
        rows_data = self._get_json(path)
        df = pd.DataFrame(rows_data)
        if not df.empty:
            df["pulled_at"] = pd.Timestamp.now('UTC')
        else:
            self.logger.warning("No FRS facilities returned for state=%s", state_code)
        return df


if __name__ == "__main__":
    from config.settings import get_settings

    settings = get_settings(require_eia=False)
    client = EnvirofactsClient(settings=settings)
    demo = client.get_facilities_by_state("CA", rows=25)
    print(demo.head())
