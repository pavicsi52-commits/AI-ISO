"""Tests for connector configuration validation rules."""

from __future__ import annotations

from shared_core.validation.rules import connectors

_BASE = {"timeout_seconds": 30, "version": "1.0"}


def test_validate_ssh_connector_passes_with_password() -> None:
    config = {**_BASE, "host": "1.2.3.4", "username": "root", "password": "x"}

    assert connectors.validate_ssh_connector(config).valid is True


def test_validate_ssh_connector_passes_with_private_key() -> None:
    config = {**_BASE, "host": "1.2.3.4", "username": "root", "private_key": "---KEY---"}

    assert connectors.validate_ssh_connector(config).valid is True


def test_validate_ssh_connector_fails_without_credentials() -> None:
    config = {**_BASE, "host": "1.2.3.4", "username": "root"}

    result = connectors.validate_ssh_connector(config)

    assert result.valid is False


def test_validate_ssh_connector_fails_without_host() -> None:
    config = {**_BASE, "username": "root", "password": "x"}

    result = connectors.validate_ssh_connector(config)

    assert result.valid is False


def test_validate_ssh_connector_fails_for_bad_timeout() -> None:
    config = {
        "host": "1.2.3.4",
        "username": "root",
        "password": "x",
        "version": "1.0",
        "timeout_seconds": -1,
    }

    assert connectors.validate_ssh_connector(config).valid is False


def test_validate_ssh_connector_fails_for_excessive_timeout() -> None:
    config = {
        "host": "1.2.3.4",
        "username": "root",
        "password": "x",
        "version": "1.0",
        "timeout_seconds": 999999,
    }

    assert connectors.validate_ssh_connector(config).valid is False


def test_validate_ssh_connector_fails_without_version() -> None:
    config = {"host": "1.2.3.4", "username": "root", "password": "x", "timeout_seconds": 30}

    assert connectors.validate_ssh_connector(config).valid is False


def test_validate_ssh_connector_fails_for_non_list_capabilities() -> None:
    config = {
        **_BASE,
        "host": "1.2.3.4",
        "username": "root",
        "password": "x",
        "capabilities": "not-a-list",
    }

    assert connectors.validate_ssh_connector(config).valid is False


def test_validate_winrm_connector_requires_full_credentials() -> None:
    assert connectors.validate_winrm_connector({**_BASE, "host": "h"}).valid is False
    assert (
        connectors.validate_winrm_connector(
            {**_BASE, "host": "h", "username": "u", "password": "p"}
        ).valid
        is True
    )


def test_validate_redfish_connector_requires_certificate_when_tls_verified() -> None:
    config = {**_BASE, "host": "h", "username": "u", "password": "p", "verify_tls": True}

    assert connectors.validate_redfish_connector(config).valid is False

    config["certificate"] = "cert-data"
    assert connectors.validate_redfish_connector(config).valid is True


def test_validate_redfish_connector_skips_certificate_when_tls_disabled() -> None:
    config = {**_BASE, "host": "h", "username": "u", "password": "p", "verify_tls": False}

    assert connectors.validate_redfish_connector(config).valid is True


def test_validate_snmp_connector_accepts_community_string() -> None:
    config = {**_BASE, "host": "h", "community": "public"}

    assert connectors.validate_snmp_connector(config).valid is True


def test_validate_snmp_connector_accepts_v3_username() -> None:
    config = {**_BASE, "host": "h", "username": "snmpv3user"}

    assert connectors.validate_snmp_connector(config).valid is True


def test_validate_snmp_connector_fails_without_either() -> None:
    config = {**_BASE, "host": "h"}

    assert connectors.validate_snmp_connector(config).valid is False


def test_validate_docker_connector_passes_with_host() -> None:
    config = {**_BASE, "host": "unix:///var/run/docker.sock"}

    assert connectors.validate_docker_connector(config).valid is True


def test_validate_kubernetes_connector_requires_token_or_cert() -> None:
    config = {**_BASE, "host": "h", "certificate": "ca-cert"}

    assert connectors.validate_kubernetes_connector(config).valid is False

    config["token"] = "bearer-token"
    assert connectors.validate_kubernetes_connector(config).valid is True


def test_validate_vmware_connector_requires_full_credentials() -> None:
    assert connectors.validate_vmware_connector({**_BASE, "host": "h"}).valid is False
    assert (
        connectors.validate_vmware_connector(
            {**_BASE, "host": "h", "username": "u", "password": "p"}
        ).valid
        is True
    )


def test_validate_cloud_api_connector_accepts_api_key() -> None:
    config = {**_BASE, "host": "api.cloud.example", "api_key": "sk-123"}

    assert connectors.validate_cloud_api_connector(config).valid is True


def test_validate_cloud_api_connector_accepts_key_pair() -> None:
    config = {**_BASE, "host": "api.cloud.example", "access_key": "AK", "secret_key": "SK"}

    assert connectors.validate_cloud_api_connector(config).valid is True


def test_validate_cloud_api_connector_fails_without_credentials() -> None:
    config = {**_BASE, "host": "api.cloud.example"}

    assert connectors.validate_cloud_api_connector(config).valid is False
