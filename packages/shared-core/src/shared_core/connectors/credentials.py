"""Connector credentials.

Per docs/027_Enterprise_Connector_SDK.md.txt "AUTHENTICATION": Username
Password, SSH Keys, API Keys, OAuth2, JWT, Bearer Tokens, Kerberos,
Certificates, Future SSO. "SECURITY": Never log passwords, Mask
secrets. A :class:`Credential` never renders its secret material in
``repr()``/``str()`` -- only :meth:`Credential.reveal` does, so an
accidentally-logged credential object can never leak a plaintext
secret. Persisting a credential at rest (docs/027's "Encrypt
credentials") is the caller's own concern via
:mod:`shared_core.security`/:mod:`shared_core.database` -- this SDK has
no credential store of its own to encrypt into (none is named in
docs/027's "DIRECTORY STRUCTURE").
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

_SECRET_MASK = "***"


class CredentialType(StrEnum):
    """Every credential type docs/027 "AUTHENTICATION" names."""

    USERNAME_PASSWORD = "username_password"
    SSH_KEY = "ssh_key"
    API_KEY = "api_key"
    OAUTH2 = "oauth2"
    JWT = "jwt"
    BEARER_TOKEN = "bearer_token"
    KERBEROS = "kerberos"
    CERTIFICATE = "certificate"
    SSO = "sso"


@dataclass(frozen=True, slots=True)
class Credential:
    """A connector credential. Secret fields never appear in ``repr()``/``str()``."""

    credential_type: CredentialType
    identity: str | None = None
    secrets: dict[str, str] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)

    def __repr__(self) -> str:
        masked = ", ".join(f"{key}={_SECRET_MASK}" for key in self.secrets)
        return (
            f"Credential(credential_type={self.credential_type!r}, "
            f"identity={self.identity!r}, secrets={{{masked}}})"
        )

    def reveal(self, key: str) -> str:
        """Return one secret field's actual value, by name.

        Raises:
            KeyError: If *key* isn't one of this credential's secret fields.
        """
        return self.secrets[key]

    def has_secret(self, key: str) -> bool:
        """Whether this credential carries a secret field named *key*."""
        return key in self.secrets


def username_password(username: str, password: str) -> Credential:
    """Build a ``USERNAME_PASSWORD`` credential."""
    return Credential(
        credential_type=CredentialType.USERNAME_PASSWORD,
        identity=username,
        secrets={"password": password},
    )


def api_key(key: str, *, identity: str | None = None) -> Credential:
    """Build an ``API_KEY`` credential."""
    return Credential(
        credential_type=CredentialType.API_KEY, identity=identity, secrets={"api_key": key}
    )


def bearer_token(token: str) -> Credential:
    """Build a ``BEARER_TOKEN`` credential."""
    return Credential(credential_type=CredentialType.BEARER_TOKEN, secrets={"token": token})


def jwt_credential(token: str) -> Credential:
    """Build a ``JWT`` credential."""
    return Credential(credential_type=CredentialType.JWT, secrets={"token": token})


def ssh_key(
    private_key: str, *, identity: str | None = None, passphrase: str | None = None
) -> Credential:
    """Build an ``SSH_KEY`` credential."""
    secrets = {"private_key": private_key}
    if passphrase is not None:
        secrets["passphrase"] = passphrase
    return Credential(credential_type=CredentialType.SSH_KEY, identity=identity, secrets=secrets)


def certificate(cert_pem: str, key_pem: str) -> Credential:
    """Build a ``CERTIFICATE`` credential."""
    return Credential(
        credential_type=CredentialType.CERTIFICATE,
        secrets={"certificate": cert_pem, "private_key": key_pem},
    )


def oauth2_credential(
    access_token: str, *, refresh_token: str | None = None, identity: str | None = None
) -> Credential:
    """Build an ``OAUTH2`` credential."""
    secrets = {"access_token": access_token}
    if refresh_token is not None:
        secrets["refresh_token"] = refresh_token
    return Credential(credential_type=CredentialType.OAUTH2, identity=identity, secrets=secrets)


__all__ = [
    "Credential",
    "CredentialType",
    "api_key",
    "bearer_token",
    "certificate",
    "jwt_credential",
    "oauth2_credential",
    "ssh_key",
    "username_password",
]
