"""Tests for request validation rules."""

from __future__ import annotations

from shared_core.validation.rules import request


def test_validate_headers_passes_when_all_required_present() -> None:
    result = request.validate_headers(
        {"X-Request-ID": "1", "Content-Type": "application/json"}, required=["x-request-id"]
    )

    assert result.valid is True


def test_validate_headers_fails_when_missing() -> None:
    result = request.validate_headers({}, required=["X-Request-ID"])

    assert result.valid is False
    assert "X-Request-ID" in result.errors[0]


def test_validate_query_params_required() -> None:
    result = request.validate_query_params({"page": "1"}, required=["page", "size"])

    assert result.valid is False
    assert "size" in result.errors[0]


def test_validate_query_params_allowed_rejects_unexpected() -> None:
    result = request.validate_query_params({"page": "1", "hack": "1"}, allowed=["page"])

    assert result.valid is False
    assert "hack" in result.errors[0]


def test_validate_query_params_passes() -> None:
    result = request.validate_query_params(
        {"page": "1"}, required=["page"], allowed=["page", "size"]
    )

    assert result.valid is True


def test_validate_body_size_passes_within_limit() -> None:
    result = request.validate_body_size(1000, max_bytes=2000)

    assert result.valid is True


def test_validate_body_size_fails_over_limit() -> None:
    result = request.validate_body_size(3000, max_bytes=2000)

    assert result.valid is False


def test_validate_body_size_warns_when_no_content_length() -> None:
    result = request.validate_body_size(None, max_bytes=2000)

    assert result.valid is True
    assert result.warnings


def test_validate_path_params_matches_pattern() -> None:
    result = request.validate_path_params({"id": "123"}, patterns={"id": r"\d+"})

    assert result.valid is True


def test_validate_path_params_rejects_mismatch() -> None:
    result = request.validate_path_params({"id": "abc"}, patterns={"id": r"\d+"})

    assert result.valid is False


def test_validate_cookies_required() -> None:
    result = request.validate_cookies({}, required=["session_id"])

    assert result.valid is False


def test_validate_cookies_passes() -> None:
    result = request.validate_cookies({"session_id": "abc"}, required=["session_id"])

    assert result.valid is True


def test_validate_file_upload_rejects_bad_extension() -> None:
    result = request.validate_file_upload(
        "malware.exe", 100, allowed_extensions=["png", "jpg"], max_bytes=1_000_000
    )

    assert result.valid is False


def test_validate_file_upload_rejects_oversized_file() -> None:
    result = request.validate_file_upload(
        "photo.png", 5_000_000, allowed_extensions=["png"], max_bytes=1_000_000
    )

    assert result.valid is False


def test_validate_file_upload_passes() -> None:
    result = request.validate_file_upload(
        "photo.png", 100, allowed_extensions=["png", "jpg"], max_bytes=1_000_000
    )

    assert result.valid is True


def test_validate_file_upload_skips_extension_check_when_none_configured() -> None:
    result = request.validate_file_upload("anything.bin", 100, max_bytes=1_000_000)

    assert result.valid is True


def test_validate_multipart_content_type_passes() -> None:
    result = request.validate_multipart_content_type("multipart/form-data; boundary=xyz")

    assert result.valid is True


def test_validate_multipart_content_type_fails_for_json() -> None:
    result = request.validate_multipart_content_type("application/json")

    assert result.valid is False


def test_validate_multipart_content_type_fails_for_none() -> None:
    result = request.validate_multipart_content_type(None)

    assert result.valid is False


def test_validate_json_body_passes_for_valid_json() -> None:
    result = request.validate_json_body('{"a": 1}')

    assert result.valid is True


def test_validate_json_body_fails_for_malformed_json() -> None:
    result = request.validate_json_body("{not json")

    assert result.valid is False


def test_validate_json_body_fails_for_excessive_nesting() -> None:
    nested = "1"
    for _ in range(40):
        nested = f"[{nested}]"

    result = request.validate_json_body(nested, max_depth=32)

    assert result.valid is False


def test_validate_json_body_passes_for_shallow_nesting() -> None:
    result = request.validate_json_body('{"a": {"b": {"c": 1}}}', max_depth=32)

    assert result.valid is True
