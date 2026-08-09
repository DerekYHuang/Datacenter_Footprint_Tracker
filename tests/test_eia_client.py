"""
Tests use `responses` to mock HTTP calls -- no real API key or network
access is required to run the test suite. This also means CI can run
these safely without any secrets configured.
"""

from __future__ import annotations

import responses

from config.settings import Settings
from src.ingest.eia_client import EIAClient

FAKE_SETTINGS = Settings(
    eia_api_key="fake-test-key",
    envirofacts_base_url="https://data.epa.gov/efservice",
    census_api_key="",
    duckdb_path="data/processed/test_warehouse.duckdb",
    log_level="DEBUG",
)


@responses.activate
def test_get_retail_price_parses_rows():
    responses.add(
        responses.GET,
        "https://api.eia.gov/v2/electricity/retail-sales/data/",
        json={
            "response": {
                "data": [
                    {"period": "2026-01", "stateid": "CA", "sectorid": "ALL", "price": 24.5},
                    {"period": "2026-02", "stateid": "CA", "sectorid": "ALL", "price": 24.9},
                ]
            }
        },
        status=200,
    )

    client = EIAClient(settings=FAKE_SETTINGS)
    df = client.get_retail_price(state="CA")

    assert len(df) == 2
    assert "pulled_at" in df.columns
    assert df.iloc[0]["price"] == 24.5


@responses.activate
def test_get_retail_price_handles_empty_response():
    responses.add(
        responses.GET,
        "https://api.eia.gov/v2/electricity/retail-sales/data/",
        json={"response": {"data": []}},
        status=200,
    )

    client = EIAClient(settings=FAKE_SETTINGS)
    df = client.get_retail_price(state="ZZ")

    assert df.empty


@responses.activate
def test_unauthorized_raises_clear_error():
    responses.add(
        responses.GET,
        "https://api.eia.gov/v2/electricity/retail-sales/data/",
        json={"error": "invalid api_key"},
        status=401,
    )

    client = EIAClient(settings=FAKE_SETTINGS)

    try:
        client.get_retail_price(state="CA")
        assert False, "expected EIAClientError to be raised"
    except Exception as exc:
        assert "401" in str(exc) or "Unauthorized" in str(exc)
