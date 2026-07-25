"""Tests for lifecycle.py, sandbox.py, validator.py, and registry.py."""

from __future__ import annotations

import asyncio

import pytest
from shared_core.plugins.dependency import PluginDependency
from shared_core.plugins.exceptions import (
    CircularDependencyError,
    DependencyResolutionError,
    InvalidLifecycleTransitionError,
    PluginExecutionTimeoutError,
    PluginNotFoundError,
    SandboxViolationError,
    SignatureVerificationError,
    VersionIncompatibleError,
)
from shared_core.plugins.lifecycle import PluginLifecycle, PluginState
from shared_core.plugins.manifest import PluginManifest, sign_manifest
from shared_core.plugins.metadata import PluginMetadata, PluginType
from shared_core.plugins.permissions import PluginPermission
from shared_core.plugins.registry import PluginRegistry
from shared_core.plugins.sandbox import PluginSandbox, SandboxPolicy
from shared_core.plugins.validator import validate_manifest
from shared_core.security.encryption import generate_rsa_keypair

# --- shared helpers ---


def _manifest(
    plugin_id: str = "sample",
    version: str = "1.0.0",
    dependencies: tuple[PluginDependency, ...] = (),
    compatibility: str = "*",
) -> PluginManifest:
    return PluginManifest(
        metadata=PluginMetadata(
            plugin_id=plugin_id, name="Sample", version=version, category=PluginType.AUTOMATION
        ),
        entry_point="sample.plugin:SamplePlugin",
        dependencies=dependencies,
        compatibility=compatibility,
    )


# --- lifecycle.py ---


def test_lifecycle_starts_discovered() -> None:
    lifecycle = PluginLifecycle()

    assert lifecycle.state == PluginState.DISCOVERED
    assert lifecycle.history == [PluginState.DISCOVERED]


def test_lifecycle_full_happy_path() -> None:
    lifecycle = PluginLifecycle()

    for target in (
        PluginState.VALIDATED,
        PluginState.INSTALLED,
        PluginState.ENABLED,
        PluginState.INITIALIZED,
        PluginState.STARTED,
        PluginState.PAUSED,
        PluginState.STARTED,
        PluginState.STOPPED,
        PluginState.DISABLED,
        PluginState.UNINSTALLED,
    ):
        lifecycle.transition(target)

    assert lifecycle.state == PluginState.UNINSTALLED
    assert lifecycle.is_terminal() is True


def test_lifecycle_transition_raises_when_not_allowed() -> None:
    lifecycle = PluginLifecycle()

    with pytest.raises(InvalidLifecycleTransitionError):
        lifecycle.transition(PluginState.STARTED)


def test_lifecycle_can_transition_reports_without_raising() -> None:
    lifecycle = PluginLifecycle()

    assert lifecycle.can_transition(PluginState.VALIDATED) is True
    assert lifecycle.can_transition(PluginState.STARTED) is False


def test_lifecycle_supports_a_custom_transition_table() -> None:
    custom = {
        PluginState.DISCOVERED: frozenset({PluginState.FAILED}),
        PluginState.FAILED: frozenset(),
    }
    lifecycle = PluginLifecycle(transitions=custom)

    lifecycle.transition(PluginState.FAILED)

    assert lifecycle.is_terminal() is True


# --- sandbox.py ---


def test_sandbox_check_permission_allows_granted() -> None:
    sandbox = PluginSandbox(
        "sample", SandboxPolicy(allowed_permissions=frozenset({PluginPermission.NETWORK}))
    )

    sandbox.check_permission(PluginPermission.NETWORK)  # doesn't raise


def test_sandbox_check_permission_denies_ungranted() -> None:
    sandbox = PluginSandbox("sample", SandboxPolicy())

    with pytest.raises(SandboxViolationError):
        sandbox.check_permission(PluginPermission.DATABASE)


def test_sandbox_check_filesystem_access_allows_matching_glob() -> None:
    sandbox = PluginSandbox(
        "sample",
        SandboxPolicy(
            allowed_permissions=frozenset({PluginPermission.FILESYSTEM}),
            allowed_filesystem_globs=("/data/sample/*",),
        ),
    )

    sandbox.check_filesystem_access("/data/sample/file.txt")  # doesn't raise


def test_sandbox_check_filesystem_access_denies_unmatched_path() -> None:
    sandbox = PluginSandbox(
        "sample",
        SandboxPolicy(
            allowed_permissions=frozenset({PluginPermission.FILESYSTEM}),
            allowed_filesystem_globs=("/data/sample/*",),
        ),
    )

    with pytest.raises(SandboxViolationError):
        sandbox.check_filesystem_access("/etc/passwd")


def test_sandbox_check_filesystem_access_denies_without_permission() -> None:
    sandbox = PluginSandbox("sample", SandboxPolicy())

    with pytest.raises(SandboxViolationError):
        sandbox.check_filesystem_access("/data/sample/file.txt")


def test_sandbox_check_network_access_allows_listed_host() -> None:
    sandbox = PluginSandbox(
        "sample",
        SandboxPolicy(
            allowed_permissions=frozenset({PluginPermission.NETWORK}),
            allowed_network_hosts=("api.example.com",),
        ),
    )

    sandbox.check_network_access("api.example.com")  # doesn't raise


def test_sandbox_check_network_access_denies_unlisted_host() -> None:
    sandbox = PluginSandbox(
        "sample",
        SandboxPolicy(
            allowed_permissions=frozenset({PluginPermission.NETWORK}),
            allowed_network_hosts=("api.example.com",),
        ),
    )

    with pytest.raises(SandboxViolationError):
        sandbox.check_network_access("evil.example.com")


def test_sandbox_check_memory_usage_passes_with_a_generous_limit() -> None:
    sandbox = PluginSandbox("sample", SandboxPolicy(memory_limit_mb=1_000_000.0))

    usage = sandbox.check_memory_usage()

    assert usage > 0


def test_sandbox_check_memory_usage_raises_with_a_tiny_limit() -> None:
    sandbox = PluginSandbox("sample", SandboxPolicy(memory_limit_mb=0.0001))

    with pytest.raises(SandboxViolationError):
        sandbox.check_memory_usage()


async def test_sandbox_run_returns_the_result_within_the_timeout() -> None:
    sandbox = PluginSandbox("sample", SandboxPolicy(execution_timeout_seconds=1.0))

    async def fast() -> str:
        return "done"

    result = await sandbox.run(fast())

    assert result == "done"


async def test_sandbox_run_raises_past_the_timeout() -> None:
    sandbox = PluginSandbox("sample", SandboxPolicy(execution_timeout_seconds=0.01))

    async def slow() -> None:
        await asyncio.sleep(10)

    with pytest.raises(PluginExecutionTimeoutError):
        await sandbox.run(slow())


# --- validator.py ---


def test_validate_manifest_passes_for_a_self_contained_manifest() -> None:
    validate_manifest(_manifest())  # doesn't raise


def test_validate_manifest_raises_for_incompatible_framework_version() -> None:
    with pytest.raises(VersionIncompatibleError):
        validate_manifest(_manifest(compatibility=">=99.0.0"))


def test_validate_manifest_raises_for_a_missing_dependency() -> None:
    manifest = _manifest(dependencies=(PluginDependency(depends_on_plugin_id="missing"),))

    with pytest.raises(DependencyResolutionError):
        validate_manifest(manifest, installed={})


def test_validate_manifest_raises_for_a_dependency_cycle() -> None:
    other = _manifest("other", dependencies=(PluginDependency(depends_on_plugin_id="sample"),))
    manifest = _manifest(dependencies=(PluginDependency(depends_on_plugin_id="other"),))

    with pytest.raises(CircularDependencyError):
        validate_manifest(manifest, installed={"other": other})


def test_validate_manifest_verifies_a_valid_signature() -> None:
    private_key, public_key = generate_rsa_keypair()
    manifest = _manifest()
    signed = PluginManifest(
        metadata=manifest.metadata,
        entry_point=manifest.entry_point,
        signature=sign_manifest(manifest, private_key=private_key),
    )

    validate_manifest(signed, public_key=public_key)  # doesn't raise


def test_validate_manifest_raises_for_an_unsigned_manifest_when_a_key_is_given() -> None:
    _, public_key = generate_rsa_keypair()

    with pytest.raises(SignatureVerificationError):
        validate_manifest(_manifest(), public_key=public_key)


# --- registry.py ---


def test_registry_register_then_get_round_trips() -> None:
    registry = PluginRegistry()
    manifest = _manifest()

    record = registry.register(manifest)

    assert registry.get("sample") is record
    assert record.lifecycle.state == PluginState.DISCOVERED


def test_registry_get_raises_for_unregistered_plugin() -> None:
    registry = PluginRegistry()

    with pytest.raises(PluginNotFoundError):
        registry.get("missing")


def test_registry_has_and_unregister() -> None:
    registry = PluginRegistry()
    registry.register(_manifest())

    assert registry.has("sample") is True

    registry.unregister("sample")

    assert registry.has("sample") is False


def test_registry_list_plugins_and_by_state() -> None:
    registry = PluginRegistry()
    registry.register(_manifest("a"))
    registry.register(_manifest("b"))

    assert {record.manifest.metadata.plugin_id for record in registry.list_plugins()} == {
        "a",
        "b",
    }
    assert len(registry.list_by_state(PluginState.DISCOVERED)) == 2


def test_registry_list_enabled_and_disabled() -> None:
    registry = PluginRegistry()
    enabled_record = registry.register(_manifest("enabled-plugin"))
    disabled_record = registry.register(_manifest("disabled-plugin"))
    for target in (PluginState.VALIDATED, PluginState.INSTALLED, PluginState.ENABLED):
        enabled_record.lifecycle.transition(target)
    for target in (
        PluginState.VALIDATED,
        PluginState.INSTALLED,
        PluginState.ENABLED,
        PluginState.DISABLED,
    ):
        disabled_record.lifecycle.transition(target)

    assert [r.manifest.metadata.plugin_id for r in registry.list_enabled()] == ["enabled-plugin"]
    assert [r.manifest.metadata.plugin_id for r in registry.list_disabled()] == ["disabled-plugin"]


def test_registry_version_of() -> None:
    registry = PluginRegistry()
    registry.register(_manifest("sample", "2.3.4"))

    assert registry.version_of("sample") == "2.3.4"


def test_registry_version_of_raises_for_unregistered_plugin() -> None:
    registry = PluginRegistry()

    with pytest.raises(PluginNotFoundError):
        registry.version_of("missing")


def test_registry_manifests_by_id() -> None:
    registry = PluginRegistry()
    registry.register(_manifest("a"))
    registry.register(_manifest("b"))

    manifests = registry.manifests_by_id()

    assert set(manifests) == {"a", "b"}
