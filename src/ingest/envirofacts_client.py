"""
Client for EPA's Toxics Release Inventory (TRI) facility data via the
Envirofacts "efservice" API.

Docs: https://www.epa.gov/enviro/envirofacts-data-service-api-v1
Confirmed-working example pattern from EPA's own documentation:
  https://data.epa.gov/efservice/tri_facility/state_abbr/VA/rows/499:504

No API key required.

NOTE ON ENDPOINT HISTORY: this project originally tried the generic
"efservice/frs.frs_program_facility" join (intermittent 500s) and then
EPA's dedicated FRS Facility Search REST API at ofmpub.epa.gov
(intermittent 503s). Both are real EPA outages/instability, not bugs in
this code. TRI_FACILITY was chosen instead because EPA's own docs show a
confirmed-working request against it, and because TRI (facilities that
report toxic chemical releases) is directly relevant to the
semiconductor/data-center environmental angle of this project.

I pull by state (guaranteed by the documented pattern) and filter to a
county client-side in pandas, rather than guessing at whether county-level
URL filtering is supported/how county names are cased in this table.
"""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd
import requests
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

from config.settings import Settings
from src.utils.logging_config import get_logger

REQUEST_TIMEOUT_SECONDS = 30


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

        if response.status_code in (500, 503):
            raise EnvirofactsClientError(
                f"EPA Envirofacts returned {response.status_code} for {path}. "
                "This is EPA's public API being unstable, not a local bug -- "
                "tenacity will retry automatically. If it keeps failing after "
                "retries, EPA's service may be down; try again later."
            )
        response.raise_for_status()

        try:
            return response.json()
        except ValueError as exc:
            raise EnvirofactsClientError(
                f"Envirofacts returned non-JSON response for {path}. Raw "
                f"text (first 500 chars): {response.text[:500]}"
            ) from exc

    def get_facilities(
        self,
        state_abbr: str,
        county_name: str | None = None,
        city_name: str | None = None,
    ) -> pd.DataFrame:
        """
        Pull TRI-reporting facilities for a state, optionally filtered to
        a county or city (filtered client-side after the pull, since the
        documented API pattern only guarantees state-level filtering).
        """
        path = f"/tri_facility/state_abbr/{state_abbr}/JSON"
        rows_data = self._get_json(path)
        df = pd.DataFrame(rows_data)

        if df.empty:
            self.logger.warning("No TRI facilities returned for state=%s", state_abbr)
            return df

        df.columns = [c.upper() for c in df.columns]
        df["PULLED_AT"] = pd.Timestamp.now("UTC")

        county_col = next((c for c in df.columns if "COUNTY" in c), None)
        city_col = next((c for c in df.columns if c == "CITY_NAME" or c == "CITY"), None)

        if county_name and county_col:
            before = len(df)
            df = df[df[county_col].astype(str).str.upper() == county_name.upper()]
            self.logger.info(
                "Filtered to county=%s: %d -> %d rows", county_name, before, len(df)
            )
        elif county_name:
            self.logger.warning(
                "No county column found to filter on (available columns: %s)",
                list(df.columns),
            )

        if city_name and city_col:
            df = df[df[city_col].astype(str).str.upper() == city_name.upper()]

        return df

    def get_facilities_by_state(self, state_code: str, rows: int = 1000) -> pd.DataFrame:
        """Kept for backwards compatibility with run_pipeline.py."""
        return self.get_facilities(state_abbr=state_code)


if __name__ == "__main__":
    # Manual smoke test / debug tool. Run with:
    #   python -m src.ingest.envirofacts_client
    # This prints the REAL columns EPA returns -- use this output to fix
    # normalize.py's field_map if anything still doesn't line up.
    from config.settings import get_settings

    settings = get_settings(require_eia=False)
    client = EnvirofactsClient(settings=settings)
    demo = client.get_facilities(state_abbr="CA", county_name="SANTA CLARA")
    print(demo.head(10))
    print(f"\nRows returned: {len(demo)}")
    print(f"Columns: {list(demo.columns)}")



if __name__ == "__main__":
    from config.settings import get_settings

    settings = get_settings(require_eia=False)
    client = EnvirofactsClient(settings=settings)
    demo = client.get_facilities_by_state("CA", rows=25)
    print(demo.head())
