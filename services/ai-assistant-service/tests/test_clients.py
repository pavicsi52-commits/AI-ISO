"""Provider client tests against each vendor's *own documented* wire format.

Every response body below is shaped exactly as the vendor documents it
-- OpenAI's ``choices[].message``, Anthropic's typed content blocks,
Gemini's ``candidates[].content.parts``, Ollama's single ``message``.
That is the point: these tests verify the translation layer against the
real contract, so the only thing stubbed anywhere in this suite is the
model's creativity, never the protocol.

Requests are intercepted with ``pytest-httpx``, so the client's real
``httpx`` code path -- headers, query parameters, JSON body, status
handling -- executes unchanged.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from typing import Any

import httpx
import pytest
import pytest_asyncio
from pytest_httpx import HTTPXMock
from shared_core.exceptions.ai import AIError

from app.clients.anthropic_client import ANTHROPIC_VERSION, AnthropicClient
from app.clients.base import ChatMessage, ToolSpecification
from app.clients.embedding_client import EmbeddingClient
from app.clients.gemini_client import GeminiClient
from app.clients.ollama_client import OllamaClient
from app.clients.openai_compatible import OpenAiCompatibleClient
from app.models.enums import MessageRole

MESSAGES = [
    ChatMessage(role=MessageRole.SYSTEM, content="You are an infrastructure assistant."),
    ChatMessage(role=MessageRole.USER, content="Is db-1 healthy?"),
]

TOOL = ToolSpecification(
    name="inventory_list_assets",
    description="List assets.",
    parameters_schema={"type": "object", "properties": {}},
)


def _body(request: httpx.Request) -> dict[str, Any]:
    """The JSON body a client actually put on the wire."""
    parsed: dict[str, Any] = json.loads(request.content)
    return parsed


def _sent_body(httpx_mock: HTTPXMock) -> dict[str, Any]:
    """The JSON body of the first intercepted request."""
    return _body(httpx_mock.get_requests()[0])


@pytest_asyncio.fixture
async def http_client() -> AsyncIterator[httpx.AsyncClient]:
    async with httpx.AsyncClient() as client:
        yield client


class TestOpenAiCompatibleClient:
    def _client(self, http_client: httpx.AsyncClient, **kwargs: object) -> OpenAiCompatibleClient:
        return OpenAiCompatibleClient(
            http_client,
            base_url="https://api.openai.test/v1",
            api_key="sk-test",
            provider="openai",
            **kwargs,  # type: ignore[arg-type]
        )

    async def test_documented_response_is_translated(
        self, httpx_mock: HTTPXMock, http_client: httpx.AsyncClient
    ) -> None:
        httpx_mock.add_response(
            url="https://api.openai.test/v1/chat/completions",
            json={
                "id": "chatcmpl-1",
                "model": "gpt-4o-2024-08-06",
                "choices": [
                    {
                        "index": 0,
                        "message": {"role": "assistant", "content": "db-1 is healthy."},
                        "finish_reason": "stop",
                    }
                ],
                "usage": {"prompt_tokens": 42, "completion_tokens": 7},
            },
        )
        completion = await self._client(http_client).chat(MESSAGES, model="gpt-4o")

        assert completion.content == "db-1 is healthy."
        assert completion.model == "gpt-4o-2024-08-06"
        assert completion.provider == "openai"
        assert completion.prompt_tokens == 42
        assert completion.completion_tokens == 7
        assert completion.finish_reason == "stop"

    async def test_request_carries_auth_and_parameters(
        self, httpx_mock: HTTPXMock, http_client: httpx.AsyncClient
    ) -> None:
        httpx_mock.add_response(
            json={"choices": [{"message": {"content": "ok"}}], "usage": {}},
        )
        await self._client(http_client).chat(
            MESSAGES, model="gpt-4o", temperature=0.7, max_tokens=256, tools=[TOOL]
        )

        request = httpx_mock.get_requests()[0]
        assert request.headers["Authorization"] == "Bearer sk-test"
        payload = _body(request)
        assert payload["temperature"] == 0.7
        assert payload["max_tokens"] == 256
        assert payload["messages"][0] == {
            "role": "system",
            "content": "You are an infrastructure assistant.",
        }
        assert payload["tools"][0]["function"]["name"] == "inventory_list_assets"

    async def test_azure_sends_its_api_version(
        self, httpx_mock: HTTPXMock, http_client: httpx.AsyncClient
    ) -> None:
        """Azure rejects a request without ``api-version``."""
        httpx_mock.add_response(json={"choices": [{"message": {"content": "ok"}}], "usage": {}})
        await self._client(http_client, api_version="2024-02-01").chat(MESSAGES, model="gpt-4o")

        assert httpx_mock.get_requests()[0].url.params["api-version"] == "2024-02-01"

    async def test_tool_call_arguments_are_parsed_from_json_string(
        self, httpx_mock: HTTPXMock, http_client: httpx.AsyncClient
    ) -> None:
        httpx_mock.add_response(
            json={
                "choices": [
                    {
                        "message": {
                            "content": None,
                            "tool_calls": [
                                {
                                    "id": "call_abc",
                                    "type": "function",
                                    "function": {
                                        "name": "inventory_list_assets",
                                        "arguments": '{"organization_id": "org-1"}',
                                    },
                                }
                            ],
                        },
                        "finish_reason": "tool_calls",
                    }
                ],
                "usage": {},
            }
        )
        completion = await self._client(http_client).chat(MESSAGES, model="gpt-4o")

        assert completion.content == ""
        assert len(completion.tool_calls) == 1
        assert completion.tool_calls[0].call_id == "call_abc"
        assert completion.tool_calls[0].arguments == {"organization_id": "org-1"}

    async def test_malformed_tool_arguments_are_dropped_not_fatal(
        self, httpx_mock: HTTPXMock, http_client: httpx.AsyncClient
    ) -> None:
        """A model emitting broken JSON must not fail the user's turn."""
        httpx_mock.add_response(
            json={
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
            }
        )
        completion = await self._client(http_client).chat(MESSAGES, model="gpt-4o")

        assert completion.tool_calls == []
        assert completion.content == "I will answer directly."

    async def test_tool_result_is_sent_with_its_call_id(
        self, httpx_mock: HTTPXMock, http_client: httpx.AsyncClient
    ) -> None:
        httpx_mock.add_response(json={"choices": [{"message": {"content": "ok"}}], "usage": {}})
        await self._client(http_client).chat(
            [
                *MESSAGES,
                ChatMessage(
                    role=MessageRole.TOOL,
                    content='{"assets": []}',
                    tool_call_id="call_abc",
                    tool_name="inventory_list_assets",
                ),
            ],
            model="gpt-4o",
        )

        payload = _sent_body(httpx_mock)
        assert payload["messages"][-1] == {
            "role": "tool",
            "content": '{"assets": []}',
            "tool_call_id": "call_abc",
        }

    @pytest.mark.parametrize("status", [400, 401, 429, 500, 503])
    async def test_error_status_becomes_ai_error(
        self, httpx_mock: HTTPXMock, http_client: httpx.AsyncClient, status: int
    ) -> None:
        httpx_mock.add_response(status_code=status, json={"error": "nope"})
        with pytest.raises(AIError, match=f"HTTP {status}"):
            await self._client(http_client).chat(MESSAGES, model="gpt-4o")

    async def test_empty_choices_becomes_ai_error(
        self, httpx_mock: HTTPXMock, http_client: httpx.AsyncClient
    ) -> None:
        httpx_mock.add_response(json={"choices": [], "usage": {}})
        with pytest.raises(AIError, match="no choices"):
            await self._client(http_client).chat(MESSAGES, model="gpt-4o")

    async def test_transport_failure_becomes_ai_error(
        self, httpx_mock: HTTPXMock, http_client: httpx.AsyncClient
    ) -> None:
        httpx_mock.add_exception(httpx.ConnectError("connection refused"))
        with pytest.raises(AIError, match="unreachable"):
            await self._client(http_client).chat(MESSAGES, model="gpt-4o")


class TestAnthropicClient:
    def _client(self, http_client: httpx.AsyncClient) -> AnthropicClient:
        return AnthropicClient(
            http_client, base_url="https://api.anthropic.test/v1", api_key="sk-ant-test"
        )

    async def test_documented_response_is_translated(
        self, httpx_mock: HTTPXMock, http_client: httpx.AsyncClient
    ) -> None:
        httpx_mock.add_response(
            url="https://api.anthropic.test/v1/messages",
            json={
                "id": "msg_1",
                "type": "message",
                "role": "assistant",
                "model": "claude-sonnet-4-5",
                "content": [{"type": "text", "text": "db-1 is healthy."}],
                "stop_reason": "end_turn",
                "usage": {"input_tokens": 42, "output_tokens": 7},
            },
        )
        completion = await self._client(http_client).chat(MESSAGES, model="claude-sonnet-4-5")

        assert completion.content == "db-1 is healthy."
        assert completion.provider == "anthropic"
        assert completion.prompt_tokens == 42
        assert completion.completion_tokens == 7
        assert completion.finish_reason == "end_turn"

    async def test_system_prompt_is_hoisted_out_of_the_message_list(
        self, httpx_mock: HTTPXMock, http_client: httpx.AsyncClient
    ) -> None:
        """Anthropic takes ``system`` top-level and rejects a system role."""
        httpx_mock.add_response(json={"content": [{"type": "text", "text": "ok"}], "usage": {}})
        await self._client(http_client).chat(MESSAGES, model="claude-sonnet-4-5")

        request = httpx_mock.get_requests()[0]
        payload = _body(request)
        assert payload["system"] == "You are an infrastructure assistant."
        assert [message["role"] for message in payload["messages"]] == ["user"]
        assert request.headers["x-api-key"] == "sk-ant-test"
        assert request.headers["anthropic-version"] == ANTHROPIC_VERSION

    async def test_tool_role_is_delivered_as_a_user_turn(
        self, httpx_mock: HTTPXMock, http_client: httpx.AsyncClient
    ) -> None:
        httpx_mock.add_response(json={"content": [{"type": "text", "text": "ok"}], "usage": {}})
        await self._client(http_client).chat(
            [
                *MESSAGES,
                ChatMessage(role=MessageRole.ASSISTANT, content="checking"),
                ChatMessage(role=MessageRole.TOOL, content="result", tool_call_id="t1"),
            ],
            model="claude-sonnet-4-5",
        )

        payload = _sent_body(httpx_mock)
        assert [message["role"] for message in payload["messages"]] == [
            "user",
            "assistant",
            "user",
        ]

    async def test_interleaved_text_and_tool_use_blocks(
        self, httpx_mock: HTTPXMock, http_client: httpx.AsyncClient
    ) -> None:
        """Anthropic returns typed blocks, not separate content/tool fields."""
        httpx_mock.add_response(
            json={
                "content": [
                    {"type": "text", "text": "Let me check. "},
                    {
                        "type": "tool_use",
                        "id": "toolu_1",
                        "name": "inventory_list_assets",
                        "input": {"organization_id": "org-1"},
                    },
                    {"type": "text", "text": "One moment."},
                ],
                "stop_reason": "tool_use",
                "usage": {"input_tokens": 1, "output_tokens": 2},
            }
        )
        completion = await self._client(http_client).chat(MESSAGES, model="claude-sonnet-4-5")

        assert completion.content == "Let me check. One moment."
        assert len(completion.tool_calls) == 1
        assert completion.tool_calls[0].call_id == "toolu_1"
        assert completion.tool_calls[0].arguments == {"organization_id": "org-1"}

    async def test_tools_use_input_schema_not_parameters(
        self, httpx_mock: HTTPXMock, http_client: httpx.AsyncClient
    ) -> None:
        httpx_mock.add_response(json={"content": [], "usage": {}})
        await self._client(http_client).chat(MESSAGES, model="claude-sonnet-4-5", tools=[TOOL])

        payload = _sent_body(httpx_mock)
        assert "input_schema" in payload["tools"][0]
        assert "parameters" not in payload["tools"][0]

    async def test_error_and_transport_failure(
        self, httpx_mock: HTTPXMock, http_client: httpx.AsyncClient
    ) -> None:
        httpx_mock.add_response(status_code=429, json={"error": {}})
        with pytest.raises(AIError, match="HTTP 429"):
            await self._client(http_client).chat(MESSAGES, model="claude-sonnet-4-5")

        httpx_mock.add_exception(httpx.ReadTimeout("timed out"))
        with pytest.raises(AIError, match="unreachable"):
            await self._client(http_client).chat(MESSAGES, model="claude-sonnet-4-5")


class TestGeminiClient:
    def _client(self, http_client: httpx.AsyncClient) -> GeminiClient:
        return GeminiClient(http_client, base_url="https://gemini.test/v1beta", api_key="key-test")

    async def test_documented_response_is_translated(
        self, httpx_mock: HTTPXMock, http_client: httpx.AsyncClient
    ) -> None:
        httpx_mock.add_response(
            json={
                "candidates": [
                    {
                        "content": {
                            "parts": [{"text": "db-1 is healthy."}],
                            "role": "model",
                        },
                        "finishReason": "STOP",
                    }
                ],
                "usageMetadata": {"promptTokenCount": 42, "candidatesTokenCount": 7},
            }
        )
        completion = await self._client(http_client).chat(MESSAGES, model="gemini-2.0-flash")

        assert completion.content == "db-1 is healthy."
        assert completion.provider == "gemini"
        assert completion.prompt_tokens == 42
        assert completion.completion_tokens == 7
        assert completion.finish_reason == "STOP"

    async def test_model_is_in_the_path_and_key_in_the_query(
        self, httpx_mock: HTTPXMock, http_client: httpx.AsyncClient
    ) -> None:
        httpx_mock.add_response(json={"candidates": [{"content": {"parts": []}}]})
        await self._client(http_client).chat(MESSAGES, model="gemini-2.0-flash")

        url = httpx_mock.get_requests()[0].url
        assert url.path.endswith("/models/gemini-2.0-flash:generateContent")
        assert url.params["key"] == "key-test"

    async def test_assistant_role_is_renamed_to_model(
        self, httpx_mock: HTTPXMock, http_client: httpx.AsyncClient
    ) -> None:
        httpx_mock.add_response(json={"candidates": [{"content": {"parts": []}}]})
        await self._client(http_client).chat(
            [*MESSAGES, ChatMessage(role=MessageRole.ASSISTANT, content="checking")],
            model="gemini-2.0-flash",
        )

        payload = _sent_body(httpx_mock)
        assert [turn["role"] for turn in payload["contents"]] == ["user", "model"]
        assert payload["systemInstruction"]["parts"][0]["text"] == (
            "You are an infrastructure assistant."
        )

    async def test_generation_config_carries_the_parameters(
        self, httpx_mock: HTTPXMock, http_client: httpx.AsyncClient
    ) -> None:
        httpx_mock.add_response(json={"candidates": [{"content": {"parts": []}}]})
        await self._client(http_client).chat(
            MESSAGES, model="gemini-2.0-flash", temperature=0.9, max_tokens=128, tools=[TOOL]
        )

        payload = _sent_body(httpx_mock)
        assert payload["generationConfig"] == {"temperature": 0.9, "maxOutputTokens": 128}
        declarations = payload["tools"][0]["functionDeclarations"]
        assert declarations[0]["name"] == "inventory_list_assets"

    async def test_function_call_part_is_parsed(
        self, httpx_mock: HTTPXMock, http_client: httpx.AsyncClient
    ) -> None:
        httpx_mock.add_response(
            json={
                "candidates": [
                    {
                        "content": {
                            "parts": [
                                {"text": "Checking. "},
                                {
                                    "functionCall": {
                                        "name": "inventory_list_assets",
                                        "args": {"organization_id": "org-1"},
                                    }
                                },
                            ]
                        }
                    }
                ]
            }
        )
        completion = await self._client(http_client).chat(MESSAGES, model="gemini-2.0-flash")

        assert completion.content == "Checking. "
        assert completion.tool_calls[0].name == "inventory_list_assets"
        assert completion.tool_calls[0].arguments == {"organization_id": "org-1"}

    async def test_no_candidates_becomes_ai_error(
        self, httpx_mock: HTTPXMock, http_client: httpx.AsyncClient
    ) -> None:
        """Gemini returns zero candidates when a safety filter trips."""
        httpx_mock.add_response(json={"candidates": []})
        with pytest.raises(AIError, match="no candidates"):
            await self._client(http_client).chat(MESSAGES, model="gemini-2.0-flash")

    async def test_error_and_transport_failure(
        self, httpx_mock: HTTPXMock, http_client: httpx.AsyncClient
    ) -> None:
        httpx_mock.add_response(status_code=403, json={})
        with pytest.raises(AIError, match="HTTP 403"):
            await self._client(http_client).chat(MESSAGES, model="gemini-2.0-flash")

        httpx_mock.add_exception(httpx.ConnectError("refused"))
        with pytest.raises(AIError, match="unreachable"):
            await self._client(http_client).chat(MESSAGES, model="gemini-2.0-flash")


class TestOllamaClient:
    def _client(self, http_client: httpx.AsyncClient) -> OllamaClient:
        return OllamaClient(http_client, base_url="http://ollama.test:11434")

    async def test_documented_response_is_translated(
        self, httpx_mock: HTTPXMock, http_client: httpx.AsyncClient
    ) -> None:
        httpx_mock.add_response(
            url="http://ollama.test:11434/api/chat",
            json={
                "model": "llama3.1",
                "message": {"role": "assistant", "content": "db-1 is healthy."},
                "done": True,
                "done_reason": "stop",
                "prompt_eval_count": 42,
                "eval_count": 7,
            },
        )
        completion = await self._client(http_client).chat(MESSAGES, model="llama3.1")

        assert completion.content == "db-1 is healthy."
        assert completion.provider == "ollama"
        assert completion.prompt_tokens == 42
        assert completion.completion_tokens == 7
        assert completion.finish_reason == "stop"

    async def test_stream_false_is_explicit(
        self, httpx_mock: HTTPXMock, http_client: httpx.AsyncClient
    ) -> None:
        """Omitting it returns NDJSON, which would break the JSON parse."""
        httpx_mock.add_response(json={"message": {"content": "ok"}})
        await self._client(http_client).chat(
            MESSAGES, model="llama3.1", temperature=0.5, max_tokens=64
        )

        payload = _sent_body(httpx_mock)
        assert payload["stream"] is False
        assert payload["options"] == {"temperature": 0.5, "num_predict": 64}

    async def test_tool_call_is_parsed_from_the_message(
        self, httpx_mock: HTTPXMock, http_client: httpx.AsyncClient
    ) -> None:
        httpx_mock.add_response(
            json={
                "message": {
                    "role": "assistant",
                    "content": "",
                    "tool_calls": [
                        {
                            "function": {
                                "name": "inventory_list_assets",
                                "arguments": {"organization_id": "org-1"},
                            }
                        }
                    ],
                }
            }
        )
        completion = await self._client(http_client).chat(MESSAGES, model="llama3.1")

        assert completion.tool_calls[0].name == "inventory_list_assets"
        assert completion.tool_calls[0].arguments == {"organization_id": "org-1"}

    async def test_error_and_transport_failure(
        self, httpx_mock: HTTPXMock, http_client: httpx.AsyncClient
    ) -> None:
        httpx_mock.add_response(status_code=404, json={"error": "model not found"})
        with pytest.raises(AIError, match="HTTP 404"):
            await self._client(http_client).chat(MESSAGES, model="missing")

        httpx_mock.add_exception(httpx.ConnectError("refused"))
        with pytest.raises(AIError, match="unreachable"):
            await self._client(http_client).chat(MESSAGES, model="llama3.1")


class TestEmbeddingClient:
    def _openai(self, http_client: httpx.AsyncClient) -> EmbeddingClient:
        return EmbeddingClient(
            http_client,
            base_url="https://api.openai.test/v1",
            api_key="sk-test",
            provider="openai",
        )

    def _ollama(self, http_client: httpx.AsyncClient) -> EmbeddingClient:
        return EmbeddingClient(
            http_client,
            base_url="http://ollama.test:11434",
            api_key="",
            provider="ollama",
            ollama_style=True,
        )

    async def test_empty_input_makes_no_request(
        self, httpx_mock: HTTPXMock, http_client: httpx.AsyncClient
    ) -> None:
        assert await self._openai(http_client).embed([], model="text-embedding-3-small") == []
        assert httpx_mock.get_requests() == []

    async def test_openai_shape_is_parsed(
        self, httpx_mock: HTTPXMock, http_client: httpx.AsyncClient
    ) -> None:
        httpx_mock.add_response(
            url="https://api.openai.test/v1/embeddings",
            json={
                "object": "list",
                "data": [
                    {"object": "embedding", "index": 0, "embedding": [0.1, 0.2]},
                    {"object": "embedding", "index": 1, "embedding": [0.3, 0.4]},
                ],
                "model": "text-embedding-3-small",
            },
        )
        vectors = await self._openai(http_client).embed(
            ["first", "second"], model="text-embedding-3-small"
        )
        assert vectors == [[0.1, 0.2], [0.3, 0.4]]

    async def test_out_of_order_response_is_reordered_by_index(
        self, httpx_mock: HTTPXMock, http_client: httpx.AsyncClient
    ) -> None:
        """Trusting arrival order would attach every vector to the wrong text."""
        httpx_mock.add_response(
            json={
                "data": [
                    {"index": 2, "embedding": [3.0]},
                    {"index": 0, "embedding": [1.0]},
                    {"index": 1, "embedding": [2.0]},
                ]
            }
        )
        vectors = await self._openai(http_client).embed(
            ["a", "b", "c"], model="text-embedding-3-small"
        )
        assert vectors == [[1.0], [2.0], [3.0]]

    async def test_ollama_shape_is_parsed(
        self, httpx_mock: HTTPXMock, http_client: httpx.AsyncClient
    ) -> None:
        httpx_mock.add_response(
            url="http://ollama.test:11434/api/embed",
            json={"model": "nomic-embed-text", "embeddings": [[0.1, 0.2], [0.3, 0.4]]},
        )
        vectors = await self._ollama(http_client).embed(["a", "b"], model="nomic-embed-text")
        assert vectors == [[0.1, 0.2], [0.3, 0.4]]

    async def test_count_mismatch_is_rejected(
        self, httpx_mock: HTTPXMock, http_client: httpx.AsyncClient
    ) -> None:
        """Silently zipping mismatched lists would mis-attribute vectors."""
        httpx_mock.add_response(json={"data": [{"index": 0, "embedding": [1.0]}]})
        with pytest.raises(AIError, match="returned 1 embeddings for 2 inputs"):
            await self._openai(http_client).embed(["a", "b"], model="text-embedding-3-small")

    async def test_error_and_transport_failure(
        self, httpx_mock: HTTPXMock, http_client: httpx.AsyncClient
    ) -> None:
        httpx_mock.add_response(status_code=500, json={})
        with pytest.raises(AIError, match="HTTP 500"):
            await self._openai(http_client).embed(["a"], model="text-embedding-3-small")

        httpx_mock.add_exception(httpx.ConnectError("refused"))
        with pytest.raises(AIError, match="unreachable"):
            await self._openai(http_client).embed(["a"], model="text-embedding-3-small")
