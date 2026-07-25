"""Tests for authentication/authorization/refresh-token orchestration."""

from __future__ import annotations

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from shared_core.enums import Permission, Role
from shared_core.exceptions import AuthenticationError
from shared_core.security.apikey import create_api_key, revoke_api_key
from shared_core.security.authentication import authenticate_with_api_key, authenticate_with_jwt
from shared_core.security.authorization import authorize
from shared_core.security.jwt import decode_token, encode_token
from shared_core.security.policies import Policy, PolicyContext, PolicyEngine
from shared_core.security.refresh import issue_token_pair, rotate_token_pair


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


# --- authentication/ ---


def test_authenticate_with_jwt_returns_the_subject(rsa_keypair: tuple[str, str]) -> None:
    private_key, public_key = rsa_keypair
    token = encode_token({"sub": "user-1"}, private_key=private_key)

    result = authenticate_with_jwt(token, public_key=public_key)

    assert result.subject == "user-1"
    assert result.method == "jwt"


def test_authenticate_with_jwt_rejects_token_without_sub(rsa_keypair: tuple[str, str]) -> None:
    private_key, public_key = rsa_keypair
    token = encode_token({"role": "operator"}, private_key=private_key)

    with pytest.raises(AuthenticationError, match="sub"):
        authenticate_with_jwt(token, public_key=public_key)


def test_authenticate_with_api_key_succeeds_for_matching_key() -> None:
    raw_key, record = create_api_key()

    result = authenticate_with_api_key(raw_key, record=record)

    assert result.subject == record.key_id
    assert result.method == "api_key"


def test_authenticate_with_api_key_fails_for_missing_record() -> None:
    raw_key, _ = create_api_key()

    with pytest.raises(AuthenticationError, match="invalid"):
        authenticate_with_api_key(raw_key, record=None)


def test_authenticate_with_api_key_fails_for_wrong_key() -> None:
    _, record = create_api_key()

    with pytest.raises(AuthenticationError, match="invalid"):
        authenticate_with_api_key("wrong-raw-key", record=record)


def test_authenticate_with_api_key_fails_for_revoked_key() -> None:
    raw_key, record = create_api_key()
    revoked = revoke_api_key(record)

    with pytest.raises(AuthenticationError, match="expired or revoked"):
        authenticate_with_api_key(raw_key, record=revoked)


# --- authorization/ ---


def test_authorize_grants_when_role_has_permission() -> None:
    result = authorize(role=Role.OPERATOR, permission=Permission.CREATE)

    assert result.granted is True


def test_authorize_denies_when_role_lacks_permission() -> None:
    result = authorize(role=Role.VIEWER, permission=Permission.DELETE)

    assert result.granted is False
    assert "lacks" in result.reason


def test_authorize_checks_policies_when_provided() -> None:
    engine = PolicyEngine()
    engine.register("create", Policy(name="deny_all", predicate=lambda ctx: False))

    result = authorize(
        role=Role.OPERATOR,
        permission=Permission.CREATE,
        policy_engine=engine,
        policy_context=PolicyContext(action="create"),
    )

    assert result.granted is False
    assert "policy" in result.reason


def test_authorize_grants_when_rbac_and_policy_both_pass() -> None:
    engine = PolicyEngine()
    engine.register("create", Policy(name="allow_all", predicate=lambda ctx: True))

    result = authorize(
        role=Role.OPERATOR,
        permission=Permission.CREATE,
        policy_engine=engine,
        policy_context=PolicyContext(action="create"),
    )

    assert result.granted is True


def test_authorize_skips_policy_check_when_not_provided() -> None:
    result = authorize(role=Role.OPERATOR, permission=Permission.CREATE)

    assert result.granted is True


# --- refresh/ ---


def test_issue_token_pair_returns_both_tokens(rsa_keypair: tuple[str, str]) -> None:
    private_key, _ = rsa_keypair

    pair = issue_token_pair({"sub": "user-1"}, private_key=private_key)

    assert pair.access_token
    assert pair.refresh_token
    assert pair.access_token != pair.refresh_token


def test_rotate_token_pair_issues_a_new_pair(rsa_keypair: tuple[str, str]) -> None:
    private_key, public_key = rsa_keypair
    original = issue_token_pair({"sub": "user-1"}, private_key=private_key)

    rotated = rotate_token_pair(
        original.refresh_token, public_key=public_key, private_key=private_key
    )

    assert rotated.access_token != original.access_token
    assert rotated.refresh_token != original.refresh_token


def test_rotate_token_pair_preserves_claims(rsa_keypair: tuple[str, str]) -> None:
    private_key, public_key = rsa_keypair
    original = issue_token_pair({"sub": "user-1", "org_id": "org-42"}, private_key=private_key)

    rotated = rotate_token_pair(
        original.refresh_token, public_key=public_key, private_key=private_key
    )
    claims = decode_token(rotated.access_token, public_key=public_key)

    assert claims["sub"] == "user-1"
    assert claims["org_id"] == "org-42"


def test_rotate_token_pair_rejects_an_access_token(rsa_keypair: tuple[str, str]) -> None:
    private_key, public_key = rsa_keypair
    pair = issue_token_pair({"sub": "user-1"}, private_key=private_key)

    with pytest.raises(AuthenticationError, match="not a refresh token"):
        rotate_token_pair(pair.access_token, public_key=public_key, private_key=private_key)


def test_rotate_token_pair_checks_revocation(rsa_keypair: tuple[str, str]) -> None:
    private_key, public_key = rsa_keypair
    pair = issue_token_pair({"sub": "user-1"}, private_key=private_key)

    with pytest.raises(AuthenticationError, match="revoked"):
        rotate_token_pair(
            pair.refresh_token,
            public_key=public_key,
            private_key=private_key,
            is_revoked=lambda jti: True,
        )
