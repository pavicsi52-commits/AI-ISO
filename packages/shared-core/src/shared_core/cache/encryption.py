"""Cache value encryption.

Per docs/019_Enterprise_Cache_Framework.md.txt "ENCRYPTION": "Encrypt
sensitive cache values. AES-256. Configurable."

Deliberately does *not* import :mod:`shared_core.security.encryption`
(Prompt 017), even though it implements the same AES-256-GCM algorithm:
Prompt 017's ``security`` package already depends on this ``cache``
package (``security.ratelimit``/``security.sessions`` use
:class:`~shared_core.cache.manager.CacheManager`), so a ``cache ->
security`` import here would create a circular import. Key generation
(two lines: a random 256-bit key, base64-encoded) is small enough to
duplicate rather than invert the framework's one-directional dependency
rule for it. Same algorithm, key format, and nonce size as Prompt 017's
implementation either way, so keys remain interchangeable; only
``encrypt``/``decrypt`` differ, and only because they're bytes-native here
(see below) rather than ``str``-in/``str``-out.
"""

from __future__ import annotations

import base64
import os
from typing import Final

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from shared_core.cache.exceptions import CacheEncryptionError

_KEY_SIZE_BYTES: Final[int] = 32  # AES-256
_NONCE_SIZE_BYTES: Final[int] = 12

__all__ = ["decrypt_value", "encrypt_value", "generate_encryption_key"]


def generate_encryption_key() -> str:
    """Generate a new base64-encoded AES-256 key."""
    return base64.urlsafe_b64encode(os.urandom(_KEY_SIZE_BYTES)).decode("ascii")


def encrypt_value(data: bytes, *, key: str) -> bytes:
    """Encrypt a raw cache payload with AES-256-GCM.

    Args:
        data: The (already serialized/compressed) payload to encrypt.
        key: A base64-encoded 256-bit key, as returned by
            :func:`generate_encryption_key`.

    Returns:
        A ``nonce || ciphertext`` byte string.
    """
    try:
        aesgcm = AESGCM(base64.urlsafe_b64decode(key))
        nonce = os.urandom(_NONCE_SIZE_BYTES)
        ciphertext = aesgcm.encrypt(nonce, data, None)
        return nonce + ciphertext
    except Exception as exc:
        raise CacheEncryptionError("Failed to encrypt cache value.") from exc


def decrypt_value(token: bytes, *, key: str) -> bytes:
    """Decrypt a payload produced by :func:`encrypt_value`."""
    try:
        aesgcm = AESGCM(base64.urlsafe_b64decode(key))
        nonce, ciphertext = token[:_NONCE_SIZE_BYTES], token[_NONCE_SIZE_BYTES:]
        return aesgcm.decrypt(nonce, ciphertext, None)
    except Exception as exc:
        raise CacheEncryptionError("Failed to decrypt cache value.") from exc
