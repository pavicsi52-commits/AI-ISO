"""Service-layer interface.

Business services (docs/008_Backend_Master_Architecture.md.txt) implement
this protocol so API routers can depend on the abstraction rather than a
concrete implementation.
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable
from uuid import UUID


@runtime_checkable
class ServiceProtocol[EntityT](Protocol):
    """Structural interface for a business service operating on ``EntityT``."""

    async def get(self, entity_id: UUID) -> EntityT:
        """Return the entity with the given ID, raising if not found."""
        ...

    async def create(self, payload: dict[str, Any]) -> EntityT:
        """Validate and create a new entity from the given payload."""
        ...

    async def update(self, entity_id: UUID, payload: dict[str, Any]) -> EntityT:
        """Validate and apply a partial update to an existing entity."""
        ...

    async def delete(self, entity_id: UUID) -> None:
        """Delete the entity with the given ID."""
        ...
