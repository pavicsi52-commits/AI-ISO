"""Hashing helper functions.

Not for password hashing — see docs/012_Shared_Core_Framework.md.txt
``security/`` (Argon2) for that. These are for checksums and cache keys.
"""

from __future__ import annotations

import hashlib


def sha256_hex(value: str | bytes) -> str:
    """Return the hex-encoded SHA-256 digest of ``value``."""
    data = value.encode("utf-8") if isinstance(value, str) else value
    return hashlib.sha256(data).hexdigest()


def stable_hash(*parts: str) -> str:
    """Return a stable SHA-256 hex digest of the given parts joined with '|'.

    Useful for building deterministic cache keys from multiple inputs.
    """
    return sha256_hex("|".join(parts))
