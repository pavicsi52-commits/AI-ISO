"""Tests for response envelope validation rules."""

from __future__ import annotations

from shared_core.validation.rules import response


def test_valid_success_envelope() -> None:
    payload = {
        "success": True,
        "message": "ok",
        "data": {"id": 1},
        "meta": {"request_id": "req-1", "timestamp": "2026-01-01T00:00:00Z"},
    }

    assert response.validate_response_envelope(payload).valid is True


def test_valid_error_envelope() -> None:
    payload = {
        "success": False,
        "message": "failed",
        "error": {"code": "AIIOS-VAL-0001", "details": ["bad"]},
        "meta": {"request_id": "req-1", "timestamp": "2026-01-01T00:00:00Z"},
    }

    assert response.validate_response_envelope(payload).valid is True


def test_missing_success_field() -> None:
    payload = {"message": "ok", "data": {}, "meta": {"request_id": "r", "timestamp": "t"}}

    result = response.validate_response_envelope(payload)

    assert result.valid is False
    assert any("success" in error for error in result.errors)


def test_missing_message_field() -> None:
    payload = {"success": True, "data": {}, "meta": {"request_id": "r", "timestamp": "t"}}

    result = response.validate_response_envelope(payload)

    assert any("message" in error for error in result.errors)


def test_missing_meta_object() -> None:
    payload = {"success": True, "message": "ok", "data": {}}

    result = response.validate_response_envelope(payload)

    assert any("meta" in error for error in result.errors)


def test_meta_missing_request_id() -> None:
    payload = {
        "success": True,
        "message": "ok",
        "data": {},
        "meta": {"timestamp": "t"},
    }

    result = response.validate_response_envelope(payload)

    assert any("request_id" in error for error in result.errors)


def test_meta_missing_timestamp() -> None:
    payload = {
        "success": True,
        "message": "ok",
        "data": {},
        "meta": {"request_id": "r"},
    }

    result = response.validate_response_envelope(payload)

    assert any("timestamp" in error for error in result.errors)


def test_success_response_missing_data() -> None:
    payload = {"success": True, "message": "ok", "meta": {"request_id": "r", "timestamp": "t"}}

    result = response.validate_response_envelope(payload)

    assert any("data" in error for error in result.errors)


def test_error_response_missing_error_object() -> None:
    payload = {"success": False, "message": "failed", "meta": {"request_id": "r", "timestamp": "t"}}

    result = response.validate_response_envelope(payload)

    assert any("error" in error for error in result.errors)


def test_error_response_missing_code() -> None:
    payload = {
        "success": False,
        "message": "failed",
        "error": {"details": []},
        "meta": {"request_id": "r", "timestamp": "t"},
    }

    result = response.validate_response_envelope(payload)

    assert any("code" in error for error in result.errors)


def test_error_response_details_must_be_a_list() -> None:
    payload = {
        "success": False,
        "message": "failed",
        "error": {"code": "AIIOS-VAL-0001", "details": "not-a-list"},
        "meta": {"request_id": "r", "timestamp": "t"},
    }

    result = response.validate_response_envelope(payload)

    assert any("details" in error for error in result.errors)
