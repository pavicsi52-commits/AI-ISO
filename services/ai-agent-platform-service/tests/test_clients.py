"""Model-provider, automation, and policy-engine clients -- all real HTTP.

No local model backend (Ollama/vLLM/OpenAI/Anthropic/Gemini) is
guaranteed reachable or credentialed in this environment (see
``tests/conftest.py``'s own module docstring), so these tests use two
genuinely real targets instead of ever mocking ``httpx``:

- ``UNREACHABLE_BASE_URL`` (``http://127.0.0.1:1``) -- a real loopback
  port nothing listens on, so a client's own "the provider is
  unreachable" branch is exercised by a real, fast connection refusal.
- ``fake_server`` -- a genuine local ``http.server`` bound to
  ``127.0.0.1`` on an OS-assigned port, run in a background thread for
  the duration of one test. httpx performs a real TCP connect and a
  real HTTP/1.1 round trip against it; nothing about the client under
  test, or about ``httpx`` itself, is patched or intercepted. This is
  the only way to exercise a *successful* response's translation logic
  without a live, credentialed vendor account -- the same reasoning
  behind constructing a client directly with a deliberately bad
  ``base_url`` for the failure paths.

``OllamaClient`` additionally gets one test against its real default,
IPv4-explicit endpoint (``http://127.0.0.1:11434``), adapting to
whichever real outcome this environment has -- reachable or not.
"""

from __future__ import annotations

import json
import threading
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import parse_qs, urlsplit
from uuid import uuid4

import httpx
import pytest
import pytest_asyncio
from shared_core.exceptions.ai import AIError
from shared_core.exceptions.dependency import DependencyError

from app.clients.anthropic_client import ANTHROPIC_VERSION, AnthropicClient
from app.clients.automation_client import AutomationClient
from app.clients.base import (
    ChatCompletion,
    ChatMessage,
    ModelClient,
    RequestedToolCall,
    ToolSpecification,
)
from app.clients.dispatch import dispatch_chat
from app.clients.gemini_client import GeminiClient
from app.clients.ollama_client import OllamaClient
from app.clients.openai_compatible import OpenAiCompatibleClient
from app.clients.policy_engine_client import PolicyDecision, PolicyEngineClient
from app.clients.registry import ModelRegistry, build_model_clients
from app.config.settings import AiAgentPlatformServiceSettings
from app.models.enums import ModelProvider, RoutingStrategy
from app.models.profile import AgentProfile

UNREACHABLE_BASE_URL = "http://127.0.0.1:1"
"""A real loopback port nothing listens on: fails fast, never mocked."""

MESSAGES = [
    ChatMessage(role="system", content="You are a test assistant."),
    ChatMessage(role="user", content="Is the service healthy?"),
]

TOOL = ToolSpecification(
    name="lookup", description="Looks something up.", parameters_schema={"type": "object"}
)


# ---- a genuine local HTTP server, not a mock of httpx -----------------------


@dataclass
class CapturedRequest:
    """One request the fake server actually received, over a real socket."""

    method: str
    raw_path: str
    headers: dict[str, str]
    body: bytes = field(default=b"")

    @property
    def path(self) -> str:
        return urlsplit(self.raw_path).path

    @property
    def query(self) -> dict[str, str]:
        parsed = parse_qs(urlsplit(self.raw_path).query)
        return {key: values[0] for key, values in parsed.items()}

    def json(self) -> Any:
        return json.loads(self.body) if self.body else None


class _RealHttpServer:
    """A real ``http.server`` on ``127.0.0.1``, run in a background thread.

    Queued responses are served in order, oldest first; every received
    request is recorded. Real sockets, real HTTP parsing -- the client
    under test never knows this isn't a genuine vendor endpoint.
    """

    def __init__(self) -> None:
        self.requests: list[CapturedRequest] = []
        self._responses: list[tuple[int, bytes]] = []
        outer = self

        class Handler(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def _respond(self) -> None:
                length = int(self.headers.get("Content-Length") or 0)
                body = self.rfile.read(length) if length else b""
                outer.requests.append(
                    CapturedRequest(
                        method=self.command,
                        raw_path=self.path,
                        headers={key.lower(): value for key, value in self.headers.items()},
                        body=body,
                    )
                )
                if outer._responses:
                    status, payload = outer._responses.pop(0)
                else:
                    status, payload = 200, b"{}"
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)

            def do_POST(self) -> None:
                self._respond()

            def do_GET(self) -> None:
                self._respond()

            def log_message(self, log_format: str, *args: Any) -> None:
                pass

        self._httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self._thread = threading.Thread(target=self._httpd.serve_forever, daemon=True)
        self._thread.start()

    @property
    def base_url(self) -> str:
        return f"http://127.0.0.1:{self._httpd.server_address[1]}"

    def queue_response(self, status: int, body: dict[str, Any] | list[Any]) -> None:
        self._responses.append((status, json.dumps(body).encode("utf-8")))

    def close(self) -> None:
        self._httpd.shutdown()
        self._httpd.server_close()


@pytest.fixture
def fake_server() -> AsyncIterator[_RealHttpServer]:  # type: ignore[misc]
    server = _RealHttpServer()
    try:
        yield server  # type: ignore[misc]
    finally:
        server.close()


@pytest_asyncio.fixture
async def local_http_client() -> AsyncIterator[httpx.AsyncClient]:
    """A short-timeout client for tests that deliberately hit a dead port."""
    async with httpx.AsyncClient(timeout=5.0) as client:
        yield client


# ---- app/clients/base.py -----------------------------------------------------


class TestBaseTypes:
    def test_chat_message_defaults_and_is_frozen(self) -> None:
        message = ChatMessage(role="user", content="hi")
        assert message.tool_call_id is None
        assert message.tool_name is None
        with pytest.raises(AttributeError):
            message.content = "changed"  # type: ignore[misc]

    def test_tool_specification_fields(self) -> None:
        spec = ToolSpecification(
            name="lookup", description="Looks things up.", parameters_schema={"type": "object"}
        )
        assert spec.name == "lookup"
        assert spec.parameters_schema == {"type": "object"}

    def test_requested_tool_call_fields(self) -> None:
        call = RequestedToolCall(call_id="1", name="lookup", arguments={"x": 1})
        assert call.call_id == "1"
        assert call.arguments == {"x": 1}

    def test_chat_completion_defaults(self) -> None:
        completion = ChatCompletion(content="hi", model="m", provider="p")
        assert completion.prompt_tokens == 0
        assert completion.completion_tokens == 0
        assert completion.latency_ms == 0.0
        assert completion.tool_calls == []
        assert completion.finish_reason is None

    async def test_every_real_client_satisfies_the_model_client_protocol(
        self, local_http_client: httpx.AsyncClient
    ) -> None:
        clients: list[ModelClient] = [
            AnthropicClient(local_http_client, base_url="https://example.test", api_key="k"),
            GeminiClient(local_http_client, base_url="https://example.test", api_key="k"),
            OllamaClient(local_http_client, base_url="https://example.test"),
            OpenAiCompatibleClient(
                local_http_client, base_url="https://example.test", api_key="k", provider="openai"
            ),
        ]
        for client in clients:
            assert isinstance(client, ModelClient)
            assert isinstance(client.provider, str)


# ---- app/clients/openai_compatible.py -----------------------------------------


class TestOpenAiCompatibleClient:
    def _client(
        self, http_client: httpx.AsyncClient, fake_server: _RealHttpServer, **kwargs: Any
    ) -> OpenAiCompatibleClient:
        return OpenAiCompatibleClient(
            http_client,
            base_url=fake_server.base_url,
            api_key="sk-test",
            provider="openai",
            **kwargs,
        )

    async def test_documented_response_is_translated(
        self, http_client: httpx.AsyncClient, fake_server: _RealHttpServer
    ) -> None:
        fake_server.queue_response(
            200,
            {
                "id": "chatcmpl-1",
                "model": "gpt-4o-2024-08-06",
                "choices": [
                    {
                        "index": 0,
                        "message": {"role": "assistant", "content": "It is healthy."},
                        "finish_reason": "stop",
                    }
                ],
                "usage": {"prompt_tokens": 42, "completion_tokens": 7},
            },
        )
        completion = await self._client(http_client, fake_server).chat(MESSAGES, model="gpt-4o")

        assert completion.content == "It is healthy."
        assert completion.model == "gpt-4o-2024-08-06"
        assert completion.provider == "openai"
        assert completion.prompt_tokens == 42
        assert completion.completion_tokens == 7
        assert completion.finish_reason == "stop"
        assert completion.latency_ms >= 0
        assert fake_server.requests[0].path == "/chat/completions"

    async def test_request_carries_auth_and_parameters(
        self, http_client: httpx.AsyncClient, fake_server: _RealHttpServer
    ) -> None:
        fake_server.queue_response(200, {"choices": [{"message": {"content": "ok"}}], "usage": {}})
        await self._client(http_client, fake_server).chat(
            MESSAGES, model="gpt-4o", temperature=0.7, max_tokens=256, tools=[TOOL]
        )

        request = fake_server.requests[0]
        assert request.headers["authorization"] == "Bearer sk-test"
        payload = request.json()
        assert payload["temperature"] == 0.7
        assert payload["max_tokens"] == 256
        assert payload["messages"][0] == {
            "role": "system",
            "content": "You are a test assistant.",
        }
        assert payload["tools"][0]["function"]["name"] == "lookup"

    async def test_azure_sends_its_api_version_as_a_query_parameter(
        self, http_client: httpx.AsyncClient, fake_server: _RealHttpServer
    ) -> None:
        fake_server.queue_response(200, {"choices": [{"message": {"content": "ok"}}], "usage": {}})
        await self._client(http_client, fake_server, api_version="2024-02-01").chat(
            MESSAGES, model="gpt-4o"
        )
        assert fake_server.requests[0].query["api-version"] == "2024-02-01"

    async def test_no_api_key_omits_the_authorization_header(
        self, http_client: httpx.AsyncClient, fake_server: _RealHttpServer
    ) -> None:
        fake_server.queue_response(200, {"choices": [{"message": {"content": "ok"}}], "usage": {}})
        client = OpenAiCompatibleClient(
            http_client, base_url=fake_server.base_url, api_key="", provider="vllm"
        )
        await client.chat(MESSAGES, model="local-model")
        assert "authorization" not in fake_server.requests[0].headers

    async def test_tool_call_arguments_are_parsed_from_a_json_string(
        self, http_client: httpx.AsyncClient, fake_server: _RealHttpServer
    ) -> None:
        fake_server.queue_response(
            200,
            {
                "choices": [
                    {
                        "message": {
                            "content": None,
                            "tool_calls": [
                                {
                                    "id": "call_abc",
                                    "type": "function",
                                    "function": {
                                        "name": "lookup",
                                        "arguments": '{"organization_id": "org-1"}',
                                    },
                                }
                            ],
                        },
                        "finish_reason": "tool_calls",
                    }
                ],
                "usage": {},
            },
        )
        completion = await self._client(http_client, fake_server).chat(MESSAGES, model="gpt-4o")

        assert completion.content == ""
        assert len(completion.tool_calls) == 1
        assert completion.tool_calls[0].call_id == "call_abc"
        assert completion.tool_calls[0].arguments == {"organization_id": "org-1"}

    async def test_malformed_tool_arguments_are_dropped_not_fatal(
        self, http_client: httpx.AsyncClient, fake_server: _RealHttpServer
    ) -> None:
        fake_server.queue_response(
            200,
            {
                "choices": [
                    {
                        "message": {
                            "content": "I will answer directly.",
                            "tool_calls": [
                                {
                                    "id": "call_bad",
                                    "function": {"name": "x", "arguments": "{not json"},
                                },
                                {"id": "call_none", "function": {"arguments": "{}"}},
                                {
                                    "id": "call_list",
                                    "function": {"name": "y", "arguments": "[1, 2]"},
                                },
                            ],
                        }
                    }
                ],
                "usage": {},
            },
        )
        completion = await self._client(http_client, fake_server).chat(MESSAGES, model="gpt-4o")

        assert completion.tool_calls == []
        assert completion.content == "I will answer directly."

    async def test_tool_result_message_is_sent_with_its_call_id(
        self, http_client: httpx.AsyncClient, fake_server: _RealHttpServer
    ) -> None:
        fake_server.queue_response(200, {"choices": [{"message": {"content": "ok"}}], "usage": {}})
        await self._client(http_client, fake_server).chat(
            [
                *MESSAGES,
                ChatMessage(
                    role="tool",
                    content='{"assets": []}',
                    tool_call_id="call_abc",
                    tool_name="lookup",
                ),
            ],
            model="gpt-4o",
        )
        payload = fake_server.requests[0].json()
        assert payload["messages"][-1] == {
            "role": "tool",
            "content": '{"assets": []}',
            "tool_call_id": "call_abc",
        }

    @pytest.mark.parametrize("status", [400, 401, 429, 500, 503])
    async def test_non_200_status_becomes_ai_error(
        self, http_client: httpx.AsyncClient, fake_server: _RealHttpServer, status: int
    ) -> None:
        fake_server.queue_response(status, {"error": "nope"})
        with pytest.raises(AIError, match=f"HTTP {status}"):
            await self._client(http_client, fake_server).chat(MESSAGES, model="gpt-4o")

    async def test_empty_choices_becomes_ai_error(
        self, http_client: httpx.AsyncClient, fake_server: _RealHttpServer
    ) -> None:
        fake_server.queue_response(200, {"choices": [], "usage": {}})
        with pytest.raises(AIError, match="no choices"):
            await self._client(http_client, fake_server).chat(MESSAGES, model="gpt-4o")

    async def test_transport_failure_becomes_ai_error(
        self, local_http_client: httpx.AsyncClient
    ) -> None:
        client = OpenAiCompatibleClient(
            local_http_client, base_url=UNREACHABLE_BASE_URL, api_key="sk-test", provider="openai"
        )
        with pytest.raises(AIError, match="unreachable"):
            await client.chat(MESSAGES, model="gpt-4o")


# ---- app/clients/anthropic_client.py -------------------------------------------


class TestAnthropicClient:
    def _client(
        self, http_client: httpx.AsyncClient, fake_server: _RealHttpServer
    ) -> AnthropicClient:
        return AnthropicClient(http_client, base_url=fake_server.base_url, api_key="sk-ant-test")

    async def test_documented_response_is_translated(
        self, http_client: httpx.AsyncClient, fake_server: _RealHttpServer
    ) -> None:
        fake_server.queue_response(
            200,
            {
                "id": "msg_1",
                "type": "message",
                "role": "assistant",
                "model": "claude-sonnet-4-5",
                "content": [{"type": "text", "text": "It is healthy."}],
                "stop_reason": "end_turn",
                "usage": {"input_tokens": 42, "output_tokens": 7},
            },
        )
        completion = await self._client(http_client, fake_server).chat(
            MESSAGES, model="claude-sonnet-4-5"
        )

        assert completion.content == "It is healthy."
        assert completion.provider == "anthropic"
        assert completion.prompt_tokens == 42
        assert completion.completion_tokens == 7
        assert completion.finish_reason == "end_turn"
        assert fake_server.requests[0].path == "/messages"

    async def test_system_prompt_is_hoisted_out_of_the_message_list(
        self, http_client: httpx.AsyncClient, fake_server: _RealHttpServer
    ) -> None:
        fake_server.queue_response(200, {"content": [{"type": "text", "text": "ok"}], "usage": {}})
        await self._client(http_client, fake_server).chat(MESSAGES, model="claude-sonnet-4-5")

        request = fake_server.requests[0]
        payload = request.json()
        assert payload["system"] == "You are a test assistant."
        assert [message["role"] for message in payload["messages"]] == ["user"]
        assert request.headers["x-api-key"] == "sk-ant-test"
        assert request.headers["anthropic-version"] == ANTHROPIC_VERSION

    async def test_no_system_message_omits_the_system_field(
        self, http_client: httpx.AsyncClient, fake_server: _RealHttpServer
    ) -> None:
        fake_server.queue_response(200, {"content": [], "usage": {}})
        await self._client(http_client, fake_server).chat(
            [ChatMessage(role="user", content="hi")], model="claude-sonnet-4-5"
        )
        assert "system" not in fake_server.requests[0].json()

    async def test_tool_role_is_delivered_as_a_user_turn(
        self, http_client: httpx.AsyncClient, fake_server: _RealHttpServer
    ) -> None:
        fake_server.queue_response(200, {"content": [{"type": "text", "text": "ok"}], "usage": {}})
        await self._client(http_client, fake_server).chat(
            [
                *MESSAGES,
                ChatMessage(role="assistant", content="checking"),
                ChatMessage(role="tool", content="result", tool_call_id="t1"),
            ],
            model="claude-sonnet-4-5",
        )
        payload = fake_server.requests[0].json()
        assert [message["role"] for message in payload["messages"]] == [
            "user",
            "assistant",
            "user",
        ]

    async def test_interleaved_text_and_tool_use_blocks(
        self, http_client: httpx.AsyncClient, fake_server: _RealHttpServer
    ) -> None:
        fake_server.queue_response(
            200,
            {
                "content": [
                    {"type": "text", "text": "Let me check. "},
                    {
                        "type": "tool_use",
                        "id": "toolu_1",
                        "name": "lookup",
                        "input": {"organization_id": "org-1"},
                    },
                    {"type": "text", "text": "One moment."},
                ],
                "stop_reason": "tool_use",
                "usage": {"input_tokens": 1, "output_tokens": 2},
            },
        )
        completion = await self._client(http_client, fake_server).chat(
            MESSAGES, model="claude-sonnet-4-5"
        )

        assert completion.content == "Let me check. One moment."
        assert len(completion.tool_calls) == 1
        assert completion.tool_calls[0].call_id == "toolu_1"
        assert completion.tool_calls[0].arguments == {"organization_id": "org-1"}

    async def test_tools_use_input_schema_not_parameters(
        self, http_client: httpx.AsyncClient, fake_server: _RealHttpServer
    ) -> None:
        fake_server.queue_response(200, {"content": [], "usage": {}})
        await self._client(http_client, fake_server).chat(
            MESSAGES, model="claude-sonnet-4-5", tools=[TOOL]
        )
        payload = fake_server.requests[0].json()
        assert "input_schema" in payload["tools"][0]
        assert "parameters" not in payload["tools"][0]

    async def test_non_200_status_becomes_ai_error(
        self, http_client: httpx.AsyncClient, fake_server: _RealHttpServer
    ) -> None:
        fake_server.queue_response(429, {"error": {}})
        with pytest.raises(AIError, match="HTTP 429"):
            await self._client(http_client, fake_server).chat(MESSAGES, model="claude-sonnet-4-5")

    async def test_transport_failure_becomes_ai_error(
        self, local_http_client: httpx.AsyncClient
    ) -> None:
        client = AnthropicClient(
            local_http_client, base_url=UNREACHABLE_BASE_URL, api_key="sk-ant-test"
        )
        with pytest.raises(AIError, match="unreachable"):
            await client.chat(MESSAGES, model="claude-sonnet-4-5")


# ---- app/clients/gemini_client.py --------------------------------------------


class TestGeminiClient:
    def _client(self, http_client: httpx.AsyncClient, fake_server: _RealHttpServer) -> GeminiClient:
        return GeminiClient(http_client, base_url=fake_server.base_url, api_key="key-test")

    async def test_documented_response_is_translated(
        self, http_client: httpx.AsyncClient, fake_server: _RealHttpServer
    ) -> None:
        fake_server.queue_response(
            200,
            {
                "candidates": [
                    {
                        "content": {"parts": [{"text": "It is healthy."}], "role": "model"},
                        "finishReason": "STOP",
                    }
                ],
                "usageMetadata": {"promptTokenCount": 42, "candidatesTokenCount": 7},
            },
        )
        completion = await self._client(http_client, fake_server).chat(
            MESSAGES, model="gemini-2.0-flash"
        )

        assert completion.content == "It is healthy."
        assert completion.provider == "google_gemini"
        assert completion.prompt_tokens == 42
        assert completion.completion_tokens == 7
        assert completion.finish_reason == "STOP"

    async def test_model_is_in_the_path_and_key_in_the_query(
        self, http_client: httpx.AsyncClient, fake_server: _RealHttpServer
    ) -> None:
        fake_server.queue_response(200, {"candidates": [{"content": {"parts": []}}]})
        await self._client(http_client, fake_server).chat(MESSAGES, model="gemini-2.0-flash")

        request = fake_server.requests[0]
        assert request.path.endswith("/models/gemini-2.0-flash:generateContent")
        assert request.query["key"] == "key-test"

    async def test_assistant_role_is_renamed_to_model(
        self, http_client: httpx.AsyncClient, fake_server: _RealHttpServer
    ) -> None:
        fake_server.queue_response(200, {"candidates": [{"content": {"parts": []}}]})
        await self._client(http_client, fake_server).chat(
            [*MESSAGES, ChatMessage(role="assistant", content="checking")],
            model="gemini-2.0-flash",
        )
        payload = fake_server.requests[0].json()
        assert [turn["role"] for turn in payload["contents"]] == ["user", "model"]
        assert payload["systemInstruction"]["parts"][0]["text"] == "You are a test assistant."

    async def test_generation_config_carries_the_parameters(
        self, http_client: httpx.AsyncClient, fake_server: _RealHttpServer
    ) -> None:
        fake_server.queue_response(200, {"candidates": [{"content": {"parts": []}}]})
        await self._client(http_client, fake_server).chat(
            MESSAGES, model="gemini-2.0-flash", temperature=0.9, max_tokens=128, tools=[TOOL]
        )
        payload = fake_server.requests[0].json()
        assert payload["generationConfig"] == {"temperature": 0.9, "maxOutputTokens": 128}
        declarations = payload["tools"][0]["functionDeclarations"]
        assert declarations[0]["name"] == "lookup"

    async def test_function_call_part_is_parsed(
        self, http_client: httpx.AsyncClient, fake_server: _RealHttpServer
    ) -> None:
        fake_server.queue_response(
            200,
            {
                "candidates": [
                    {
                        "content": {
                            "parts": [
                                {"text": "Checking. "},
                                {
                                    "functionCall": {
                                        "name": "lookup",
                                        "args": {"organization_id": "org-1"},
                                    }
                                },
                            ]
                        }
                    }
                ]
            },
        )
        completion = await self._client(http_client, fake_server).chat(
            MESSAGES, model="gemini-2.0-flash"
        )
        assert completion.content == "Checking. "
        assert completion.tool_calls[0].name == "lookup"
        assert completion.tool_calls[0].arguments == {"organization_id": "org-1"}

    async def test_no_candidates_becomes_ai_error(
        self, http_client: httpx.AsyncClient, fake_server: _RealHttpServer
    ) -> None:
        fake_server.queue_response(200, {"candidates": []})
        with pytest.raises(AIError, match="no candidates"):
            await self._client(http_client, fake_server).chat(MESSAGES, model="gemini-2.0-flash")

    async def test_non_200_status_becomes_ai_error(
        self, http_client: httpx.AsyncClient, fake_server: _RealHttpServer
    ) -> None:
        fake_server.queue_response(403, {})
        with pytest.raises(AIError, match="HTTP 403"):
            await self._client(http_client, fake_server).chat(MESSAGES, model="gemini-2.0-flash")

    async def test_transport_failure_becomes_ai_error(
        self, local_http_client: httpx.AsyncClient
    ) -> None:
        client = GeminiClient(local_http_client, base_url=UNREACHABLE_BASE_URL, api_key="key-test")
        with pytest.raises(AIError, match="unreachable"):
            await client.chat(MESSAGES, model="gemini-2.0-flash")


# ---- app/clients/ollama_client.py -----------------------------------------------


class TestOllamaClient:
    def _client(self, http_client: httpx.AsyncClient, fake_server: _RealHttpServer) -> OllamaClient:
        return OllamaClient(http_client, base_url=fake_server.base_url)

    async def test_documented_response_is_translated(
        self, http_client: httpx.AsyncClient, fake_server: _RealHttpServer
    ) -> None:
        fake_server.queue_response(
            200,
            {
                "model": "llama3.1",
                "message": {"role": "assistant", "content": "It is healthy."},
                "done": True,
                "done_reason": "stop",
                "prompt_eval_count": 42,
                "eval_count": 7,
            },
        )
        completion = await self._client(http_client, fake_server).chat(MESSAGES, model="llama3.1")

        assert completion.content == "It is healthy."
        assert completion.provider == "ollama"
        assert completion.prompt_tokens == 42
        assert completion.completion_tokens == 7
        assert completion.finish_reason == "stop"
        assert fake_server.requests[0].path == "/api/chat"

    async def test_stream_false_is_sent_explicitly(
        self, http_client: httpx.AsyncClient, fake_server: _RealHttpServer
    ) -> None:
        fake_server.queue_response(200, {"message": {"content": "ok"}})
        await self._client(http_client, fake_server).chat(
            MESSAGES, model="llama3.1", temperature=0.5, max_tokens=64
        )
        payload = fake_server.requests[0].json()
        assert payload["stream"] is False
        assert payload["options"] == {"temperature": 0.5, "num_predict": 64}

    async def test_missing_message_defaults_to_empty_content(
        self, http_client: httpx.AsyncClient, fake_server: _RealHttpServer
    ) -> None:
        fake_server.queue_response(200, {"done": True})
        completion = await self._client(http_client, fake_server).chat(MESSAGES, model="llama3.1")
        assert completion.content == ""

    async def test_tool_call_is_parsed_from_the_message(
        self, http_client: httpx.AsyncClient, fake_server: _RealHttpServer
    ) -> None:
        fake_server.queue_response(
            200,
            {
                "message": {
                    "role": "assistant",
                    "content": "",
                    "tool_calls": [
                        {"function": {"name": "lookup", "arguments": {"organization_id": "org-1"}}}
                    ],
                }
            },
        )
        completion = await self._client(http_client, fake_server).chat(MESSAGES, model="llama3.1")
        assert completion.tool_calls[0].name == "lookup"
        assert completion.tool_calls[0].arguments == {"organization_id": "org-1"}

    async def test_non_200_status_becomes_ai_error(
        self, http_client: httpx.AsyncClient, fake_server: _RealHttpServer
    ) -> None:
        fake_server.queue_response(404, {"error": "model not found"})
        with pytest.raises(AIError, match="HTTP 404"):
            await self._client(http_client, fake_server).chat(MESSAGES, model="missing")

    async def test_transport_failure_becomes_ai_error(
        self, local_http_client: httpx.AsyncClient
    ) -> None:
        client = OllamaClient(local_http_client, base_url=UNREACHABLE_BASE_URL)
        with pytest.raises(AIError, match="unreachable"):
            await client.chat(MESSAGES, model="llama3.1")

    async def test_real_default_ollama_endpoint(self, local_http_client: httpx.AsyncClient) -> None:
        # IPv4-explicit -- never "localhost" (tests/conftest.py's own
        # module docstring on Docker's broken IPv6 loopback). No local
        # Ollama daemon is guaranteed running in every environment this
        # suite executes in, so a genuine connection failure is an
        # accepted, expected outcome; this test adapts to whichever real
        # outcome this environment actually has.
        client = OllamaClient(local_http_client, base_url="http://127.0.0.1:11434")
        try:
            completion = await client.chat(MESSAGES, model="llama3")
        except AIError as exc:
            assert "ollama" in str(exc)
        else:
            assert completion.provider == "ollama"


# ---- app/clients/automation_client.py -------------------------------------------


class TestAutomationClient:
    def _client(
        self, http_client: httpx.AsyncClient, fake_server: _RealHttpServer, **kwargs: Any
    ) -> AutomationClient:
        kwargs.setdefault("poll_interval_seconds", 0.01)
        kwargs.setdefault("max_poll_attempts", 5)
        return AutomationClient(
            http_client, base_url=fake_server.base_url, caller_token="caller-token-abc", **kwargs
        )

    async def test_execute_and_wait_polls_until_completed(
        self, http_client: httpx.AsyncClient, fake_server: _RealHttpServer
    ) -> None:
        job_id = uuid4()
        fake_server.queue_response(201, {"data": {"id": "exec-1"}})
        fake_server.queue_response(200, {"data": {"status": "running"}})
        fake_server.queue_response(200, {"data": {"status": "completed", "result": {"ok": True}}})

        execution = await self._client(http_client, fake_server).execute_and_wait(
            job_id, variables={"x": 1}, target_ids=[uuid4()], timeout_seconds=30
        )

        assert execution["status"] == "completed"
        assert execution["result"] == {"ok": True}
        assert len(fake_server.requests) == 3
        assert fake_server.requests[0].path == f"/automation/jobs/{job_id}/execute"
        assert fake_server.requests[1].path == "/automation/executions/exec-1"
        assert fake_server.requests[2].path == "/automation/executions/exec-1"

    async def test_caller_token_is_sent_as_a_bearer_header(
        self, http_client: httpx.AsyncClient, fake_server: _RealHttpServer
    ) -> None:
        fake_server.queue_response(201, {"data": {"id": "exec-1"}})
        fake_server.queue_response(200, {"data": {"status": "completed"}})
        await self._client(http_client, fake_server).execute_and_wait(uuid4(), variables={})
        assert fake_server.requests[0].headers["authorization"] == "Bearer caller-token-abc"
        assert fake_server.requests[1].headers["authorization"] == "Bearer caller-token-abc"

    async def test_dispatch_request_payload_shape(
        self, http_client: httpx.AsyncClient, fake_server: _RealHttpServer
    ) -> None:
        fake_server.queue_response(201, {"data": {"id": "exec-1"}})
        fake_server.queue_response(200, {"data": {"status": "completed"}})
        target = uuid4()
        await self._client(http_client, fake_server).execute_and_wait(
            uuid4(), variables={"a": 1}, target_ids=[target], timeout_seconds=99
        )
        payload = fake_server.requests[0].json()
        assert payload["target_ids"] == [str(target)]
        assert payload["variables"] == {"a": 1}
        assert payload["timeout_seconds"] == 99

    async def test_no_target_ids_sends_an_empty_list(
        self, http_client: httpx.AsyncClient, fake_server: _RealHttpServer
    ) -> None:
        fake_server.queue_response(201, {"data": {"id": "exec-1"}})
        fake_server.queue_response(200, {"data": {"status": "completed"}})
        await self._client(http_client, fake_server).execute_and_wait(uuid4(), variables={})
        assert fake_server.requests[0].json()["target_ids"] == []

    @pytest.mark.parametrize("status", ["failed", "cancelled"])
    async def test_non_completed_terminal_status_raises(
        self, http_client: httpx.AsyncClient, fake_server: _RealHttpServer, status: str
    ) -> None:
        fake_server.queue_response(201, {"data": {"id": "exec-1"}})
        fake_server.queue_response(200, {"data": {"status": status, "error_message": "boom"}})
        with pytest.raises(DependencyError, match=f"ended in status {status!r}"):
            await self._client(http_client, fake_server).execute_and_wait(uuid4(), variables={})

    async def test_never_reaching_a_terminal_status_times_out(
        self, http_client: httpx.AsyncClient, fake_server: _RealHttpServer
    ) -> None:
        fake_server.queue_response(201, {"data": {"id": "exec-1"}})
        for _ in range(3):
            fake_server.queue_response(200, {"data": {"status": "running"}})
        with pytest.raises(DependencyError, match="did not reach a terminal status"):
            await self._client(http_client, fake_server, max_poll_attempts=3).execute_and_wait(
                uuid4(), variables={}
            )

    async def test_dispatch_non_created_status_raises(
        self, http_client: httpx.AsyncClient, fake_server: _RealHttpServer
    ) -> None:
        fake_server.queue_response(400, {"error": "bad job"})
        with pytest.raises(DependencyError, match="HTTP 400"):
            await self._client(http_client, fake_server).execute_and_wait(uuid4(), variables={})

    async def test_dispatch_transport_failure_is_unreachable(
        self, local_http_client: httpx.AsyncClient
    ) -> None:
        client = AutomationClient(
            local_http_client, base_url=UNREACHABLE_BASE_URL, caller_token="t"
        )
        with pytest.raises(DependencyError, match="unreachable"):
            await client.execute_and_wait(uuid4(), variables={})

    async def test_get_execution_non_200_status_raises(
        self, http_client: httpx.AsyncClient, fake_server: _RealHttpServer
    ) -> None:
        fake_server.queue_response(404, {"error": "not found"})
        client = self._client(http_client, fake_server)
        with pytest.raises(DependencyError, match="HTTP 404"):
            await client._get_execution("exec-missing")

    async def test_get_execution_transport_failure_is_unreachable(
        self, local_http_client: httpx.AsyncClient
    ) -> None:
        client = AutomationClient(
            local_http_client, base_url=UNREACHABLE_BASE_URL, caller_token="t"
        )
        with pytest.raises(DependencyError, match="unreachable"):
            await client._get_execution("exec-1")


# ---- app/clients/policy_engine_client.py ----------------------------------------


class TestPolicyEngineClient:
    def _client(
        self, http_client: httpx.AsyncClient, fake_server: _RealHttpServer
    ) -> PolicyEngineClient:
        return PolicyEngineClient(
            http_client, base_url=fake_server.base_url, caller_token="caller-token-xyz"
        )

    async def test_evaluate_success_shape_and_request(
        self, http_client: httpx.AsyncClient, fake_server: _RealHttpServer
    ) -> None:
        fake_server.queue_response(
            200,
            {
                "data": {
                    "effect": "permit",
                    "permitted": True,
                    "denied": False,
                    "reason": "role has access",
                    "risk_score": 0.2,
                    "obligations": {"log": True},
                    "decision_id": "dec-1",
                }
            },
        )
        org_id = uuid4()
        decision = await self._client(http_client, fake_server).evaluate(
            organization_id=org_id,
            subject_type="agent",
            subject_id="agent-1",
            resource_type="automation_job",
            action="execute",
        )

        assert isinstance(decision, PolicyDecision)
        assert decision.effect == "permit"
        assert decision.permitted is True
        assert decision.denied is False
        assert decision.reason == "role has access"
        assert decision.risk_score == 0.2
        assert decision.obligations == {"log": True}
        assert decision.decision_id == "dec-1"
        assert decision.requires_approval is False

        request = fake_server.requests[0]
        assert request.path == "/policies/evaluate"
        assert request.query["organization_id"] == str(org_id)
        assert request.headers["authorization"] == "Bearer caller-token-xyz"
        payload = request.json()
        assert payload["subject_type"] == "agent"
        assert payload["subject_id"] == "agent-1"
        assert payload["resource_type"] == "automation_job"
        assert payload["action"] == "execute"
        assert payload["attributes"] == {}
        assert payload["record"] is True

    async def test_require_approval_effect_sets_the_property(
        self, http_client: httpx.AsyncClient, fake_server: _RealHttpServer
    ) -> None:
        fake_server.queue_response(
            200,
            {
                "data": {
                    "effect": "require_approval",
                    "permitted": False,
                    "denied": False,
                    "reason": "needs a human",
                }
            },
        )
        decision = await self._client(http_client, fake_server).evaluate(
            organization_id=uuid4(),
            subject_type="agent",
            subject_id="a1",
            resource_type="tool",
            action="call",
        )
        assert decision.requires_approval is True
        assert decision.risk_score == 0.0
        assert decision.obligations == {}
        assert decision.decision_id is None

    async def test_optional_fields_and_attributes_are_sent(
        self, http_client: httpx.AsyncClient, fake_server: _RealHttpServer
    ) -> None:
        fake_server.queue_response(
            200,
            {"data": {"effect": "deny", "permitted": False, "denied": True, "reason": "blocked"}},
        )
        await self._client(http_client, fake_server).evaluate(
            organization_id=uuid4(),
            subject_type="agent",
            subject_id="a1",
            resource_type="tool",
            action="call",
            resource_id="tool-1",
            project_id="proj-1",
            attributes={"subject": {"role": "executor"}},
            record=False,
        )
        payload = fake_server.requests[0].json()
        assert payload["resource_id"] == "tool-1"
        assert payload["project_id"] == "proj-1"
        assert payload["attributes"] == {"subject": {"role": "executor"}}
        assert payload["record"] is False

    async def test_non_200_status_becomes_dependency_error(
        self, http_client: httpx.AsyncClient, fake_server: _RealHttpServer
    ) -> None:
        fake_server.queue_response(403, {"error": "forbidden"})
        with pytest.raises(DependencyError, match="HTTP 403"):
            await self._client(http_client, fake_server).evaluate(
                organization_id=uuid4(),
                subject_type="agent",
                subject_id="a1",
                resource_type="tool",
                action="call",
            )

    async def test_transport_failure_is_unreachable(
        self, local_http_client: httpx.AsyncClient
    ) -> None:
        client = PolicyEngineClient(
            local_http_client, base_url=UNREACHABLE_BASE_URL, caller_token="t"
        )
        with pytest.raises(DependencyError, match="unreachable"):
            await client.evaluate(
                organization_id=uuid4(),
                subject_type="agent",
                subject_id="a1",
                resource_type="tool",
                action="call",
            )


# ---- app/clients/registry.py --------------------------------------------------


class TestBuildModelClients:
    def _settings(self, **overrides: Any) -> AiAgentPlatformServiceSettings:
        return AiAgentPlatformServiceSettings(**overrides)

    def test_self_hosted_providers_are_always_registered(
        self, http_client: httpx.AsyncClient
    ) -> None:
        clients = build_model_clients(http_client, self._settings())
        assert ModelProvider.OLLAMA in clients
        assert ModelProvider.VLLM in clients
        assert ModelProvider.LOCAL in clients
        assert isinstance(clients[ModelProvider.OLLAMA], OllamaClient)
        assert isinstance(clients[ModelProvider.VLLM], OpenAiCompatibleClient)
        assert isinstance(clients[ModelProvider.LOCAL], OpenAiCompatibleClient)

    def test_credentialed_providers_absent_with_no_key_configured(
        self, http_client: httpx.AsyncClient
    ) -> None:
        clients = build_model_clients(http_client, self._settings())
        assert ModelProvider.OPENAI not in clients
        assert ModelProvider.AZURE_OPENAI not in clients
        assert ModelProvider.ANTHROPIC not in clients
        assert ModelProvider.GOOGLE_GEMINI not in clients
        assert ModelProvider.OPENROUTER not in clients

    def test_openai_key_registers_openai(self, http_client: httpx.AsyncClient) -> None:
        clients = build_model_clients(http_client, self._settings(openai_api_key="sk-test"))
        assert isinstance(clients[ModelProvider.OPENAI], OpenAiCompatibleClient)
        assert clients[ModelProvider.OPENAI].provider == "openai"

    def test_azure_needs_both_the_key_and_the_base_url(
        self, http_client: httpx.AsyncClient
    ) -> None:
        only_key = build_model_clients(http_client, self._settings(azure_openai_api_key="k"))
        assert ModelProvider.AZURE_OPENAI not in only_key

        only_url = build_model_clients(
            http_client, self._settings(azure_openai_base_url="https://azure.test")
        )
        assert ModelProvider.AZURE_OPENAI not in only_url

        both = build_model_clients(
            http_client,
            self._settings(azure_openai_api_key="k", azure_openai_base_url="https://azure.test"),
        )
        assert isinstance(both[ModelProvider.AZURE_OPENAI], OpenAiCompatibleClient)

    def test_anthropic_key_registers_anthropic(self, http_client: httpx.AsyncClient) -> None:
        clients = build_model_clients(http_client, self._settings(anthropic_api_key="sk-ant"))
        assert isinstance(clients[ModelProvider.ANTHROPIC], AnthropicClient)

    def test_gemini_key_registers_gemini(self, http_client: httpx.AsyncClient) -> None:
        clients = build_model_clients(http_client, self._settings(gemini_api_key="g"))
        assert isinstance(clients[ModelProvider.GOOGLE_GEMINI], GeminiClient)

    def test_openrouter_key_registers_openrouter(self, http_client: httpx.AsyncClient) -> None:
        clients = build_model_clients(http_client, self._settings(openrouter_api_key="or"))
        assert isinstance(clients[ModelProvider.OPENROUTER], OpenAiCompatibleClient)
        assert clients[ModelProvider.OPENROUTER].provider == "openrouter"

    def test_every_credential_configured_together(self, http_client: httpx.AsyncClient) -> None:
        clients = build_model_clients(
            http_client,
            self._settings(
                openai_api_key="a",
                azure_openai_api_key="b",
                azure_openai_base_url="https://az.test",
                anthropic_api_key="c",
                gemini_api_key="d",
                openrouter_api_key="e",
            ),
        )
        assert set(clients) == {
            ModelProvider.OPENAI,
            ModelProvider.AZURE_OPENAI,
            ModelProvider.ANTHROPIC,
            ModelProvider.GOOGLE_GEMINI,
            ModelProvider.OPENROUTER,
            ModelProvider.OLLAMA,
            ModelProvider.VLLM,
            ModelProvider.LOCAL,
        }


class TestModelRegistry:
    def _registry_with(
        self, clients: dict[ModelProvider, ModelClient], **kwargs: Any
    ) -> ModelRegistry:
        kwargs.setdefault("default_provider", ModelProvider.OLLAMA)
        kwargs.setdefault("default_model", "test-model")
        return ModelRegistry(clients, **kwargs)

    def test_available_providers_is_sorted_by_name(self, http_client: httpx.AsyncClient) -> None:
        settings = AiAgentPlatformServiceSettings(openai_api_key="k", anthropic_api_key="k")
        registry = self._registry_with(build_model_clients(http_client, settings))
        assert registry.available_providers == sorted(registry.available_providers, key=str)
        assert ModelProvider.OPENAI in registry.available_providers

    def test_get_returns_the_configured_client(self, http_client: httpx.AsyncClient) -> None:
        settings = AiAgentPlatformServiceSettings()
        registry = self._registry_with(build_model_clients(http_client, settings))
        assert isinstance(registry.get(ModelProvider.OLLAMA), OllamaClient)

    def test_get_unconfigured_provider_raises_listing_whats_available(
        self, http_client: httpx.AsyncClient
    ) -> None:
        settings = AiAgentPlatformServiceSettings()
        registry = self._registry_with(build_model_clients(http_client, settings))
        with pytest.raises(AIError, match="anthropic is not configured"):
            registry.get(ModelProvider.ANTHROPIC)

    def test_observed_latency_starts_empty(self, http_client: httpx.AsyncClient) -> None:
        registry = self._registry_with(
            {ModelProvider.OLLAMA: OllamaClient(http_client, base_url=UNREACHABLE_BASE_URL)}
        )
        assert registry.observed_latency_ms() == {}

    async def test_chat_succeeds_against_a_real_local_server(
        self, http_client: httpx.AsyncClient, fake_server: _RealHttpServer
    ) -> None:
        fake_server.queue_response(
            200,
            {
                "model": "llama3",
                "message": {"role": "assistant", "content": "hello"},
                "done": True,
                "done_reason": "stop",
                "prompt_eval_count": 3,
                "eval_count": 2,
            },
        )
        registry = self._registry_with(
            {ModelProvider.OLLAMA: OllamaClient(http_client, base_url=fake_server.base_url)}
        )
        completion = await registry.chat(
            [ChatMessage(role="user", content="hi")], provider=ModelProvider.OLLAMA
        )
        assert completion.content == "hello"
        assert completion.provider == "ollama"
        assert registry.observed_latency_ms()[ModelProvider.OLLAMA] == completion.latency_ms

    async def test_chat_falls_over_to_the_next_provider_after_a_failure(
        self, http_client: httpx.AsyncClient, fake_server: _RealHttpServer
    ) -> None:
        fake_server.queue_response(200, {"choices": [{"message": {"content": "ok"}}], "usage": {}})
        registry = self._registry_with(
            {
                ModelProvider.OLLAMA: OllamaClient(http_client, base_url=UNREACHABLE_BASE_URL),
                ModelProvider.VLLM: OpenAiCompatibleClient(
                    http_client, base_url=fake_server.base_url, api_key="", provider="vllm"
                ),
            },
            fallback_providers=(ModelProvider.VLLM,),
        )
        completion = await registry.chat(
            [ChatMessage(role="user", content="hi")], strategy=RoutingStrategy.FALLBACK
        )
        assert completion.provider == "vllm"
        assert ModelProvider.OLLAMA not in registry.observed_latency_ms()
        assert ModelProvider.VLLM in registry.observed_latency_ms()

    async def test_chat_reports_an_unconfigured_rule_winner_as_not_configured(
        self, http_client: httpx.AsyncClient
    ) -> None:
        # order_by_rules can place a provider ahead of the chain that was
        # never actually registered (tests/test_routing.py's own "winner
        # outside the original candidates" case) -- ModelRegistry.chat
        # must report that leg as "not configured" and keep going rather
        # than crash.
        registry = self._registry_with(
            {ModelProvider.OLLAMA: OllamaClient(http_client, base_url=UNREACHABLE_BASE_URL)}
        )
        with pytest.raises(AIError, match="azure_openai: not configured") as excinfo:
            await registry.chat(
                [ChatMessage(role="user", content="hi")],
                strategy=RoutingStrategy.RULE_BASED,
                rules=[("go", ModelProvider.AZURE_OPENAI)],
                variables={"go": True},
            )
        assert "Every model provider in the rule_based chain failed" in str(excinfo.value)
        assert "ollama:" in str(excinfo.value)

    async def test_chat_with_no_reachable_provider_names_the_whole_chain(
        self, model_registry: ModelRegistry
    ) -> None:
        # No local model backend is guaranteed running (tests/conftest.py
        # own module docstring): the default provider genuinely fails,
        # and every self-hosted provider this registry knows about gets
        # tried too, in order, before it gives up for real.
        with pytest.raises(AIError, match="Every model provider in the fallback chain failed"):
            await model_registry.chat([ChatMessage(role="user", content="hi")])


# ---- app/clients/dispatch.py -----------------------------------------------------


class TestDispatchChat:
    def _profile(self, **overrides: Any) -> AgentProfile:
        defaults: dict[str, Any] = {
            "model_provider": ModelProvider.OLLAMA,
            "routing_strategy": RoutingStrategy.FALLBACK,
            "model_name": "llama3",
            "temperature": 0.3,
            "max_tokens": 50,
        }
        defaults.update(overrides)
        return AgentProfile(**defaults)

    async def test_dispatches_using_the_profiles_own_settings(
        self, http_client: httpx.AsyncClient, fake_server: _RealHttpServer
    ) -> None:
        fake_server.queue_response(
            200,
            {
                "model": "llama3",
                "message": {"role": "assistant", "content": "hi there"},
                "done": True,
                "prompt_eval_count": 1,
                "eval_count": 1,
            },
        )
        registry = ModelRegistry(
            {ModelProvider.OLLAMA: OllamaClient(http_client, base_url=fake_server.base_url)},
            default_provider=ModelProvider.OLLAMA,
            default_model="llama3",
        )
        completion = await dispatch_chat(
            registry, self._profile(), [ChatMessage(role="user", content="hello")]
        )

        assert completion.content == "hi there"
        payload = fake_server.requests[0].json()
        assert payload["options"] == {"temperature": 0.3, "num_predict": 50}

    async def test_coerces_plain_str_provider_and_strategy(
        self, http_client: httpx.AsyncClient, fake_server: _RealHttpServer
    ) -> None:
        # The "enum-as-str" convention: a profile loaded back from the
        # database has these fields as plain strings, not enum members.
        fake_server.queue_response(200, {"message": {"content": "ok"}, "done": True})
        registry = ModelRegistry(
            {ModelProvider.OLLAMA: OllamaClient(http_client, base_url=fake_server.base_url)},
            default_provider=ModelProvider.OLLAMA,
            default_model="llama3",
        )
        profile = self._profile(model_provider="ollama", routing_strategy="fallback")
        assert isinstance(profile.model_provider, str)
        assert isinstance(profile.routing_strategy, str)

        completion = await dispatch_chat(
            registry, profile, [ChatMessage(role="user", content="hi")]
        )
        assert completion.provider == "ollama"

    async def test_propagates_ai_error_when_every_provider_fails(
        self, http_client: httpx.AsyncClient
    ) -> None:
        registry = ModelRegistry(
            {ModelProvider.OLLAMA: OllamaClient(http_client, base_url=UNREACHABLE_BASE_URL)},
            default_provider=ModelProvider.OLLAMA,
            default_model="llama3",
        )
        with pytest.raises(AIError, match="Every model provider in the fallback chain failed"):
            await dispatch_chat(registry, self._profile(), [ChatMessage(role="user", content="hi")])

    async def test_passes_tools_through(
        self, http_client: httpx.AsyncClient, fake_server: _RealHttpServer
    ) -> None:
        fake_server.queue_response(200, {"message": {"content": "ok"}, "done": True})
        registry = ModelRegistry(
            {ModelProvider.OLLAMA: OllamaClient(http_client, base_url=fake_server.base_url)},
            default_provider=ModelProvider.OLLAMA,
            default_model="llama3",
        )
        await dispatch_chat(
            registry, self._profile(), [ChatMessage(role="user", content="hi")], tools=[TOOL]
        )
        payload = fake_server.requests[0].json()
        assert payload["tools"][0]["function"]["name"] == "lookup"
