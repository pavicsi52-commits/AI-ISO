"""JWT verification key material.

This service verifies, but never issues, tokens -- authentication and
signing are ``services/authentication-service``'s job (docs/033's own
"DO NOT IMPLEMENT" scope, plus "Integrate Prompt 017"). RSA public keys
are, by design, safe to duplicate across services; a real deployment
mounts the same public key file authentication-service's private key
pairs with. There is nothing to *generate* here -- this service holds
no private key, so a missing file is a real configuration error, not
something to paper over with an ephemeral fallback.
"""

from __future__ import annotations

from pathlib import Path

from shared_core.exceptions.dependency import DependencyError


def load_public_key(public_key_path: str) -> str:
    """Load the RS256 public key used to verify caller identity tokens.

    Raises:
        DependencyError: If no key file exists at *public_key_path*.
    """
    path = Path(public_key_path)
    if not path.is_file():
        raise DependencyError(
            f"JWT public key not found at {public_key_path!r}. This service verifies tokens "
            "issued by services/authentication-service and cannot generate one of its own."
        )
    return path.read_text(encoding="ascii")


def load_signing_keypair(private_key_path: str, public_key_path: str) -> tuple[str, str]:
    """Load this service's own Ed25519 content-signing keypair.

    Unlike the JWT verification key, this service *is* the owner of
    this key material -- but a missing file still fails fast rather
    than silently generating a fresh identity on every restart, the
    same "nothing to generate on the fly, an operator must provision
    it" discipline ``services/secrets-management-service``'s own
    ``config/master_key.py`` established: a rotating signing identity
    on every container restart would silently break every prior
    signature's own ``public_key_fingerprint`` continuity. Provision
    with :func:`app.signing.signer.generate_signing_keypair`.

    Raises:
        DependencyError: If either key file is missing.
    """
    private_path = Path(private_key_path)
    public_path = Path(public_key_path)
    if not private_path.is_file() or not public_path.is_file():
        raise DependencyError(
            f"Signing keypair not found at {private_key_path!r} / {public_key_path!r}. "
            "Generate one with app.signing.signer.generate_signing_keypair() and store it "
            "there -- this service has no fallback for missing key material."
        )
    return private_path.read_text(encoding="ascii"), public_path.read_text(encoding="ascii")


__all__ = ["load_public_key", "load_signing_keypair"]
