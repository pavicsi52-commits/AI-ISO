"""Tests for field-level validation rules."""

from __future__ import annotations

import pytest
from shared_core.validation.rules import field


@pytest.mark.parametrize(
    ("value", "expected_valid"),
    [
        ("10.0.0.0/8", True),
        ("192.168.1.1/32", True),
        ("2001:db8::/32", True),
        ("not-a-cidr", False),
        ("10.0.0.0/99", False),
    ],
)
def test_validate_cidr(value: str, expected_valid: bool) -> None:
    assert field.validate_cidr(value).valid is expected_valid


@pytest.mark.parametrize(
    ("value", "expected_valid"),
    [
        ("1.2.3", True),
        ("1.2.3-rc.1", True),
        ("1.2.3+build.5", True),
        ("1.2.3-alpha.1+build.5", True),
        ("1.2", False),
        ("v1.2.3", False),
        ("1.2.3.4", False),
    ],
)
def test_validate_semantic_version(value: str, expected_valid: bool) -> None:
    assert field.validate_semantic_version(value).valid is expected_valid


@pytest.mark.parametrize(
    ("value", "expected_valid"),
    [
        ("* * * * *", True),
        ("*/5 * * * *", True),
        ("0 0 1 1 *", True),
        ("0-30/5 8-18 * * 1-5", True),
        ("60 * * * *", False),  # minute out of range
        ("* * * * * *", False),  # too many fields
        ("* * *", False),  # too few fields
        ("a * * * *", False),  # not numeric
        ("*/0 * * * *", False),  # step must be positive
        ("*/a * * * *", False),  # step must be a digit
        ("a-10 * * * *", False),  # range with non-digit start
        ("50-10 * * * *", False),  # range start > end
        ("0-99 * * * *", False),  # range end out of bounds
    ],
)
def test_validate_cron_expression(value: str, expected_valid: bool) -> None:
    assert field.validate_cron_expression(value).valid is expected_valid


@pytest.mark.parametrize(
    ("value", "expected_valid"),
    [
        ("ABCDE-12345-FGHIJ-67890", True),
        ("ABCD-1234-EFGH-5678", True),
        ("not-a-license-key", False),
        ("abcde-12345-fghij-67890", False),  # lowercase not allowed
    ],
)
def test_validate_license_key(value: str, expected_valid: bool) -> None:
    assert field.validate_license_key(value).valid is expected_valid


@pytest.mark.parametrize(
    ("value", "expected_valid"),
    [
        ("+14155551234", True),
        ("14155551234", True),
        ("123", False),
        ("not-a-phone", False),
    ],
)
def test_validate_phone(value: str, expected_valid: bool) -> None:
    assert field.validate_phone(value).valid is expected_valid


@pytest.mark.parametrize(
    ("value", "expected_valid"),
    [
        ("MY_SECRET", True),
        ("my-secret-1", True),
        ("1_starts_with_digit", False),
        ("has spaces", False),
        ("", False),
    ],
)
def test_validate_secret_name(value: str, expected_valid: bool) -> None:
    assert field.validate_secret_name(value).valid is expected_valid


def test_validate_team_name_accepts_a_normal_name() -> None:
    assert field.validate_team_name("Platform Team").valid is True


def test_validate_job_name_accepts_a_normal_name() -> None:
    assert field.validate_job_name("nightly-backup").valid is True


def test_validate_workflow_name_accepts_a_normal_name() -> None:
    assert field.validate_workflow_name("deploy-pipeline").valid is True


# --- adapted legacy validators still work through the new rich result ---


def test_validate_email_adapts_legacy_result() -> None:
    result = field.validate_email("user@example.com")

    assert result.valid is True
    assert result.suggestions == []


def test_validate_email_adapts_legacy_failure() -> None:
    result = field.validate_email("not-an-email")

    assert result.valid is False
    assert result.errors


def test_validate_uuid_adapts_legacy_result() -> None:
    assert field.validate_uuid("550e8400-e29b-41d4-a716-446655440000").valid is True
    assert field.validate_uuid("not-a-uuid").valid is False


def test_validate_password_adapts_legacy_result() -> None:
    assert field.validate_password("Str0ng!Password").valid is True
    assert field.validate_password("weak").valid is False


def test_validate_hostname_ipv4_ipv6_mac_domain_url_port_username() -> None:
    assert field.validate_hostname("example.com").valid is True
    assert field.validate_ipv4("10.0.0.1").valid is True
    assert field.validate_ipv6("::1").valid is True
    assert field.validate_mac_address("00:11:22:33:44:55").valid is True
    assert field.validate_domain("example.com").valid is True
    assert field.validate_url("https://example.com").valid is True
    assert field.validate_port(8080).valid is True
    assert field.validate_username("valid_user").valid is True


def test_validate_organization_project_asset_playbook_name() -> None:
    assert field.validate_organization_name("Acme Corp").valid is True
    assert field.validate_project_name("Project X").valid is True
    assert field.validate_asset_name("web-server-01").valid is True
    assert field.validate_playbook_name("deploy.yml").valid is True
