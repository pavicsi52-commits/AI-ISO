"""Tests for :mod:`app.signing.signer` -- real Ed25519 sign/verify, no mocking."""

from __future__ import annotations

import hashlib

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from app.signing.signer import (
    SigningError,
    compute_fingerprint,
    generate_signing_keypair,
    sign_checksum,
    verify_signature,
)


def _checksum(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


class TestGenerateSigningKeypair:
    def test_generates_pem_keypair(self) -> None:
        private_pem, public_pem = generate_signing_keypair()
        assert "BEGIN PRIVATE KEY" in private_pem
        assert "BEGIN PUBLIC KEY" in public_pem

    def test_each_call_generates_a_distinct_keypair(self) -> None:
        first_private, _ = generate_signing_keypair()
        second_private, _ = generate_signing_keypair()
        assert first_private != second_private


class TestComputeFingerprint:
    def test_returns_sha256_prefixed_fingerprint(self) -> None:
        _private, public_pem = generate_signing_keypair()
        fingerprint = compute_fingerprint(public_pem)
        assert fingerprint.startswith("SHA256:")

    def test_same_key_produces_same_fingerprint(self) -> None:
        _private, public_pem = generate_signing_keypair()
        assert compute_fingerprint(public_pem) == compute_fingerprint(public_pem)

    def test_different_keys_produce_different_fingerprints(self) -> None:
        _p1, pub1 = generate_signing_keypair()
        _p2, pub2 = generate_signing_keypair()
        assert compute_fingerprint(pub1) != compute_fingerprint(pub2)

    def test_malformed_key_raises_signing_error(self) -> None:
        with pytest.raises(SigningError, match="Malformed public key"):
            compute_fingerprint("not a real PEM key")


class TestSignAndVerify:
    def test_verify_succeeds_for_genuine_signature(self) -> None:
        private_pem, public_pem = generate_signing_keypair()
        checksum = _checksum("echo hello")
        signature = sign_checksum(checksum, private_key_pem=private_pem)
        assert verify_signature(checksum, signature=signature, public_key_pem=public_pem) is True

    def test_verify_fails_for_wrong_checksum(self) -> None:
        private_pem, public_pem = generate_signing_keypair()
        signature = sign_checksum(_checksum("original"), private_key_pem=private_pem)
        assert (
            verify_signature(_checksum("tampered"), signature=signature, public_key_pem=public_pem)
            is False
        )

    def test_verify_fails_for_wrong_public_key(self) -> None:
        private_pem, _public_pem = generate_signing_keypair()
        _other_private, other_public_pem = generate_signing_keypair()
        checksum = _checksum("echo hello")
        signature = sign_checksum(checksum, private_key_pem=private_pem)
        assert (
            verify_signature(checksum, signature=signature, public_key_pem=other_public_pem)
            is False
        )

    def test_verify_fails_for_garbage_signature(self) -> None:
        _private_pem, public_pem = generate_signing_keypair()
        checksum = _checksum("echo hello")
        assert (
            verify_signature(checksum, signature="not-valid-base64!!!", public_key_pem=public_pem)
            is False
        )

    def test_verify_fails_for_malformed_public_key(self) -> None:
        private_pem, _public_pem = generate_signing_keypair()
        checksum = _checksum("echo hello")
        signature = sign_checksum(checksum, private_key_pem=private_pem)
        assert verify_signature(checksum, signature=signature, public_key_pem="garbage") is False

    def test_sign_with_malformed_private_key_raises(self) -> None:
        with pytest.raises(SigningError, match="Malformed private key"):
            sign_checksum(_checksum("x"), private_key_pem="not a real key")

    def test_sign_with_non_ed25519_key_raises(self) -> None:
        rsa_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        rsa_pem = rsa_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        ).decode("ascii")
        with pytest.raises(SigningError, match="not an Ed25519 private key"):
            sign_checksum(_checksum("x"), private_key_pem=rsa_pem)
