"""Playbook dependencies. Per docs/041 "DEPENDENCIES" "Support":
Playbook Dependencies, Role Dependencies, Collection Dependencies,
Python Packages, External Modules, Plugin Dependencies, Circular
Dependency Detection.

Circular-dependency detection is real graph traversal, not a
placeholder: for a ``PLAYBOOK``-type dependency, the declared *name* is
resolved to actual playbook(s) with that name in the same organization,
and their own declared dependencies are walked depth-first looking for
a path back to the originating playbook.
"""

from __future__ import annotations

from uuid import UUID

from shared_core.exceptions.conflict import ConflictError

from app.models.enums import DependencyType
from app.models.playbook_dependency import PlaybookDependency
from app.repositories.playbook import PlaybookRepository
from app.repositories.playbook_dependency import PlaybookDependencyRepository


class PlaybookDependencyService:
    """Creates, reads, deletes, and circularity-checks playbook dependencies."""

    def __init__(
        self, dependencies: PlaybookDependencyRepository, playbooks: PlaybookRepository
    ) -> None:
        self._dependencies = dependencies
        self._playbooks = playbooks

    async def list_for_playbook(self, playbook_id: UUID) -> list[PlaybookDependency]:
        """Every dependency declared by *playbook_id*."""
        return await self._dependencies.list_for_playbook(playbook_id)

    async def create(
        self,
        playbook_id: UUID,
        *,
        dependency_type: DependencyType,
        name: str,
        version_constraint: str | None,
    ) -> PlaybookDependency:
        """Declare a new dependency for a playbook.

        Raises:
            NotFoundError: If *playbook_id* does not exist.
            ConflictError: If declaring a ``PLAYBOOK`` dependency on
                *name* would create a circular dependency chain.
        """
        playbook = await self._playbooks.require_by_id(playbook_id)
        if dependency_type is DependencyType.PLAYBOOK and await self._creates_cycle(
            playbook.organization_id, playbook.name, name
        ):
            raise ConflictError(
                f"Adding a dependency on {name!r} would create a circular "
                f"dependency chain back to {playbook.name!r}."
            )
        return await self._dependencies.create(
            PlaybookDependency(
                organization_id=playbook.organization_id,
                playbook_id=playbook_id,
                dependency_type=dependency_type,
                name=name,
                version_constraint=version_constraint,
            )
        )

    async def delete(self, dependency_id: UUID) -> None:
        """Remove a declared dependency."""
        await self._dependencies.delete(dependency_id)

    async def _creates_cycle(
        self, organization_id: UUID, origin_name: str, new_dependency_name: str
    ) -> bool:
        """Whether declaring a dependency on *new_dependency_name* would
        eventually lead back to *origin_name*, via real depth-first
        traversal of the existing dependency graph.
        """
        if new_dependency_name == origin_name:
            return True

        visited: set[str] = set()
        stack = [new_dependency_name]
        while stack:
            current_name = stack.pop()
            if current_name in visited:
                continue
            visited.add(current_name)

            candidates = await self._playbooks.list_by_name(organization_id, current_name)
            for candidate in candidates:
                for dependency in await self._dependencies.list_for_playbook(candidate.id):
                    # ``dependency.dependency_type`` round-tripped through a
                    # plain ``String`` column (no SQLAlchemy ``Enum`` type),
                    # so it's not guaranteed to be the *same object* as
                    # ``DependencyType.PLAYBOOK`` -- compare by value, not
                    # identity, unlike the *parameter* check in ``create()``
                    # above (which never leaves this process).
                    if dependency.dependency_type != DependencyType.PLAYBOOK:
                        continue
                    if dependency.name == origin_name:
                        return True
                    if dependency.name not in visited:
                        stack.append(dependency.name)
        return False


__all__ = ["PlaybookDependencyService"]
