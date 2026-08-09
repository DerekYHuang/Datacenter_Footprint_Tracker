"""
Confirms the RedactingFilter actually strips API keys out of log messages.
This is a security-relevant test: if someone refactors logging_config.py
and breaks redaction, this should fail loudly.
"""

from __future__ import annotations

import logging

from src.utils.logging_config import RedactingFilter


def test_api_key_query_param_is_redacted():
    record = logging.LogRecord(
        name="test",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="GET https://api.eia.gov/v2/electricity?api_key=super-secret-value&x=1",
        args=(),
        exc_info=None,
    )
    RedactingFilter().filter(record)
    assert "super-secret-value" not in record.getMessage()
    assert "REDACTED" in record.getMessage()


def test_bearer_token_is_redacted():
    record = logging.LogRecord(
        name="test",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="Authorization: Bearer abc123.def456",
        args=(),
        exc_info=None,
    )
    RedactingFilter().filter(record)
    assert "abc123.def456" not in record.getMessage()
