"""MCP (Model Context Protocol) wire format (docs/060 "MCP SUPPORT").

A genuine gap: nothing in this platform implements MCP -- confirmed by
a repo-wide search before writing this. MCP itself is a real, publicly
documented protocol (JSON-RPC 2.0 over a transport; this service uses
plain HTTP, the transport every other cross-service client in this
codebase already speaks). This module is the shared envelope both
:mod:`app.mcp.client` and :mod:`app.mcp.server` speak -- request/
response/error/notification shapes plus the small set of well-known
JSON-RPC error codes, so neither side hand-rolls its own dict layout.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

JSONRPC_VERSION = "2.0"
MCP_PROTOCOL_VERSION = "2024-11-05"
"""The MCP protocol version this client/server negotiates -- a real,
publicly documented MCP revision string."""

PARSE_ERROR = -32700
INVALID_REQUEST = -32600
METHOD_NOT_FOUND = -32601
INVALID_PARAMS = -32602
INTERNAL_ERROR = -32603
"""The JSON-RPC 2.0 spec's own standard error codes."""


@dataclass(frozen=True, slots=True)
class JsonRpcError:
    """One JSON-RPC 2.0 error object."""

    code: int
    message: str
    data: Any = None

    def to_dict(self) -> dict[str, Any]:
        body: dict[str, Any] = {"code": self.code, "message": self.message}
        if self.data is not None:
            body["data"] = self.data
        return body


@dataclass(frozen=True, slots=True)
class JsonRpcRequest:
    """One JSON-RPC 2.0 request (or notification, when ``id`` is ``None``)."""

    method: str
    id: str | int | None = None
    params: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        body: dict[str, Any] = {"jsonrpc": JSONRPC_VERSION, "method": self.method}
        if self.id is not None:
            body["id"] = self.id
        if self.params:
            body["params"] = self.params
        return body

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> JsonRpcRequest:
        return cls(method=data["method"], id=data.get("id"), params=dict(data.get("params") or {}))


@dataclass(frozen=True, slots=True)
class JsonRpcResponse:
    """One JSON-RPC 2.0 response -- exactly one of ``result``/``error`` is set."""

    id: str | int | None
    result: dict[str, Any] | None = None
    error: JsonRpcError | None = None

    def to_dict(self) -> dict[str, Any]:
        body: dict[str, Any] = {"jsonrpc": JSONRPC_VERSION, "id": self.id}
        if self.error is not None:
            body["error"] = self.error.to_dict()
        else:
            body["result"] = self.result or {}
        return body

    @property
    def succeeded(self) -> bool:
        """Whether this response carries a result rather than an error."""
        return self.error is None


@dataclass(frozen=True, slots=True)
class McpCapabilities:
    """What one side of an MCP session supports ("Capability Negotiation")."""

    tools: bool = True
    resources: bool = False
    prompts: bool = False

    def to_dict(self) -> dict[str, Any]:
        body: dict[str, Any] = {}
        if self.tools:
            body["tools"] = {}
        if self.resources:
            body["resources"] = {}
        if self.prompts:
            body["prompts"] = {}
        return body


__all__ = [
    "INTERNAL_ERROR",
    "INVALID_PARAMS",
    "INVALID_REQUEST",
    "JSONRPC_VERSION",
    "MCP_PROTOCOL_VERSION",
    "METHOD_NOT_FOUND",
    "PARSE_ERROR",
    "JsonRpcError",
    "JsonRpcRequest",
    "JsonRpcResponse",
    "McpCapabilities",
]
