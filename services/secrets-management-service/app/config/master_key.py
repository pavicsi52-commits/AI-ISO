"""Envelope-encryption master key material.

Per docs/035 "ENCRYPTION": "Master Key", "Envelope Encryption". This
service never encrypts a secret value directly with the master key --
it wraps (encrypts) per-secret Data Encryption Keys (DEKs), which in
turn encrypt secret values (see ``app/encryption/envelope.py``). The
master key itself is loaded from a local file (a base64-encoded
AES-256 key, in the exact format
:func:`shared_core.security.encryption.generate_encryption_key`
produces) rather than generated here -- a missing key file is a real
configuration error, not something to paper over with an ephemeral
fallback, the same "nothing to generate, fail fast" discipline
``app/config/keys.py::load_public_key`` established for the JWT
verification key every downstream AI-IOS service already loads.

Docs/035's own "KEY MANAGEMENT" section explicitly marks "Hardware
Security Module" and "Cloud KMS Integration" as "(future)" -- a local
master key file is the correct scope for this prompt, not a gap.
"""

from __future__ import annotations

from pathlib import Path

from shared_core.exceptions.dependency import DependencyError


def load_master_key(master_key_path: str) -> str:
    """Load the base64-encoded AES-256 master key used to wrap Data
    Encryption Keys.

    Raises:
        DependencyError: If no key file exists at *master_key_path*.
    """
    path = Path(master_key_path)
    if not path.is_file():
        raise DependencyError(
            f"Master key not found at {master_key_path!r}. Generate one with "
            "shared_core.security.encryption.generate_encryption_key() and store it there "
            "-- this service has no fallback for missing key material."
        )
    return path.read_text(encoding="ascii").strip()


__all__ = ["load_master_key"]
