"""Event serialization.

Per docs/020_Enterprise_Event_Framework.md.txt "PERFORMANCE": "Efficient
Serialization", "Compression".
"""

from __future__ import annotations

import base64
from typing import Any

from shared_core.cache.compression import CompressionAlgorithm, compress, decompress
from shared_core.events.base import BaseEvent
from shared_core.events.constants import DEFAULT_PAYLOAD_COMPRESSION_THRESHOLD_BYTES
from shared_core.events.registry import EventRegistry, default_registry
from shared_core.events.versioning import VersionMigrator
from shared_core.helpers.json_helper import from_json, to_json

_RESERVED_ENVELOPE_FIELDS = frozenset({"event_name", "event_version", "event_type"})


def serialize_event(event: BaseEvent) -> dict[str, Any]:
    """Serialize an event to a plain dict suitable for JSON encoding.

    Includes ``event_name``/``event_version``/``event_type`` (``ClassVar``s,
    so not part of Pydantic's own field serialization) alongside the
    instance fields.
    """
    return {
        "event_name": event.event_name,
        "event_version": event.event_version,
        "event_type": event.event_type.value,
        **event.model_dump(mode="json"),
    }


def deserialize_event(
    data: dict[str, Any],
    *,
    registry: EventRegistry = default_registry,
    migrator: VersionMigrator | None = None,
    target_version: str | None = None,
) -> BaseEvent:
    """Deserialize a dict back into its registered event class.

    If *migrator* is given and the stored ``event_version`` is older than
    *target_version* (or the latest registered version, if
    *target_version* is omitted), the payload is migrated forward before
    validation -- "Consumers must support backward compatibility"
    (docs/020 "EVENT VERSIONING"). The event is always validated against
    the *target* version's class, not the version it was stored as, so a
    migrated payload is checked against the shape it was migrated to.
    """
    event_name = data["event_name"]
    stored_version = data.get("event_version", "v1")

    if target_version is not None:
        resolved_target = target_version
    else:
        lookup_version = (
            stored_version if registry.is_registered(event_name, stored_version) else None
        )
        resolved_target = registry.lookup(event_name, lookup_version).event_version

    fields = {k: v for k, v in data.items() if k not in _RESERVED_ENVELOPE_FIELDS}
    if migrator is not None and stored_version != resolved_target:
        fields["payload"] = migrator.migrate(
            event_name,
            fields.get("payload", {}),
            from_version=stored_version,
            to_version=resolved_target,
        )
    event_cls = registry.lookup(event_name, resolved_target)
    return event_cls.model_validate(fields)


def compact_payload(
    payload: dict[str, Any],
    *,
    threshold_bytes: int = DEFAULT_PAYLOAD_COMPRESSION_THRESHOLD_BYTES,
) -> dict[str, Any]:
    """Compress *payload* if its JSON encoding is at least *threshold_bytes* long.

    Returns *payload* unchanged if it's small, or a
    ``{"__compressed__": True, "data": "<base64>"}`` envelope if
    compressed -- either shape round-trips through the plain JSON-dict
    contract :meth:`shared_core.queue.manager.QueueManager.publish`
    requires.
    """
    encoded = to_json(payload).encode("utf-8")
    if len(encoded) < threshold_bytes:
        return payload
    compressed = compress(
        encoded, algorithm=CompressionAlgorithm.ZSTD, threshold_bytes=threshold_bytes
    )
    return {"__compressed__": True, "data": base64.urlsafe_b64encode(compressed).decode("ascii")}


def expand_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """Reverse :func:`compact_payload` -- returns *payload* unchanged if it wasn't compressed."""
    if not payload.get("__compressed__"):
        return payload
    compressed = base64.urlsafe_b64decode(payload["data"])
    decoded = decompress(compressed)
    result: dict[str, Any] = from_json(decoded)
    return result


__all__ = ["compact_payload", "deserialize_event", "expand_payload", "serialize_event"]
