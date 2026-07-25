"""Enterprise Notification Framework constants.

Single source of truth for retry, rate-limit, attachment, digest, and
quiet-hours defaults used across the framework, per
docs/025_Enterprise_Notification_Framework.md.txt.
"""

from __future__ import annotations

from typing import Final

# Retry ("RETRY")
DEFAULT_RETRY_MAX_ATTEMPTS: Final[int] = 3

# Rate limiting ("RATE LIMITING")
DEFAULT_RATE_LIMIT_MAX_PER_USER: Final[int] = 100
DEFAULT_RATE_LIMIT_MAX_PER_ORGANIZATION: Final[int] = 1_000
DEFAULT_RATE_LIMIT_MAX_PER_CHANNEL: Final[int] = 500
DEFAULT_RATE_LIMIT_WINDOW_SECONDS: Final[int] = 60

# Attachments ("ATTACHMENTS": Maximum Size Validation)
DEFAULT_MAX_ATTACHMENT_SIZE_BYTES: Final[int] = 25 * 1024 * 1024  # 25 MiB

# Digest ("DIGEST")
DEFAULT_DIGEST_MAX_ITEMS: Final[int] = 50

# In-app ("IN-APP NOTIFICATIONS": Pagination)
DEFAULT_IN_APP_PAGE_SIZE: Final[int] = 20

# History / Analytics ("ANALYTICS")
DEFAULT_HISTORY_BUFFER_SIZE: Final[int] = 5_000

# Delivery ("DELIVERY")
DEFAULT_DELIVERY_TIMEOUT_SECONDS: Final[float] = 10.0

# Webhook ("WEBHOOKS")
DEFAULT_WEBHOOK_SIGNATURE_HEADER: Final[str] = "X-AIIOS-Signature"
