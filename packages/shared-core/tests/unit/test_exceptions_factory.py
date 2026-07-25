"""Tests for the error-code-driven exception factory."""

from __future__ import annotations

from shared_core.exceptions import (
    NotFoundError,
    UnknownError,
    ValidationError,
    create_exception,
    get_exception_class,
)


def test_get_exception_class_returns_the_registered_class() -> None:
    assert get_exception_class("AIIOS-VAL-0001") is ValidationError
    assert get_exception_class("AIIOS-NF-0001") is NotFoundError


def test_get_exception_class_falls_back_to_unknown_error() -> None:
    assert get_exception_class("AIIOS-NOT-A-REAL-CODE-9999") is UnknownError


def test_create_exception_builds_an_instance_of_the_right_class() -> None:
    exc = create_exception("AIIOS-VAL-0001", "field is required")

    assert isinstance(exc, ValidationError)
    assert exc.message == "field is required"


def test_create_exception_passes_through_keyword_arguments() -> None:
    exc = create_exception(
        "AIIOS-NF-0001",
        "widget missing",
        details=["id=42"],
        user_message="Widget not found.",
        request_id="req-1",
    )

    assert isinstance(exc, NotFoundError)
    assert exc.details == ["id=42"]
    assert exc.user_message == "Widget not found."
    assert exc.request_id == "req-1"


def test_create_exception_for_unrecognized_code_builds_unknown_error() -> None:
    exc = create_exception("AIIOS-NOT-A-REAL-CODE-9999", "something odd")

    assert isinstance(exc, UnknownError)
    assert exc.message == "something odd"
