"""Security validation rules (docs/016 "SECURITY VALIDATION").

Per docs/016 "DO NOT IMPLEMENT": "Authentication" -- these wrap
:mod:`shared_core.security`'s existing JWT/RBAC/API-key primitives
(Prompt 012, expanded Prompt 017) into structured
:class:`~shared_core.validation.results.ValidationResult`s. No token
verification, password hashing, or session logic is reimplemented here.
"""

from __future__ import annotations

import secrets
from collections.abc import Sequence
from datetime import UTC, datetime

from shared_core.constants.authentication import AuthConstants
from shared_core.enums.permission import Permission
from shared_core.enums.role import Role
from shared_core.exceptions.authentication import AuthenticationError
from shared_core.security.apikey import hash_api_key
from shared_core.security.jwt import decode_token
from shared_core.security.rbac import has_all_permissions, has_any_permission, has_permission
from shared_core.validation.base import ValidationSeverity
from shared_core.validation.results import ValidationResult


def validate_jwt(
    token: str, *, public_key: str, issuer: str = AuthConstants.JWT_ISSUER
) -> ValidationResult:
    """Validate a JWT decodes and verifies successfully."""
    try:
        decode_token(token, public_key=public_key, issuer=issuer)
    except AuthenticationError as exc:
        return ValidationResult.fail(str(exc))
    return ValidationResult.ok()


def validate_permission(*, role: Role, permission: Permission) -> ValidationResult:
    """Validate a role grants a specific permission."""
    if not has_permission(role, permission):
        return ValidationResult.fail(
            f"Role '{role.value}' lacks the '{permission.value}' permission."
        )
    return ValidationResult.ok()


def validate_rbac(
    *, role: Role, required_permissions: set[Permission], require_all: bool = True
) -> ValidationResult:
    """Validate a role satisfies a set of required permissions."""
    granted = (
        has_all_permissions(role, required_permissions)
        if require_all
        else has_any_permission(role, required_permissions)
    )
    if not granted:
        return ValidationResult.fail(
            f"Role '{role.value}' does not satisfy the required permissions."
        )
    return ValidationResult.ok()


def validate_api_key(api_key: str, *, expected_hash: str) -> ValidationResult:
    """Validate an API key matches its stored hash."""
    if not secrets.compare_digest(hash_api_key(api_key), expected_hash):
        return ValidationResult.fail("API key is invalid.")
    return ValidationResult.ok()


def validate_session(
    *, is_active: bool, expires_at: datetime, now: datetime | None = None
) -> ValidationResult:
    """Validate a session is active and unexpired."""
    current = now or datetime.now(UTC)
    if not is_active:
        return ValidationResult.fail("Session is not active.")
    if current >= expires_at:
        return ValidationResult.fail("Session has expired.")
    return ValidationResult.ok()


def validate_secret_access(*, role: Role, allowed_roles: set[Role]) -> ValidationResult:
    """Validate a role is permitted to access a secret."""
    if role not in allowed_roles:
        return ValidationResult.fail("You are not permitted to access this secret.")
    return ValidationResult.ok()


def validate_rate_limit(*, current_count: int, limit: int) -> ValidationResult:
    """Validate a caller has not exceeded their rate limit."""
    if current_count > limit:
        return ValidationResult.fail(
            f"Rate limit exceeded ({current_count}/{limit}).",
            severity=ValidationSeverity.WARNING,
        )
    return ValidationResult.ok()


def validate_csrf_token(provided: str | None, *, expected: str) -> ValidationResult:
    """Validate a CSRF token matches, using a constant-time comparison."""
    if not provided or not secrets.compare_digest(provided, expected):
        return ValidationResult.fail("CSRF token is missing or invalid.")
    return ValidationResult.ok()


def validate_origin(origin: str | None, *, allowed_origins: Sequence[str]) -> ValidationResult:
    """Validate a request's Origin header is in the allow-list."""
    if origin is None or origin not in allowed_origins:
        return ValidationResult.fail(f"Origin '{origin}' is not allowed.")
    return ValidationResult.ok()
