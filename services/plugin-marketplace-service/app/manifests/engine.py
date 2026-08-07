"""Manifest validation (docs/059 "PLUGIN MANIFEST").

A genuine gap beyond ``shared_core.plugins.manifest.PluginManifest`` --
that dataclass covers ``name``/``version``/``description``/``author``/
``plugin_type``/``permissions``/``dependencies``/``signature``, but not
Publisher (only a bare ``author``/``vendor`` string), split
Category+Type, structured multi-platform Supported-Platform-Versions
(only one ``compatibility: str`` specifier), plural Entry Points (only
singular ``entry_point``), API Requirements, Health Checks, or Checksum
(only an RSA-PSS ``signature``). This module validates docs/059's own
richer, literal manifest shape directly against the raw submitted dict
rather than aliasing the framework's.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from app.models.enums import PluginCategory, PluginType

_REQUIRED_STRING_FIELDS = ("name", "publisher", "category", "type", "version")
_REQUIRED_LIST_FIELDS = (
    "entry_points",
    "supported_platform_versions",
    "permissions_required",
    "dependencies",
    "api_requirements",
    "health_checks",
)


@dataclass(frozen=True, slots=True)
class ManifestValidationResult:
    """The outcome of validating one submitted manifest."""

    valid: bool
    errors: tuple[str, ...] = ()
    checksum: str = ""


def compute_manifest_checksum(manifest: Mapping[str, Any]) -> str:
    """SHA-256 hex digest of *manifest*'s own canonical (sorted-key,
    compact) JSON, excluding the ``checksum`` field itself -- the same
    "hash of everything but the signature/checksum field" shape
    ``shared_core.plugins.manifest.sign_manifest`` already uses for its
    own RSA-PSS signing.
    """
    canonical = {key: value for key, value in manifest.items() if key != "checksum"}
    payload = json.dumps(canonical, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _validate_required_fields(manifest: Mapping[str, Any]) -> list[str]:
    errors: list[str] = []
    for field_name in _REQUIRED_STRING_FIELDS:
        value = manifest.get(field_name)
        if not isinstance(value, str) or not value.strip():
            errors.append(f"Missing or empty required field {field_name!r}.")
    for field_name in _REQUIRED_LIST_FIELDS:
        value = manifest.get(field_name, [])
        if not isinstance(value, list):
            errors.append(f"Field {field_name!r} must be a list.")
    return errors


def _validate_category_and_type(manifest: Mapping[str, Any]) -> list[str]:
    errors: list[str] = []
    category = manifest.get("category")
    if isinstance(category, str) and category not in set(PluginCategory):
        errors.append(f"Unknown category {category!r}.")
    plugin_type = manifest.get("type")
    if isinstance(plugin_type, str) and plugin_type not in set(PluginType):
        errors.append(f"Unknown type {plugin_type!r}.")
    return errors


def _validate_entry_points(manifest: Mapping[str, Any]) -> list[str]:
    entry_points = manifest.get("entry_points", [])
    if isinstance(entry_points, list) and not entry_points:
        return ["'entry_points' must declare at least one entry point."]
    return []


def _validate_platform_versions(manifest: Mapping[str, Any]) -> list[str]:
    platform_versions = manifest.get("supported_platform_versions", [])
    if not isinstance(platform_versions, list):
        return []
    if not platform_versions:
        return ["'supported_platform_versions' must declare at least one supported platform."]
    errors: list[str] = []
    for index, entry in enumerate(platform_versions):
        platform = entry.get("platform") if isinstance(entry, dict) else None
        constraint = entry.get("version_constraint") if isinstance(entry, dict) else None
        if not isinstance(platform, str) or not platform:
            errors.append(f"'supported_platform_versions[{index}].platform' is required.")
        if not isinstance(constraint, str) or not constraint:
            errors.append(f"'supported_platform_versions[{index}].version_constraint' is required.")
    return errors


def _validate_permissions_required(manifest: Mapping[str, Any]) -> list[str]:
    permissions_required = manifest.get("permissions_required")
    if not isinstance(permissions_required, list):
        return []
    return [
        f"'permissions_required[{index}]' must be a non-empty string."
        for index, entry in enumerate(permissions_required)
        if not isinstance(entry, str) or not entry
    ]


def _validate_dependencies(manifest: Mapping[str, Any]) -> list[str]:
    dependencies = manifest.get("dependencies")
    if not isinstance(dependencies, list):
        return []
    return [
        f"'dependencies[{index}]' must be an object with a 'plugin_slug'."
        for index, entry in enumerate(dependencies)
        if not isinstance(entry, dict) or not entry.get("plugin_slug")
    ]


def _validate_checksum(manifest: Mapping[str, Any], *, computed_checksum: str) -> list[str]:
    declared_checksum = manifest.get("checksum")
    if declared_checksum is None:
        return []
    if not isinstance(declared_checksum, str) or declared_checksum != computed_checksum:
        return ["Declared checksum does not match the computed content checksum."]
    return []


def validate_manifest(manifest: Mapping[str, Any]) -> ManifestValidationResult:
    """Validate a submitted plugin manifest against docs/059's own
    "PLUGIN MANIFEST" field list.

    Every check accumulates into ``errors`` rather than short-circuiting,
    so a submitter sees every problem at once instead of fixing them one
    at a time across repeated submissions.
    """
    computed_checksum = compute_manifest_checksum(manifest)
    errors = [
        *_validate_required_fields(manifest),
        *_validate_category_and_type(manifest),
        *_validate_entry_points(manifest),
        *_validate_platform_versions(manifest),
        *_validate_permissions_required(manifest),
        *_validate_dependencies(manifest),
        *_validate_checksum(manifest, computed_checksum=computed_checksum),
    ]
    return ManifestValidationResult(
        valid=not errors, errors=tuple(errors), checksum=computed_checksum
    )


__all__ = ["ManifestValidationResult", "compute_manifest_checksum", "validate_manifest"]
