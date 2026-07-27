"""Workflow definition lifecycle. Per docs/042 "WORKFLOW EXECUTION"/
DATABASE TABLES: a workflow definition is metadata plus a pointer to
its own *current* :class:`~app.models.workflow_version.WorkflowVersion`.
Creating a definition always creates its own first version in the same
call (a definition with no DAG isn't meaningfully "created" yet),
matching ``services/playbook-service``'s own
``PlaybookService.create()`` precedent.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from shared_core.exceptions.conflict import ConflictError

from app.models.workflow_definition import WorkflowDefinition
from app.repositories.workflow_definition import WorkflowDefinitionRepository
from app.services.version import WorkflowVersionService


class WorkflowDefinitionService:
    """Creates, reads, updates, and deletes workflow definitions."""

    def __init__(
        self, definitions: WorkflowDefinitionRepository, versions: WorkflowVersionService
    ) -> None:
        self._definitions = definitions
        self._versions = versions

    async def get_by_id(self, definition_id: UUID) -> WorkflowDefinition:
        """Return the workflow definition identified by *definition_id*.

        Raises:
            NotFoundError: If no such definition exists.
        """
        return await self._definitions.require_by_id(definition_id)

    async def list_for_org(self, organization_id: UUID) -> list[WorkflowDefinition]:
        """Every workflow definition belonging to *organization_id*."""
        return await self._definitions.list_for_org(organization_id)

    async def create(
        self,
        *,
        organization_id: UUID,
        project_id: UUID | None,
        workflow_key: str,
        name: str,
        description: str | None,
        owner: str | None,
        tags: list[str],
        default_variables: dict[str, Any],
        nodes: list[dict[str, Any]],
        edges: list[dict[str, Any]],
    ) -> WorkflowDefinition:
        """Define a new workflow and its own first DAG version ("Create").

        Raises:
            ConflictError: If *workflow_key* is already used by another
                definition in *organization_id*.
            InvalidWorkflowDefinitionError: If the given DAG is
                structurally invalid.
            CycleDetectedError: If the given DAG contains a cycle.
        """
        existing = await self._definitions.get_by_key(organization_id, workflow_key)
        if existing is not None:
            raise ConflictError(
                f"Workflow key {workflow_key!r} is already used by another definition "
                f"in this organization."
            )
        definition = await self._definitions.create(
            WorkflowDefinition(
                organization_id=organization_id,
                project_id=project_id,
                workflow_key=workflow_key,
                name=name,
                description=description,
                owner=owner,
                tags=tags,
                default_variables=default_variables,
            )
        )
        version = await self._versions.create_version(
            definition, nodes=nodes, edges=edges, current_version_number=None
        )
        definition.current_version_number = version.version_number
        return await self._definitions.update(definition)

    async def update(
        self,
        definition_id: UUID,
        *,
        name: str,
        description: str | None,
        owner: str | None,
        tags: list[str],
        default_variables: dict[str, Any],
        nodes: list[dict[str, Any]],
        edges: list[dict[str, Any]],
    ) -> WorkflowDefinition:
        """Replace a definition's own metadata and record a new DAG
        version ("Update").

        Raises:
            NotFoundError: If *definition_id* does not exist.
            InvalidWorkflowDefinitionError: If the given DAG is
                structurally invalid.
            CycleDetectedError: If the given DAG contains a cycle.
        """
        definition = await self.get_by_id(definition_id)
        definition.name = name
        definition.description = description
        definition.owner = owner
        definition.tags = tags
        definition.default_variables = default_variables
        version = await self._versions.create_version(
            definition,
            nodes=nodes,
            edges=edges,
            current_version_number=definition.current_version_number,
        )
        definition.current_version_number = version.version_number
        return await self._definitions.update(definition)

    async def delete(self, definition_id: UUID) -> None:
        """Soft-delete a workflow definition ("Delete")."""
        await self._definitions.delete(definition_id)


__all__ = ["WorkflowDefinitionService"]
