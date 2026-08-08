"""Tool registration (docs/060 "TOOL REGISTRY"; backs ``GET/POST
/agents/tools``)."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from shared_core.exceptions.conflict import ConflictError

from app.models.enums import PermissionCategory, ToolKind
from app.models.tool import AgentTool
from app.repositories.tool import AgentToolRepository


class ToolService:
    """Registers and manages one organization's own tool catalogue."""

    def __init__(self, tools: AgentToolRepository) -> None:
        self._tools = tools

    async def register_tool(
        self,
        *,
        organization_id: UUID,
        tool_key: str,
        name: str,
        tool_kind: ToolKind,
        description: str | None = None,
        category: str = "general",
        parameters_schema: dict[str, Any] | None = None,
        required_permission: PermissionCategory = PermissionCategory.TOOL_INVOCATION,
        is_mutating: bool = False,
        metadata: dict[str, Any] | None = None,
    ) -> AgentTool:
        """Register a new tool.

        Raises:
            ConflictError: If *tool_key* is already registered in
                *organization_id*.
        """
        if await self._tools.get_by_key(organization_id, tool_key) is not None:
            raise ConflictError(
                f"Tool key {tool_key!r} is already registered in this organization."
            )

        return await self._tools.create(
            AgentTool(
                organization_id=organization_id,
                tool_key=tool_key,
                name=name,
                description=description,
                tool_kind=tool_kind,
                category=category,
                parameters_schema=parameters_schema or {"type": "object", "properties": {}},
                required_permission=required_permission,
                is_mutating=is_mutating,
                enabled=True,
                metadata_=metadata or {},
            )
        )

    async def set_enabled(self, tool: AgentTool, *, enabled: bool) -> AgentTool:
        """Enable or disable *tool*."""
        tool.enabled = enabled
        return await self._tools.update(tool)

    async def deprecate(self, tool: AgentTool) -> AgentTool:
        """Mark *tool* deprecated -- it stays visible but should no
        longer be granted to new agents."""
        tool.is_deprecated = True
        return await self._tools.update(tool)


__all__ = ["ToolService"]
