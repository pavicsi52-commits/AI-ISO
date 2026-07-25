"""Tests for security validation rules (wrapping shared_core.security)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from shared_core.enums import Permission, Role
from shared_core.security.apikey import hash_api_key
from shared_core.security.jwt import encode_token
from shared_core.validation.base import ValidationSeverity
from shared_core.validation.rules import security


@pytest.fixture(scope="module")
def rsa_keypair() -> tuple[str, str]:
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    private_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode("ascii")
    public_pem = (
        private_key.public_key()
        .public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )
        .decode("ascii")
    )
    return private_pem, public_pem


def test_validate_jwt_passes_for_a_valid_token(rsa_keypair: tuple[str, str]) -> None:
    private_key, public_key = rsa_keypair
    token = encode_token({"sub": "user-1"}, private_key=private_key)

    assert security.validate_jwt(token, public_key=public_key).valid is True


def test_validate_jwt_fails_for_a_malformed_token(rsa_keypair: tuple[str, str]) -> None:
    _, public_key = rsa_keypair

    result = security.validate_jwt("not-a-real-token", public_key=public_key)

    assert result.valid is False


def test_validate_jwt_fails_for_an_expired_token(rsa_keypair: tuple[str, str]) -> None:
    # Comfortably outside the JWT clock-skew leeway window (see
    # shared_core.security.jwt.CLOCK_SKEW_LEEWAY_SECONDS), so this tests
    # genuine expiration rather than racing the tolerance window.
    private_key, public_key = rsa_keypair
    token = encode_token({"sub": "user-1"}, private_key=private_key, ttl_seconds=-60)

    result = security.validate_jwt(token, public_key=public_key)

    assert result.valid is False


def test_validate_permission_passes_when_granted() -> None:
    result = security.validate_permission(role=Role.OPERATOR, permission=Permission.CREATE)

    assert result.valid is True


def test_validate_permission_fails_when_not_granted() -> None:
    result = security.validate_permission(role=Role.VIEWER, permission=Permission.DELETE)

    assert result.valid is False


def test_validate_rbac_require_all_passes() -> None:
    result = security.validate_rbac(
        role=Role.SUPER_ADMIN, required_permissions={Permission.READ, Permission.DELETE}
    )

    assert result.valid is True


def test_validate_rbac_require_all_fails_when_missing_one() -> None:
    result = security.validate_rbac(
        role=Role.VIEWER, required_permissions={Permission.READ, Permission.DELETE}
    )

    assert result.valid is False


def test_validate_rbac_require_any_passes_with_one_match() -> None:
    result = security.validate_rbac(
        role=Role.VIEWER,
        required_permissions={Permission.READ, Permission.DELETE},
        require_all=False,
    )

    assert result.valid is True


def test_validate_api_key_passes_for_matching_hash() -> None:
    api_key = "aiios_testkey123"
    expected_hash = hash_api_key(api_key)

    assert security.validate_api_key(api_key, expected_hash=expected_hash).valid is True


def test_validate_api_key_fails_for_mismatched_hash() -> None:
    result = security.validate_api_key("wrong-key", expected_hash=hash_api_key("aiios_real"))

    assert result.valid is False


def test_validate_session_passes_for_active_unexpired_session() -> None:
    now = datetime(2026, 1, 1, tzinfo=UTC)
    result = security.validate_session(is_active=True, expires_at=now + timedelta(hours=1), now=now)

    assert result.valid is True


def test_validate_session_fails_for_inactive_session() -> None:
    now = datetime(2026, 1, 1, tzinfo=UTC)
    result = security.validate_session(
        is_active=False, expires_at=now + timedelta(hours=1), now=now
    )

    assert result.valid is False


def test_validate_session_fails_for_expired_session() -> None:
    now = datetime(2026, 1, 1, tzinfo=UTC)
    result = security.validate_session(is_active=True, expires_at=now - timedelta(hours=1), now=now)

    assert result.valid is False


def test_validate_secret_access_passes_for_allowed_role() -> None:
    result = security.validate_secret_access(
        role=Role.SUPER_ADMIN, allowed_roles={Role.SUPER_ADMIN, Role.ORGANIZATION_ADMIN}
    )

    assert result.valid is True


def test_validate_secret_access_fails_for_disallowed_role() -> None:
    result = security.validate_secret_access(role=Role.VIEWER, allowed_roles={Role.SUPER_ADMIN})

    assert result.valid is False


def test_validate_rate_limit_passes_under_limit() -> None:
    assert security.validate_rate_limit(current_count=5, limit=10).valid is True


def test_validate_rate_limit_fails_over_limit() -> None:
    result = security.validate_rate_limit(current_count=11, limit=10)

    assert result.valid is False
    assert result.severity == ValidationSeverity.WARNING


def test_validate_csrf_token_passes_for_matching_token() -> None:
    assert security.validate_csrf_token("abc123", expected="abc123").valid is True


def test_validate_csrf_token_fails_for_mismatched_token() -> None:
    assert security.validate_csrf_token("wrong", expected="abc123").valid is False


def test_validate_csrf_token_fails_when_missing() -> None:
    assert security.validate_csrf_token(None, expected="abc123").valid is False


def test_validate_origin_passes_for_allowed_origin() -> None:
    result = security.validate_origin(
        "https://app.aiios.example", allowed_origins=["https://app.aiios.example"]
    )

    assert result.valid is True


def test_validate_origin_fails_for_disallowed_origin() -> None:
    result = security.validate_origin(
        "https://evil.example", allowed_origins=["https://app.aiios.example"]
    )

    assert result.valid is False


def test_validate_origin_fails_when_missing() -> None:
    result = security.validate_origin(None, allowed_origins=["https://app.aiios.example"])

    assert result.valid is False
