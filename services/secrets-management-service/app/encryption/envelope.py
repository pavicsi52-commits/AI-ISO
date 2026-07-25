"""Envelope encryption: a master key wraps Data Encryption Keys (DEKs),
and DEKs encrypt secret values. Per docs/035 "ENCRYPTION AT REST":
Envelope Encryption, AES-256-GCM, Key Hierarchy, Data Encryption Keys.

Key hierarchy (outermost to innermost)::

    Master Key (local file, never persisted to the database)
        wraps -> Data Encryption Key (DEK, stored wrapped in ``encryption_keys``)
            encrypts -> Secret value (stored in ``secret_versions.ciphertext``)

Rotating the master key means re-wrapping every DEK; rotating a DEK means
re-encrypting every secret value currently under it. Both are exposed
here as pure, database-independent operations -- callers in
``app.services`` are responsible for persisting the results.
"""

from __future__ import annotations

from shared_core.security.encryption import decrypt, encrypt, generate_encryption_key


class EnvelopeEncryption:
    """Master-key-wraps-DEK-encrypts-value envelope encryption."""

    def __init__(self, master_key: str) -> None:
        self._master_key = master_key

    def generate_dek(self) -> str:
        """Generate a new, unwrapped Data Encryption Key."""
        return generate_encryption_key()

    def wrap_dek(self, raw_dek: str) -> str:
        """Encrypt *raw_dek* under the master key, for storage."""
        return encrypt(raw_dek, key=self._master_key)

    def unwrap_dek(self, wrapped_dek: str) -> str:
        """Decrypt a DEK previously wrapped by :meth:`wrap_dek`."""
        return decrypt(wrapped_dek, key=self._master_key)

    def encrypt_value(self, plaintext: str, *, wrapped_dek: str) -> str:
        """Encrypt *plaintext* with the DEK unwrapped from *wrapped_dek*."""
        return encrypt(plaintext, key=self.unwrap_dek(wrapped_dek))

    def decrypt_value(self, ciphertext: str, *, wrapped_dek: str) -> str:
        """Decrypt a value produced by :meth:`encrypt_value`."""
        return decrypt(ciphertext, key=self.unwrap_dek(wrapped_dek))

    def rewrap_dek(self, wrapped_dek: str, *, new_master_key: str) -> str:
        """Re-wrap a DEK under *new_master_key* ("Master Key Rotation")."""
        raw_dek = self.unwrap_dek(wrapped_dek)
        return encrypt(raw_dek, key=new_master_key)

    def reencrypt_value(
        self, ciphertext: str, *, old_wrapped_dek: str, new_wrapped_dek: str
    ) -> str:
        """Re-encrypt a secret value under a new DEK ("DEK Rotation")."""
        plaintext = self.decrypt_value(ciphertext, wrapped_dek=old_wrapped_dek)
        return self.encrypt_value(plaintext, wrapped_dek=new_wrapped_dek)


__all__ = ["EnvelopeEncryption"]
