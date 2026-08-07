"""Ed25519 content signing, verification, and key fingerprinting. Per
docs/059 "SECURITY" "Support": Digital Signatures, Publisher
Verification, Content Integrity, Signature Verification.

No ``shared_core`` equivalent exists -- ``shared_core.security
.encryption`` only provides AES-256-GCM and RSA *encryption* (OAEP),
``shared_core.security.hashing`` only provides shared-secret HMAC
signing, and ``shared_core.plugins.manifest.sign_manifest`` is RSA-PSS
keyed to a different (framework-level) manifest shape than this
service's own richer, DB-persisted one -- so this module is built
directly on ``cryptography``, mirroring the same precedent
``playbook-service/app/signing/signer.py`` and
``secrets-management-service/app/ssh/keygen.py`` already established.
Ed25519 (not RSA-PSS): modern, fast, small-signature, the same
algorithm those two precedents already settled on.
"""

from __future__ import annotations

import base64
import binascii
import hashlib

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ed25519


class SigningError(Exception):
    """A signing/verification key is malformed or the wrong algorithm."""


def generate_signing_keypair() -> tuple[str, str]:
    """Generate a new Ed25519 signing keypair.

    Returns:
        ``(private_key_pem, public_key_pem)`` -- the private key in
        PKCS8 PEM, the public key in SubjectPublicKeyInfo PEM.
    """
    private_key = ed25519.Ed25519PrivateKey.generate()
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


def compute_fingerprint(public_key_pem: str) -> str:
    """Compute the ``SHA256:...`` fingerprint of an Ed25519 public key,
    the same ``SHA256:<base64-digest>`` shape
    ``secrets-management-service/app/ssh/keygen.compute_fingerprint``
    established for SSH keys.

    Raises:
        SigningError: If *public_key_pem* isn't a valid Ed25519 public key.
    """
    public_key = _load_public_key(public_key_pem)
    raw = public_key.public_bytes(
        encoding=serialization.Encoding.Raw, format=serialization.PublicFormat.Raw
    )
    digest = hashlib.sha256(raw).digest()
    encoded = base64.b64encode(digest).decode("ascii").rstrip("=")
    return f"SHA256:{encoded}"


def sign_checksum(checksum: str, *, private_key_pem: str) -> str:
    """Sign *checksum* (a hex SHA-256 string) with an Ed25519 private key.

    Returns:
        The base64-encoded signature.

    Raises:
        SigningError: If *private_key_pem* isn't a valid Ed25519 private key.
    """
    private_key = _load_private_key(private_key_pem)
    signature = private_key.sign(checksum.encode("ascii"))
    return base64.b64encode(signature).decode("ascii")


def verify_signature(checksum: str, *, signature: str, public_key_pem: str) -> bool:
    """Verify a base64 Ed25519 *signature* was produced over *checksum*
    by the holder of *public_key_pem*'s own private key.

    Never raises -- any malformed input (bad PEM, bad base64, wrong
    algorithm, or a genuinely invalid signature) simply means "not
    verified", the same defensive shape publisher verification needs.
    """
    try:
        public_key = _load_public_key(public_key_pem)
        signature_bytes = base64.b64decode(signature, validate=True)
        public_key.verify(signature_bytes, checksum.encode("ascii"))
    except (SigningError, InvalidSignature, ValueError, binascii.Error):
        return False
    return True


def _load_private_key(private_key_pem: str) -> ed25519.Ed25519PrivateKey:
    try:
        key = serialization.load_pem_private_key(private_key_pem.encode("ascii"), password=None)
    except ValueError as exc:
        raise SigningError(f"Malformed private key: {exc}") from exc
    if not isinstance(key, ed25519.Ed25519PrivateKey):
        raise SigningError("Signing key is not an Ed25519 private key.")
    return key


def _load_public_key(public_key_pem: str) -> ed25519.Ed25519PublicKey:
    try:
        key = serialization.load_pem_public_key(public_key_pem.encode("ascii"))
    except ValueError as exc:
        raise SigningError(f"Malformed public key: {exc}") from exc
    if not isinstance(key, ed25519.Ed25519PublicKey):
        raise SigningError("Verification key is not an Ed25519 public key.")
    return key


__all__ = [
    "SigningError",
    "compute_fingerprint",
    "generate_signing_keypair",
    "sign_checksum",
    "verify_signature",
]
