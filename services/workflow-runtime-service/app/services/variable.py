"""Per docs/042 "VARIABLES" "Support": Global Variables, Workflow
Variables, Node Variables, Environment Variables, Secrets References,
Computed Variables, Runtime Variables.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from app.models.enums import WorkflowVariableScope
from app.models.workflow_variable import WorkflowVariable
from app.repositories.workflow_variable import WorkflowVariableRepository


class WorkflowVariableService:
    """Records and reads definition-level and instance-level workflow variables."""

    def __init__(self, variables: WorkflowVariableRepository) -> None:
        self._variables = variables

    async def record_for_definition(
        self,
        *,
        organization_id: UUID,
        definition_id: UUID,
        name: str,
        value: Any,
        scope: WorkflowVariableScope = WorkflowVariableScope.WORKFLOW,
        is_secret: bool = False,
    ) -> WorkflowVariable:
        """Record one definition-level default variable."""
        return await self._variables.create(
            WorkflowVariable(
                organization_id=organization_id,
                definition_id=definition_id,
                instance_id=None,
                scope=scope,
                name=name,
                value=value,
                is_secret=is_secret,
            )
        )

    async def record_for_instance(
        self,
        *,
        organization_id: UUID,
        definition_id: UUID,
        instance_id: UUID,
        name: str,
        value: Any,
        scope: WorkflowVariableScope = WorkflowVariableScope.RUNTIME,
        is_secret: bool = False,
    ) -> WorkflowVariable:
        """Record one instance-level resolved runtime variable."""
        return await self._variables.create(
            WorkflowVariable(
                organization_id=organization_id,
                definition_id=definition_id,
                instance_id=instance_id,
                scope=scope,
                name=name,
                value=value,
                is_secret=is_secret,
            )
        )

    async def list_for_definition(self, definition_id: UUID) -> list[WorkflowVariable]:
        """Every definition-level default variable."""
        return await self._variables.list_for_definition(definition_id)

    async def list_for_instance(self, instance_id: UUID) -> list[WorkflowVariable]:
        """Every resolved runtime variable recorded for *instance_id*."""
        return await self._variables.list_for_instance(instance_id)


__all__ = ["WorkflowVariableService"]
