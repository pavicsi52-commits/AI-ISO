"""Repository interface.

Every concrete repository (docs/018_Enterprise_Database_Framework.md.txt)
implements this protocol. Services depend on this protocol, never on a
concrete repository class.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable
from uuid import UUID


@runtime_checkable
class RepositoryProtocol[EntityT](Protocol):
    """Structural interface for a persistence repository of ``EntityT``."""

    async def get_by_id(self, entity_id: UUID) -> EntityT | None:
        """Return the entity with the given ID, or ``None`` if not found."""
        ...

    async def create(self, entity: EntityT) -> EntityT:
        """Persist a new entity and return it."""
        ...

    async def update(self, entity: EntityT) -> EntityT:
        """Persist changes to an existing entity and return it."""
        ...

    async def delete(self, entity_id: UUID) -> None:
        """Soft-delete the entity with the given ID."""
        ...

    async def exists(self, entity_id: UUID) -> bool:
        """Return whether an entity with the given ID exists."""
        ...
