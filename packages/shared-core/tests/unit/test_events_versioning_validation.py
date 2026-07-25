"""Tests for event versioning, the version-aware registry, and validation."""

from __future__ import annotations

from typing import ClassVar
from uuid import uuid4

import pytest
from shared_core.constants.logging import LoggingConstants
from shared_core.enums.permission import Permission
from shared_core.enums.role import Role
from shared_core.events.base import BaseEvent
from shared_core.events.constants import DEFAULT_PAYLOAD_COMPRESSION_THRESHOLD_BYTES
from shared_core.events.exceptions import EventValidationError, EventVersionMismatchError
from shared_core.events.registry import EventRegistry
from shared_core.events.serializer import compact_payload, deserialize_event, expand_payload
from shared_core.events.validator import (
    mask_sensitive_payload,
    validate_event,
    validate_metadata,
    validate_payload,
    validate_permissions,
    validate_schema,
    validate_tenant,
    validate_version,
)
from shared_core.events.versioning import VersionMigrator, is_compatible, parse_version
from shared_core.exceptions.not_found import NotFoundError
from shared_core.security.context import SecurityContext


class _OrderPlacedV1(BaseEvent):
    event_name: ClassVar[str] = "order.placed"
    event_version: ClassVar[str] = "v1"


class _OrderPlacedV2(BaseEvent):
    event_name: ClassVar[str] = "order.placed"
    event_version: ClassVar[str] = "v2"


# --- versioning.py ---


def test_parse_version_extracts_the_integer() -> None:
    assert parse_version("v1") == 1
    assert parse_version("v42") == 42


def test_parse_version_rejects_malformed_strings() -> None:
    with pytest.raises(ValueError, match="Invalid event version format"):
        parse_version("1")
    with pytest.raises(ValueError, match="Invalid event version format"):
        parse_version("version1")


def test_is_compatible_allows_backward_only() -> None:
    assert is_compatible(consumer_version="v2", event_version="v1") is True
    assert is_compatible(consumer_version="v2", event_version="v2") is True
    assert is_compatible(consumer_version="v1", event_version="v2") is False


def test_version_migrator_chains_steps_in_order() -> None:
    migrator = VersionMigrator()
    migrator.register("order.placed", "v1", lambda p: {**p, "step": [*p.get("step", []), "v1->v2"]})
    migrator.register("order.placed", "v2", lambda p: {**p, "step": [*p.get("step", []), "v2->v3"]})

    result = migrator.migrate("order.placed", {}, from_version="v1", to_version="v3")

    assert result["step"] == ["v1->v2", "v2->v3"]


def test_version_migrator_raises_when_a_step_is_missing() -> None:
    migrator = VersionMigrator()
    migrator.register("order.placed", "v1", lambda p: p)

    with pytest.raises(EventVersionMismatchError):
        migrator.migrate("order.placed", {}, from_version="v1", to_version="v3")


def test_version_migrator_has_migration_path() -> None:
    migrator = VersionMigrator()
    migrator.register("order.placed", "v1", lambda p: p)

    assert migrator.has_migration_path("order.placed", from_version="v1", to_version="v2") is True
    assert migrator.has_migration_path("order.placed", from_version="v1", to_version="v3") is False


# --- registry.py: version-aware behavior ---


@pytest.fixture
def registry() -> EventRegistry:
    reg = EventRegistry()
    reg.register(_OrderPlacedV1)
    reg.register(_OrderPlacedV2)
    return reg


def test_lookup_without_version_returns_the_latest(registry: EventRegistry) -> None:
    assert registry.lookup("order.placed") is _OrderPlacedV2


def test_lookup_with_explicit_version_returns_that_version(registry: EventRegistry) -> None:
    assert registry.lookup("order.placed", "v1") is _OrderPlacedV1
    assert registry.lookup("order.placed", "v2") is _OrderPlacedV2


def test_lookup_raises_not_found_for_unregistered_version(registry: EventRegistry) -> None:
    with pytest.raises(NotFoundError):
        registry.lookup("order.placed", "v9")


def test_is_registered_checks_version_when_given(registry: EventRegistry) -> None:
    assert registry.is_registered("order.placed", "v1") is True
    assert registry.is_registered("order.placed", "v9") is False
    assert registry.is_registered("order.placed") is True


def test_is_version_supported(registry: EventRegistry) -> None:
    assert registry.is_version_supported("order.placed", "v2") is True
    assert registry.is_version_supported("order.placed", "v3") is False


def test_supported_versions_is_oldest_first(registry: EventRegistry) -> None:
    assert registry.supported_versions("order.placed") == ["v1", "v2"]


def test_describe_returns_a_json_schema(registry: EventRegistry) -> None:
    schema = registry.describe("order.placed", "v1")

    assert schema["title"] == "_OrderPlacedV1"
    assert "properties" in schema


# --- validator.py ---


def test_validate_schema_passes_for_a_registered_event(registry: EventRegistry) -> None:
    event = _OrderPlacedV1(source_service="orders")
    validate_schema(event, registry=registry)


def test_validate_schema_raises_for_an_unregistered_event() -> None:
    empty_registry = EventRegistry()
    event = _OrderPlacedV1(source_service="orders")

    with pytest.raises(EventValidationError, match="not registered"):
        validate_schema(event, registry=empty_registry)


def test_validate_schema_raises_when_instance_type_mismatches_registration() -> None:
    class _Impostor(BaseEvent):
        event_name: ClassVar[str] = "order.placed"
        event_version: ClassVar[str] = "v1"

    mismatched_registry = EventRegistry()
    mismatched_registry.register(_Impostor)
    event = _OrderPlacedV1(source_service="orders")  # also names itself "order.placed"/"v1"

    with pytest.raises(EventValidationError, match="is a _OrderPlacedV1"):
        validate_schema(event, registry=mismatched_registry)


def test_validate_version_passes_for_a_supported_version(registry: EventRegistry) -> None:
    event = _OrderPlacedV1(source_service="orders")
    validate_version(event, registry=registry)


def test_validate_version_raises_for_an_unsupported_version(registry: EventRegistry) -> None:
    class _OrderPlacedV9(BaseEvent):
        event_name: ClassVar[str] = "order.placed"
        event_version: ClassVar[str] = "v9"

    event = _OrderPlacedV9(source_service="orders")

    with pytest.raises(EventValidationError, match="not a supported version"):
        validate_version(event, registry=registry)


def test_validate_payload_requires_source_service() -> None:
    event = _OrderPlacedV1(source_service="orders")
    validate_payload(event)

    event.source_service = ""
    with pytest.raises(EventValidationError, match="source_service"):
        validate_payload(event)


def test_validate_metadata_rejects_reserved_key_collisions() -> None:
    event = _OrderPlacedV1(source_service="orders", metadata={"event_id": "nope"})

    with pytest.raises(EventValidationError, match="reserved fields"):
        validate_metadata(event)


def test_validate_metadata_allows_non_reserved_keys() -> None:
    event = _OrderPlacedV1(source_service="orders", metadata={"trace_id": "abc"})
    validate_metadata(event)


def test_validate_tenant_allows_matching_organization() -> None:
    org_id = uuid4()
    event = _OrderPlacedV1(source_service="orders", organization_id=org_id)
    context = SecurityContext(role=Role.OPERATOR, organization_id=org_id)

    validate_tenant(event, context=context)


def test_validate_tenant_rejects_mismatched_organization() -> None:
    event = _OrderPlacedV1(source_service="orders", organization_id=uuid4())
    context = SecurityContext(role=Role.OPERATOR, organization_id=uuid4())

    with pytest.raises(EventValidationError, match="tenant"):
        validate_tenant(event, context=context)


def test_validate_tenant_bypasses_for_super_admin() -> None:
    event = _OrderPlacedV1(source_service="orders", organization_id=uuid4())
    context = SecurityContext(role=Role.SUPER_ADMIN, organization_id=uuid4())

    validate_tenant(event, context=context)


def test_validate_permissions_skips_when_none_required() -> None:
    event = _OrderPlacedV1(source_service="orders")
    validate_permissions(event, context=SecurityContext())


def test_validate_permissions_allows_a_sufficient_role() -> None:
    event = _OrderPlacedV1(source_service="orders")
    context = SecurityContext(role=Role.OPERATOR)

    validate_permissions(event, required_permission=Permission.READ, context=context)


def test_validate_permissions_rejects_an_insufficient_role() -> None:
    event = _OrderPlacedV1(source_service="orders")
    context = SecurityContext(role=Role.VIEWER)

    with pytest.raises(EventValidationError, match="lacks permission"):
        validate_permissions(event, required_permission=Permission.DELETE, context=context)


def test_validate_permissions_rejects_when_role_is_unset() -> None:
    event = _OrderPlacedV1(source_service="orders")

    with pytest.raises(EventValidationError, match="lacks permission"):
        validate_permissions(event, required_permission=Permission.READ, context=SecurityContext())


def test_mask_sensitive_payload_masks_without_mutating_the_original() -> None:
    event = _OrderPlacedV1(source_service="orders", payload={"password": "hunter2", "amount": 10})

    masked = mask_sensitive_payload(event)

    assert masked.payload["password"] == LoggingConstants.MASKED_VALUE
    assert masked.payload["amount"] == 10
    assert event.payload["password"] == "hunter2"  # original untouched


def test_validate_event_runs_the_full_pipeline_and_passes(registry: EventRegistry) -> None:
    event = _OrderPlacedV1(source_service="orders")
    validate_event(event, registry=registry)


def test_validate_event_stops_at_the_first_failure(registry: EventRegistry) -> None:
    event = _OrderPlacedV1(source_service="")

    with pytest.raises(EventValidationError, match="source_service"):
        validate_event(event, registry=registry)


def test_compression_threshold_constant_is_positive() -> None:
    assert DEFAULT_PAYLOAD_COMPRESSION_THRESHOLD_BYTES > 0


# --- serializer.py: compaction and migration-on-deserialize ---


def test_compact_payload_leaves_small_payloads_unchanged() -> None:
    payload = {"amount": 10}

    assert compact_payload(payload, threshold_bytes=4096) == payload


def test_compact_payload_compresses_and_expand_payload_reverses_it() -> None:
    payload = {"description": "x" * 100}

    compacted = compact_payload(payload, threshold_bytes=10)

    assert compacted["__compressed__"] is True
    assert "data" in compacted
    assert expand_payload(compacted) == payload


def test_expand_payload_leaves_an_uncompressed_payload_unchanged() -> None:
    payload = {"amount": 10}

    assert expand_payload(payload) == payload


def test_deserialize_event_migrates_an_older_payload_forward(registry: EventRegistry) -> None:
    migrator = VersionMigrator()
    migrator.register("order.placed", "v1", lambda p: {**p, "migrated": True})
    data = {
        "event_name": "order.placed",
        "event_version": "v1",
        "event_type": "domain",
        "event_id": str(uuid4()),
        "source_service": "orders",
        "payload": {"amount": 10},
    }

    event = deserialize_event(data, registry=registry, migrator=migrator, target_version="v2")

    assert isinstance(event, _OrderPlacedV2)
    assert event.payload == {"amount": 10, "migrated": True}
