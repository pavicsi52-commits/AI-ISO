"""Shared type aliases used across API, database, event, and queue code."""

from shared_core.types.api import JsonValue, QueryParams
from shared_core.types.database import EntityId, TenantScope
from shared_core.types.event import EventPayload
from shared_core.types.queue import QueueMessage
from shared_core.types.response import ResponseData

__all__ = [
    "EntityId",
    "EventPayload",
    "JsonValue",
    "QueryParams",
    "QueueMessage",
    "ResponseData",
    "TenantScope",
]
