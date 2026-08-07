"""Model Context Protocol client + server (docs/060 "MCP SUPPORT")."""

from __future__ import annotations

from app.mcp.client import McpClient
from app.mcp.protocol import (
    INTERNAL_ERROR,
    INVALID_PARAMS,
    INVALID_REQUEST,
    MCP_PROTOCOL_VERSION,
    METHOD_NOT_FOUND,
    PARSE_ERROR,
    JsonRpcError,
    JsonRpcRequest,
    JsonRpcResponse,
    McpCapabilities,
)
from app.mcp.server import CallTool, McpServer, McpSession

__all__ = [
    "INTERNAL_ERROR",
    "INVALID_PARAMS",
    "INVALID_REQUEST",
    "MCP_PROTOCOL_VERSION",
    "METHOD_NOT_FOUND",
    "PARSE_ERROR",
    "CallTool",
    "JsonRpcError",
    "JsonRpcRequest",
    "JsonRpcResponse",
    "McpCapabilities",
    "McpClient",
    "McpServer",
    "McpSession",
]
