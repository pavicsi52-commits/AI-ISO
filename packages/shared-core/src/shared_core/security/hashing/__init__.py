"""HMAC signing and verification.

Distinct from :mod:`shared_core.helpers.hash_helper` (checksums, cache
keys) and :mod:`shared_core.security.password` (Argon2 password hashing)
-- this is for signing/verifying data with a shared secret (webhook
payload signatures, signed URLs).
"""

from __future__ import annotations

import hashlib
import hmac


def sign(payload: str | bytes, *, secret: str) -> str:
    """Return the hex-encoded HMAC-SHA256 signature of *payload*."""
    data = payload.encode("utf-8") if isinstance(payload, str) else payload
    return hmac.new(secret.encode("utf-8"), data, hashlib.sha256).hexdigest()


def verify_signature(payload: str | bytes, *, signature: str, secret: str) -> bool:
    """Verify an HMAC-SHA256 signature using a constant-time comparison."""
    expected = sign(payload, secret=secret)
    return hmac.compare_digest(expected, signature)
