"""Sensitive-data masking for log records.

Per docs/014_Enterprise_Logging_Framework.md.txt "MASKING": automatically
mask passwords, secrets, JWTs, tokens, API keys, and credit-card-like
number sequences -- both when they appear as named fields (``password=``)
and when they appear inline in free text (a JWT pasted into an error
message). Named PII fields (e.g. ``ssn``) are covered via
:data:`shared_core.constants.logging.LoggingConstants.SENSITIVE_FIELD_NAMES`;
free-form PII detection is out of scope (unreliable pattern matching would
over-mask legitimate, non-sensitive log data).
"""

from __future__ import annotations

import logging
import re
from typing import Any

from shared_core.constants.logging import LoggingConstants

_JWT_PATTERN = re.compile(r"eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+")
_CREDIT_CARD_PATTERN = re.compile(r"\b(?:\d[ -]?){13,19}\b")

_TEXT_PATTERNS: tuple[re.Pattern[str], ...] = (_JWT_PATTERN, _CREDIT_CARD_PATTERN)


def mask_text(value: str) -> str:
    """Scrub JWTs and credit-card-like number sequences out of free text."""
    masked = value
    for pattern in _TEXT_PATTERNS:
        masked = pattern.sub(LoggingConstants.MASKED_VALUE, masked)
    return masked


def mask_value(key: str, value: Any) -> Any:
    """Mask *value* if *key* names a sensitive field, or it's free text containing one."""
    if key.lower() in LoggingConstants.SENSITIVE_FIELD_NAMES:
        return LoggingConstants.MASKED_VALUE
    if isinstance(value, str):
        return mask_text(value)
    return value


def mask_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """Mask every sensitive field/value in a log record payload."""
    return {key: mask_value(key, value) for key, value in payload.items()}


class SensitiveDataFilter(logging.Filter):
    """Masks a record's message and extra fields before any formatter sees it.

    Attach to any handler (not just :class:`~shared_core.logging.json_formatter.JsonFormatter`
    consumers) so masking applies uniformly regardless of output format.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.msg, str):
            record.msg = mask_text(record.msg)
        extra_fields = getattr(record, "extra_fields", None)
        if isinstance(extra_fields, dict):
            record.extra_fields = mask_payload(extra_fields)
        return True
