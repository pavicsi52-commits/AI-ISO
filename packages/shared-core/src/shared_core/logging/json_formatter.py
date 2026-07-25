"""JSON log formatter.

Per docs/014_Enterprise_Logging_Framework.md.txt "LOG FORMAT": JSON only.
"""

from __future__ import annotations

import json
import logging

from shared_core.logging.filters import mask_payload
from shared_core.logging.formatter import build_log_record


class JsonFormatter(logging.Formatter):
    """Formats log records as single-line JSON documents.

    Every record carries the full field set from
    docs/014_Enterprise_Logging_Framework.md.txt "LOG FORMAT". Sensitive
    field names and inline JWTs/credit-card-like sequences are masked
    automatically before serialization.
    """

    def __init__(self, *, service: str, environment: str) -> None:
        super().__init__()
        self._service = service
        self._environment = environment

    def format(self, record: logging.LogRecord) -> str:
        payload = build_log_record(record, service=self._service, environment=self._environment)
        return json.dumps(mask_payload(payload), default=str)
