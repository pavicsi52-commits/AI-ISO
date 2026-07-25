"""Password and username field validation.

This is the basic validator used until
docs/017_Enterprise_Security_Framework.md.txt's full password policy
(history, breach check, dictionary check) is implemented.
"""

from __future__ import annotations

import re

from shared_core.constants import AuthConstants, ValidationConstants
from shared_core.validators.results import ValidationResult

_USERNAME_PATTERN = re.compile(r"^[A-Za-z0-9_.-]+$")
_HAS_UPPER = re.compile(r"[A-Z]")
_HAS_LOWER = re.compile(r"[a-z]")
_HAS_DIGIT = re.compile(r"\d")
_HAS_SPECIAL = re.compile(r"[^A-Za-z0-9]")


def validate_password(value: str) -> ValidationResult:
    """Validate password strength: length, and character class diversity."""
    errors: list[str] = []
    if not (AuthConstants.PASSWORD_MIN_LENGTH <= len(value) <= AuthConstants.PASSWORD_MAX_LENGTH):
        errors.append(
            f"Password must be between {AuthConstants.PASSWORD_MIN_LENGTH} and "
            f"{AuthConstants.PASSWORD_MAX_LENGTH} characters."
        )
    if not _HAS_UPPER.search(value):
        errors.append("Password must contain an uppercase letter.")
    if not _HAS_LOWER.search(value):
        errors.append("Password must contain a lowercase letter.")
    if not _HAS_DIGIT.search(value):
        errors.append("Password must contain a digit.")
    if not _HAS_SPECIAL.search(value):
        errors.append("Password must contain a special character.")

    if errors:
        return ValidationResult.fail(*errors)
    return ValidationResult.ok()


def validate_username(value: str) -> ValidationResult:
    """Validate username length and allowed character set."""
    if not (
        ValidationConstants.USERNAME_MIN_LENGTH
        <= len(value)
        <= ValidationConstants.USERNAME_MAX_LENGTH
    ):
        return ValidationResult.fail(
            f"Username must be between {ValidationConstants.USERNAME_MIN_LENGTH} and "
            f"{ValidationConstants.USERNAME_MAX_LENGTH} characters."
        )
    if not _USERNAME_PATTERN.match(value):
        return ValidationResult.fail(
            "Username may only contain letters, numbers, underscores, dots, and hyphens."
        )
    return ValidationResult.ok()
