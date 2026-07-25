"""Event validation.

Per docs/020_Enterprise_Event_Framework.md.txt "VALIDATION": "Every event
validated before publish." Validate Schema, Version, Payload, Metadata,
Tenant, Permissions. Also docs/020 "SECURITY": "Validate Tenant, Validate
Permissions, Mask Sensitive Data."

Implemented directly against :class:`~shared_core.events.base.BaseEvent`
rather than routed through :mod:`shared_core.validation`'s pipeline
(Prompt 016): that framework's layers are shaped around request/response/
field validation, not an event envelope, and forcing the fit would cost
more clarity than it would save. What *is* reused: RBAC
(:mod:`shared_core.security.rbac`) for permission checks and
:func:`shared_core.logging.filters.mask_payload` for sensitive-data
masking -- exactly the primitives Prompt 016/014 already built for this.
"""

from __future__ import annotations

from shared_core.enums.permission import Permission
from shared_core.enums.role import Role
from shared_core.events.base import BaseEvent
from shared_core.events.exceptions import EventValidationError
from shared_core.events.registry import EventRegistry, default_registry
from shared_core.logging.filters import mask_payload
from shared_core.security.context import SecurityContext, get_security_context
from shared_core.security.rbac import has_permission

_RESERVED_METADATA_KEYS = frozenset(
    {"event_id", "event_name", "event_version", "event_type", "source_service", "timestamp"}
)


def validate_schema(event: BaseEvent, *, registry: EventRegistry = default_registry) -> None:
    """Ensure the event's class is registered under its own ``event_name``.

    Raises:
        EventValidationError: If unregistered, or registered to a
            different class than the instance's own type.
    """
    if not registry.is_registered(event.event_name):
        raise EventValidationError(f"Event '{event.event_name}' is not registered.")
    expected_cls = registry.lookup(event.event_name, event.event_version)
    if not isinstance(event, expected_cls):
        raise EventValidationError(
            f"Event instance is a {type(event).__name__}, but '{event.event_name}' "
            f"version {event.event_version} is registered to {expected_cls.__name__}."
        )


def validate_version(event: BaseEvent, *, registry: EventRegistry = default_registry) -> None:
    """Ensure the event's version is a version registered for its name.

    Raises:
        EventValidationError: If the version isn't registered.
    """
    if not registry.is_version_supported(event.event_name, event.event_version):
        raise EventValidationError(
            f"Event '{event.event_name}' version {event.event_version} is not a supported version."
        )


def validate_payload(event: BaseEvent) -> None:
    """Ensure framework-level invariants Pydantic's field types alone don't cover.

    Raises:
        EventValidationError: If a required envelope field is missing/empty.
    """
    if not event.source_service:
        raise EventValidationError("Event must set source_service.")
    if not event.event_name:  # pragma: no cover -- ClassVar, always set on a real subclass
        raise EventValidationError("Event must set event_name.")


def validate_metadata(event: BaseEvent) -> None:
    """Ensure ``metadata`` doesn't redefine a reserved top-level envelope field name.

    Raises:
        EventValidationError: If a collision is found.
    """
    collisions = _RESERVED_METADATA_KEYS & event.metadata.keys()
    if collisions:
        raise EventValidationError(
            f"Event metadata must not redefine reserved fields: {sorted(collisions)}."
        )


def validate_tenant(event: BaseEvent, *, context: SecurityContext | None = None) -> None:
    """Ensure a tenant-scoped event matches the caller's own tenant.

    A super admin, or an event/context with no organization set, bypasses
    the check -- there's nothing to compare.

    Raises:
        EventValidationError: If the event's ``organization_id`` doesn't
            match the caller's.
    """
    ctx = context or get_security_context()
    if ctx.role == Role.SUPER_ADMIN:
        return
    tenant_mismatch = (
        event.organization_id is not None
        and ctx.organization_id is not None
        and event.organization_id != ctx.organization_id
    )
    if tenant_mismatch:
        raise EventValidationError("Event organization_id does not match the caller's tenant.")


def validate_permissions(
    event: BaseEvent,
    *,
    required_permission: Permission | None = None,
    context: SecurityContext | None = None,
) -> None:
    """Ensure the caller holds *required_permission*, if one is given.

    Raises:
        EventValidationError: If the caller lacks the permission.
    """
    if required_permission is None:
        return
    ctx = context or get_security_context()
    if ctx.role is None or not has_permission(ctx.role, required_permission):
        raise EventValidationError(
            f"Caller lacks permission '{required_permission.value}' "
            f"to publish '{event.event_name}'."
        )


def mask_sensitive_payload(event: BaseEvent) -> BaseEvent:
    """Return a copy of *event* with its payload's sensitive fields masked.

    For safe audit logging only -- never mutates the original, and never
    used for the value actually published.
    """
    return event.model_copy(update={"payload": mask_payload(event.payload)})


def validate_event(
    event: BaseEvent,
    *,
    registry: EventRegistry = default_registry,
    required_permission: Permission | None = None,
    context: SecurityContext | None = None,
) -> None:
    """Run the full validation pipeline. Raises on the first failure.

    Raises:
        EventValidationError: If any validation step fails.
    """
    validate_schema(event, registry=registry)
    validate_version(event, registry=registry)
    validate_payload(event)
    validate_metadata(event)
    validate_tenant(event, context=context)
    validate_permissions(event, required_permission=required_permission, context=context)


__all__ = [
    "mask_sensitive_payload",
    "validate_event",
    "validate_metadata",
    "validate_payload",
    "validate_permissions",
    "validate_schema",
    "validate_tenant",
    "validate_version",
]
