"""JWT verification key material.

This service verifies, but never issues, tokens -- authentication and
signing are ``services/authentication-service``'s job (docs/032's own
"DO NOT IMPLEMENT": Authentication). RSA public keys are, by design,
safe to duplicate across services; a real deployment mounts the same
public key file authentication-service's private key pairs with.
There is nothing to *generate* here -- this service holds no private
key, so a missing file is a real configuration error, not something to
paper over with an ephemeral fallback.
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


__all__ = ["load_public_key"]
