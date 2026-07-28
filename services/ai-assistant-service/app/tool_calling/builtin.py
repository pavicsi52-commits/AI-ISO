"""Built-in tool handlers ("TOOL CALLING").

Binds each platform read to a tool key the model can request. Every
handler is read-only: nothing here mutates another service's state.
That is why none of these tools sets ``is_mutating``, and why an
assistant answering a question can never change infrastructure as a
side effect.

Each handler returns a JSON-shaped dict, which
:class:`~app.tool_calling.executor.ToolExecutor` redacts before it
reaches the model.

**Definitions and handlers are kept together on purpose.**
:data:`BUILTIN_TOOL_DEFINITIONS` describes each tool to the model and
:func:`build_builtin_handlers` implements it; a definition without a
handler is denied at execution time with a clear reason rather than
failing obscurely, and :func:`missing_handlers` makes any drift between
the two visible.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.clients.platform import PlatformClient
from app.models.enums import ToolKind
from app.tool_calling.registry import ToolHandler, ToolHandlerRegistry


@dataclass(frozen=True, slots=True)
class BuiltinToolDefinition:
    """A built-in tool's own registerable description."""

    tool_key: str
    name: str
    description: str
    tool_kind: ToolKind
    parameters_schema: dict[str, Any]
    required_permission: str | None = None
    is_mutating: bool = False


def _schema(**properties: str) -> dict[str, Any]:
    """Build a strict object schema with every property required.

    Every built-in tool takes only required string identifiers, so this
    keeps the definitions readable instead of repeating the same nested
    JSON Schema nine times.
    """
    return {
        "type": "object",
        "properties": {
            name: {"type": "string", "description": description}
            for name, description in properties.items()
        },
        "required": sorted(properties),
        "additionalProperties": False,
    }


BUILTIN_TOOL_DEFINITIONS: tuple[BuiltinToolDefinition, ...] = (
    BuiltinToolDefinition(
        tool_key="inventory_list_assets",
        name="List inventory assets",
        description="List the infrastructure assets registered for an organization.",
        tool_kind=ToolKind.INVENTORY_QUERY,
        parameters_schema=_schema(organization_id="The organization's own UUID."),
    ),
    BuiltinToolDefinition(
        tool_key="inventory_get_asset",
        name="Get inventory asset",
        description="Fetch one asset's own full record by id.",
        tool_kind=ToolKind.INVENTORY_QUERY,
        parameters_schema=_schema(asset_id="The asset's own UUID."),
    ),
    BuiltinToolDefinition(
        tool_key="inventory_get_topology",
        name="Get asset topology",
        description="Fetch an asset's own immediate topology neighbours.",
        tool_kind=ToolKind.INVENTORY_QUERY,
        parameters_schema=_schema(asset_id="The asset's own UUID."),
    ),
    BuiltinToolDefinition(
        tool_key="alerting_list_alerts",
        name="List alerts",
        description="List operational alerts for an organization.",
        tool_kind=ToolKind.ALERT_QUERY,
        parameters_schema=_schema(organization_id="The organization's own UUID."),
    ),
    BuiltinToolDefinition(
        tool_key="monitoring_get_health",
        name="Get target health",
        description="Fetch the recorded health checks for one monitored target.",
        tool_kind=ToolKind.MONITORING_QUERY,
        parameters_schema=_schema(target_id="The monitored target's own UUID."),
    ),
    BuiltinToolDefinition(
        tool_key="monitoring_get_statistics",
        name="Get monitoring statistics",
        description="Fetch organization-wide monitoring analytics.",
        tool_kind=ToolKind.MONITORING_QUERY,
        parameters_schema=_schema(organization_id="The organization's own UUID."),
    ),
    BuiltinToolDefinition(
        tool_key="validation_list_results",
        name="List validation results",
        description="Fetch validation results recorded against one target.",
        tool_kind=ToolKind.VALIDATION_EXECUTION,
        parameters_schema=_schema(target_id="The validation target's own UUID."),
    ),
    BuiltinToolDefinition(
        tool_key="configuration_get_drift",
        name="Get configuration drift",
        description="Fetch recorded configuration drift for one profile.",
        tool_kind=ToolKind.CONFIGURATION_QUERY,
        parameters_schema=_schema(
            organization_id="The organization's own UUID.",
            profile_id="The configuration profile's own UUID.",
        ),
    ),
    BuiltinToolDefinition(
        tool_key="automation_list_executions",
        name="List automation executions",
        description="Fetch automation execution history for an organization.",
        tool_kind=ToolKind.AUTOMATION_EXECUTION,
        parameters_schema=_schema(organization_id="The organization's own UUID."),
    ),
)


def build_builtin_handlers(platform: PlatformClient) -> dict[str, ToolHandler]:
    """Build every built-in handler, bound to *platform*."""

    async def list_assets(arguments: dict[str, Any]) -> dict[str, Any]:
        assets = await platform.list_assets(str(arguments["organization_id"]))
        return {"count": len(assets), "assets": assets}

    async def get_asset(arguments: dict[str, Any]) -> dict[str, Any]:
        return {"asset": await platform.get_asset(str(arguments["asset_id"]))}

    async def get_topology(arguments: dict[str, Any]) -> dict[str, Any]:
        return {"topology": await platform.get_topology(str(arguments["asset_id"]))}

    async def list_alerts(arguments: dict[str, Any]) -> dict[str, Any]:
        alerts = await platform.list_alerts(str(arguments["organization_id"]))
        return {"count": len(alerts), "alerts": alerts}

    async def get_health(arguments: dict[str, Any]) -> dict[str, Any]:
        results = await platform.get_monitoring_health(str(arguments["target_id"]))
        return {"count": len(results), "health": results}

    async def get_statistics(arguments: dict[str, Any]) -> dict[str, Any]:
        return {
            "statistics": await platform.get_monitoring_statistics(
                str(arguments["organization_id"])
            )
        }

    async def list_validation(arguments: dict[str, Any]) -> dict[str, Any]:
        results = await platform.list_validation_results(str(arguments["target_id"]))
        return {"count": len(results), "results": results}

    async def get_drift(arguments: dict[str, Any]) -> dict[str, Any]:
        records = await platform.get_configuration_drift(
            str(arguments["organization_id"]), str(arguments["profile_id"])
        )
        return {"count": len(records), "drift": records}

    async def list_executions(arguments: dict[str, Any]) -> dict[str, Any]:
        executions = await platform.list_automation_executions(str(arguments["organization_id"]))
        return {"count": len(executions), "executions": executions}

    return {
        "inventory_list_assets": list_assets,
        "inventory_get_asset": get_asset,
        "inventory_get_topology": get_topology,
        "alerting_list_alerts": list_alerts,
        "monitoring_get_health": get_health,
        "monitoring_get_statistics": get_statistics,
        "validation_list_results": list_validation,
        "configuration_get_drift": get_drift,
        "automation_list_executions": list_executions,
    }


def build_builtin_registry(platform: PlatformClient) -> ToolHandlerRegistry:
    """A registry pre-loaded with every built-in handler."""
    return ToolHandlerRegistry(build_builtin_handlers(platform))


def missing_handlers(handlers: dict[str, ToolHandler]) -> list[str]:
    """Definitions with no handler -- should always be empty.

    Exists so a test can assert the two halves stayed in sync rather
    than discovering the drift when a model requests a tool that
    cannot run.
    """
    return sorted(
        definition.tool_key
        for definition in BUILTIN_TOOL_DEFINITIONS
        if definition.tool_key not in handlers
    )


__all__ = [
    "BUILTIN_TOOL_DEFINITIONS",
    "BuiltinToolDefinition",
    "build_builtin_handlers",
    "build_builtin_registry",
    "missing_handlers",
]
