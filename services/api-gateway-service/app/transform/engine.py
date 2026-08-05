"""Request/response transformation.

Genuinely new logic -- `shared_core` has no request/response
transformation primitive to wrap (confirmed during this prompt's own
research phase). Every transformation is a pure function of its own
``config`` dict (read from :attr:`~app.models.transformation
.ApiTransformationRule.config`) and the headers/path/body it applies to.
"""

from __future__ import annotations

import re
from typing import Any


def apply_header_transform(headers: dict[str, str], config: dict[str, Any]) -> dict[str, str]:
    """Add/remove headers per *config* (``{"add": {...}, "remove": [...]}``, case-insensitive removal)."""
    result = dict(headers)
    for name in config.get("remove", []):
        for key in [k for k in result if k.lower() == str(name).lower()]:
            result.pop(key, None)
    for name, value in config.get("add", {}).items():
        result[str(name)] = str(value)
    return result


def apply_url_rewrite(path: str, config: dict[str, Any]) -> str:
    """Rewrite *path* via a regex ``pattern``/``replacement`` pair in *config*."""
    pattern = config.get("pattern")
    replacement = config.get("replacement")
    if not pattern or replacement is None:
        return path
    return re.sub(pattern, replacement, path)


def inject_metadata_headers(
    headers: dict[str, str], *, correlation_id: str, request_id: str
) -> dict[str, str]:
    """Inject platform-standard correlation/request-id headers ("Metadata Injection", "Correlation IDs")."""
    result = dict(headers)
    result.setdefault("X-Correlation-ID", correlation_id)
    result.setdefault("X-Request-ID", request_id)
    return result


def normalize_error_body(*, status_code: int, detail: str, request_id: str) -> dict[str, Any]:
    """A uniform error body shape for any upstream failure ("Error Normalization")."""
    return {
        "success": False,
        "error": {"status_code": status_code, "message": detail},
        "request_id": request_id,
    }


def apply_body_transform(body: dict[str, Any], config: dict[str, Any]) -> dict[str, Any]:
    """Add/remove/rename top-level body fields per *config*
    (``{"add": {...}, "remove": [...], "rename": {"old": "new"}}``)."""
    result = dict(body)
    for name in config.get("remove", []):
        result.pop(name, None)
    for old_name, new_name in config.get("rename", {}).items():
        if old_name in result:
            result[new_name] = result.pop(old_name)
    for name, value in config.get("add", {}).items():
        result[name] = value
    return result


__all__ = [
    "apply_body_transform",
    "apply_header_transform",
    "apply_url_rewrite",
    "inject_metadata_headers",
    "normalize_error_body",
]
