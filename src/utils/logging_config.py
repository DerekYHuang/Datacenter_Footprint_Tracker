"""
Shared logging setup.

SECURITY NOTE: `RedactingFilter` scrubs anything that looks like an API key
or token from log records before they're written anywhere. This matters
because request libraries / tracebacks can accidentally dump full URLs
(including query-string API keys) into logs.
"""

from __future__ import annotations

import logging
import re
import sys

_SECRET_PATTERNS = [
    re.compile(r"(api_key=)([^&\s]+)", re.IGNORECASE),
    re.compile(r"(x-api-key[:=]\s*)([^\s,&]+)", re.IGNORECASE),
    re.compile(r"(Bearer\s+)([A-Za-z0-9\-_.]+)", re.IGNORECASE),
]


class RedactingFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        msg = record.getMessage()
        redacted = msg
        for pattern in _SECRET_PATTERNS:
            redacted = pattern.sub(r"\1***REDACTED***", redacted)
        if redacted != msg:
            record.msg = redacted
            record.args = ()
        return True


def get_logger(name: str, level: str = "INFO") -> logging.Logger:
    logger = logging.getLogger(name)
    if not logger.handlers:
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(
            logging.Formatter("%(asctime)s | %(levelname)-8s | %(name)s | %(message)s")
        )
        handler.addFilter(RedactingFilter())
        logger.addHandler(handler)
        logger.setLevel(getattr(logging, level.upper(), logging.INFO))
    return logger
