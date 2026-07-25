"""Tests for the reusable field validators."""

from __future__ import annotations

import pytest
from shared_core.validators import (
    validate_asset_name,
    validate_domain,
    validate_email,
    validate_hostname,
    validate_ipv4,
    validate_ipv6,
    validate_mac_address,
    validate_organization_name,
    validate_password,
    validate_playbook_name,
    validate_port,
    validate_project_name,
    validate_url,
    validate_username,
    validate_uuid,
)


@pytest.mark.parametrize(
    "value",
    ["550e8400-e29b-41d4-a716-446655440000", "00000000-0000-0000-0000-000000000000"],
)
def test_validate_uuid_accepts_valid_uuids(value: str) -> None:
    assert validate_uuid(value).valid


@pytest.mark.parametrize("value", ["not-a-uuid", "", "12345"])
def test_validate_uuid_rejects_invalid_uuids(value: str) -> None:
    result = validate_uuid(value)
    assert not result.valid
    assert result.errors


@pytest.mark.parametrize("value", ["user@example.com", "a.b+tag@sub.example.co"])
def test_validate_email_accepts_valid_addresses(value: str) -> None:
    assert validate_email(value).valid


@pytest.mark.parametrize("value", ["", "not-an-email", "missing@domain", "@example.com"])
def test_validate_email_rejects_invalid_addresses(value: str) -> None:
    assert not validate_email(value).valid


def test_validate_email_rejects_overly_long_address() -> None:
    long_local = "a" * 250
    assert not validate_email(f"{long_local}@example.com").valid


@pytest.mark.parametrize("value", ["example.com", "sub.example.co.uk", "a"])
def test_validate_hostname_accepts_valid_hostnames(value: str) -> None:
    assert validate_hostname(value).valid


@pytest.mark.parametrize("value", ["", "-bad.com", "bad-.com", "a" * 300])
def test_validate_hostname_rejects_invalid_hostnames(value: str) -> None:
    assert not validate_hostname(value).valid


def test_validate_ipv4_accepts_valid_address() -> None:
    assert validate_ipv4("192.168.1.1").valid


@pytest.mark.parametrize("value", ["999.999.999.999", "not-an-ip", "::1"])
def test_validate_ipv4_rejects_invalid_address(value: str) -> None:
    assert not validate_ipv4(value).valid


def test_validate_ipv6_accepts_valid_address() -> None:
    assert validate_ipv6("2001:db8::1").valid


@pytest.mark.parametrize("value", ["not-an-ip", "192.168.1.1"])
def test_validate_ipv6_rejects_invalid_address(value: str) -> None:
    assert not validate_ipv6(value).valid


@pytest.mark.parametrize("value", ["00:1A:2B:3C:4D:5E", "00-1a-2b-3c-4d-5e"])
def test_validate_mac_address_accepts_valid_address(value: str) -> None:
    assert validate_mac_address(value).valid


@pytest.mark.parametrize("value", ["not-a-mac", "00:1A:2B:3C:4D", "gg:1A:2B:3C:4D:5E"])
def test_validate_mac_address_rejects_invalid_address(value: str) -> None:
    assert not validate_mac_address(value).valid


@pytest.mark.parametrize("value", [1, 80, 443, 65_535])
def test_validate_port_accepts_valid_ports(value: int) -> None:
    assert validate_port(value).valid


@pytest.mark.parametrize("value", [0, -1, 65_536, 100_000])
def test_validate_port_rejects_invalid_ports(value: int) -> None:
    assert not validate_port(value).valid


@pytest.mark.parametrize("value", ["example.com", "sub.example.co.uk"])
def test_validate_domain_accepts_valid_domains(value: str) -> None:
    assert validate_domain(value).valid


@pytest.mark.parametrize("value", ["not_a_domain", "-bad.com", ""])
def test_validate_domain_rejects_invalid_domains(value: str) -> None:
    assert not validate_domain(value).valid


@pytest.mark.parametrize("value", ["https://example.com", "http://sub.example.com/path?x=1"])
def test_validate_url_accepts_valid_urls(value: str) -> None:
    assert validate_url(value).valid


@pytest.mark.parametrize("value", ["ftp://example.com", "not-a-url", "https://"])
def test_validate_url_rejects_invalid_urls(value: str) -> None:
    assert not validate_url(value).valid


def test_validate_password_accepts_strong_password() -> None:
    assert validate_password("Str0ng!Passw0rd").valid


def test_validate_password_rejects_weak_password() -> None:
    result = validate_password("weak")
    assert not result.valid
    assert len(result.errors) > 1


@pytest.mark.parametrize("value", ["john.doe", "user_123", "a-b-c"])
def test_validate_username_accepts_valid_usernames(value: str) -> None:
    assert validate_username(value).valid


@pytest.mark.parametrize("value", ["ab", "has space", "way-too-long-username-exceeding-limit"])
def test_validate_username_rejects_invalid_usernames(value: str) -> None:
    assert not validate_username(value).valid


_RESOURCE_NAME_VALIDATORS = [
    validate_project_name,
    validate_organization_name,
    validate_asset_name,
    validate_playbook_name,
]


@pytest.mark.parametrize("validator", _RESOURCE_NAME_VALIDATORS)
def test_resource_name_validators_accept_reasonable_names(validator) -> None:  # type: ignore[no-untyped-def]
    assert validator("My Resource-01").valid


@pytest.mark.parametrize("validator", _RESOURCE_NAME_VALIDATORS)
def test_resource_name_validators_reject_names_starting_with_symbol(validator) -> None:  # type: ignore[no-untyped-def]
    assert not validator("-bad-start").valid
