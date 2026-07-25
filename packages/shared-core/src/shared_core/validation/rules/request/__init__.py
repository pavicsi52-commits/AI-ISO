"""Request validation rules (docs/016 "REQUEST VALIDATION").

Headers, query parameters, body, path parameters, cookies, files,
multipart, and JSON -- framework-agnostic (plain dicts/primitives in,
:class:`~shared_core.validation.results.ValidationResult` out) so they
work the same whether the caller is FastAPI middleware, a background
worker consuming an inbound message, or a test.
"""

from __future__ import annotations

import json
import re
from collections.abc import Mapping, Sequence

from shared_core.validation.results import ValidationResult


def validate_headers(
    headers: Mapping[str, str], *, required: Sequence[str] = ()
) -> ValidationResult:
    """Validate that every header in *required* is present (case-insensitive)."""
    present = {name.lower() for name in headers}
    missing = [name for name in required if name.lower() not in present]
    if missing:
        return ValidationResult.fail(f"Missing required header(s): {', '.join(missing)}.")
    return ValidationResult.ok()


def validate_query_params(
    params: Mapping[str, str],
    *,
    required: Sequence[str] = (),
    allowed: Sequence[str] | None = None,
) -> ValidationResult:
    """Validate required query parameters are present and, if *allowed* is
    given, that no unrecognized parameter was sent.
    """
    errors: list[str] = []
    missing = [name for name in required if name not in params]
    if missing:
        errors.append(f"Missing required query parameter(s): {', '.join(missing)}.")
    if allowed is not None:
        unexpected = [name for name in params if name not in allowed]
        if unexpected:
            errors.append(f"Unrecognized query parameter(s): {', '.join(unexpected)}.")
    if errors:
        return ValidationResult.fail(*errors)
    return ValidationResult.ok()


def validate_body_size(content_length: int | None, *, max_bytes: int) -> ValidationResult:
    """Validate a request body doesn't exceed *max_bytes*."""
    if content_length is None:
        return ValidationResult.ok(warnings=["No Content-Length header; size was not checked."])
    if content_length > max_bytes:
        return ValidationResult.fail(
            f"Request body of {content_length} bytes exceeds the {max_bytes}-byte limit."
        )
    return ValidationResult.ok()


def validate_path_params(
    params: Mapping[str, str], *, patterns: Mapping[str, str] | None = None
) -> ValidationResult:
    """Validate each named path parameter matches its regex pattern, if given."""
    errors: list[str] = []
    for name, pattern in (patterns or {}).items():
        value = params.get(name)
        if value is not None and not re.fullmatch(pattern, value):
            errors.append(f"Path parameter '{name}' does not match the expected format.")
    if errors:
        return ValidationResult.fail(*errors)
    return ValidationResult.ok()


def validate_cookies(
    cookies: Mapping[str, str], *, required: Sequence[str] = ()
) -> ValidationResult:
    """Validate that every cookie in *required* is present."""
    missing = [name for name in required if name not in cookies]
    if missing:
        return ValidationResult.fail(f"Missing required cookie(s): {', '.join(missing)}.")
    return ValidationResult.ok()


def validate_file_upload(
    filename: str,
    size_bytes: int,
    *,
    allowed_extensions: Sequence[str] = (),
    max_bytes: int,
) -> ValidationResult:
    """Validate an uploaded file's extension and size."""
    errors: list[str] = []
    if allowed_extensions:
        extension = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
        normalized_allowed = {ext.lower().lstrip(".") for ext in allowed_extensions}
        if extension not in normalized_allowed:
            errors.append(
                f"File extension '.{extension}' is not allowed. "
                f"Allowed: {', '.join(sorted(normalized_allowed))}."
            )
    if size_bytes > max_bytes:
        errors.append(f"File size {size_bytes} bytes exceeds the {max_bytes}-byte limit.")
    if errors:
        return ValidationResult.fail(*errors)
    return ValidationResult.ok()


def validate_multipart_content_type(content_type: str | None) -> ValidationResult:
    """Validate a request declares a ``multipart/form-data`` content type."""
    if not content_type or not content_type.startswith("multipart/form-data"):
        return ValidationResult.fail("Content-Type must be 'multipart/form-data'.")
    return ValidationResult.ok()


def validate_json_body(raw: str | bytes, *, max_depth: int = 32) -> ValidationResult:
    """Validate *raw* is well-formed JSON not exceeding *max_depth* nesting
    (guards against pathologically nested payloads).
    """
    try:
        parsed = json.loads(raw)
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        return ValidationResult.fail(f"Request body is not valid JSON: {exc}")

    if _json_depth(parsed) > max_depth:
        return ValidationResult.fail(f"JSON body exceeds the maximum nesting depth of {max_depth}.")
    return ValidationResult.ok()


def _json_depth(value: object, current: int = 1) -> int:
    if isinstance(value, dict) and value:
        return max(_json_depth(v, current + 1) for v in value.values())
    if isinstance(value, list) and value:
        return max(_json_depth(v, current + 1) for v in value)
    return current
