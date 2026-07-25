"""Phone number field validation.

No ``validate_phone`` exists anywhere in ``shared_core.validators`` (only
``validate_email``/``validate_username``/etc.) -- this mirrors that
package's own ``validate_email`` shape (a plain function returning
:class:`~shared_core.validators.results.ValidationResult`) so it slots
into this service's Pydantic schemas exactly like the shared_core
validators do, per docs/031's own field list ("Phone Number").
"""

from __future__ import annotations

import re

from shared_core.validators.results import ValidationResult

# E.164: optional leading '+', 8-15 digits total, no leading zero after the '+'.
_PHONE_PATTERN = re.compile(r"^\+?[1-9]\d{7,14}$")


def validate_phone(value: str) -> ValidationResult:
    """Validate that ``value`` is a syntactically well-formed E.164-ish phone number."""
    stripped = re.sub(r"[\s().-]", "", value)
    if not _PHONE_PATTERN.match(stripped):
        return ValidationResult.fail(f"'{value}' is not a valid phone number.")
    return ValidationResult.ok()


__all__ = ["validate_phone"]
