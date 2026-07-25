"""Connector validation.

Per docs/027_Enterprise_Connector_SDK.md.txt "VALIDATION": Connection
Validation, Credential Validation, Certificate Validation, Capability
Validation, Schema Validation.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from datetime import UTC, datetime

from shared_core.connectors.connection import ConnectionConfig
from shared_core.connectors.credentials import Credential, CredentialType
from shared_core.connectors.exceptions import CapabilityNotSupportedError, ConnectorValidationError

_MIN_PORT = 1
_MAX_PORT = 65535

_REQUIRED_SECRETS_BY_TYPE: dict[CredentialType, tuple[str, ...]] = {
    CredentialType.USERNAME_PASSWORD: ("password",),
    CredentialType.SSH_KEY: ("private_key",),
    CredentialType.API_KEY: ("api_key",),
    CredentialType.OAUTH2: ("access_token",),
    CredentialType.JWT: ("token",),
    CredentialType.BEARER_TOKEN: ("token",),
    CredentialType.CERTIFICATE: ("certificate", "private_key"),
}


def validate_connection_config(config: ConnectionConfig) -> None:
    """Validate a :class:`ConnectionConfig` is usable ("Connection Validation").

    Raises:
        ConnectorValidationError: If invalid.
    """
    if not config.host.strip():
        raise ConnectorValidationError("Connection config requires a non-empty host.")
    if config.port is not None and not (_MIN_PORT <= config.port <= _MAX_PORT):
        raise ConnectorValidationError(
            f"Invalid port {config.port}; must be {_MIN_PORT}-{_MAX_PORT}."
        )
    if config.connect_timeout_seconds <= 0:
        raise ConnectorValidationError("connect_timeout_seconds must be positive.")


def validate_credential(credential: Credential) -> None:
    """Validate a :class:`Credential` carries the secrets its type requires.

    Raises:
        ConnectorValidationError: If a required secret is missing.
    """
    required = _REQUIRED_SECRETS_BY_TYPE.get(credential.credential_type, ())
    missing = [key for key in required if not credential.has_secret(key)]
    if missing:
        raise ConnectorValidationError(
            f"Credential type {credential.credential_type.value!r} is missing "
            f"required secret(s): {', '.join(missing)}."
        )


def validate_certificate_expiry(not_after: datetime, *, now: datetime | None = None) -> None:
    """Validate a certificate hasn't expired ("Certificate Validation").

    Raises:
        ConnectorValidationError: If *not_after* is at or before *now*.
    """
    moment = now or datetime.now(UTC)
    if not_after <= moment:
        raise ConnectorValidationError(f"Certificate expired at {not_after.isoformat()}.")


def validate_capability(capability: str, supported: frozenset[str]) -> None:
    """Validate *capability* is among *supported* ("Capability Validation").

    Raises:
        CapabilityNotSupportedError: If unsupported.
    """
    if capability not in supported:
        raise CapabilityNotSupportedError(
            f"Capability {capability!r} is not supported; supported: {sorted(supported)}."
        )


def validate_schema(payload: Mapping[str, object], required_fields: Iterable[str]) -> None:
    """Validate *payload* has every field in *required_fields* ("Schema Validation").

    Raises:
        ConnectorValidationError: If a required field is missing.
    """
    missing = [name for name in required_fields if name not in payload]
    if missing:
        raise ConnectorValidationError(
            f"Payload is missing required field(s): {', '.join(missing)}."
        )


__all__ = [
    "validate_capability",
    "validate_certificate_expiry",
    "validate_connection_config",
    "validate_credential",
    "validate_schema",
]
