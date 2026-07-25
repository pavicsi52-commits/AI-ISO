"""Connector validation rules (docs/016 "CONNECTOR VALIDATION").

Structural validation of a connector's *configuration* (credentials
present, timeout sane, certificate present when required, version/
capabilities declared) for SSH, WinRM, Redfish, SNMP, Docker, Kubernetes,
VMware, and generic cloud API connectors. No connection is attempted --
that requires real infrastructure and belongs to the connector
implementations themselves, not this framework (docs/016
"DO NOT IMPLEMENT": "Inventory", "Automation").
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from shared_core.validation.results import ValidationResult

_DEFAULT_MAX_TIMEOUT_SECONDS = 300


def _check_common(
    config: Mapping[str, Any],
    *,
    required_credential_fields: Sequence[str],
    requires_certificate: bool = False,
) -> list[str]:
    errors: list[str] = []

    missing_credentials = [field for field in required_credential_fields if not config.get(field)]
    if missing_credentials:
        errors.append(f"Missing required credential field(s): {', '.join(missing_credentials)}.")

    timeout = config.get("timeout_seconds")
    if not isinstance(timeout, int | float) or timeout <= 0:
        errors.append("Connector 'timeout_seconds' must be a positive number.")
    elif timeout > _DEFAULT_MAX_TIMEOUT_SECONDS:
        errors.append(
            f"Connector 'timeout_seconds' ({timeout}) exceeds the maximum of "
            f"{_DEFAULT_MAX_TIMEOUT_SECONDS}."
        )

    if requires_certificate and not config.get("certificate"):
        errors.append("Connector requires a 'certificate' field.")

    if not config.get("version"):
        errors.append("Connector must declare a 'version'.")

    capabilities = config.get("capabilities")
    if capabilities is not None and not isinstance(capabilities, list):
        errors.append("Connector 'capabilities' must be a list.")

    return errors


def validate_ssh_connector(config: Mapping[str, Any]) -> ValidationResult:
    """Validate an SSH connector config: host/username + (password or private_key)."""
    errors = _check_common(config, required_credential_fields=["host", "username"])
    if not config.get("password") and not config.get("private_key"):
        errors.append("SSH connector requires either 'password' or 'private_key'.")
    return ValidationResult.fail(*errors) if errors else ValidationResult.ok()


def validate_winrm_connector(config: Mapping[str, Any]) -> ValidationResult:
    """Validate a WinRM connector config."""
    errors = _check_common(config, required_credential_fields=["host", "username", "password"])
    return ValidationResult.fail(*errors) if errors else ValidationResult.ok()


def validate_redfish_connector(config: Mapping[str, Any]) -> ValidationResult:
    """Validate a Redfish (BMC/out-of-band management) connector config."""
    errors = _check_common(
        config,
        required_credential_fields=["host", "username", "password"],
        requires_certificate=bool(config.get("verify_tls", True)),
    )
    return ValidationResult.fail(*errors) if errors else ValidationResult.ok()


def validate_snmp_connector(config: Mapping[str, Any]) -> ValidationResult:
    """Validate an SNMP connector config: host + community (v1/v2c) or credentials (v3)."""
    errors = _check_common(config, required_credential_fields=["host"])
    if not config.get("community") and not config.get("username"):
        errors.append("SNMP connector requires either 'community' (v1/v2c) or 'username' (v3).")
    return ValidationResult.fail(*errors) if errors else ValidationResult.ok()


def validate_docker_connector(config: Mapping[str, Any]) -> ValidationResult:
    """Validate a Docker connector config: a daemon endpoint."""
    errors = _check_common(config, required_credential_fields=["host"], requires_certificate=False)
    return ValidationResult.fail(*errors) if errors else ValidationResult.ok()


def validate_kubernetes_connector(config: Mapping[str, Any]) -> ValidationResult:
    """Validate a Kubernetes connector config: an API server + credentials."""
    errors = _check_common(config, required_credential_fields=["host"], requires_certificate=True)
    if not config.get("token") and not config.get("client_certificate"):
        errors.append(
            "Kubernetes connector requires either a bearer 'token' or 'client_certificate'."
        )
    return ValidationResult.fail(*errors) if errors else ValidationResult.ok()


def validate_vmware_connector(config: Mapping[str, Any]) -> ValidationResult:
    """Validate a VMware (vCenter/ESXi) connector config."""
    errors = _check_common(config, required_credential_fields=["host", "username", "password"])
    return ValidationResult.fail(*errors) if errors else ValidationResult.ok()


def validate_cloud_api_connector(config: Mapping[str, Any]) -> ValidationResult:
    """Validate a generic cloud API connector config: an API key or access/secret key pair."""
    errors = _check_common(config, required_credential_fields=[])
    has_api_key = bool(config.get("api_key"))
    has_key_pair = bool(config.get("access_key")) and bool(config.get("secret_key"))
    if not has_api_key and not has_key_pair:
        errors.append(
            "Cloud API connector requires either an 'api_key' or an "
            "'access_key'/'secret_key' pair."
        )
    return ValidationResult.fail(*errors) if errors else ValidationResult.ok()
