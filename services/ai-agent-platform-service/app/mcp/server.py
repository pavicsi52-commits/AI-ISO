"""MCP server: expose this service's own tools to external MCP clients
(docs/060 "MCP SUPPORT": Model Context Protocol Server, Dynamic Tool
Discovery, Remote Tool Invocation, Secure Sessions, Capability
Negotiation).

Transport-agnostic on purpose: :meth:`McpServer.handle_request` takes
and returns plain JSON-RPC dicts, so the actual HTTP route (added in
this service's own API layer) is a thin wrapper -- decode the body,
call this, encode the response. This mirrors every other genuinely
new protocol surface in this codebase (e.g. ``services/knowledge
-graph-service``'s own ``POST /graph/cypher``): the protocol logic and
the transport plumbing stay separate.

**Secure Sessions**: every method except ``initialize`` requires a
live ``session_id`` obtained from a prior ``initialize`` call -- a
client that never negotiated a session cannot list or call tools.
Sessions carry no expiry here (there is no session-sweep worker); a
production deployment fronts this with whatever session-timeout policy
its own transport layer enforces.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from app.clients.base import ToolSpecification
from app.mcp.protocol import (
    INTERNAL_ERROR,
    INVALID_PARAMS,
    INVALID_REQUEST,
    MCP_PROTOCOL_VERSION,
    METHOD_NOT_FOUND,
    JsonRpcError,
    JsonRpcRequest,
    JsonRpcResponse,
    McpCapabilities,
)

CallTool = Callable[[str, dict[str, Any]], Awaitable[Any]]
"""Invokes one tool by name; arguments in, a JSON-shaped result out.
Satisfied by a thin wrapper around this service's own
:class:`~app.tool_execution.executor.ToolExecutor`."""


@dataclass(slots=True)
class McpSession:
    """One negotiated MCP session ("Secure Sessions")."""

    session_id: str
    capabilities: McpCapabilities
    context: dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))


class McpServer:
    """Answers MCP JSON-RPC requests over this service's own tool set."""

    def __init__(
        self,
        *,
        server_name: str,
        server_version: str,
        tool_specs: list[ToolSpecification],
        call_tool: CallTool,
    ) -> None:
        self._server_name = server_name
        self._server_version = server_version
        self._tool_specs = tool_specs
        self._call_tool = call_tool
        self._sessions: dict[str, McpSession] = {}

    @property
    def active_session_count(self) -> int:
        """How many sessions are currently negotiated."""
        return len(self._sessions)

    async def handle_request(
        self, raw: dict[str, Any], *, session_id: str | None = None
    ) -> tuple[dict[str, Any], str | None]:
        """Answer one JSON-RPC request.

        Returns ``(response_body, session_id)`` -- the second element
        is the session id the caller should use (and persist, e.g. as
        an HTTP header) on every subsequent call; it changes only on a
        successful ``initialize``.
        """
        try:
            request = JsonRpcRequest.from_dict(raw)
        except KeyError as exc:
            error = JsonRpcResponse(
                id=raw.get("id"),
                error=JsonRpcError(INVALID_REQUEST, f"Malformed request: {exc}"),
            )
            return error.to_dict(), session_id

        if request.method == "initialize":
            return self._handle_initialize(request)

        session = self._sessions.get(session_id or "")
        if session is None:
            error = JsonRpcResponse(
                id=request.id,
                error=JsonRpcError(
                    INVALID_REQUEST, "No active MCP session; call 'initialize' first."
                ),
            )
            return error.to_dict(), session_id

        if request.method == "tools/list":
            return self._handle_tools_list(request), session_id
        if request.method == "tools/call":
            return await self._handle_tools_call(request, session), session_id

        error = JsonRpcResponse(
            id=request.id,
            error=JsonRpcError(METHOD_NOT_FOUND, f"Unknown method {request.method!r}."),
        )
        return error.to_dict(), session_id

    def _handle_initialize(self, request: JsonRpcRequest) -> tuple[dict[str, Any], str]:
        """ "Capability Negotiation" -- create a fresh session and
        report what this server supports."""
        session = McpSession(session_id=uuid4().hex, capabilities=McpCapabilities())
        self._sessions[session.session_id] = session
        result = JsonRpcResponse(
            id=request.id,
            result={
                "protocolVersion": MCP_PROTOCOL_VERSION,
                "capabilities": session.capabilities.to_dict(),
                "serverInfo": {"name": self._server_name, "version": self._server_version},
                "sessionId": session.session_id,
            },
        )
        return result.to_dict(), session.session_id

    def _handle_tools_list(self, request: JsonRpcRequest) -> dict[str, Any]:
        """ "Dynamic Tool Discovery" -- this server's own tool set, live."""
        tools = [
            {
                "name": spec.name,
                "description": spec.description,
                "inputSchema": spec.parameters_schema,
            }
            for spec in self._tool_specs
        ]
        return JsonRpcResponse(id=request.id, result={"tools": tools}).to_dict()

    async def _handle_tools_call(
        self, request: JsonRpcRequest, session: McpSession
    ) -> dict[str, Any]:
        """ "Remote Tool Invocation" plus "Context Synchronization" --
        merges any caller-sent context into the session before calling,
        and returns the session's own running context back with the
        result so a client can merge it into its own state.
        """
        name = request.params.get("name")
        if not name:
            error = JsonRpcResponse(
                id=request.id, error=JsonRpcError(INVALID_PARAMS, "tools/call requires 'name'.")
            )
            return error.to_dict()

        session.context.update(request.params.get("context") or {})
        arguments = dict(request.params.get("arguments") or {})
        try:
            outcome = await self._call_tool(str(name), arguments)
        except Exception as exc:
            error = JsonRpcResponse(id=request.id, error=JsonRpcError(INTERNAL_ERROR, str(exc)))
            return error.to_dict()

        return JsonRpcResponse(
            id=request.id,
            result={
                "content": [{"type": "text", "text": str(outcome)}],
                "context": session.context,
            },
        ).to_dict()


__all__ = ["CallTool", "McpServer", "McpSession"]
