"""Builds a real :class:`~app.tool_registry.registry.ToolHandlerRegistry`
from one agent's own registered :class:`~app.models.tool.AgentTool`
rows (docs/060 "TOOL EXECUTION").

Built fresh per execution, never cached across calls: ``AUTOMATION``/
``CONNECTOR_SDK`` tools need an :class:`~app.clients.automation_client
.AutomationClient` carrying *this* call's own ``caller_token`` -- an
agent's own automation tool call must act with the authority of
whoever triggered it, the same precedent
:mod:`app.clients.automation_client`'s own docstring already
establishes.

A tool whose own kind has no client configured on this deployment (no
Neo4j, say) is skipped rather than registered with a handler that
would only fail -- :meth:`~app.tool_registry.registry
.ToolHandlerRegistry.get` already reports "no registered handler" as
a clean denial, which is a more honest outcome than registering a
handler doomed to raise.
"""

from __future__ import annotations

from dataclasses import dataclass

import httpx
from shared_core.logging.logger import get_logger
from sqlalchemy.ext.asyncio import AsyncSession

from app.clients.automation_client import AutomationClient
from app.graph.client import GraphClient
from app.models.enums import ToolKind
from app.models.tool import AgentTool
from app.sandbox.policy import AgentSandboxPolicy
from app.tool_execution.handlers import (
    build_automation_handler,
    build_database_query_handler,
    build_knowledge_graph_query_handler,
    build_python_handler,
    build_rest_handler,
    build_shell_handler,
    build_webhook_handler,
)
from app.tool_registry.registry import ToolHandler, ToolHandlerRegistry

logger = get_logger("app.services.tool_handlers")


@dataclass(frozen=True, slots=True)
class HandlerDependencies:
    """Every real dependency a tool's own kind might need to build its handler."""

    http_client: httpx.AsyncClient
    sandbox_policy: AgentSandboxPolicy
    automation_client: AutomationClient | None
    graph_client: GraphClient | None
    session: AsyncSession | None


def _build_simple(kind: ToolKind, deps: HandlerDependencies) -> ToolHandler | None:
    """The four kinds whose own handler needs no availability check --
    their dependency (an HTTP client or the sandbox policy) is always
    present."""
    builders: dict[ToolKind, ToolHandler] = {
        ToolKind.REST: build_rest_handler(deps.http_client),
        ToolKind.WEBHOOK: build_webhook_handler(deps.http_client),
        ToolKind.SHELL: build_shell_handler(deps.sandbox_policy),
        ToolKind.PYTHON: build_python_handler(deps.sandbox_policy),
    }
    return builders.get(kind)


def _build_one(tool: AgentTool, kind: ToolKind, deps: HandlerDependencies) -> ToolHandler | None:
    """Build *tool*'s own handler, or ``None`` when this deployment has
    no client its kind needs.

    ``WORKFLOW`` is handled directly by ``ExecutionService`` via
    ``WorkflowPersistenceService``, never through this generic
    registry; ``CUSTOM`` has no generic implementation by design --
    both simply have no branch here and fall through to ``None``.
    """
    simple = _build_simple(kind, deps)
    if simple is not None:
        return simple

    if kind in (ToolKind.AUTOMATION, ToolKind.CONNECTOR_SDK) and deps.automation_client is not None:
        return build_automation_handler(deps.automation_client)

    if (
        kind is ToolKind.KNOWLEDGE_GRAPH_QUERY
        and deps.graph_client is not None
        and deps.graph_client.enabled
    ):
        return build_knowledge_graph_query_handler(deps.graph_client)

    if kind is ToolKind.DATABASE_QUERY and deps.session is not None:
        sql_template = tool.metadata_.get("sql_template") if tool.metadata_ else None
        if sql_template:
            return _build_database_query(tool, str(sql_template), deps)

    return None


def _build_database_query(
    tool: AgentTool, sql_template: str, deps: HandlerDependencies
) -> ToolHandler | None:
    """Build one ``DATABASE_QUERY`` handler, or ``None`` when its own
    stored ``sql_template`` is rejected.

    A template that is not a ``SELECT`` is a misconfiguration of *that
    one tool row*, so it is skipped exactly like an unavailable client
    -- letting the :class:`ValueError` escape would take every other
    tool in the same execution down with it, which is the opposite of
    what this module's own "skip rather than register a handler doomed
    to raise" rule is for.
    """
    if deps.session is None:  # pragma: no cover - guarded by the caller
        return None
    try:
        return build_database_query_handler(deps.session, sql_template)
    except ValueError as exc:
        logger.warning(
            "Skipping a DATABASE_QUERY tool whose own sql_template was rejected.",
            extra={"extra_fields": {"tool_key": tool.tool_key, "error": str(exc)}},
        )
        return None


def build_handler_registry(
    tools: list[AgentTool],
    *,
    http_client: httpx.AsyncClient,
    sandbox_policy: AgentSandboxPolicy,
    automation_client: AutomationClient | None,
    graph_client: GraphClient | None,
    session: AsyncSession | None,
) -> ToolHandlerRegistry:
    """Register one real handler per tool, skipping any kind this
    deployment has no client for."""
    deps = HandlerDependencies(
        http_client=http_client,
        sandbox_policy=sandbox_policy,
        automation_client=automation_client,
        graph_client=graph_client,
        session=session,
    )
    registry = ToolHandlerRegistry()
    for tool in tools:
        kind = tool.tool_kind if isinstance(tool.tool_kind, ToolKind) else ToolKind(tool.tool_kind)
        handler = _build_one(tool, kind, deps)
        if handler is None:
            logger.warning(
                "Skipping tool with no available handler dependency for its own kind.",
                extra={"extra_fields": {"tool_key": tool.tool_key, "tool_kind": str(kind)}},
            )
            continue
        registry.register(tool.tool_key, handler)
    return registry


__all__ = ["HandlerDependencies", "build_handler_registry"]
