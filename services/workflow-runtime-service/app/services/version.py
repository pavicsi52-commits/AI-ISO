"""Workflow DAG version management. Per docs/042 "WORKFLOW EXECUTION"/
DATABASE TABLES: every new version is compiled -- and therefore
structurally validated, with cycles rejected -- before it's persisted,
the same "a version is an immutable, verifiable snapshot, never a bare
JSON blob" precedent
``services/playbook-service``'s own ``PlaybookVersionService``
established for structural content validation.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from app.models.workflow_definition import WorkflowDefinition
from app.models.workflow_version import WorkflowVersion
from app.repositories.workflow_version import WorkflowVersionRepository
from app.services.compiler import compile_version

_INITIAL_VERSION = "1.0.0"


class WorkflowVersionService:
    """Creates and reads compiled workflow DAG version snapshots."""

    def __init__(self, versions: WorkflowVersionRepository) -> None:
        self._versions = versions

    async def get_by_id(self, version_id: UUID) -> WorkflowVersion:
        """Return the version identified by *version_id*.

        Raises:
            NotFoundError: If no such version exists.
        """
        return await self._versions.require_by_id(version_id)

    async def list_for_definition(self, definition_id: UUID) -> list[WorkflowVersion]:
        """Every version recorded for *definition_id*, newest first."""
        return await self._versions.list_for_definition(definition_id)

    async def get_latest_for_definition(self, definition_id: UUID) -> WorkflowVersion | None:
        """Return *definition_id*'s most recently created version, or ``None``."""
        return await self._versions.get_latest_for_definition(definition_id)

    async def create_version(
        self,
        definition: WorkflowDefinition,
        *,
        nodes: list[dict[str, Any]],
        edges: list[dict[str, Any]],
        current_version_number: str | None,
    ) -> WorkflowVersion:
        """Compile, validate, and snapshot a new DAG version.

        Raises:
            InvalidWorkflowDefinitionError: If *nodes*/*edges* are
                structurally invalid.
            CycleDetectedError: If *nodes*/*edges* contain a cycle.
        """
        version_number = (
            _bump_patch(current_version_number) if current_version_number else _INITIAL_VERSION
        )
        version = WorkflowVersion(
            organization_id=definition.organization_id,
            definition_id=definition.id,
            version_number=version_number,
            nodes=nodes,
            edges=edges,
            compiled_execution_plan=[],
        )
        compiled = compile_version(definition, version)
        version.compiled_execution_plan = compiled.execution_plan
        return await self._versions.create(version)


def _bump_patch(version_number: str) -> str:
    major, minor, patch = version_number.split(".")
    return f"{major}.{minor}.{int(patch) + 1}"


__all__ = ["WorkflowVersionService"]
