"""
Centralized configuration.

SECURITY NOTES:
- All secrets are loaded from environment variables (via a local .env file
  that is gitignored). Nothing in this file should ever contain a real key.
- We validate required keys at startup and fail fast with a clear error
  rather than letting a script silently make unauthenticated / broken calls.
- We never print or log the actual key value anywhere in this codebase --
  only whether it is present. Grep the repo for "API_KEY" before committing
  if you're ever unsure.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

# Load .env from the project root. This does nothing (safely) if the file
# doesn't exist, e.g. in CI where secrets are injected as real env vars.
PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(PROJECT_ROOT / ".env")


class MissingSecretError(RuntimeError):
    """Raised when a required secret/config value is not set."""


def _require(name: str) -> str:
    value = os.getenv(name)
    if not value or value.strip() == "" or "your_" in value:
        raise MissingSecretError(
            f"Missing required environment variable: {name}. "
            f"Copy .env.example to .env and fill in a real value."
        )
    return value


def _optional(name: str, default: str = "") -> str:
    return os.getenv(name, default)


@dataclass(frozen=True)
class Settings:
    eia_api_key: str
    envirofacts_base_url: str
    census_api_key: str
    duckdb_path: str
    log_level: str


def get_settings(require_eia: bool = True) -> Settings:
    """
    Build a Settings object. Pass require_eia=False for code paths (like
    Envirofacts-only scripts or tests) that don't need the EIA key, so you
    aren't forced to have every credential set just to run one ingester.
    """
    return Settings(
        eia_api_key=_require("EIA_API_KEY") if require_eia else _optional("EIA_API_KEY"),
        envirofacts_base_url=_optional(
            "ENVIROFACTS_BASE_URL", "https://data.epa.gov/efservice"
        ),
        census_api_key=_optional("CENSUS_API_KEY"),
        duckdb_path=_optional("DUCKDB_PATH", "data/processed/warehouse.duckdb"),
        log_level=_optional("LOG_LEVEL", "INFO"),
    )
