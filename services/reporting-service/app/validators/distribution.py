"""Distribution target validation.

``ReportRecipient.target`` is channel-dependent -- an address for
email, a URL for webhook, a user id for in-app -- so it is validated
per channel here rather than being split into a column per channel that
is ``NULL`` for every other one.

Validating at registration time matters: a typo'd webhook URL that
only surfaces during an unattended 03:00 scheduled run is exactly the
failure this prevents.
"""

from __future__ import annotations

import re
from urllib.parse import urlparse

from shared_core.exceptions.validation import ValidationError

from app.models.enums import DistributionChannel

_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_ALLOWED_WEBHOOK_SCHEMES = frozenset({"http", "https"})
_MAX_TARGET_LENGTH = 1024


def validate_target(channel: DistributionChannel, target: str) -> None:
    """Validate a recipient target for its channel.

    Raises:
        ValidationError: If the target is empty, over-long, or not
            valid for *channel*.
    """
    cleaned = target.strip()
    if not cleaned:
        raise ValidationError(f"A {str(channel)!r} recipient requires a target.")
    if len(cleaned) > _MAX_TARGET_LENGTH:
        raise ValidationError(f"Recipient target exceeds {_MAX_TARGET_LENGTH} characters.")

    if channel is DistributionChannel.EMAIL and not _EMAIL.match(cleaned):
        raise ValidationError(f"{cleaned!r} is not a valid email address.")

    if channel is DistributionChannel.WEBHOOK:
        parsed = urlparse(cleaned)
        if parsed.scheme not in _ALLOWED_WEBHOOK_SCHEMES or not parsed.netloc:
            raise ValidationError(
                f"A webhook recipient requires an absolute http(s) URL; got {cleaned!r}."
            )


__all__ = ["validate_target"]
