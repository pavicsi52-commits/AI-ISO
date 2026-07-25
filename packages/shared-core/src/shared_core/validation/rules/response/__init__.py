"""Response validation rules (docs/016 "RESPONSE VALIDATION").

"Every response shall comply with Prompt 006. No invalid response leaves
the API." -- this validates a response payload against the standard
success/error envelope shape from docs/006_API_Design_Master.md.txt
before it's returned to a client.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from shared_core.validation.results import ValidationResult


def _check_envelope_basics(payload: Mapping[str, Any]) -> list[str]:
    errors: list[str] = []
    if not isinstance(payload.get("success"), bool):
        errors.append("Response must have a boolean 'success' field.")
    if not isinstance(payload.get("message"), str) or not payload.get("message"):
        errors.append("Response must have a non-empty string 'message' field.")
    return errors


def _check_meta(payload: Mapping[str, Any]) -> list[str]:
    meta = payload.get("meta")
    if not isinstance(meta, Mapping):
        return ["Response must have a 'meta' object."]
    errors: list[str] = []
    if not meta.get("request_id"):
        errors.append("Response 'meta' must include a non-empty 'request_id'.")
    if "timestamp" not in meta:
        errors.append("Response 'meta' must include a 'timestamp'.")
    return errors


def _check_success_or_error_shape(payload: Mapping[str, Any]) -> list[str]:
    if payload.get("success") is True:
        return [] if "data" in payload else ["A success response must include a 'data' field."]
    if payload.get("success") is False:
        return _check_error_object(payload.get("error"))
    return []


def _check_error_object(error: object) -> list[str]:
    if not isinstance(error, Mapping):
        return ["An error response must include an 'error' object."]
    errors: list[str] = []
    if not error.get("code"):
        errors.append("Response 'error' must include a non-empty 'code'.")
    if not isinstance(error.get("details"), list):
        errors.append("Response 'error' must include a 'details' list.")
    return errors


def validate_response_envelope(payload: Mapping[str, Any]) -> ValidationResult:
    """Validate *payload* follows the standard success/error envelope.

    Success shape: ``{success: true, message, data, meta: {request_id, timestamp}}``.
    Error shape: ``{success: false, message, error: {code, details}, meta: {...}}``.
    """
    errors = [
        *_check_envelope_basics(payload),
        *_check_meta(payload),
        *_check_success_or_error_shape(payload),
    ]
    if errors:
        return ValidationResult.fail(*errors)
    return ValidationResult.ok()
