"""Generic key/value execution context entries for a workflow instance.

Mirrors ``shared_core.workflow.context.WorkflowContext``'s own
``connector_context``/``ai_context``/``plugin_context`` dicts -- see
``app/models/workflow_context.py``'s own docstring.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from app.models.workflow_context import WorkflowContextEntry
from app.repositories.workflow_context import WorkflowContextEntryRepository


class WorkflowContextEntryService:
    """Records and reads a workflow instance's own generic context entries."""

    def __init__(self, context_entries: WorkflowContextEntryRepository) -> None:
        self._context_entries = context_entries

    async def record(
        self, *, organization_id: UUID, instance_id: UUID, key: str, value: Any
    ) -> WorkflowContextEntry:
        """Record one context entry for *instance_id*."""
        return await self._context_entries.create(
            WorkflowContextEntry(
                organization_id=organization_id, instance_id=instance_id, key=key, value=value
            )
        )

    async def list_for_instance(self, instance_id: UUID) -> list[WorkflowContextEntry]:
        """Every context entry recorded for *instance_id*."""
        return await self._context_entries.list_for_instance(instance_id)


__all__ = ["WorkflowContextEntryService"]
