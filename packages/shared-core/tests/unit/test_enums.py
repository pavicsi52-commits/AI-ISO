"""Structural tests for the centralized enumerations module."""

from __future__ import annotations

from enum import StrEnum

from shared_core import enums
from shared_core.enums import (
    AssetStatus,
    AuditAction,
    ExecutionStatus,
    HealthStatus,
    HttpMethod,
    JobStatus,
    NotificationChannel,
    NotificationType,
    Permission,
    Priority,
    Role,
    Severity,
    ValidationStatus,
)

ALL_ENUM_CLASSES = [
    AssetStatus,
    AuditAction,
    ExecutionStatus,
    HealthStatus,
    HttpMethod,
    JobStatus,
    NotificationChannel,
    NotificationType,
    Permission,
    Priority,
    Role,
    Severity,
    ValidationStatus,
]


def test_all_enums_are_exported_from_package_root() -> None:
    for enum_cls in ALL_ENUM_CLASSES:
        assert getattr(enums, enum_cls.__name__) is enum_cls


def test_every_enum_is_a_str_enum_with_lowercase_or_upper_http_values() -> None:
    for enum_cls in ALL_ENUM_CLASSES:
        assert issubclass(enum_cls, StrEnum)
        assert len(list(enum_cls)) > 0


def test_enum_members_have_unique_values() -> None:
    for enum_cls in ALL_ENUM_CLASSES:
        values = [member.value for member in enum_cls]
        assert len(values) == len(set(values)), f"{enum_cls.__name__} has duplicate values"


def test_http_method_covers_standard_rest_verbs() -> None:
    for verb in ("GET", "POST", "PUT", "PATCH", "DELETE"):
        assert HttpMethod(verb) == verb


def test_health_status_covers_healthy_and_unhealthy() -> None:
    assert HealthStatus.HEALTHY.value == "healthy"
    assert HealthStatus.UNHEALTHY.value == "unhealthy"


def test_role_includes_super_admin_and_viewer() -> None:
    assert Role.SUPER_ADMIN in Role
    assert Role.VIEWER in Role
