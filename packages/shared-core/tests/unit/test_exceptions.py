"""Tests for the custom exception hierarchy."""

from __future__ import annotations

from uuid import uuid4

import pytest
from shared_core.exceptions import (
    ALL_EXCEPTION_CLASSES,
    AIError,
    AIIOSException,
    AIIOSTimeoutError,
    AuthenticationError,
    AuthorizationError,
    AutomationError,
    BusinessRuleError,
    CacheError,
    ConfigurationError,
    ConflictError,
    DatabaseError,
    DependencyError,
    ExternalError,
    InternalError,
    InventoryError,
    MonitoringError,
    NetworkError,
    NotFoundError,
    NotificationError,
    QueueError,
    RateLimitError,
    StorageError,
    UnknownError,
    ValidationError,
    WorkflowError,
)


@pytest.mark.parametrize("exc_cls", ALL_EXCEPTION_CLASSES)
def test_every_exception_inherits_aiios_exception(exc_cls: type[AIIOSException]) -> None:
    assert issubclass(exc_cls, AIIOSException)


@pytest.mark.parametrize("exc_cls", ALL_EXCEPTION_CLASSES)
def test_every_exception_has_a_wellformed_error_code(exc_cls: type[AIIOSException]) -> None:
    assert exc_cls.error_code.startswith("AIIOS-")
    domain, number = exc_cls.error_code.removeprefix("AIIOS-").rsplit("-", 1)
    assert domain.isupper()
    assert number.isdigit()
    assert len(number) == 4


@pytest.mark.parametrize("exc_cls", ALL_EXCEPTION_CLASSES)
def test_every_exception_has_a_valid_http_status(exc_cls: type[AIIOSException]) -> None:
    assert 400 <= exc_cls.status_code < 600


@pytest.mark.parametrize("exc_cls", ALL_EXCEPTION_CLASSES)
def test_every_exception_has_a_valid_severity(exc_cls: type[AIIOSException]) -> None:
    assert exc_cls.severity in {"low", "medium", "high", "critical"}


@pytest.mark.parametrize("exc_cls", ALL_EXCEPTION_CLASSES)
def test_every_exception_has_a_nonempty_default_user_message(
    exc_cls: type[AIIOSException],
) -> None:
    assert exc_cls.default_user_message


@pytest.mark.parametrize("exc_cls", ALL_EXCEPTION_CLASSES)
def test_every_exception_is_constructible_with_just_a_message(
    exc_cls: type[AIIOSException],
) -> None:
    exc = exc_cls("something went wrong")

    assert exc.message == "something went wrong"
    assert exc.user_message == exc_cls.default_user_message


def test_error_codes_are_unique_across_the_hierarchy() -> None:
    codes = [exc_cls.error_code for exc_cls in ALL_EXCEPTION_CLASSES]
    assert len(codes) == len(set(codes))


def test_covers_every_category_named_in_the_spec() -> None:
    # docs/015_Enterprise_Exception_Framework.md.txt "EXCEPTION CATEGORIES"
    expected_classes = {
        AuthenticationError,
        AuthorizationError,
        ValidationError,
        DatabaseError,
        ConfigurationError,
        DependencyError,
        StorageError,
        QueueError,
        CacheError,
        WorkflowError,
        AutomationError,
        InventoryError,
        MonitoringError,
        AIError,
        NotificationError,
        BusinessRuleError,
        AIIOSTimeoutError,
        ConflictError,
        NotFoundError,
        RateLimitError,
        InternalError,
        ExternalError,
        UnknownError,
    }
    assert expected_classes <= set(ALL_EXCEPTION_CLASSES)


def test_base_exception_carries_context() -> None:
    org_id = uuid4()
    project_id = uuid4()

    exc = ValidationError(
        "bad input",
        details=["field 'name' is required"],
        request_id="req-1",
        correlation_id="corr-1",
        organization_id=org_id,
        project_id=project_id,
    )

    assert exc.message == "bad input"
    assert exc.details == ["field 'name' is required"]
    assert exc.request_id == "req-1"
    assert exc.correlation_id == "corr-1"
    assert exc.organization_id == org_id
    assert exc.project_id == project_id
    assert str(exc) == "bad input"


def test_base_exception_defaults_to_empty_details_and_metadata() -> None:
    exc = NotFoundError("not found")

    assert exc.details == []
    assert exc.metadata == {}
    assert exc.request_id is None


def test_user_message_defaults_to_class_default() -> None:
    exc = NotFoundError("widget 42 missing from table widgets")

    assert exc.user_message == "The requested resource was not found."


def test_user_message_can_be_overridden_explicitly() -> None:
    exc = NotFoundError("widget 42 missing", user_message="Widget not found.")

    assert exc.user_message == "Widget not found."
    assert exc.message == "widget 42 missing"


def test_to_dict_serializes_all_fields() -> None:
    org_id = uuid4()
    exc = DatabaseError("connection lost", organization_id=org_id)

    payload = exc.to_dict()

    assert payload["error_code"] == "AIIOS-DB-0001"
    assert payload["message"] == "connection lost"
    assert payload["user_message"] == DatabaseError.default_user_message
    assert payload["status_code"] == 500
    assert payload["retryable"] is True
    assert payload["organization_id"] == str(org_id)
    assert payload["project_id"] is None
    assert "timestamp" in payload


def test_to_public_dict_never_includes_internal_message() -> None:
    exc = DatabaseError("SELECT * FROM users WHERE password_hash = 'abc' -- leaked SQL")

    public = exc.to_public_dict()

    assert "message" not in public
    assert "metadata" not in public
    assert public["error_code"] == "AIIOS-DB-0001"
    assert public["user_message"] == DatabaseError.default_user_message
    assert "leaked SQL" not in str(public)


def test_to_public_dict_includes_details() -> None:
    exc = ValidationError("bad input", details=["name is required"])

    public = exc.to_public_dict()

    assert public["details"] == ["name is required"]


def test_retryable_exceptions_are_flagged_correctly() -> None:
    assert DatabaseError("x").retryable is True
    assert DependencyError("x").retryable is True
    assert RateLimitError("x").retryable is True
    assert AIIOSTimeoutError("x").retryable is True
    assert CacheError("x").retryable is True
    assert QueueError("x").retryable is True
    assert StorageError("x").retryable is True
    assert NetworkError("x").retryable is True
    assert NotificationError("x").retryable is True
    assert ExternalError("x").retryable is True


def test_non_retryable_exceptions_are_flagged_correctly() -> None:
    # docs/015 "RETRY POLICY": Validation, Authentication, Authorization,
    # Business Rule, Conflict are explicitly not retryable.
    assert ValidationError("x").retryable is False
    assert AuthenticationError("x").retryable is False
    assert AuthorizationError("x").retryable is False
    assert BusinessRuleError("x").retryable is False
    assert ConflictError("x").retryable is False
