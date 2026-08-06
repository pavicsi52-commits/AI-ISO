"""Pure tests for app/signatures/engine.py -- no database, no fixtures."""

from __future__ import annotations

import hashlib
import hmac
import time

import pytest

from app.models.enums import SignatureAlgorithm
from app.signatures.engine import (
    SigningSecret,
    build_signed_headers,
    is_timestamp_fresh,
    sign_payload,
    verify_payload_signature,
    verify_signed_request,
    verify_with_any_secret,
)


class TestSignPayload:
    def test_sha256_matches_a_hand_computed_digest(self) -> None:
        body = b'{"hello":"world"}'
        expected = hmac.new(b"secret", body, hashlib.sha256).hexdigest()
        assert (
            sign_payload(body, secret="secret", algorithm=SignatureAlgorithm.HMAC_SHA256)
            == expected
        )

    def test_sha512_matches_a_hand_computed_digest(self) -> None:
        body = b'{"hello":"world"}'
        expected = hmac.new(b"secret", body, hashlib.sha512).hexdigest()
        assert (
            sign_payload(body, secret="secret", algorithm=SignatureAlgorithm.HMAC_SHA512)
            == expected
        )

    def test_defaults_to_sha256(self) -> None:
        body = b"payload"
        assert sign_payload(body, secret="secret") == sign_payload(
            body, secret="secret", algorithm=SignatureAlgorithm.HMAC_SHA256
        )

    def test_different_secrets_produce_different_signatures(self) -> None:
        body = b"payload"
        assert sign_payload(body, secret="a") != sign_payload(body, secret="b")

    def test_different_bodies_produce_different_signatures(self) -> None:
        assert sign_payload(b"one", secret="secret") != sign_payload(b"two", secret="secret")


class TestVerifyPayloadSignature:
    def test_a_correct_sha256_signature_verifies(self) -> None:
        body = b"payload"
        signature = sign_payload(body, secret="secret", algorithm=SignatureAlgorithm.HMAC_SHA256)
        assert verify_payload_signature(body, signature=signature, secret="secret") is True

    def test_a_correct_sha512_signature_verifies(self) -> None:
        body = b"payload"
        signature = sign_payload(body, secret="secret", algorithm=SignatureAlgorithm.HMAC_SHA512)
        result = verify_payload_signature(
            body, signature=signature, secret="secret", algorithm=SignatureAlgorithm.HMAC_SHA512
        )
        assert result is True

    def test_a_tampered_body_fails_verification(self) -> None:
        body = b"payload"
        signature = sign_payload(body, secret="secret")
        assert verify_payload_signature(b"tampered", signature=signature, secret="secret") is False

    def test_the_wrong_secret_fails_verification(self) -> None:
        body = b"payload"
        signature = sign_payload(body, secret="secret")
        assert verify_payload_signature(body, signature=signature, secret="wrong") is False

    def test_a_signature_computed_under_the_wrong_algorithm_fails_verification(self) -> None:
        body = b"payload"
        signature = sign_payload(body, secret="secret", algorithm=SignatureAlgorithm.HMAC_SHA256)
        result = verify_payload_signature(
            body, signature=signature, secret="secret", algorithm=SignatureAlgorithm.HMAC_SHA512
        )
        assert result is False


class TestSigningSecret:
    def test_holds_its_own_fields(self) -> None:
        secret = SigningSecret(version=2, secret="s", algorithm=SignatureAlgorithm.HMAC_SHA256)
        assert secret.version == 2
        assert secret.secret == "s"
        assert secret.algorithm == SignatureAlgorithm.HMAC_SHA256


class TestVerifyWithAnySecret:
    def test_matches_the_only_candidate(self) -> None:
        body = b"payload"
        candidate = SigningSecret(version=1, secret="s1", algorithm=SignatureAlgorithm.HMAC_SHA256)
        signature = sign_payload(body, secret="s1")
        result = verify_with_any_secret(body, signature=signature, secrets=[candidate])
        assert result is candidate

    def test_a_signature_from_an_older_secret_still_verifies_during_rotation(self) -> None:
        body = b"payload"
        old = SigningSecret(
            version=1, secret="old-secret", algorithm=SignatureAlgorithm.HMAC_SHA256
        )
        new = SigningSecret(
            version=2, secret="new-secret", algorithm=SignatureAlgorithm.HMAC_SHA256
        )
        # Signed under the OLDER secret -- rotation must still accept it.
        signature = sign_payload(body, secret="old-secret")
        result = verify_with_any_secret(body, signature=signature, secrets=[new, old])
        assert result is old

    def test_returns_none_when_no_secret_matches(self) -> None:
        body = b"payload"
        candidate = SigningSecret(version=1, secret="s1", algorithm=SignatureAlgorithm.HMAC_SHA256)
        signature = sign_payload(body, secret="different")
        assert verify_with_any_secret(body, signature=signature, secrets=[candidate]) is None

    def test_returns_none_for_an_empty_secrets_list(self) -> None:
        body = b"payload"
        signature = sign_payload(body, secret="whatever")
        assert verify_with_any_secret(body, signature=signature, secrets=[]) is None


class TestIsTimestampFresh:
    def test_exactly_at_the_tolerance_boundary_is_fresh(self) -> None:
        assert is_timestamp_fresh(1000, tolerance_seconds=30, now=1030) is True

    def test_one_second_past_the_tolerance_boundary_is_stale(self) -> None:
        assert is_timestamp_fresh(1000, tolerance_seconds=30, now=1031) is False

    def test_exactly_at_the_boundary_in_the_past_direction_is_fresh(self) -> None:
        assert is_timestamp_fresh(1030, tolerance_seconds=30, now=1000) is True

    def test_zero_offset_is_fresh(self) -> None:
        assert is_timestamp_fresh(1000, tolerance_seconds=30, now=1000) is True

    def test_a_timestamp_far_in_the_future_is_stale(self) -> None:
        assert is_timestamp_fresh(1000, tolerance_seconds=30, now=500) is False

    def test_defaults_to_the_real_current_time_when_now_is_omitted(self) -> None:
        assert is_timestamp_fresh(int(time.time()), tolerance_seconds=5) is True


class TestBuildSignedHeaders:
    def test_returns_the_four_expected_headers(self) -> None:
        headers = build_signed_headers(
            b"body",
            secret="secret",
            algorithm=SignatureAlgorithm.HMAC_SHA256,
            timestamp=1_700_000_000,
            nonce="nonce-1",
        )
        assert set(headers) == {
            "X-Webhook-Signature",
            "X-Webhook-Timestamp",
            "X-Webhook-Nonce",
            "X-Webhook-Signature-Algorithm",
        }

    def test_timestamp_is_stringified(self) -> None:
        headers = build_signed_headers(
            b"body",
            secret="secret",
            algorithm=SignatureAlgorithm.HMAC_SHA256,
            timestamp=1_700_000_000,
            nonce="nonce-1",
        )
        assert headers["X-Webhook-Timestamp"] == "1700000000"

    def test_nonce_is_passed_through_unchanged(self) -> None:
        headers = build_signed_headers(
            b"body",
            secret="secret",
            algorithm=SignatureAlgorithm.HMAC_SHA256,
            timestamp=1_700_000_000,
            nonce="nonce-xyz",
        )
        assert headers["X-Webhook-Nonce"] == "nonce-xyz"

    def test_algorithm_header_uses_the_enum_value_string(self) -> None:
        headers = build_signed_headers(
            b"body",
            secret="secret",
            algorithm=SignatureAlgorithm.HMAC_SHA512,
            timestamp=1_700_000_000,
            nonce="n",
        )
        assert headers["X-Webhook-Signature-Algorithm"] == "hmac_sha512"

    def test_signature_covers_timestamp_and_nonce_together_with_the_body(self) -> None:
        timestamp = 1_700_000_000
        nonce = "nonce-1"
        body = b"body"
        headers = build_signed_headers(
            body,
            secret="secret",
            algorithm=SignatureAlgorithm.HMAC_SHA256,
            timestamp=timestamp,
            nonce=nonce,
        )
        signed_payload = timestamp.to_bytes(8, "big") + nonce.encode("utf-8") + body
        expected_signature = sign_payload(signed_payload, secret="secret")
        assert headers["X-Webhook-Signature"] == expected_signature

    def test_a_body_only_signature_would_not_match_the_header(self) -> None:
        # Proves the timestamp/nonce are genuinely folded into the signed bytes -- signing
        # the body alone would let a replayed request forge a fresh timestamp afterward.
        timestamp = 1_700_000_000
        nonce = "nonce-1"
        body = b"body"
        headers = build_signed_headers(
            body,
            secret="secret",
            algorithm=SignatureAlgorithm.HMAC_SHA256,
            timestamp=timestamp,
            nonce=nonce,
        )
        body_only_signature = sign_payload(body, secret="secret")
        assert headers["X-Webhook-Signature"] != body_only_signature


class TestVerifySignedRequest:
    def _headers_for(
        self, *, body: bytes, secret: str, timestamp: int, nonce: str, algorithm: SignatureAlgorithm
    ) -> dict[str, str]:
        return build_signed_headers(
            body, secret=secret, algorithm=algorithm, timestamp=timestamp, nonce=nonce
        )

    def test_a_fresh_correctly_signed_request_returns_the_matching_secret(self) -> None:
        body = b"payload"
        secret = SigningSecret(version=1, secret="s1", algorithm=SignatureAlgorithm.HMAC_SHA256)
        headers = self._headers_for(
            body=body,
            secret="s1",
            timestamp=1000,
            nonce="n1",
            algorithm=SignatureAlgorithm.HMAC_SHA256,
        )
        result = verify_signed_request(
            body,
            signature=headers["X-Webhook-Signature"],
            timestamp=1000,
            nonce="n1",
            secrets=[secret],
            tolerance_seconds=300,
            now=1000,
        )
        assert result is secret

    def test_rotation_still_verifies_against_an_older_secret(self) -> None:
        body = b"payload"
        old = SigningSecret(version=1, secret="old", algorithm=SignatureAlgorithm.HMAC_SHA256)
        new = SigningSecret(version=2, secret="new", algorithm=SignatureAlgorithm.HMAC_SHA256)
        headers = self._headers_for(
            body=body,
            secret="old",
            timestamp=1000,
            nonce="n1",
            algorithm=SignatureAlgorithm.HMAC_SHA256,
        )
        result = verify_signed_request(
            body,
            signature=headers["X-Webhook-Signature"],
            timestamp=1000,
            nonce="n1",
            secrets=[new, old],
            tolerance_seconds=300,
            now=1000,
        )
        assert result is old

    def test_a_stale_timestamp_with_an_otherwise_correct_signature_is_still_rejected(self) -> None:
        body = b"payload"
        secret = SigningSecret(version=1, secret="s1", algorithm=SignatureAlgorithm.HMAC_SHA256)
        headers = self._headers_for(
            body=body,
            secret="s1",
            timestamp=1000,
            nonce="n1",
            algorithm=SignatureAlgorithm.HMAC_SHA256,
        )
        # `now` is far past the tolerance window -- the signature itself is perfectly valid.
        result = verify_signed_request(
            body,
            signature=headers["X-Webhook-Signature"],
            timestamp=1000,
            nonce="n1",
            secrets=[secret],
            tolerance_seconds=30,
            now=10_000,
        )
        assert result is None

    def test_freshness_is_checked_before_any_signature_comparison_is_attempted(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        calls: list[str] = []
        original = verify_with_any_secret

        def _spy(*args: object, **kwargs: object) -> SigningSecret | None:
            calls.append("called")
            return original(*args, **kwargs)  # type: ignore[arg-type]

        monkeypatch.setattr("app.signatures.engine.verify_with_any_secret", _spy)

        body = b"payload"
        secret = SigningSecret(version=1, secret="s1", algorithm=SignatureAlgorithm.HMAC_SHA256)
        headers = self._headers_for(
            body=body,
            secret="s1",
            timestamp=1000,
            nonce="n1",
            algorithm=SignatureAlgorithm.HMAC_SHA256,
        )
        result = verify_signed_request(
            body,
            signature=headers["X-Webhook-Signature"],
            timestamp=1000,
            nonce="n1",
            secrets=[secret],
            tolerance_seconds=30,
            now=10_000,  # stale
        )
        assert result is None
        assert calls == []  # the (relatively expensive, multi-secret) comparison never ran

    def test_no_secret_matching_a_fresh_request_returns_none(self) -> None:
        body = b"payload"
        secret = SigningSecret(version=1, secret="s1", algorithm=SignatureAlgorithm.HMAC_SHA256)
        result = verify_signed_request(
            body,
            signature="0" * 64,
            timestamp=1000,
            nonce="n1",
            secrets=[secret],
            tolerance_seconds=300,
            now=1000,
        )
        assert result is None
