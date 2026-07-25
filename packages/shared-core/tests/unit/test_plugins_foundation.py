"""Tests for constants.py, exceptions.py, metadata.py, permissions.py,
dependency.py, versioning.py, resolver.py, and manifest.py.
"""

from __future__ import annotations

import pytest
from shared_core.plugins import exceptions as plugin_exceptions
from shared_core.plugins.dependency import PluginDependency
from shared_core.plugins.exceptions import (
    CircularDependencyError,
    DependencyResolutionError,
    InvalidManifestError,
    PermissionDeniedError,
    SignatureVerificationError,
    VersionIncompatibleError,
)
from shared_core.plugins.manifest import (
    PluginManifest,
    manifest_to_dict,
    parse_manifest_dict,
    parse_manifest_json,
    parse_manifest_yaml,
    require_valid_signature,
    sign_manifest,
    verify_manifest_signature,
)
from shared_core.plugins.metadata import PluginMetadata, PluginType
from shared_core.plugins.permissions import PermissionRegistry, PluginPermission
from shared_core.plugins.resolver import DependencyResolver
from shared_core.plugins.versioning import (
    MigrationRegistry,
    is_compatible,
    is_downgrade,
    is_upgrade,
    parse_version,
    require_compatible,
)
from shared_core.security.encryption import generate_rsa_keypair

# --- shared helpers ---


def _metadata(plugin_id: str = "sample", version: str = "1.0.0") -> PluginMetadata:
    return PluginMetadata(
        plugin_id=plugin_id, name="Sample", version=version, category=PluginType.AUTOMATION
    )


def _manifest(
    plugin_id: str = "sample",
    version: str = "1.0.0",
    dependencies: tuple[PluginDependency, ...] = (),
) -> PluginManifest:
    return PluginManifest(
        metadata=_metadata(plugin_id, version),
        entry_point="sample.plugin:SamplePlugin",
        dependencies=dependencies,
    )


# --- exceptions.py ---


def test_every_plugin_exception_has_a_unique_error_code() -> None:
    codes = [getattr(plugin_exceptions, name).error_code for name in plugin_exceptions.__all__]

    assert len(codes) == len(set(codes))


# --- metadata.py ---


def test_plugin_metadata_defaults() -> None:
    metadata = _metadata()

    assert metadata.author is None
    assert metadata.tags == ()


# --- permissions.py ---


def test_permission_registry_grant_and_check() -> None:
    registry = PermissionRegistry()

    registry.grant("sample", frozenset({PluginPermission.NETWORK}), granted_by="admin")

    assert registry.has_permission("sample", PluginPermission.NETWORK) is True
    assert registry.has_permission("sample", PluginPermission.DATABASE) is False


def test_permission_registry_require_permission_raises_when_missing() -> None:
    registry = PermissionRegistry()

    with pytest.raises(PermissionDeniedError):
        registry.require_permission("sample", PluginPermission.FILESYSTEM)


def test_permission_registry_revoke_removes_the_grant() -> None:
    registry = PermissionRegistry()
    registry.grant("sample", frozenset({PluginPermission.NETWORK}))

    registry.revoke("sample")

    assert registry.granted_permissions("sample") == frozenset()


# --- versioning.py ---


def test_parse_version_raises_for_invalid_text() -> None:
    with pytest.raises(VersionIncompatibleError):
        parse_version("not-a-version")


@pytest.mark.parametrize(
    ("version", "constraint", "expected"),
    [
        ("1.5.0", ">=1.0.0,<2.0.0", True),
        ("2.0.0", ">=1.0.0,<2.0.0", False),
        ("1.0.0", "*", True),
        ("1.0.0", "", True),
    ],
)
def test_is_compatible(version: str, constraint: str, expected: bool) -> None:
    assert is_compatible(version, constraint) is expected


def test_is_compatible_raises_for_an_invalid_constraint() -> None:
    with pytest.raises(VersionIncompatibleError):
        is_compatible("1.0.0", "not a constraint")


def test_require_compatible_raises_when_not_satisfied() -> None:
    with pytest.raises(VersionIncompatibleError):
        require_compatible("2.0.0", ">=1.0.0,<2.0.0", subject="Framework")


def test_is_upgrade_and_is_downgrade() -> None:
    assert is_upgrade("1.0.0", "2.0.0") is True
    assert is_upgrade("2.0.0", "1.0.0") is False
    assert is_downgrade("2.0.0", "1.0.0") is True


async def test_migration_registry_runs_the_registered_hook() -> None:
    registry = MigrationRegistry()
    calls: list[tuple[str, str]] = []

    async def hook(from_version: str, to_version: str) -> None:
        calls.append((from_version, to_version))

    registry.register("1.0.0", "2.0.0", hook)

    ran = await registry.migrate("1.0.0", "2.0.0")

    assert ran is True
    assert calls == [("1.0.0", "2.0.0")]


async def test_migration_registry_migrate_returns_false_when_unregistered() -> None:
    registry = MigrationRegistry()

    ran = await registry.migrate("1.0.0", "2.0.0")

    assert ran is False


# --- resolver.py ---


def test_resolver_validate_passes_for_satisfied_required_dependency() -> None:
    manifests = {
        "base": _manifest("base", "1.0.0"),
        "app": _manifest(
            "app",
            "1.0.0",
            dependencies=(
                PluginDependency(depends_on_plugin_id="base", version_constraint=">=1.0.0"),
            ),
        ),
    }
    resolver = DependencyResolver(manifests)

    resolver.validate("app")  # doesn't raise


def test_resolver_validate_raises_for_missing_required_dependency() -> None:
    manifests = {
        "app": _manifest("app", dependencies=(PluginDependency(depends_on_plugin_id="missing"),))
    }
    resolver = DependencyResolver(manifests)

    with pytest.raises(DependencyResolutionError):
        resolver.validate("app")


def test_resolver_validate_skips_a_missing_optional_dependency() -> None:
    manifests = {
        "app": _manifest(
            "app",
            dependencies=(PluginDependency(depends_on_plugin_id="missing", optional=True),),
        )
    }
    resolver = DependencyResolver(manifests)

    resolver.validate("app")  # doesn't raise


def test_resolver_validate_raises_for_incompatible_version() -> None:
    manifests = {
        "base": _manifest("base", "0.5.0"),
        "app": _manifest(
            "app",
            dependencies=(
                PluginDependency(depends_on_plugin_id="base", version_constraint=">=1.0.0"),
            ),
        ),
    }
    resolver = DependencyResolver(manifests)

    with pytest.raises(DependencyResolutionError):
        resolver.validate("app")


def test_resolver_validate_raises_for_unregistered_plugin() -> None:
    resolver = DependencyResolver({})

    with pytest.raises(DependencyResolutionError):
        resolver.validate("missing")


def test_resolver_has_cycle_detects_a_direct_cycle() -> None:
    manifests = {
        "a": _manifest("a", dependencies=(PluginDependency(depends_on_plugin_id="b"),)),
        "b": _manifest("b", dependencies=(PluginDependency(depends_on_plugin_id="a"),)),
    }
    resolver = DependencyResolver(manifests)

    assert resolver.has_cycle() is True


def test_resolver_has_cycle_is_false_for_an_acyclic_graph() -> None:
    manifests = {
        "base": _manifest("base"),
        "app": _manifest("app", dependencies=(PluginDependency(depends_on_plugin_id="base"),)),
    }
    resolver = DependencyResolver(manifests)

    assert resolver.has_cycle() is False


def test_resolver_resolve_order_puts_dependencies_first() -> None:
    manifests = {
        "app": _manifest("app", dependencies=(PluginDependency(depends_on_plugin_id="base"),)),
        "base": _manifest("base"),
    }
    resolver = DependencyResolver(manifests)

    order = resolver.resolve_order()

    assert order.index("base") < order.index("app")


def test_resolver_resolve_order_raises_for_a_cycle() -> None:
    manifests = {
        "a": _manifest("a", dependencies=(PluginDependency(depends_on_plugin_id="b"),)),
        "b": _manifest("b", dependencies=(PluginDependency(depends_on_plugin_id="a"),)),
    }
    resolver = DependencyResolver(manifests)

    with pytest.raises(CircularDependencyError):
        resolver.resolve_order()


# --- manifest.py ---


def test_parse_manifest_dict_round_trips_through_manifest_to_dict() -> None:
    data = {
        "plugin_id": "sample",
        "name": "Sample",
        "version": "1.0.0",
        "category": "automation",
        "entry_point": "sample.plugin:SamplePlugin",
        "dependencies": [{"plugin_id": "base", "version_constraint": ">=1.0.0"}],
        "permissions": ["network"],
        "compatibility": ">=1.0.0,<2.0.0",
    }

    manifest = parse_manifest_dict(data)

    assert manifest.metadata.plugin_id == "sample"
    assert manifest.dependencies[0].depends_on_plugin_id == "base"
    assert PluginPermission.NETWORK in manifest.permissions
    assert manifest_to_dict(manifest, include_signature=False)["plugin_id"] == "sample"


def test_parse_manifest_dict_raises_for_a_missing_required_field() -> None:
    with pytest.raises(InvalidManifestError):
        parse_manifest_dict({"name": "Sample"})


def test_parse_manifest_dict_raises_for_an_invalid_category() -> None:
    with pytest.raises(InvalidManifestError):
        parse_manifest_dict(
            {
                "plugin_id": "sample",
                "name": "Sample",
                "version": "1.0.0",
                "category": "not-a-category",
                "entry_point": "sample.plugin:SamplePlugin",
            }
        )


def test_parse_manifest_json_round_trips() -> None:
    text = (
        '{"plugin_id": "sample", "name": "Sample", "version": "1.0.0", '
        '"category": "automation", "entry_point": "sample.plugin:SamplePlugin"}'
    )

    manifest = parse_manifest_json(text)

    assert manifest.metadata.plugin_id == "sample"


def test_parse_manifest_json_raises_for_invalid_json() -> None:
    with pytest.raises(InvalidManifestError):
        parse_manifest_json("{not json")


def test_parse_manifest_yaml_round_trips() -> None:
    text = """
plugin_id: sample
name: Sample
version: "1.0.0"
category: automation
entry_point: "sample.plugin:SamplePlugin"
"""

    manifest = parse_manifest_yaml(text)

    assert manifest.metadata.plugin_id == "sample"


def test_parse_manifest_yaml_raises_for_a_non_mapping_document() -> None:
    with pytest.raises(InvalidManifestError):
        parse_manifest_yaml("- just\n- a\n- list\n")


def test_sign_and_verify_manifest_round_trips() -> None:
    private_key, public_key = generate_rsa_keypair()
    manifest = _manifest()

    signature = sign_manifest(manifest, private_key=private_key)
    signed = PluginManifest(
        metadata=manifest.metadata,
        entry_point=manifest.entry_point,
        dependencies=manifest.dependencies,
        permissions=manifest.permissions,
        compatibility=manifest.compatibility,
        configuration_schema=manifest.configuration_schema,
        signature=signature,
    )

    assert verify_manifest_signature(signed, public_key=public_key) is True


def test_verify_manifest_signature_returns_false_when_missing() -> None:
    manifest = _manifest()

    assert verify_manifest_signature(manifest, public_key=generate_rsa_keypair()[1]) is False


def test_verify_manifest_signature_returns_false_for_malformed_signature() -> None:
    _, public_key = generate_rsa_keypair()
    manifest = PluginManifest(
        metadata=_metadata(), entry_point="sample.plugin:SamplePlugin", signature="not-base64!!"
    )

    assert verify_manifest_signature(manifest, public_key=public_key) is False


def test_verify_manifest_signature_returns_false_when_tampered() -> None:
    private_key, public_key = generate_rsa_keypair()
    manifest = _manifest()
    signature = sign_manifest(manifest, private_key=private_key)
    tampered = PluginManifest(
        metadata=_metadata(version="2.0.0"),  # different payload, same signature
        entry_point=manifest.entry_point,
        signature=signature,
    )

    assert verify_manifest_signature(tampered, public_key=public_key) is False


def test_require_valid_signature_raises_when_verification_fails() -> None:
    manifest = _manifest()

    with pytest.raises(SignatureVerificationError):
        require_valid_signature(manifest, public_key=generate_rsa_keypair()[1])
