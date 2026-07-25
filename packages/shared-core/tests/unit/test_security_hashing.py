"""Tests for HMAC signing/verification."""

from __future__ import annotations

from shared_core.security.hashing import sign, verify_signature


def test_sign_is_deterministic_for_same_payload_and_secret() -> None:
    assert sign("payload", secret="secret") == sign("payload", secret="secret")


def test_sign_differs_for_different_secrets() -> None:
    assert sign("payload", secret="secret-a") != sign("payload", secret="secret-b")


def test_sign_accepts_bytes_payload() -> None:
    assert sign(b"payload", secret="secret") == sign("payload", secret="secret")


def test_verify_signature_passes_for_correct_signature() -> None:
    signature = sign("webhook body", secret="shared-secret")

    assert verify_signature("webhook body", signature=signature, secret="shared-secret") is True


def test_verify_signature_fails_for_tampered_payload() -> None:
    signature = sign("original body", secret="shared-secret")

    result = verify_signature("tampered body", signature=signature, secret="shared-secret")

    assert result is False


def test_verify_signature_fails_for_wrong_secret() -> None:
    signature = sign("webhook body", secret="correct-secret")

    result = verify_signature("webhook body", signature=signature, secret="wrong-secret")

    assert result is False
