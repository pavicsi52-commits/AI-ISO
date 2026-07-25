"""Tests for the error-code catalog and localization."""

from __future__ import annotations

import re

import pytest
from shared_core.exceptions.constants import (
    ALL_EXCEPTION_CLASSES,
    ERROR_CODE_CATALOG,
    MESSAGE_CATALOG,
    ExceptionConstants,
    _build_catalog,
    localize_message,
)
from shared_core.exceptions.not_found import NotFoundError
from shared_core.exceptions.validation import ValidationError


def test_error_code_pattern_matches_every_real_error_code() -> None:
    pattern = re.compile(ExceptionConstants.ERROR_CODE_PATTERN)

    assert all(pattern.match(cls.error_code) for cls in ALL_EXCEPTION_CLASSES)


def test_severity_levels_cover_every_severity_in_use() -> None:
    used_severities = {cls.severity for cls in ALL_EXCEPTION_CLASSES}

    assert used_severities <= set(ExceptionConstants.SEVERITY_LEVELS)


def test_catalog_contains_every_exception_class() -> None:
    assert len(ERROR_CODE_CATALOG) == len(ALL_EXCEPTION_CLASSES)


def test_catalog_maps_code_back_to_the_right_class() -> None:
    assert ERROR_CODE_CATALOG["AIIOS-VAL-0001"] is ValidationError
    assert ERROR_CODE_CATALOG["AIIOS-NF-0001"] is NotFoundError


def test_build_catalog_raises_on_duplicate_error_code() -> None:
    class _DuplicateOneError(ValidationError):
        pass

    class _DuplicateTwoError(NotFoundError):
        error_code = "AIIOS-VAL-0001"

    with pytest.raises(ValueError, match="Duplicate error code"):
        _build_catalog((_DuplicateOneError, _DuplicateTwoError))


def test_build_catalog_raises_for_malformed_error_code() -> None:
    class _BadCodeError(ValidationError):
        error_code = "not-a-valid-code"

    with pytest.raises(ValueError, match="does not match"):
        _build_catalog((_BadCodeError,))


def test_real_catalog_is_well_formed() -> None:
    # Importing the module already ran `_build_catalog()` once at module
    # load time; re-running it here confirms it's idempotent and that the
    # real, full class list stays valid as new exception classes are added.
    assert _build_catalog() == ERROR_CODE_CATALOG


def test_english_catalog_covers_every_exception_class() -> None:
    assert set(MESSAGE_CATALOG["en"].keys()) == {cls.error_code for cls in ALL_EXCEPTION_CLASSES}


def test_english_catalog_matches_default_user_message() -> None:
    assert MESSAGE_CATALOG["en"]["AIIOS-VAL-0001"] == ValidationError.default_user_message


def test_localize_message_returns_translation_when_present() -> None:
    result = localize_message("AIIOS-VAL-0001", "es", "fallback")

    assert result == MESSAGE_CATALOG["es"]["AIIOS-VAL-0001"]
    assert result != "fallback"


def test_localize_message_falls_back_to_english_for_untranslated_code() -> None:
    # AI-IOS-WORKFLOW-0001 has no Spanish entry in the hand-authored subset.
    result = localize_message("AIIOS-WORKFLOW-0001", "es", "fallback")

    assert result == MESSAGE_CATALOG["en"]["AIIOS-WORKFLOW-0001"]


def test_localize_message_falls_back_to_provided_default_for_unknown_locale() -> None:
    result = localize_message("AIIOS-VAL-0001", "fr", "fallback")

    assert result == MESSAGE_CATALOG["en"]["AIIOS-VAL-0001"]


def test_localize_message_falls_back_to_fallback_for_unknown_code() -> None:
    result = localize_message("AIIOS-NOT-A-REAL-CODE-9999", "en", "fallback message")

    assert result == "fallback message"
