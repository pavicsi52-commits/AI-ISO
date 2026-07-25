"""Structural tests for the centralized constants module.

These classes hold no logic, so tests verify the properties that actually
matter: every constant is the declared type, positive numeric constants are
positive, and nothing is an empty string/collection.
"""

from __future__ import annotations

import inspect

from shared_core import constants
from shared_core.constants import (
    AIConstants,
    AuthConstants,
    AutomationConstants,
    DatabaseConstants,
    DockerConstants,
    HttpConstants,
    InventoryConstants,
    KubernetesConstants,
    LoggingConstants,
    MonitoringConstants,
    Neo4jConstants,
    RabbitMQConstants,
    RedisConstants,
    ValidationConstants,
)

ALL_CONSTANT_CLASSES = [
    AIConstants,
    AuthConstants,
    AutomationConstants,
    DatabaseConstants,
    DockerConstants,
    HttpConstants,
    InventoryConstants,
    KubernetesConstants,
    LoggingConstants,
    MonitoringConstants,
    Neo4jConstants,
    RabbitMQConstants,
    RedisConstants,
    ValidationConstants,
]


def _public_attrs(cls: type) -> dict[str, object]:
    return {
        name: value
        for name, value in inspect.getmembers(cls)
        if not name.startswith("_") and not inspect.isroutine(value)
    }


def test_all_constant_classes_are_exported_from_package_root() -> None:
    for cls in ALL_CONSTANT_CLASSES:
        assert getattr(constants, cls.__name__) is cls


def test_every_constant_class_has_at_least_one_attribute() -> None:
    for cls in ALL_CONSTANT_CLASSES:
        assert len(_public_attrs(cls)) > 0, f"{cls.__name__} has no constants"


def test_no_constant_is_an_empty_string_or_empty_collection() -> None:
    for cls in ALL_CONSTANT_CLASSES:
        for name, value in _public_attrs(cls).items():
            if isinstance(value, (str, frozenset, tuple, list)):
                assert len(value) > 0, f"{cls.__name__}.{name} is empty"


def test_numeric_constants_are_non_negative() -> None:
    # DEFAULT_DB=0 (Redis) is a legitimate zero-valued index, not a bug.
    for cls in ALL_CONSTANT_CLASSES:
        for name, value in _public_attrs(cls).items():
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                assert value >= 0, f"{cls.__name__}.{name} should be non-negative, got {value}"


def test_http_header_constants_use_pascal_kebab_case() -> None:
    headers = [
        HttpConstants.HEADER_REQUEST_ID,
        HttpConstants.HEADER_CORRELATION_ID,
        HttpConstants.HEADER_ORGANIZATION_ID,
        HttpConstants.HEADER_PROJECT_ID,
        HttpConstants.HEADER_IDEMPOTENCY_KEY,
    ]
    for header in headers:
        assert all(part[:1].isupper() for part in header.split("-"))


def test_max_page_size_is_greater_than_default_page_size() -> None:
    assert HttpConstants.MAX_PAGE_SIZE > HttpConstants.DEFAULT_PAGE_SIZE


def test_logging_sensitive_field_names_cover_common_secrets() -> None:
    for field in ("password", "token", "secret", "api_key"):
        assert field in LoggingConstants.SENSITIVE_FIELD_NAMES
