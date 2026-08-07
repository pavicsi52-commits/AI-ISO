"""Tests for ``app.security.signer``: Ed25519 content signing,
verification, and key fingerprinting.

No infrastructure needed -- every keypair here is genuinely generated
by ``cryptography``, never a hardcoded fixture value.
"""

from __future__ import annotations

import base64

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from app.security.signer import (
    SigningError,
    compute_fingerprint,
    generate_signing_keypair,
    sign_checksum,
    verify_signature,
)

_MALFORMED_PEM = "not a pem at all"


def _rsa_keypair() -> tuple[str, str]:
    """A real RSA keypair -- valid PEM, wrong algorithm entirely."""
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


# ---- generate_signing_keypair ---------------------------------------------------


def test_generate_signing_keypair_returns_valid_pkcs8_and_spki_pem() -> None:
    private_pem, public_pem = generate_signing_keypair()
    assert private_pem.startswith("-----BEGIN PRIVATE KEY-----")
    assert private_pem.strip().endswith("-----END PRIVATE KEY-----")
    assert public_pem.startswith("-----BEGIN PUBLIC KEY-----")
    assert public_pem.strip().endswith("-----END PUBLIC KEY-----")


def test_generate_signing_keypair_produces_a_fresh_keypair_each_call() -> None:
    private_a, public_a = generate_signing_keypair()
    private_b, public_b = generate_signing_keypair()
    assert private_a != private_b
    assert public_a != public_b


# ---- sign_checksum + verify_signature round trip -----------------------------------


def test_sign_and_verify_round_trip_succeeds() -> None:
    private_pem, public_pem = generate_signing_keypair()
    checksum = "a" * 64
    signature = sign_checksum(checksum, private_key_pem=private_pem)
    assert verify_signature(checksum, signature=signature, public_key_pem=public_pem) is True


def test_signature_is_base64_encoded() -> None:
    private_pem, _public_pem = generate_signing_keypair()
    signature = sign_checksum("b" * 64, private_key_pem=private_pem)
    # Raises ValueError/binascii.Error if not valid base64 -- must not raise.
    decoded = base64.b64decode(signature, validate=True)
    assert len(decoded) == 64  # a raw Ed25519 signature is always 64 bytes


# ---- compute_fingerprint -----------------------------------------------------------


def test_compute_fingerprint_has_sha256_prefix() -> None:
    _private_pem, public_pem = generate_signing_keypair()
    fingerprint = compute_fingerprint(public_pem)
    assert fingerprint.startswith("SHA256:")


def test_compute_fingerprint_is_deterministic_for_the_same_key() -> None:
    _private_pem, public_pem = generate_signing_keypair()
    assert compute_fingerprint(public_pem) == compute_fingerprint(public_pem)


def test_compute_fingerprint_differs_across_keypairs() -> None:
    _private_a, public_a = generate_signing_keypair()
    _private_b, public_b = generate_signing_keypair()
    assert compute_fingerprint(public_a) != compute_fingerprint(public_b)


# ---- tampered / mismatched verification --------------------------------------------


def test_tampered_checksum_fails_verification() -> None:
    private_pem, public_pem = generate_signing_keypair()
    signature = sign_checksum("c" * 64, private_key_pem=private_pem)
    assert verify_signature("d" * 64, signature=signature, public_key_pem=public_pem) is False


def test_signature_from_a_different_keypair_fails_verification() -> None:
    private_a, _public_a = generate_signing_keypair()
    _private_b, public_b = generate_signing_keypair()
    checksum = "e" * 64
    signature = sign_checksum(checksum, private_key_pem=private_a)
    assert verify_signature(checksum, signature=signature, public_key_pem=public_b) is False


# ---- malformed PEM: raising paths (compute_fingerprint / sign_checksum) -----------


def test_compute_fingerprint_raises_signing_error_for_malformed_pem() -> None:
    try:
        compute_fingerprint(_MALFORMED_PEM)
    except SigningError:
        pass
    else:
        raise AssertionError("expected SigningError")


def test_sign_checksum_raises_signing_error_for_malformed_pem() -> None:
    try:
        sign_checksum("f" * 64, private_key_pem=_MALFORMED_PEM)
    except SigningError:
        pass
    else:
        raise AssertionError("expected SigningError")


def test_compute_fingerprint_raises_signing_error_for_a_non_ed25519_key() -> None:
    """Valid PEM, valid key -- just the wrong algorithm entirely."""
    _rsa_private_pem, rsa_public_pem = _rsa_keypair()
    try:
        compute_fingerprint(rsa_public_pem)
    except SigningError:
        pass
    else:
        raise AssertionError("expected SigningError")


def test_sign_checksum_raises_signing_error_for_a_non_ed25519_private_key() -> None:
    rsa_private_pem, _rsa_public_pem = _rsa_keypair()
    try:
        sign_checksum("g" * 64, private_key_pem=rsa_private_pem)
    except SigningError:
        pass
    else:
        raise AssertionError("expected SigningError")


# ---- verify_signature: never raises, always returns False on bad input -----------


def test_verify_signature_returns_false_for_malformed_public_key_pem() -> None:
    _private_pem, _public_pem = generate_signing_keypair()
    result = verify_signature("h" * 64, signature="not-checked", public_key_pem=_MALFORMED_PEM)
    assert result is False


def test_verify_signature_returns_false_for_malformed_base64_signature() -> None:
    _private_pem, public_pem = generate_signing_keypair()
    result = verify_signature(
        "i" * 64, signature="not valid base64 !!! ***", public_key_pem=public_pem
    )
    assert result is False


def test_verify_signature_returns_false_for_a_genuinely_wrong_signature() -> None:
    private_pem, public_pem = generate_signing_keypair()
    # Correctly signed, but over a *different* checksum than we verify against.
    wrong_signature = sign_checksum("j" * 64, private_key_pem=private_pem)
    result = verify_signature("k" * 64, signature=wrong_signature, public_key_pem=public_pem)
    assert result is False


def test_verify_signature_returns_false_for_a_non_ed25519_public_key() -> None:
    private_pem, _public_pem = generate_signing_keypair()
    _rsa_private_pem, rsa_public_pem = _rsa_keypair()
    signature = sign_checksum("l" * 64, private_key_pem=private_pem)
    result = verify_signature("l" * 64, signature=signature, public_key_pem=rsa_public_pem)
    assert result is False


def test_verify_signature_returns_false_for_syntactically_valid_but_wrong_length_base64() -> None:
    _private_pem, public_pem = generate_signing_keypair()
    bogus_signature = base64.b64encode(b"too-short").decode("ascii")
    result = verify_signature("m" * 64, signature=bogus_signature, public_key_pem=public_pem)
    assert result is False
