"""Tests for ``app.manifests.engine``: ``validate_manifest`` and
``compute_manifest_checksum`` against docs/059's own "PLUGIN MANIFEST"
field list.

No infrastructure needed -- these are pure functions over plain dicts.
"""

from __future__ import annotations

from typing import Any

import pytest

from app.manifests.engine import compute_manifest_checksum, validate_manifest
from app.models.enums import PluginCategory, PluginType


def _valid_manifest(**overrides: Any) -> dict[str, Any]:
    """A manifest with every required and optional field correctly populated."""
    manifest: dict[str, Any] = {
        "name": "Inventory Sync",
        "publisher": "acme-plugins",
        "category": PluginCategory.INVENTORY.value,
        "type": PluginType.CUSTOM_PLUGIN.value,
        "version": "1.2.3",
        "entry_points": ["main:run"],
        "supported_platform_versions": [
            {"platform": "aiios", "version_constraint": ">=1.0.0,<2.0.0"}
        ],
        "permissions_required": ["inventory"],
        "dependencies": [{"plugin_slug": "core-utils", "version_constraint": ">=1.0.0"}],
        "api_requirements": ["inventory.v1"],
        "health_checks": ["/healthz"],
    }
    manifest.update(overrides)
    return manifest


def _checksummed(manifest: dict[str, Any]) -> dict[str, Any]:
    """A copy of *manifest* with a correctly computed ``checksum`` set."""
    manifest = dict(manifest)
    manifest["checksum"] = compute_manifest_checksum(manifest)
    return manifest


_REQUIRED_STRING_FIELDS = ("name", "publisher", "category", "type", "version")


# ---- valid manifests --------------------------------------------------------


def test_fully_valid_manifest_passes() -> None:
    manifest = _checksummed(_valid_manifest())
    result = validate_manifest(manifest)
    assert result.valid is True
    assert result.errors == ()
    assert result.checksum == manifest["checksum"]


def test_valid_manifest_without_checksum_key_passes() -> None:
    """Omitting ``checksum`` entirely is allowed -- no error, and the
    result still reports the computed checksum for the caller to persist.
    """
    manifest = _valid_manifest()
    assert "checksum" not in manifest
    result = validate_manifest(manifest)
    assert result.valid is True
    assert result.errors == ()
    assert result.checksum == compute_manifest_checksum(manifest)


def test_optional_list_fields_may_be_omitted_entirely() -> None:
    """``permissions_required``/``dependencies``/``api_requirements``/
    ``health_checks`` default to ``[]`` when absent -- their absence is
    not itself an error, unlike ``entry_points``/``supported_platform_versions``.
    """
    manifest = _valid_manifest()
    for optional_field in ("permissions_required", "dependencies", "api_requirements", "health_checks"):
        del manifest[optional_field]
    result = validate_manifest(manifest)
    assert result.valid is True
    assert result.errors == ()


# ---- missing / empty required string fields ---------------------------------


@pytest.mark.parametrize("field_name", _REQUIRED_STRING_FIELDS)
def test_missing_required_string_field_is_reported(field_name: str) -> None:
    manifest = _valid_manifest()
    del manifest[field_name]
    result = validate_manifest(manifest)
    assert result.valid is False
    assert any(field_name in error for error in result.errors)


@pytest.mark.parametrize("field_name", _REQUIRED_STRING_FIELDS)
def test_empty_required_string_field_is_reported(field_name: str) -> None:
    manifest = _valid_manifest(**{field_name: ""})
    result = validate_manifest(manifest)
    assert result.valid is False
    assert any(field_name in error for error in result.errors)


@pytest.mark.parametrize("field_name", _REQUIRED_STRING_FIELDS)
def test_non_string_required_field_is_reported(field_name: str) -> None:
    manifest = _valid_manifest(**{field_name: 12345})
    result = validate_manifest(manifest)
    assert result.valid is False
    assert any(field_name in error for error in result.errors)


def test_multiple_missing_fields_all_accumulate_rather_than_short_circuit() -> None:
    manifest = _valid_manifest()
    del manifest["name"]
    del manifest["publisher"]
    del manifest["version"]
    result = validate_manifest(manifest)
    assert result.valid is False
    assert len(result.errors) >= 3
    assert any("name" in error for error in result.errors)
    assert any("publisher" in error for error in result.errors)
    assert any("version" in error for error in result.errors)


# ---- category / type ---------------------------------------------------------


def test_unknown_category_is_reported() -> None:
    manifest = _valid_manifest(category="not-a-real-category")
    result = validate_manifest(manifest)
    assert result.valid is False
    assert any("category" in error.lower() for error in result.errors)


def test_unknown_type_is_reported() -> None:
    manifest = _valid_manifest(type="not-a-real-type")
    result = validate_manifest(manifest)
    assert result.valid is False
    assert any("type" in error.lower() for error in result.errors)


def test_every_known_category_and_type_pair_validates() -> None:
    """Every declared enum value is accepted, not just the one this
    module's own ``_valid_manifest`` happens to default to.
    """
    for category in PluginCategory:
        for plugin_type in (PluginType.CUSTOM_PLUGIN, PluginType.WIDGET):
            manifest = _valid_manifest(category=category.value, type=plugin_type.value)
            result = validate_manifest(manifest)
            assert result.valid is True, result.errors


# ---- entry_points --------------------------------------------------------------


def test_missing_entry_points_key_is_reported() -> None:
    manifest = _valid_manifest()
    del manifest["entry_points"]
    result = validate_manifest(manifest)
    assert result.valid is False
    assert any("entry_points" in error for error in result.errors)


def test_empty_entry_points_list_is_reported() -> None:
    manifest = _valid_manifest(entry_points=[])
    result = validate_manifest(manifest)
    assert result.valid is False
    assert any("entry_points" in error for error in result.errors)


def test_entry_points_not_a_list_is_reported() -> None:
    manifest = _valid_manifest(entry_points="main:run")
    result = validate_manifest(manifest)
    assert result.valid is False
    assert any("entry_points" in error and "list" in error for error in result.errors)


def test_multiple_entry_points_is_valid() -> None:
    manifest = _checksummed(_valid_manifest(entry_points=["main:run", "worker:start", "cli:main"]))
    result = validate_manifest(manifest)
    assert result.valid is True


# ---- supported_platform_versions ------------------------------------------------


def test_missing_supported_platform_versions_key_is_reported() -> None:
    manifest = _valid_manifest()
    del manifest["supported_platform_versions"]
    result = validate_manifest(manifest)
    assert result.valid is False
    assert any("supported_platform_versions" in error for error in result.errors)


def test_empty_supported_platform_versions_is_reported() -> None:
    manifest = _valid_manifest(supported_platform_versions=[])
    result = validate_manifest(manifest)
    assert result.valid is False
    assert any("supported_platform_versions" in error for error in result.errors)


def test_supported_platform_versions_entry_missing_platform_is_reported() -> None:
    manifest = _valid_manifest(
        supported_platform_versions=[{"version_constraint": ">=1.0.0"}]
    )
    result = validate_manifest(manifest)
    assert result.valid is False
    assert any(
        "supported_platform_versions[0].platform" in error for error in result.errors
    )


def test_supported_platform_versions_entry_missing_version_constraint_is_reported() -> None:
    manifest = _valid_manifest(supported_platform_versions=[{"platform": "aiios"}])
    result = validate_manifest(manifest)
    assert result.valid is False
    assert any(
        "supported_platform_versions[0].version_constraint" in error for error in result.errors
    )


def test_supported_platform_versions_entry_not_a_dict_is_reported() -> None:
    manifest = _valid_manifest(supported_platform_versions=["aiios>=1.0.0"])
    result = validate_manifest(manifest)
    assert result.valid is False
    assert any(
        "supported_platform_versions[0].platform" in error for error in result.errors
    )
    assert any(
        "supported_platform_versions[0].version_constraint" in error for error in result.errors
    )


def test_supported_platform_versions_multiple_entries_index_each_error() -> None:
    manifest = _valid_manifest(
        supported_platform_versions=[
            {"platform": "aiios", "version_constraint": ">=1.0.0"},
            {"platform": "", "version_constraint": ">=2.0.0"},
        ]
    )
    result = validate_manifest(manifest)
    assert result.valid is False
    assert any("supported_platform_versions[1].platform" in error for error in result.errors)
    assert not any("supported_platform_versions[0]" in error for error in result.errors)


# ---- permissions_required -------------------------------------------------------


@pytest.mark.parametrize("bad_entry", ["", 42, None, {}])
def test_permissions_required_malformed_entry_is_reported(bad_entry: Any) -> None:
    manifest = _valid_manifest(permissions_required=["inventory", bad_entry])
    result = validate_manifest(manifest)
    assert result.valid is False
    assert any("permissions_required[1]" in error for error in result.errors)


def test_permissions_required_all_valid_strings_passes() -> None:
    manifest = _checksummed(
        _valid_manifest(permissions_required=["inventory", "automation", "network"])
    )
    result = validate_manifest(manifest)
    assert result.valid is True


# ---- dependencies ---------------------------------------------------------------


def test_dependencies_entry_missing_plugin_slug_is_reported() -> None:
    manifest = _valid_manifest(dependencies=[{"version_constraint": ">=1.0.0"}])
    result = validate_manifest(manifest)
    assert result.valid is False
    assert any("dependencies[0]" in error for error in result.errors)


def test_dependencies_entry_not_a_dict_is_reported() -> None:
    manifest = _valid_manifest(dependencies=["core-utils"])
    result = validate_manifest(manifest)
    assert result.valid is False
    assert any("dependencies[0]" in error for error in result.errors)


def test_dependencies_entry_with_empty_plugin_slug_is_reported() -> None:
    manifest = _valid_manifest(dependencies=[{"plugin_slug": ""}])
    result = validate_manifest(manifest)
    assert result.valid is False
    assert any("dependencies[0]" in error for error in result.errors)


def test_dependencies_valid_entries_pass() -> None:
    manifest = _checksummed(
        _valid_manifest(
            dependencies=[
                {"plugin_slug": "core-utils", "version_constraint": ">=1.0.0"},
                {"plugin_slug": "other-plugin"},
            ]
        )
    )
    result = validate_manifest(manifest)
    assert result.valid is True


# ---- api_requirements / health_checks list-type enforcement -------------------


def test_api_requirements_not_a_list_is_reported() -> None:
    manifest = _valid_manifest(api_requirements="inventory.v1")
    result = validate_manifest(manifest)
    assert result.valid is False
    assert any("api_requirements" in error and "list" in error for error in result.errors)


def test_health_checks_not_a_list_is_reported() -> None:
    manifest = _valid_manifest(health_checks="/healthz")
    result = validate_manifest(manifest)
    assert result.valid is False
    assert any("health_checks" in error and "list" in error for error in result.errors)


# ---- checksum -----------------------------------------------------------------


def test_tampered_checksum_fails_validation() -> None:
    manifest = _checksummed(_valid_manifest())
    manifest["checksum"] = "0" * 64
    result = validate_manifest(manifest)
    assert result.valid is False
    assert any("checksum" in error.lower() for error in result.errors)


def test_non_string_checksum_fails_validation() -> None:
    manifest = _valid_manifest(checksum=12345)
    result = validate_manifest(manifest)
    assert result.valid is False
    assert any("checksum" in error.lower() for error in result.errors)


def test_compute_manifest_checksum_excludes_checksum_key_itself() -> None:
    manifest = _valid_manifest()
    without_checksum = compute_manifest_checksum(manifest)
    manifest_with_bogus_checksum = dict(manifest, checksum="whatever-this-is-ignored")
    with_bogus_checksum = compute_manifest_checksum(manifest_with_bogus_checksum)
    assert without_checksum == with_bogus_checksum


def test_checksum_is_stable_regardless_of_dict_key_order() -> None:
    manifest = _valid_manifest()
    reordered = {key: manifest[key] for key in reversed(list(manifest.keys()))}
    assert manifest.keys() != list(reordered.keys())  # sanity: genuinely reordered
    assert compute_manifest_checksum(manifest) == compute_manifest_checksum(reordered)


def test_checksum_changes_when_content_changes() -> None:
    manifest_a = _valid_manifest(version="1.0.0")
    manifest_b = _valid_manifest(version="2.0.0")
    assert compute_manifest_checksum(manifest_a) != compute_manifest_checksum(manifest_b)


def test_checksum_is_a_deterministic_sha256_hex_digest() -> None:
    manifest = _valid_manifest()
    checksum = compute_manifest_checksum(manifest)
    assert len(checksum) == 64
    assert all(char in "0123456789abcdef" for char in checksum)
    assert compute_manifest_checksum(manifest) == checksum
