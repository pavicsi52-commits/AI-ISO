"""AES-256-GCM symmetric and RSA asymmetric encryption.

Per docs/017_Enterprise_Security_Framework.md.txt "ENCRYPTION": AES-256,
RSA, key rotation.
"""

from __future__ import annotations

import base64
import os
from typing import cast

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

_KEY_SIZE_BYTES = 32  # AES-256
_NONCE_SIZE_BYTES = 12
_RSA_KEY_SIZE_BITS = 4096
_OAEP_PADDING = padding.OAEP(
    mgf=padding.MGF1(algorithm=hashes.SHA256()), algorithm=hashes.SHA256(), label=None
)


def generate_encryption_key() -> str:
    """Generate a new base64-encoded AES-256 key."""
    return base64.urlsafe_b64encode(os.urandom(_KEY_SIZE_BYTES)).decode("ascii")


def encrypt(plaintext: str, *, key: str) -> str:
    """Encrypt ``plaintext`` with AES-256-GCM.

    Args:
        plaintext: The value to encrypt.
        key: A base64-encoded 256-bit key, as returned by
            :func:`generate_encryption_key`.

    Returns:
        A base64-encoded ``nonce || ciphertext`` blob.
    """
    aesgcm = AESGCM(base64.urlsafe_b64decode(key))
    nonce = os.urandom(_NONCE_SIZE_BYTES)
    ciphertext = aesgcm.encrypt(nonce, plaintext.encode("utf-8"), None)
    return base64.urlsafe_b64encode(nonce + ciphertext).decode("ascii")


def decrypt(token: str, *, key: str) -> str:
    """Decrypt a value produced by :func:`encrypt`."""
    aesgcm = AESGCM(base64.urlsafe_b64decode(key))
    raw = base64.urlsafe_b64decode(token)
    nonce, ciphertext = raw[:_NONCE_SIZE_BYTES], raw[_NONCE_SIZE_BYTES:]
    return aesgcm.decrypt(nonce, ciphertext, None).decode("utf-8")


def rotate_key(*, old_key: str, new_key: str, ciphertext: str) -> str:
    """Re-encrypt a value under a new key.

    The standard "encrypted at rest, key rotation" pattern: decrypt with
    the outgoing key, re-encrypt with the incoming one. The caller is
    responsible for atomically swapping the stored ciphertext.
    """
    plaintext = decrypt(ciphertext, key=old_key)
    return encrypt(plaintext, key=new_key)


def generate_rsa_keypair() -> tuple[str, str]:
    """Generate a new RSA keypair for asymmetric encryption.

    Returns:
        ``(private_key_pem, public_key_pem)``.
    """
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=_RSA_KEY_SIZE_BITS)
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


def rsa_encrypt(plaintext: str, *, public_key: str) -> str:
    """Encrypt a short value (e.g. a symmetric key) with an RSA public key (OAEP padding).

    RSA is for small payloads only (a key, a token) -- use AES-256-GCM
    (:func:`encrypt`) for anything larger.
    """
    key = cast(rsa.RSAPublicKey, serialization.load_pem_public_key(public_key.encode("ascii")))
    ciphertext = key.encrypt(plaintext.encode("utf-8"), _OAEP_PADDING)
    return base64.urlsafe_b64encode(ciphertext).decode("ascii")


def rsa_decrypt(token: str, *, private_key: str) -> str:
    """Decrypt a value produced by :func:`rsa_encrypt`."""
    key = cast(
        rsa.RSAPrivateKey,
        serialization.load_pem_private_key(private_key.encode("ascii"), password=None),
    )
    ciphertext = base64.urlsafe_b64decode(token)
    plaintext = key.decrypt(ciphertext, _OAEP_PADDING)
    return plaintext.decode("utf-8")
