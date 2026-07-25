"""Tests for the expanded JWT package: ES256, key rotation, revocation."""

from __future__ import annotations

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec, rsa
from shared_core.exceptions import AuthenticationError
from shared_core.security.jwt import (
    SUPPORTED_ALGORITHMS,
    KeyRing,
    decode_token,
    encode_token,
    get_key_id,
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


@pytest.fixture(scope="module")
def ec_keypair() -> tuple[str, str]:
    private_key = ec.generate_private_key(ec.SECP256R1())
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


def test_supported_algorithms_are_rs256_and_es256_only() -> None:
    assert set(SUPPORTED_ALGORITHMS) == {"RS256", "ES256"}


def test_encode_token_rejects_unsupported_algorithm(rsa_keypair: tuple[str, str]) -> None:
    private_key, _ = rsa_keypair

    with pytest.raises(AuthenticationError, match="Unsupported"):
        encode_token({"sub": "user-1"}, private_key=private_key, algorithm="HS256")


def test_encode_and_decode_with_es256(ec_keypair: tuple[str, str]) -> None:
    private_key, public_key = ec_keypair

    token = encode_token({"sub": "user-1"}, private_key=private_key, algorithm="ES256")
    claims = decode_token(token, public_key=public_key)

    assert claims["sub"] == "user-1"


def test_encode_token_auto_generates_jti(rsa_keypair: tuple[str, str]) -> None:
    private_key, public_key = rsa_keypair

    token = encode_token({"sub": "user-1"}, private_key=private_key)
    claims = decode_token(token, public_key=public_key)

    assert claims["jti"]


def test_encode_token_preserves_explicit_jti(rsa_keypair: tuple[str, str]) -> None:
    private_key, public_key = rsa_keypair

    token = encode_token({"sub": "user-1", "jti": "custom-id"}, private_key=private_key)
    claims = decode_token(token, public_key=public_key)

    assert claims["jti"] == "custom-id"


def test_decode_token_checks_revocation_by_jti(rsa_keypair: tuple[str, str]) -> None:
    private_key, public_key = rsa_keypair
    token = encode_token({"sub": "user-1", "jti": "revoked-id"}, private_key=private_key)

    with pytest.raises(AuthenticationError, match="revoked"):
        decode_token(token, public_key=public_key, is_revoked=lambda jti: jti == "revoked-id")


def test_decode_token_allows_unrevoked_token(rsa_keypair: tuple[str, str]) -> None:
    private_key, public_key = rsa_keypair
    token = encode_token({"sub": "user-1", "jti": "active-id"}, private_key=private_key)

    claims = decode_token(token, public_key=public_key, is_revoked=lambda jti: False)

    assert claims["sub"] == "user-1"


def test_decode_token_tolerates_small_clock_skew(rsa_keypair: tuple[str, str]) -> None:
    private_key, public_key = rsa_keypair
    # 5 seconds past expiration, well within CLOCK_SKEW_LEEWAY_SECONDS (30s).
    token = encode_token({"sub": "user-1"}, private_key=private_key, ttl_seconds=-5)

    claims = decode_token(token, public_key=public_key)

    assert claims["sub"] == "user-1"


def test_get_key_id_returns_none_without_kid(rsa_keypair: tuple[str, str]) -> None:
    private_key, _ = rsa_keypair
    token = encode_token({"sub": "user-1"}, private_key=private_key)

    assert get_key_id(token) is None


def test_get_key_id_returns_kid_when_set(rsa_keypair: tuple[str, str]) -> None:
    private_key, _ = rsa_keypair
    token = encode_token({"sub": "user-1"}, private_key=private_key, key_id="key-2024")

    assert get_key_id(token) == "key-2024"


def test_key_ring_decodes_with_the_matching_key(rsa_keypair: tuple[str, str]) -> None:
    private_key, public_key = rsa_keypair
    token = encode_token({"sub": "user-1"}, private_key=private_key, key_id="key-1")

    ring = KeyRing()
    ring.add_key("key-1", public_key)

    claims = ring.decode_with_ring(token)

    assert claims["sub"] == "user-1"


def test_key_ring_supports_rotation_with_two_active_keys(
    rsa_keypair: tuple[str, str], ec_keypair: tuple[str, str]
) -> None:
    old_private, old_public = rsa_keypair
    new_private, new_public = ec_keypair

    ring = KeyRing()
    ring.add_key("old-key", old_public)
    ring.add_key("new-key", new_public)

    old_token = encode_token({"sub": "user-1"}, private_key=old_private, key_id="old-key")
    new_token = encode_token(
        {"sub": "user-2"}, private_key=new_private, algorithm="ES256", key_id="new-key"
    )

    assert ring.decode_with_ring(old_token)["sub"] == "user-1"
    assert ring.decode_with_ring(new_token)["sub"] == "user-2"


def test_key_ring_raises_when_key_id_missing(rsa_keypair: tuple[str, str]) -> None:
    private_key, _ = rsa_keypair
    token = encode_token({"sub": "user-1"}, private_key=private_key)  # no key_id

    ring = KeyRing()

    with pytest.raises(AuthenticationError, match="No matching"):
        ring.decode_with_ring(token)


def test_key_ring_raises_when_key_not_registered(rsa_keypair: tuple[str, str]) -> None:
    private_key, _ = rsa_keypair
    token = encode_token({"sub": "user-1"}, private_key=private_key, key_id="unknown-key")

    ring = KeyRing()

    with pytest.raises(AuthenticationError, match="No matching"):
        ring.decode_with_ring(token)


def test_key_ring_remove_key() -> None:
    ring = KeyRing()
    ring.add_key("key-1", "some-public-key-pem")

    assert ring.get_key("key-1") == "some-public-key-pem"

    ring.remove_key("key-1")

    assert ring.get_key("key-1") is None
