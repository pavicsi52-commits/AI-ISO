"""Concrete tool-kind handlers (docs/060 "TOOL EXECUTION").

Each ``build_*_handler`` closes over whatever real dependency that kind
needs (an HTTP client, the sandbox, a live cross-service client) and
returns a plain :data:`~app.tool_registry.registry.ToolHandler` --
arguments in, JSON-shaped result out -- so
:class:`~app.tool_execution.executor.ToolExecutor` never needs to know
which kind it is calling.

**Two of docs/060's ten kinds are deliberately not built here:**

- ``WORKFLOW`` -- wiring an in-process
  :class:`shared_core.workflow.engine.WorkflowEngine` run needs the
  same real, repository-backed checkpoint persistence
  :mod:`app.langgraph` builds over :class:`~app.models.workflow
  .AgentWorkflow`; building a disposable engine wiring here first would
  just be redone there.
- ``CUSTOM`` -- has no generic implementation by design. It is the
  platform's own extension point: whoever registers a ``CUSTOM`` tool
  supplies its own handler directly to
  :class:`~app.tool_registry.registry.ToolHandlerRegistry`.

``CONNECTOR_SDK`` and ``AUTOMATION`` share one implementation: a
connector-typed automation job is just an automation job pre-configured
with the right target, the same reasoning
:class:`~app.clients.automation_client.AutomationClient`'s own
docstring already gives for why one client covers both.
"""

from __future__ import annotations

import sys
from typing import Any
from uuid import UUID

import httpx
from shared_core.exceptions.dependency import DependencyError
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.clients.automation_client import AutomationClient
from app.graph.client import GraphClient
from app.sandbox.policy import AgentSandboxPolicy
from app.sandbox.process import run_isolated, run_script_isolated
from app.tool_registry.registry import ToolHandler

MAX_DATABASE_QUERY_ROWS = 1_000
"""A tool result is redacted and fed back into an agent's own context
-- an unbounded row count would blow past every model's context window
long before it blew past the database's own."""


def build_rest_handler(client: httpx.AsyncClient) -> ToolHandler:
    """Build the handler for a ``REST`` tool.

    Arguments: ``method`` (default ``"GET"``), ``url`` (required),
    ``params``, ``json``, ``headers``.
    """

    async def handler(arguments: dict[str, Any]) -> dict[str, Any]:
        url = arguments.get("url")
        if not url:
            raise ValueError("REST tool call is missing required argument 'url'.")
        method = str(arguments.get("method", "GET")).upper()
        try:
            response = await client.request(
                method,
                str(url),
                params=arguments.get("params"),
                json=arguments.get("json"),
                headers=arguments.get("headers"),
            )
        except httpx.HTTPError as exc:
            raise DependencyError(f"REST tool call to {url!r} failed: {exc}") from exc
        body: Any
        try:
            body = response.json()
        except ValueError:
            body = response.text
        return {"status_code": response.status_code, "body": body}

    return handler


def build_shell_handler(policy: AgentSandboxPolicy) -> ToolHandler:
    """Build the handler for a ``SHELL`` tool.

    Arguments: ``command`` -- an argv list, never a shell string, so
    there is no shell-injection surface from interpolated content.
    """

    async def handler(arguments: dict[str, Any]) -> dict[str, Any]:
        command = arguments.get("command")
        if not command or not isinstance(command, list):
            raise ValueError("SHELL tool call requires a non-empty 'command' argv list.")
        result = await run_isolated([str(part) for part in command], policy=policy)
        return {
            "exit_code": result.exit_code,
            "stdout": result.stdout,
            "stderr": result.stderr,
            "succeeded": result.succeeded,
        }

    return handler


def build_python_handler(policy: AgentSandboxPolicy) -> ToolHandler:
    """Build the handler for a ``PYTHON`` tool.

    Arguments: ``script`` -- source run under the sandbox's own Python
    interpreter, isolated to its own throwaway working directory.
    """

    async def handler(arguments: dict[str, Any]) -> dict[str, Any]:
        script = arguments.get("script")
        if not script or not isinstance(script, str):
            raise ValueError("PYTHON tool call requires a non-empty string 'script'.")
        result = await run_script_isolated([sys.executable], script, suffix=".py", policy=policy)
        return {
            "exit_code": result.exit_code,
            "stdout": result.stdout,
            "stderr": result.stderr,
            "succeeded": result.succeeded,
        }

    return handler


def build_automation_handler(client: AutomationClient) -> ToolHandler:
    """Build the handler for an ``AUTOMATION`` or ``CONNECTOR_SDK`` tool.

    Arguments: ``job_id`` (required), ``variables``, ``target_ids``,
    ``timeout_seconds``.
    """

    async def handler(arguments: dict[str, Any]) -> dict[str, Any]:
        job_id = arguments.get("job_id")
        if not job_id:
            raise ValueError("AUTOMATION tool call is missing required argument 'job_id'.")
        target_ids = arguments.get("target_ids") or []
        execution = await client.execute_and_wait(
            UUID(str(job_id)),
            variables=dict(arguments.get("variables") or {}),
            target_ids=[UUID(str(target_id)) for target_id in target_ids],
            timeout_seconds=arguments.get("timeout_seconds"),
        )
        return dict(execution)

    return handler


def build_knowledge_graph_query_handler(client: GraphClient) -> ToolHandler:
    """Build the handler for a ``KNOWLEDGE_GRAPH_QUERY`` tool.

    Arguments: ``cypher`` (required), ``parameters``, ``max_records``.
    Always opens a **read** transaction -- see
    :meth:`~app.graph.client.GraphClient.read`'s own docstring for why a
    write clause in agent-authored Cypher fails at the database.
    """

    async def handler(arguments: dict[str, Any]) -> dict[str, Any]:
        cypher = arguments.get("cypher")
        if not cypher or not isinstance(cypher, str):
            raise ValueError(
                "KNOWLEDGE_GRAPH_QUERY tool call requires a non-empty 'cypher' string."
            )
        result = await client.read(
            cypher,
            dict(arguments.get("parameters") or {}),
            max_records=arguments.get("max_records"),
        )
        return {
            "records": result.records,
            "row_count": result.row_count,
            "truncated": result.truncated,
        }

    return handler


def build_database_query_handler(session: AsyncSession, sql_template: str) -> ToolHandler:
    """Build the handler for one ``DATABASE_QUERY`` tool.

    *sql_template* is set once, by whoever registers the tool (stored
    in the tool's own :attr:`~app.models.tool.AgentTool.metadata_`) --
    never supplied by the model. Only the bind parameter **values**
    come from ``arguments``, passed through :func:`sqlalchemy.text`'s
    own parameter binding, never string-interpolated.

    A naive but real first-line guard: only a statement that is
    (syntactically) a ``SELECT`` is accepted. Defence in depth, not a
    guarantee -- the same "honest limit" this platform's own guardrail
    engine already documents for pattern-based checks.

    Raises:
        ValueError: If *sql_template* is not a ``SELECT`` statement.
    """
    if not sql_template.strip().upper().startswith("SELECT"):
        raise ValueError("DATABASE_QUERY tool's own sql_template must be a SELECT statement.")

    async def handler(arguments: dict[str, Any]) -> dict[str, Any]:
        result = await session.execute(text(sql_template), arguments)
        rows = [dict(row._mapping) for row in result.fetchmany(MAX_DATABASE_QUERY_ROWS)]
        return {
            "rows": rows,
            "row_count": len(rows),
            "truncated": len(rows) == MAX_DATABASE_QUERY_ROWS,
        }

    return handler


def build_webhook_handler(client: httpx.AsyncClient) -> ToolHandler:
    """Build the handler for a ``WEBHOOK`` tool.

    Arguments: ``url`` (required), ``method`` (default ``"POST"``),
    ``payload``. A genuine outbound HTTP call, never simulated --
    mirrors ``workflow-runtime-service``'s own ``WEBHOOK`` node handler
    shape.
    """

    async def handler(arguments: dict[str, Any]) -> dict[str, Any]:
        url = arguments.get("url")
        if not url:
            raise ValueError("WEBHOOK tool call is missing required argument 'url'.")
        method = str(arguments.get("method", "POST")).upper()
        try:
            response = await client.request(
                method, str(url), json=dict(arguments.get("payload") or {})
            )
        except httpx.HTTPError as exc:
            raise DependencyError(f"Webhook call to {url!r} failed: {exc}") from exc
        return {"status_code": response.status_code}

    return handler


__all__ = [
    "MAX_DATABASE_QUERY_ROWS",
    "build_automation_handler",
    "build_database_query_handler",
    "build_knowledge_graph_query_handler",
    "build_python_handler",
    "build_rest_handler",
    "build_shell_handler",
    "build_webhook_handler",
]
