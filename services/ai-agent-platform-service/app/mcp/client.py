"""MCP client: use an external MCP server's own tools (docs/060 "MCP
SUPPORT": Model Context Protocol Client, Dynamic Tool Discovery, Remote
Tool Invocation, Context Synchronization, Secure Sessions, Capability
Negotiation).

Plain ``httpx`` against a documented JSON-RPC-over-HTTP endpoint, the
same "no vendor SDK, one client per real wire format" shape every
provider client in :mod:`app.clients` already uses.
"""

from __future__ import annotations

from typing import Any

import httpx
from shared_core.exceptions.dependency import DependencyError

from app.clients.base import ToolSpecification
from app.mcp.protocol import MCP_PROTOCOL_VERSION, JsonRpcRequest, McpCapabilities

_SESSION_HEADER = "X-MCP-Session-Id"


class McpClient:
    """Calls a remote MCP server as a client, over HTTP JSON-RPC."""

    def __init__(
        self,
        client: httpx.AsyncClient,
        *,
        base_url: str,
        client_name: str = "ai-agent-platform-service",
        client_version: str = "1.0.0",
    ) -> None:
        self._client = client
        self._base_url = base_url.rstrip("/")
        self._client_name = client_name
        self._client_version = client_version
        self._session_id: str | None = None
        self._context: dict[str, Any] = {}
        self._request_id = 0

    @property
    def context(self) -> dict[str, Any]:
        """This session's own running "Context Synchronization" state."""
        return dict(self._context)

    def _next_id(self) -> int:
        self._request_id += 1
        return self._request_id

    async def _send(self, method: str, params: dict[str, Any]) -> dict[str, Any]:
        """Send one JSON-RPC request and return its own result object.

        Raises:
            DependencyError: If the server is unreachable, returns a
                non-200, or answers with a JSON-RPC error.
        """
        request = JsonRpcRequest(method=method, id=self._next_id(), params=params)
        headers = {_SESSION_HEADER: self._session_id} if self._session_id else {}
        try:
            response = await self._client.post(
                f"{self._base_url}/mcp", json=request.to_dict(), headers=headers
            )
        except httpx.HTTPError as exc:
            raise DependencyError(f"MCP server unreachable: {exc}") from exc
        if response.status_code != httpx.codes.OK:
            raise DependencyError(
                f"MCP server returned HTTP {response.status_code} for method {method!r}."
            )

        body = response.json()
        if "error" in body:
            error = body["error"]
            raise DependencyError(
                f"MCP server error {error.get('code')}: {error.get('message', 'unknown error')}"
            )
        session_id = response.headers.get(_SESSION_HEADER)
        if session_id:
            self._session_id = session_id
        return dict(body.get("result") or {})

    async def initialize(self) -> McpCapabilities:
        """ "Capability Negotiation" -- open a session and learn what
        the server supports.

        Raises:
            DependencyError: If the server is unreachable or refuses.
        """
        result = await self._send(
            "initialize",
            {
                "protocolVersion": MCP_PROTOCOL_VERSION,
                "capabilities": McpCapabilities().to_dict(),
                "clientInfo": {"name": self._client_name, "version": self._client_version},
            },
        )
        if result.get("sessionId"):
            self._session_id = str(result["sessionId"])
        capabilities = result.get("capabilities") or {}
        return McpCapabilities(
            tools="tools" in capabilities,
            resources="resources" in capabilities,
            prompts="prompts" in capabilities,
        )

    async def list_tools(self) -> list[ToolSpecification]:
        """ "Dynamic Tool Discovery" -- the remote server's own current tool set."""
        result = await self._send("tools/list", {})
        return [
            ToolSpecification(
                name=str(tool["name"]),
                description=str(tool.get("description", "")),
                parameters_schema=dict(tool.get("inputSchema") or {}),
            )
            for tool in result.get("tools", [])
        ]

    async def call_tool(self, name: str, arguments: dict[str, Any]) -> str:
        """ "Remote Tool Invocation" -- run one of the remote server's
        own tools and return its text content.

        Merges this session's own running context into the request and
        merges back whatever context the server returns, so a later
        call on the same session sees what earlier ones established.
        """
        result = await self._send(
            "tools/call", {"name": name, "arguments": arguments, "context": self._context}
        )
        if "context" in result:
            self._context.update(result["context"])
        content = result.get("content") or []
        return "".join(str(part.get("text", "")) for part in content if isinstance(part, dict))


__all__ = ["McpClient"]
