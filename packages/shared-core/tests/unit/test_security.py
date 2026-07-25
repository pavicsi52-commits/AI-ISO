"""Tests for the security helpers."""

from __future__ import annotations

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from shared_core.enums import Permission, Role
from shared_core.exceptions import AuthenticationError
from shared_core.security import (
    ROLE_PERMISSIONS,
    decode_token,
    decrypt,
    encode_token,
    encrypt,
    generate_api_key,
    generate_encryption_key,
    generate_random_token,
    has_all_permissions,
    has_any_permission,
    has_permission,
    hash_api_key,
    hash_password,
    mask_secret,
    needs_rehash,
    verify_password,
)


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


def test_hash_password_produces_a_verifiable_hash() -> None:
    hashed = hash_password("Str0ng!Passw0rd")

    assert hashed != "Str0ng!Passw0rd"
    assert verify_password("Str0ng!Passw0rd", hashed) is True


def test_verify_password_rejects_wrong_password() -> None:
    hashed = hash_password("Str0ng!Passw0rd")

    assert verify_password("wrong-password", hashed) is False


def test_needs_rehash_is_false_for_a_freshly_hashed_password() -> None:
    hashed = hash_password("Str0ng!Passw0rd")

    assert needs_rehash(hashed) is False


def test_encode_and_decode_token_round_trip(rsa_keypair: tuple[str, str]) -> None:
    private_key, public_key = rsa_keypair

    token = encode_token({"sub": "user-1"}, private_key=private_key)
    claims = decode_token(token, public_key=public_key)

    assert claims["sub"] == "user-1"
    assert claims["iss"] == "ai-ios"


def test_decode_token_rejects_expired_token(rsa_keypair: tuple[str, str]) -> None:
    # Comfortably outside `CLOCK_SKEW_LEEWAY_SECONDS` so this tests genuine
    # expiration, not a race against the clock-skew tolerance window.
    private_key, public_key = rsa_keypair
    token = encode_token({"sub": "user-1"}, private_key=private_key, ttl_seconds=-60)

    with pytest.raises(AuthenticationError, match="expired"):
        decode_token(token, public_key=public_key)


def test_decode_token_rejects_malformed_token(rsa_keypair: tuple[str, str]) -> None:
    _, public_key = rsa_keypair

    with pytest.raises(AuthenticationError, match="invalid"):
        decode_token("not-a-real-token", public_key=public_key)


def test_decode_token_rejects_wrong_issuer(rsa_keypair: tuple[str, str]) -> None:
    private_key, public_key = rsa_keypair
    token = encode_token({"sub": "user-1"}, private_key=private_key, issuer="someone-else")

    with pytest.raises(AuthenticationError, match="invalid"):
        decode_token(token, public_key=public_key)


def test_has_permission_for_super_admin_covers_everything() -> None:
    for permission in Permission:
        assert has_permission(Role.SUPER_ADMIN, permission)


def test_has_permission_for_viewer_is_read_only() -> None:
    assert has_permission(Role.VIEWER, Permission.READ) is True
    assert has_permission(Role.VIEWER, Permission.DELETE) is False


def test_role_permissions_covers_every_role() -> None:
    for role in Role:
        assert role in ROLE_PERMISSIONS


def test_has_any_permission() -> None:
    assert has_any_permission(Role.VIEWER, {Permission.DELETE, Permission.READ}) is True
    assert has_any_permission(Role.VIEWER, {Permission.DELETE, Permission.ADMIN}) is False


def test_has_all_permissions() -> None:
    assert has_all_permissions(Role.OPERATOR, {Permission.READ, Permission.CREATE}) is True
    assert has_all_permissions(Role.OPERATOR, {Permission.READ, Permission.DELETE}) is False


def test_encrypt_decrypt_round_trip() -> None:
    key = generate_encryption_key()
    ciphertext = encrypt("top secret value", key=key)

    assert ciphertext != "top secret value"
    assert decrypt(ciphertext, key=key) == "top secret value"


def test_decrypt_fails_with_wrong_key() -> None:
    key = generate_encryption_key()
    other_key = generate_encryption_key()
    ciphertext = encrypt("top secret value", key=key)

    with pytest.raises(Exception):  # noqa: B017 -- cryptography raises its own InvalidTag
        decrypt(ciphertext, key=other_key)


def test_generate_encryption_key_is_unique() -> None:
    assert generate_encryption_key() != generate_encryption_key()


def test_generate_api_key_has_expected_prefix() -> None:
    api_key = generate_api_key()

    assert api_key.startswith("aiios_")


def test_generate_api_key_is_unique() -> None:
    assert generate_api_key() != generate_api_key()


def test_generate_random_token_is_unique_and_nonempty() -> None:
    token = generate_random_token()

    assert len(token) > 0
    assert token != generate_random_token()


def test_hash_api_key_is_deterministic() -> None:
    api_key = generate_api_key()

    assert hash_api_key(api_key) == hash_api_key(api_key)


def test_mask_secret_hides_all_but_last_four_chars() -> None:
    assert mask_secret("supersecretvalue") == "************alue"
