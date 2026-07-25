"""JWT signing key material.

Per docs/030_Enterprise_Authentication_Service.md.txt "JWT": RS256
signing, Key Rotation. Loads an RS256 keypair from the configured file
paths, generating (and persisting) a fresh one on first run when the
files don't exist yet -- convenient for local development, where no
manual key provisioning step is needed to start the service. A real
production deployment provisions real key files ahead of time (via
infrastructure/secrets, per ``shared_core.config.secrets``) so restarts
and multi-instance deployments share one signing identity; this
fallback exists purely for local/dev convenience.
"""

from __future__ import annotations

from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from shared_core.logging.logger import get_logger

logger = get_logger("app.config.keys")

_RSA_KEY_SIZE_BITS = 4096


def generate_keypair() -> tuple[str, str]:
    """Generate a fresh RSA keypair, returning ``(private_pem, public_pem)``."""
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


def load_or_generate_keypair(private_key_path: str, public_key_path: str) -> tuple[str, str]:
    """Load an RS256 keypair from disk, generating and persisting one if absent ("Key Rotation")."""
    private_path = Path(private_key_path)
    public_path = Path(public_key_path)
    if private_path.is_file() and public_path.is_file():
        return (
            private_path.read_text(encoding="ascii"),
            public_path.read_text(encoding="ascii"),
        )

    logger.warning(
        "JWT keypair not found on disk; generating an ephemeral one.",
        extra={"extra_fields": {"private_key_path": private_key_path}},
    )
    private_pem, public_pem = generate_keypair()
    private_path.parent.mkdir(parents=True, exist_ok=True)
    private_path.write_text(private_pem, encoding="ascii")
    public_path.write_text(public_pem, encoding="ascii")
    return private_pem, public_pem


__all__ = ["generate_keypair", "load_or_generate_keypair"]
