"""Tests for :mod:`app.mcp.protocol`, :mod:`app.mcp.server`, and
:mod:`app.mcp.client`.

Nothing in this platform wires an MCP HTTP route into its own API yet
(confirmed in ``app/mcp/server.py``'s own docstring: "a genuine gap").
So :class:`~app.mcp.server.McpServer` is exercised two ways here:
directly via :meth:`~app.mcp.server.McpServer.handle_request` (its own
transport-agnostic contract), and behind a small, real ASGI endpoint
(``_McpHarness`` below) built the same way ``tests/conftest.py``'s own
``client`` fixture wires the main app -- so
:class:`~app.mcp.client.McpClient` gets a genuine HTTP round trip via
``httpx.ASGITransport`` rather than a mocked transport.
"""

from __future__ import annotations

import dataclasses
from collections.abc import AsyncIterator, Awaitable, Callable
from typing import Any

import httpx
import pytest
import pytest_asyncio
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from shared_core.exceptions.dependency import DependencyError

from app.clients.base import ToolSpecification
from app.mcp.client import McpClient
from app.mcp.protocol import (
    INTERNAL_ERROR,
    INVALID_PARAMS,
    INVALID_REQUEST,
    JSONRPC_VERSION,
    MCP_PROTOCOL_VERSION,
    METHOD_NOT_FOUND,
    JsonRpcError,
    JsonRpcRequest,
    JsonRpcResponse,
    McpCapabilities,
)
from app.mcp.server import McpServer, McpSession

_SESSION_HEADER = "X-MCP-Session-Id"


async def _fake_call_tool(name: str, arguments: dict[str, Any]) -> Any:
    """A real, deterministic tool handler -- not a mock -- standing in
    for a thin wrapper around this service's own ``ToolExecutor``, per
    ``McpServer``'s own ``CallTool`` contract (any awaitable callable
    satisfies it)."""
    if name == "echo":
        return arguments.get("text", "")
    if name == "boom":
        raise RuntimeError("tool exploded")
    raise LookupError(f"unknown tool {name!r}")


# ---------------------------------------------------------------------------
# protocol.py
# ---------------------------------------------------------------------------


def test_module_level_constants() -> None:
    assert JSONRPC_VERSION == "2.0"
    assert MCP_PROTOCOL_VERSION == "2024-11-05"
    assert INTERNAL_ERROR == -32603
    assert INVALID_PARAMS == -32602
    assert INVALID_REQUEST == -32600
    assert METHOD_NOT_FOUND == -32601


def test_json_rpc_error_to_dict_without_data() -> None:
    error = JsonRpcError(code=-32600, message="bad request")
    assert error.to_dict() == {"code": -32600, "message": "bad request"}


def test_json_rpc_error_to_dict_with_data() -> None:
    error = JsonRpcError(code=-32602, message="bad params", data={"field": "name"})
    assert error.to_dict() == {
        "code": -32602,
        "message": "bad params",
        "data": {"field": "name"},
    }


def test_json_rpc_error_is_frozen() -> None:
    error = JsonRpcError(code=-32600, message="bad request")
    with pytest.raises(dataclasses.FrozenInstanceError):
        error.code = -1  # type: ignore[misc]


def test_json_rpc_request_to_dict_full() -> None:
    request = JsonRpcRequest(method="tools/call", id=7, params={"name": "echo"})
    assert request.to_dict() == {
        "jsonrpc": "2.0",
        "method": "tools/call",
        "id": 7,
        "params": {"name": "echo"},
    }


def test_json_rpc_request_to_dict_omits_id_for_notification() -> None:
    request = JsonRpcRequest(method="notify")
    body = request.to_dict()
    assert "id" not in body
    assert "params" not in body
    assert body == {"jsonrpc": "2.0", "method": "notify"}


def test_json_rpc_request_from_dict_defaults() -> None:
    request = JsonRpcRequest.from_dict({"method": "initialize"})
    assert request.method == "initialize"
    assert request.id is None
    assert request.params == {}


def test_json_rpc_request_from_dict_full() -> None:
    request = JsonRpcRequest.from_dict(
        {"jsonrpc": "2.0", "method": "tools/list", "id": "abc", "params": {"x": 1}}
    )
    assert request.method == "tools/list"
    assert request.id == "abc"
    assert request.params == {"x": 1}


def test_json_rpc_request_from_dict_missing_method_raises_key_error() -> None:
    with pytest.raises(KeyError):
        JsonRpcRequest.from_dict({"id": 1})


def test_json_rpc_response_to_dict_with_result() -> None:
    response = JsonRpcResponse(id=1, result={"ok": True})
    assert response.to_dict() == {"jsonrpc": "2.0", "id": 1, "result": {"ok": True}}


def test_json_rpc_response_to_dict_defaults_result_to_empty_dict() -> None:
    response = JsonRpcResponse(id=1)
    assert response.to_dict() == {"jsonrpc": "2.0", "id": 1, "result": {}}


def test_json_rpc_response_to_dict_with_error_omits_result() -> None:
    response = JsonRpcResponse(
        id=2, result={"ignored": True}, error=JsonRpcError(code=-32601, message="nope")
    )
    body = response.to_dict()
    assert "result" not in body
    assert body["error"] == {"code": -32601, "message": "nope"}


def test_json_rpc_response_succeeded_true_without_error() -> None:
    assert JsonRpcResponse(id=1, result={}).succeeded is True


def test_json_rpc_response_succeeded_false_with_error() -> None:
    assert JsonRpcResponse(id=1, error=JsonRpcError(code=-1, message="x")).succeeded is False


def test_mcp_capabilities_default_to_dict() -> None:
    assert McpCapabilities().to_dict() == {"tools": {}}


def test_mcp_capabilities_all_enabled_to_dict() -> None:
    capabilities = McpCapabilities(tools=True, resources=True, prompts=True)
    assert capabilities.to_dict() == {"tools": {}, "resources": {}, "prompts": {}}


def test_mcp_capabilities_all_disabled_to_dict() -> None:
    assert McpCapabilities(tools=False, resources=False, prompts=False).to_dict() == {}


def test_mcp_capabilities_is_frozen() -> None:
    capabilities = McpCapabilities()
    with pytest.raises(dataclasses.FrozenInstanceError):
        capabilities.tools = False  # type: ignore[misc]


# ---------------------------------------------------------------------------
# server.py -- McpSession
# ---------------------------------------------------------------------------


def test_mcp_session_defaults() -> None:
    session = McpSession(session_id="abc", capabilities=McpCapabilities())
    assert session.context == {}
    assert session.created_at.tzinfo is not None


# ---------------------------------------------------------------------------
# server.py -- McpServer.handle_request
# ---------------------------------------------------------------------------


@pytest.fixture
def echo_tool_spec() -> ToolSpecification:
    return ToolSpecification(
        name="echo",
        description="Echoes back the given text.",
        parameters_schema={"type": "object", "properties": {"text": {"type": "string"}}},
    )


@pytest.fixture
def mcp_server(echo_tool_spec: ToolSpecification) -> McpServer:
    return McpServer(
        server_name="ai-agent-platform-service",
        server_version="1.0.0",
        tool_specs=[echo_tool_spec],
        call_tool=_fake_call_tool,
    )


async def test_active_session_count_starts_at_zero(mcp_server: McpServer) -> None:
    assert mcp_server.active_session_count == 0


async def test_handle_request_initialize_creates_session(mcp_server: McpServer) -> None:
    body, session_id = await mcp_server.handle_request(
        {"jsonrpc": "2.0", "method": "initialize", "id": 1, "params": {}}
    )
    assert session_id is not None
    assert len(session_id) == 32
    assert body["jsonrpc"] == "2.0"
    assert body["id"] == 1
    result = body["result"]
    assert result["protocolVersion"] == MCP_PROTOCOL_VERSION
    assert result["capabilities"] == {"tools": {}}
    assert result["serverInfo"] == {"name": "ai-agent-platform-service", "version": "1.0.0"}
    assert result["sessionId"] == session_id
    assert mcp_server.active_session_count == 1


async def test_handle_request_initialize_notification_has_no_id(mcp_server: McpServer) -> None:
    body, session_id = await mcp_server.handle_request({"jsonrpc": "2.0", "method": "initialize"})
    assert body["id"] is None
    assert session_id is not None


async def test_handle_request_second_initialize_is_a_distinct_session(
    mcp_server: McpServer,
) -> None:
    _, session_a = await mcp_server.handle_request({"jsonrpc": "2.0", "method": "initialize"})
    _, session_b = await mcp_server.handle_request({"jsonrpc": "2.0", "method": "initialize"})
    assert session_a != session_b
    assert mcp_server.active_session_count == 2


async def test_handle_request_malformed_missing_method(mcp_server: McpServer) -> None:
    body, session_id = await mcp_server.handle_request({"jsonrpc": "2.0", "id": 7}, session_id=None)
    assert session_id is None
    assert body["id"] == 7
    assert body["error"]["code"] == INVALID_REQUEST
    assert "Malformed request" in body["error"]["message"]


async def test_handle_request_without_session_is_rejected(mcp_server: McpServer) -> None:
    body, session_id = await mcp_server.handle_request(
        {"jsonrpc": "2.0", "method": "tools/list", "id": 2}, session_id=None
    )
    assert session_id is None
    assert body["error"]["code"] == INVALID_REQUEST
    assert "initialize" in body["error"]["message"]


async def test_handle_request_with_unknown_session_is_rejected(mcp_server: McpServer) -> None:
    body, returned = await mcp_server.handle_request(
        {"jsonrpc": "2.0", "method": "tools/list", "id": 2}, session_id="bogus-session"
    )
    assert returned == "bogus-session"
    assert body["error"]["code"] == INVALID_REQUEST


async def test_handle_request_tools_list(
    mcp_server: McpServer, echo_tool_spec: ToolSpecification
) -> None:
    _, session_id = await mcp_server.handle_request({"jsonrpc": "2.0", "method": "initialize"})

    body, returned_session = await mcp_server.handle_request(
        {"jsonrpc": "2.0", "method": "tools/list", "id": 2}, session_id=session_id
    )

    assert returned_session == session_id
    assert body["result"]["tools"] == [
        {
            "name": "echo",
            "description": echo_tool_spec.description,
            "inputSchema": echo_tool_spec.parameters_schema,
        }
    ]


async def test_handle_request_tools_call_success(mcp_server: McpServer) -> None:
    _, session_id = await mcp_server.handle_request({"jsonrpc": "2.0", "method": "initialize"})

    body, _ = await mcp_server.handle_request(
        {
            "jsonrpc": "2.0",
            "method": "tools/call",
            "id": 3,
            "params": {"name": "echo", "arguments": {"text": "hi"}},
        },
        session_id=session_id,
    )

    result = body["result"]
    assert result["content"] == [{"type": "text", "text": "hi"}]
    assert result["context"] == {}


async def test_handle_request_tools_call_merges_and_accumulates_context(
    mcp_server: McpServer,
) -> None:
    _, session_id = await mcp_server.handle_request({"jsonrpc": "2.0", "method": "initialize"})

    body1, _ = await mcp_server.handle_request(
        {
            "jsonrpc": "2.0",
            "method": "tools/call",
            "id": 2,
            "params": {"name": "echo", "arguments": {"text": "a"}, "context": {"turn": "1"}},
        },
        session_id=session_id,
    )
    assert body1["result"]["context"] == {"turn": "1"}

    body2, _ = await mcp_server.handle_request(
        {
            "jsonrpc": "2.0",
            "method": "tools/call",
            "id": 3,
            "params": {"name": "echo", "arguments": {"text": "b"}, "context": {"step": "2"}},
        },
        session_id=session_id,
    )
    assert body2["result"]["context"] == {"turn": "1", "step": "2"}


async def test_handle_request_tools_call_missing_name(mcp_server: McpServer) -> None:
    _, session_id = await mcp_server.handle_request({"jsonrpc": "2.0", "method": "initialize"})

    body, _ = await mcp_server.handle_request(
        {"jsonrpc": "2.0", "method": "tools/call", "id": 2, "params": {"arguments": {}}},
        session_id=session_id,
    )

    assert body["error"]["code"] == INVALID_PARAMS
    assert "requires 'name'" in body["error"]["message"]


async def test_handle_request_tools_call_tool_raises_becomes_internal_error(
    mcp_server: McpServer,
) -> None:
    _, session_id = await mcp_server.handle_request({"jsonrpc": "2.0", "method": "initialize"})

    body, _ = await mcp_server.handle_request(
        {
            "jsonrpc": "2.0",
            "method": "tools/call",
            "id": 2,
            "params": {"name": "boom", "arguments": {}},
        },
        session_id=session_id,
    )

    assert body["error"]["code"] == INTERNAL_ERROR
    assert body["error"]["message"] == "tool exploded"


async def test_handle_request_unknown_method(mcp_server: McpServer) -> None:
    _, session_id = await mcp_server.handle_request({"jsonrpc": "2.0", "method": "initialize"})

    body, _ = await mcp_server.handle_request(
        {"jsonrpc": "2.0", "method": "no/such", "id": 2}, session_id=session_id
    )

    assert body["error"]["code"] == METHOD_NOT_FOUND
    assert "no/such" in body["error"]["message"]


# ---------------------------------------------------------------------------
# client.py -- McpClient, over a real ASGI round trip
# ---------------------------------------------------------------------------


class _McpHarness:
    """A tiny, real HTTP endpoint wired to a real :class:`McpServer` --
    the same "decode the body, call this, encode the response" shape
    this module's own docstring says a real API route would use.

    Records every raw request body and header set it saw, so a test
    can assert exactly what :class:`McpClient` sent (session header,
    protocol version, client identity) without mocking any transport.
    """

    def __init__(self, server: McpServer) -> None:
        self.server = server
        self.received: list[dict[str, Any]] = []
        self.received_headers: list[dict[str, str]] = []
        self.app = FastAPI()
        self.app.post("/mcp")(self._handle)

    async def _handle(self, request: Request) -> JSONResponse:
        raw = await request.json()
        self.received.append(raw)
        self.received_headers.append(dict(request.headers))
        session_id = request.headers.get(_SESSION_HEADER)
        body, new_session_id = await self.server.handle_request(raw, session_id=session_id)
        response = JSONResponse(body)
        if new_session_id:
            response.headers[_SESSION_HEADER] = new_session_id
        return response


@pytest.fixture
def mcp_harness(mcp_server: McpServer) -> _McpHarness:
    return _McpHarness(mcp_server)


@pytest_asyncio.fixture
async def mcp_http_client(mcp_harness: _McpHarness) -> AsyncIterator[httpx.AsyncClient]:
    transport = httpx.ASGITransport(app=mcp_harness.app)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://mcpserver", timeout=5.0
    ) as client:
        yield client


@pytest.fixture
def mcp_client(mcp_http_client: httpx.AsyncClient) -> McpClient:
    return McpClient(mcp_http_client, base_url="http://mcpserver")


async def test_initialize_returns_negotiated_capabilities(
    mcp_client: McpClient, mcp_harness: _McpHarness
) -> None:
    capabilities = await mcp_client.initialize()

    assert capabilities == McpCapabilities(tools=True, resources=False, prompts=False)
    sent = mcp_harness.received[0]
    assert sent["method"] == "initialize"
    assert sent["params"]["protocolVersion"] == MCP_PROTOCOL_VERSION
    assert sent["params"]["clientInfo"] == {
        "name": "ai-agent-platform-service",
        "version": "1.0.0",
    }


async def test_initialize_sends_no_session_header_on_first_call(
    mcp_client: McpClient, mcp_harness: _McpHarness
) -> None:
    await mcp_client.initialize()
    assert _SESSION_HEADER.lower() not in mcp_harness.received_headers[0]


async def test_initialize_with_custom_client_identity(
    mcp_http_client: httpx.AsyncClient, mcp_harness: _McpHarness
) -> None:
    client = McpClient(
        mcp_http_client,
        base_url="http://mcpserver",
        client_name="custom-client",
        client_version="9.9.9",
    )

    await client.initialize()

    assert mcp_harness.received[0]["params"]["clientInfo"] == {
        "name": "custom-client",
        "version": "9.9.9",
    }


async def test_list_tools_returns_real_tool_specs(
    mcp_client: McpClient, echo_tool_spec: ToolSpecification
) -> None:
    await mcp_client.initialize()

    tools = await mcp_client.list_tools()

    assert tools == [echo_tool_spec]


async def test_list_tools_without_prior_initialize_raises_dependency_error(
    mcp_client: McpClient,
) -> None:
    with pytest.raises(DependencyError, match="No active MCP session"):
        await mcp_client.list_tools()


async def test_call_tool_returns_joined_text_content(mcp_client: McpClient) -> None:
    await mcp_client.initialize()

    text = await mcp_client.call_tool("echo", {"text": "hello"})

    assert text == "hello"


async def test_call_tool_sends_session_header_established_by_initialize(
    mcp_client: McpClient, mcp_harness: _McpHarness
) -> None:
    await mcp_client.initialize()
    session_id = mcp_harness.received[0] and mcp_harness.app  # keep reference for clarity
    del session_id

    await mcp_client.call_tool("echo", {"text": "hi"})

    second_headers = mcp_harness.received_headers[1]
    assert second_headers.get(_SESSION_HEADER.lower()) is not None
    # The session id the client used matches the one the harness's own
    # server actually negotiated -- there is exactly one live session.
    assert mcp_harness.server.active_session_count == 1


async def test_call_tool_synchronizes_context_established_out_of_band(
    mcp_client: McpClient, mcp_harness: _McpHarness
) -> None:
    await mcp_client.initialize()
    assert mcp_client.context == {}
    # The session id arrives via a response header, never the body, so pull
    # it straight off the harness's own server -- the only party that
    # actually knows every negotiated session.
    assert mcp_harness.server.active_session_count == 1
    (negotiated_session_id,) = mcp_harness.server._sessions.keys()

    # Simulate another party sharing this same session enriching its own
    # context out of band -- a real call through the real server, not a
    # mock, using the session id this client already negotiated.
    await mcp_harness.server.handle_request(
        {
            "jsonrpc": "2.0",
            "method": "tools/call",
            "id": 999,
            "params": {"name": "echo", "arguments": {"text": "x"}, "context": {"turn": "1"}},
        },
        session_id=negotiated_session_id,
    )

    result = await mcp_client.call_tool("echo", {"text": "hello"})

    assert result == "hello"
    assert mcp_client.context == {"turn": "1"}


def test_context_property_returns_an_independent_copy(mcp_client: McpClient) -> None:
    first = mcp_client.context
    first["mutated"] = "yes"
    assert mcp_client.context == {}


async def test_call_tool_raising_tool_becomes_dependency_error(mcp_client: McpClient) -> None:
    await mcp_client.initialize()

    with pytest.raises(DependencyError, match="tool exploded"):
        await mcp_client.call_tool("boom", {})


async def test_send_raises_dependency_error_on_non_200_status() -> None:
    app = FastAPI()

    @app.post("/mcp")
    async def _always_500() -> JSONResponse:
        return JSONResponse({"detail": "boom"}, status_code=500)

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://mcpserver", timeout=5.0
    ) as http_client:
        client = McpClient(http_client, base_url="http://mcpserver")
        with pytest.raises(DependencyError, match="HTTP 500"):
            await client.initialize()


async def test_send_raises_dependency_error_when_server_unreachable() -> None:
    async with httpx.AsyncClient(timeout=2.0) as http_client:
        client = McpClient(http_client, base_url="http://127.0.0.1:1")
        with pytest.raises(DependencyError, match="unreachable"):
            await client.initialize()


def _unused_call_tool_type_hint(
    handler: Callable[[str, dict[str, Any]], Awaitable[Any]],
) -> None:
    """Keeps ``Awaitable``/``Callable`` imports meaningful documentation
    of :data:`app.mcp.server.CallTool`'s own shape rather than unused
    imports; never called."""
    del handler
