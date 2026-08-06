"""HMAC signature generation/verification (docs/057 "SECURITY", "SIGNATURE
MANAGEMENT").

`shared_core.security.hashing.sign`/`.verify_signature` exist but are
hardcoded to HMAC-SHA256 -- this module must support SHA256 *and*
SHA512 through one interface (docs/057 names both), so it builds
directly on the stdlib ``hmac``/``hashlib`` modules `shared_core`'s own
version wraps, rather than fork a second, algorithm-parameterised copy
of that thin wrapper. Secret rotation with overlap, and replay
protection via timestamp/nonce validation, are both genuine gaps with
no primitive anywhere in `shared_core` -- built new.
"""

from __future__ import annotations

import hashlib
import hmac
import time
from dataclasses import dataclass

from app.models.enums import SignatureAlgorithm

_HASH_FUNCS = {
    SignatureAlgorithm.HMAC_SHA256: hashlib.sha256,
    SignatureAlgorithm.HMAC_SHA512: hashlib.sha512,
}


def sign_payload(
    body: bytes, *, secret: str, algorithm: SignatureAlgorithm = SignatureAlgorithm.HMAC_SHA256
) -> str:
    """Compute the hex HMAC digest of *body* under *secret*."""
    digest_func = _HASH_FUNCS[algorithm]
    return hmac.new(secret.encode("utf-8"), body, digest_func).hexdigest()


def verify_payload_signature(
    body: bytes,
    *,
    signature: str,
    secret: str,
    algorithm: SignatureAlgorithm = SignatureAlgorithm.HMAC_SHA256,
) -> bool:
    """Whether *signature* is the correct HMAC digest of *body* under *secret*.

    Constant-time comparison via :func:`hmac.compare_digest` -- a
    signature check must not leak timing information a caller could use
    to guess the correct digest byte by byte.
    """
    expected = sign_payload(body, secret=secret, algorithm=algorithm)
    return hmac.compare_digest(expected, signature)


@dataclass(frozen=True, slots=True)
class SigningSecret:
    """One of an endpoint's own active/rotating signing secrets."""

    version: int
    secret: str
    algorithm: SignatureAlgorithm


def verify_with_any_secret(
    body: bytes, *, signature: str, secrets: list[SigningSecret]
) -> SigningSecret | None:
    """Verify *signature* against every candidate secret; returns the one that matched.

    Trying every active/rotating secret (not just the newest) is what
    makes secret rotation safe: a receiver mid-rotation must still
    accept a signature computed under the secret it had *before* the
    rotation, for as long as that old secret's own row stays ``ROTATING``
    rather than ``EXPIRED``.
    """
    for candidate in secrets:
        if verify_payload_signature(
            body, signature=signature, secret=candidate.secret, algorithm=candidate.algorithm
        ):
            return candidate
    return None


def is_timestamp_fresh(timestamp: int, *, tolerance_seconds: int, now: int | None = None) -> bool:
    """Whether *timestamp* (Unix seconds) is within *tolerance_seconds* of now.

    Rejects a captured, replayed request whose original timestamp has
    aged out -- and, symmetrically, a timestamp implausibly far in the
    future (clock skew has a ceiling too).
    """
    current = now if now is not None else int(time.time())
    return abs(current - timestamp) <= tolerance_seconds


def build_signed_headers(
    body: bytes,
    *,
    secret: str,
    algorithm: SignatureAlgorithm,
    timestamp: int,
    nonce: str,
) -> dict[str, str]:
    """Build the standard outbound signature headers for one delivery attempt.

    The timestamp and nonce are signed *together with* the body (not
    sent unsigned alongside it) -- otherwise a receiver validating the
    signature against the body alone would accept a replayed request
    with a forged, fresh timestamp stapled on afterward.
    """
    signed_payload = timestamp.to_bytes(8, "big") + nonce.encode("utf-8") + body
    signature = sign_payload(signed_payload, secret=secret, algorithm=algorithm)
    return {
        "X-Webhook-Signature": signature,
        "X-Webhook-Timestamp": str(timestamp),
        "X-Webhook-Nonce": nonce,
        "X-Webhook-Signature-Algorithm": algorithm.value,
    }


def verify_signed_request(
    body: bytes,
    *,
    signature: str,
    timestamp: int,
    nonce: str,
    secrets: list[SigningSecret],
    tolerance_seconds: int,
    now: int | None = None,
) -> SigningSecret | None:
    """Verify a full inbound signed request: freshness, then signature.

    Returns the matching secret, or ``None`` if the timestamp has aged
    out or no candidate secret's signature matches. Freshness is checked
    *before* the (relatively expensive, and multi-secret) signature
    comparison -- an already-stale request is rejected without wasting
    cycles verifying a signature that, even if valid, would still be
    refused.
    """
    if not is_timestamp_fresh(timestamp, tolerance_seconds=tolerance_seconds, now=now):
        return None
    signed_payload = timestamp.to_bytes(8, "big") + nonce.encode("utf-8") + body
    return verify_with_any_secret(signed_payload, signature=signature, secrets=secrets)


__all__ = [
    "SigningSecret",
    "build_signed_headers",
    "is_timestamp_fresh",
    "sign_payload",
    "verify_payload_signature",
    "verify_signed_request",
    "verify_with_any_secret",
]
