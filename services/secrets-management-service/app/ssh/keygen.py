"""SSH keypair generation, serialization, and fingerprinting. Per
docs/035 "SSH KEY MANAGEMENT": RSA, ECDSA, Ed25519, Key Generation,
Fingerprint Validation.

No ``shared_core`` equivalent exists --
``shared_core.security.encryption.generate_rsa_keypair`` generates RSA
keys for asymmetric *encryption* (OAEP), not SSH authentication keys,
and has no ECDSA/Ed25519 or OpenSSH-format support -- so this module is
built directly on ``cryptography``.
"""

from __future__ import annotations

import base64
import hashlib

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec, ed25519, rsa

from app.models.enums import SSHKeyType

_RSA_KEY_SIZE_BITS = 4096
_EC_CURVE = ec.SECP256R1()
_OPENSSH_LINE_MIN_PARTS = 2

_SSHPrivateKey = rsa.RSAPrivateKey | ec.EllipticCurvePrivateKey | ed25519.Ed25519PrivateKey


def generate_ssh_keypair(key_type: SSHKeyType) -> tuple[str, str]:
    """Generate a new SSH keypair.

    Returns:
        ``(private_key_pem, public_key_openssh)`` -- the private key in
        PKCS8 PEM (for storage as a :class:`~app.models.secret.Secret`),
        the public key in OpenSSH "authorized_keys" line format
        (plaintext, stored directly on :class:`~app.models.ssh_key.SSHKey`).
    """
    private_key: _SSHPrivateKey
    if key_type == SSHKeyType.RSA:
        private_key = rsa.generate_private_key(public_exponent=65537, key_size=_RSA_KEY_SIZE_BITS)
    elif key_type == SSHKeyType.ECDSA:
        private_key = ec.generate_private_key(_EC_CURVE)
    elif key_type == SSHKeyType.ED25519:
        private_key = ed25519.Ed25519PrivateKey.generate()
    else:  # pragma: no cover -- exhaustive over SSHKeyType
        raise ValueError(f"Unsupported SSH key type: {key_type!r}")

    private_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode("ascii")
    public_openssh = (
        private_key.public_key()
        .public_bytes(
            encoding=serialization.Encoding.OpenSSH,
            format=serialization.PublicFormat.OpenSSH,
        )
        .decode("ascii")
    )
    return private_pem, public_openssh


def compute_fingerprint(public_key_openssh: str) -> str:
    """Compute the ``SHA256:...`` fingerprint of an OpenSSH public key,
    matching ``ssh-keygen -lf`` output.
    """
    parts = public_key_openssh.strip().split()
    if len(parts) < _OPENSSH_LINE_MIN_PARTS:
        raise ValueError(f"Malformed OpenSSH public key: {public_key_openssh!r}")
    raw = base64.b64decode(parts[1])
    digest = hashlib.sha256(raw).digest()
    encoded = base64.b64encode(digest).decode("ascii").rstrip("=")
    return f"SHA256:{encoded}"


__all__ = ["compute_fingerprint", "generate_ssh_keypair"]
