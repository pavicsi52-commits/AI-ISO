"""Enterprise Telemetry Framework constants.

Single source of truth for buffer sizes, batching, and export timeouts
used across the framework, per
docs/024_Enterprise_Telemetry_Framework.md.txt.
"""

from __future__ import annotations

from typing import Final

# Sampling ("SAMPLING")
DEFAULT_SAMPLE_RATIO: Final[float] = 1.0

# Batch export ("PERFORMANCE": Async Export, Batch Export, Buffered Writes)
DEFAULT_MAX_QUEUE_SIZE: Final[int] = 2048
DEFAULT_MAX_EXPORT_BATCH_SIZE: Final[int] = 512
DEFAULT_SCHEDULE_DELAY_MILLIS: Final[int] = 5_000
DEFAULT_EXPORT_TIMEOUT_MILLIS: Final[int] = 30_000

# Health ("HEALTH": Buffer Usage, Export Latency)
DEFAULT_EXPORT_TIMEOUT_SECONDS: Final[float] = 10.0

# Analytics ("ANALYTICS": Trace Search, Slowest Requests)
DEFAULT_RECENT_TRACE_BUFFER_SIZE: Final[int] = 2_000

# Security ("SECURITY": never capture ...) -- attribute keys masked before
# being attached to any span, case-insensitively matched.
SENSITIVE_ATTRIBUTE_KEYWORDS: Final[tuple[str, ...]] = (
    "password",
    "api_key",
    "apikey",
    "token",
    "secret",
    "private_key",
    "ssn",
    "credit_card",
)
MASKED_ATTRIBUTE_VALUE: Final[str] = "***MASKED***"
