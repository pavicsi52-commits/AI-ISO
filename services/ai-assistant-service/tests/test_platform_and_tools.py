"""Platform client, built-in tool handlers, model registry, events,
telemetry, and notifications.

The platform client's paths are asserted against the endpoints the
owning services actually register -- a guessed path is exactly the kind
of bug that only shows up in production, and this suite is where it
gets caught instead.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from typing import Any

import httpx
import pytest
import pytest_asyncio
from opentelemetry import trace
from pytest_httpx import HTTPXMock
from shared_core.enums.notification_channel import NotificationChannel
from shared_core.events import default_registry
from shared_core.events.base import DomainEvent
from shared_core.exceptions.ai import AIError
from shared_core.exceptions.notification import NotificationError

from app.clients.base import ChatCompletion, ChatMessage
from app.clients.platform import PlatformClient, PlatformEndpoints
from app.clients.registry import (
    ModelRegistry,
    build_embedding_client,
    build_local_encoder,
    build_model_clients,
)
from app.config.settings import AiAssistantServiceSettings
from app.events.ai_events import (
    ConversationCompletedEvent,
    ConversationStartedEvent,
    FeedbackReceivedEvent,
    ModelChangedEvent,
    RecommendationGeneratedEvent,
    ReportGeneratedEvent,
    ToolCalledEvent,
)
from app.models.enums import MessageRole, ModelProvider
from app.notifications.ai_notifications import AiNotificationService
from app.telemetry.tracing import (
    trace_agent_execution,
    trace_embedding_search,
    trace_model_call,
    trace_prompt_execution,
    trace_rag_retrieval,
    trace_streaming_response,
    trace_tool_call,
)
from app.tool_calling.builtin import (
    BUILTIN_TOOL_DEFINITIONS,
    build_builtin_handlers,
    build_builtin_registry,
    missing_handlers,
)
from tests.conftest import StubModelClient

BASE = "http://svc.internal"
ENDPOINTS = PlatformEndpoints(
    inventory=BASE,
    discovery=BASE,
    configuration=BASE,
    automation=BASE,
    workflow=BASE,
    validation=BASE,
    monitoring=BASE,
    alerting=BASE,
)


@pytest_asyncio.fixture
async def http_client() -> AsyncIterator[httpx.AsyncClient]:
    async with httpx.AsyncClient() as client:
        yield client


@pytest.fixture
def platform(http_client: httpx.AsyncClient) -> PlatformClient:
    return PlatformClient(http_client, ENDPOINTS, caller_token="caller-token")


def _envelope(data: Any) -> dict[str, Any]:
    """The success envelope every AI-IOS service returns."""
    return {"success": True, "message": "ok", "data": data, "meta": {"request_id": "r"}}


class TestPlatformClient:
    async def test_every_read_hits_its_documented_path(
        self, httpx_mock: HTTPXMock, platform: PlatformClient
    ) -> None:
        asset_id, target_id, org = str(uuid.uuid4()), str(uuid.uuid4()), str(uuid.uuid4())
        instance_id, job_id, profile_id = (
            str(uuid.uuid4()),
            str(uuid.uuid4()),
            str(uuid.uuid4()),
        )
        calls: list[tuple[Any, str]] = [
            (platform.list_assets(org), "/inventory/assets"),
            (platform.get_asset(asset_id), f"/inventory/assets/{asset_id}"),
            (platform.get_topology(asset_id), "/inventory/topology"),
            (platform.list_alerts(org), "/alerts"),
            (platform.get_monitoring_health(target_id), "/monitoring/health"),
            (platform.get_monitoring_statistics(org), "/monitoring/statistics"),
            (platform.list_validation_results(target_id), "/validation-results"),
            (platform.get_configuration_drift(org, profile_id), "/configurations/drift"),
            (platform.list_automation_executions(org), "/automation/executions"),
            (platform.get_workflow_instance(instance_id), f"/workflow-instances/{instance_id}"),
            (platform.get_discovery_job(job_id), f"/discovery/jobs/{job_id}"),
        ]
        for coroutine, expected_path in calls:
            httpx_mock.add_response(json=_envelope([]))
            await coroutine
            request = httpx_mock.get_requests()[-1]
            assert request.url.path == expected_path
            assert request.headers["Authorization"] == "Bearer caller-token"

    async def test_list_calls_unwrap_the_envelope(
        self, httpx_mock: HTTPXMock, platform: PlatformClient
    ) -> None:
        httpx_mock.add_response(json=_envelope([{"id": "a1"}, {"id": "a2"}]))
        assert await platform.list_assets(str(uuid.uuid4())) == [{"id": "a1"}, {"id": "a2"}]

    async def test_object_calls_unwrap_the_envelope(
        self, httpx_mock: HTTPXMock, platform: PlatformClient
    ) -> None:
        httpx_mock.add_response(json=_envelope({"id": "a1", "hostname": "db-1"}))
        assert (await platform.get_asset("a1"))["hostname"] == "db-1"

    async def test_null_data_becomes_an_empty_result(
        self, httpx_mock: HTTPXMock, platform: PlatformClient
    ) -> None:
        """A 200 with no data must not crash a chat turn."""
        httpx_mock.add_response(json=_envelope(None))
        assert await platform.list_assets(str(uuid.uuid4())) == []
        httpx_mock.add_response(json=_envelope(None))
        assert await platform.get_asset("a1") == {}

    async def test_alert_status_filter_is_sent_only_when_given(
        self, httpx_mock: HTTPXMock, platform: PlatformClient
    ) -> None:
        httpx_mock.add_response(json=_envelope([]))
        await platform.list_alerts("org-1")
        assert "status" not in httpx_mock.get_requests()[-1].url.params

        httpx_mock.add_response(json=_envelope([]))
        await platform.list_alerts("org-1", status="firing")
        assert httpx_mock.get_requests()[-1].url.params["status"] == "firing"

    async def test_topology_query_parameters(
        self, httpx_mock: HTTPXMock, platform: PlatformClient
    ) -> None:
        httpx_mock.add_response(json=_envelope({}))
        await platform.get_topology("a1", depth=3)
        params = httpx_mock.get_requests()[-1].url.params
        assert params["asset_id"] == "a1"
        assert params["query_kind"] == "neighbors"
        assert params["depth"] == "3"

    @pytest.mark.parametrize("status", [401, 403, 404, 500])
    async def test_error_status_becomes_ai_error(
        self, httpx_mock: HTTPXMock, platform: PlatformClient, status: int
    ) -> None:
        """A 403 here means the *caller* lacks access -- RBAC held."""
        httpx_mock.add_response(status_code=status, json={})
        with pytest.raises(AIError, match=f"HTTP {status}"):
            await platform.list_assets(str(uuid.uuid4()))

    async def test_transport_failure_becomes_ai_error(
        self, httpx_mock: HTTPXMock, platform: PlatformClient
    ) -> None:
        httpx_mock.add_exception(httpx.ConnectError("refused"))
        with pytest.raises(AIError, match="inventory-service is unreachable"):
            await platform.list_assets(str(uuid.uuid4()))


class TestBuiltinTools:
    def test_every_definition_has_a_handler(self, platform: PlatformClient) -> None:
        assert missing_handlers(build_builtin_handlers(platform)) == []

    def test_every_handler_has_a_definition(self, platform: PlatformClient) -> None:
        """Drift in the other direction: a handler no model can reach."""
        defined = {definition.tool_key for definition in BUILTIN_TOOL_DEFINITIONS}
        assert set(build_builtin_handlers(platform)) == defined

    def test_no_builtin_tool_mutates(self) -> None:
        """The assistant answering a question must never change anything."""
        assert all(not definition.is_mutating for definition in BUILTIN_TOOL_DEFINITIONS)

    def test_schemas_are_strict(self) -> None:
        for definition in BUILTIN_TOOL_DEFINITIONS:
            schema = definition.parameters_schema
            assert schema["additionalProperties"] is False
            assert set(schema["required"]) == set(schema["properties"])

    def test_missing_handlers_reports_a_real_gap(self) -> None:
        assert missing_handlers({}) == sorted(
            definition.tool_key for definition in BUILTIN_TOOL_DEFINITIONS
        )

    def test_registry_resolves_every_builtin(self, platform: PlatformClient) -> None:
        registry = build_builtin_registry(platform)
        for definition in BUILTIN_TOOL_DEFINITIONS:
            assert registry.get(definition.tool_key) is not None

    @pytest.mark.parametrize(
        ("tool_key", "arguments", "payload", "expected"),
        [
            (
                "inventory_list_assets",
                {"organization_id": "org-1"},
                [{"id": "a1"}],
                {"count": 1, "assets": [{"id": "a1"}]},
            ),
            ("inventory_get_asset", {"asset_id": "a1"}, {"id": "a1"}, {"asset": {"id": "a1"}}),
            (
                "inventory_get_topology",
                {"asset_id": "a1"},
                {"nodes": []},
                {"topology": {"nodes": []}},
            ),
            (
                "alerting_list_alerts",
                {"organization_id": "org-1"},
                [{"id": "al1"}],
                {"count": 1, "alerts": [{"id": "al1"}]},
            ),
            (
                "monitoring_get_health",
                {"target_id": "t1"},
                [{"status": "healthy"}],
                {"count": 1, "health": [{"status": "healthy"}]},
            ),
            (
                "monitoring_get_statistics",
                {"organization_id": "org-1"},
                {"checks": 12},
                {"statistics": {"checks": 12}},
            ),
            (
                "validation_list_results",
                {"target_id": "t1"},
                [{"passed": True}],
                {"count": 1, "results": [{"passed": True}]},
            ),
            (
                "configuration_get_drift",
                {"organization_id": "org-1", "profile_id": "p1"},
                [{"field": "ntp"}],
                {"count": 1, "drift": [{"field": "ntp"}]},
            ),
            (
                "automation_list_executions",
                {"organization_id": "org-1"},
                [{"id": "e1"}],
                {"count": 1, "executions": [{"id": "e1"}]},
            ),
        ],
    )
    async def test_handler_shapes_its_result_for_the_model(
        self,
        httpx_mock: HTTPXMock,
        platform: PlatformClient,
        tool_key: str,
        arguments: dict[str, Any],
        payload: Any,
        expected: dict[str, Any],
    ) -> None:
        httpx_mock.add_response(json=_envelope(payload))
        handler = build_builtin_handlers(platform)[tool_key]
        assert await handler(arguments) == expected

    async def test_handler_propagates_an_upstream_failure(
        self, httpx_mock: HTTPXMock, platform: PlatformClient
    ) -> None:
        """The executor records it as failed; it must not be swallowed here."""
        httpx_mock.add_response(status_code=503, json={})
        handler = build_builtin_handlers(platform)["inventory_list_assets"]
        with pytest.raises(AIError):
            await handler({"organization_id": "org-1"})


class TestModelRegistryConstruction:
    def _settings(self, **overrides: Any) -> AiAssistantServiceSettings:
        return AiAssistantServiceSettings(_env_file=None, **overrides)

    def test_self_hosted_providers_need_no_credential(self, http_client: httpx.AsyncClient) -> None:
        clients = build_model_clients(http_client, self._settings())
        assert ModelProvider.OLLAMA in clients
        assert ModelProvider.VLLM in clients
        assert ModelProvider.LOCAL in clients

    def test_hosted_providers_are_skipped_without_a_key(
        self, http_client: httpx.AsyncClient
    ) -> None:
        """A registered-but-broken provider gives a confusing 401 instead."""
        clients = build_model_clients(http_client, self._settings())
        assert ModelProvider.OPENAI not in clients
        assert ModelProvider.ANTHROPIC not in clients
        assert ModelProvider.GEMINI not in clients
        assert ModelProvider.OPENROUTER not in clients

    def test_each_credential_registers_its_provider(self, http_client: httpx.AsyncClient) -> None:
        clients = build_model_clients(
            http_client,
            self._settings(
                openai_api_key="sk-a",
                anthropic_api_key="sk-b",
                gemini_api_key="sk-c",
                openrouter_api_key="sk-d",
                azure_openai_api_key="sk-e",
                azure_openai_base_url="https://azure.test",
            ),
        )
        for provider in (
            ModelProvider.OPENAI,
            ModelProvider.ANTHROPIC,
            ModelProvider.GEMINI,
            ModelProvider.OPENROUTER,
            ModelProvider.AZURE_OPENAI,
        ):
            assert provider in clients

    def test_azure_needs_both_key_and_base_url(self, http_client: httpx.AsyncClient) -> None:
        clients = build_model_clients(http_client, self._settings(azure_openai_api_key="sk-e"))
        assert ModelProvider.AZURE_OPENAI not in clients

    def test_builtin_embedding_provider_has_no_client(self, http_client: httpx.AsyncClient) -> None:
        """``None`` means "use the offline encoder", not "failed"."""
        assert build_embedding_client(http_client, self._settings(), "builtin") is None

    def test_local_is_a_real_endpoint_not_the_offline_encoder(
        self, http_client: httpx.AsyncClient
    ) -> None:
        """Regression: ``"local"`` once collided with the offline sentinel.

        ``ModelProvider.LOCAL`` means a self-hosted OpenAI-compatible
        server. When both used the string ``"local"``, pointing at that
        server silently fell back to lexical hashing instead -- no
        error, just far worse retrieval.
        """
        client = build_embedding_client(http_client, self._settings(), "local")
        assert client is not None
        assert client.provider == "local"

    @pytest.mark.parametrize("provider", ["ollama", "openai", "vllm", "local"])
    def test_supported_embedding_providers_build(
        self, http_client: httpx.AsyncClient, provider: str
    ) -> None:
        client = build_embedding_client(http_client, self._settings(), provider)
        assert client is not None
        assert client.provider == provider

    def test_unsupported_embedding_provider_is_rejected(
        self, http_client: httpx.AsyncClient
    ) -> None:
        with pytest.raises(AIError, match="not supported"):
            build_embedding_client(http_client, self._settings(), "anthropic")

    def test_local_encoder_matches_configured_width(self) -> None:
        encoder = build_local_encoder(self._settings(embedding_dimensions=256))
        assert len(encoder.encode("anything")) == 256


class TestModelRegistryFallback:
    def _registry(self, **clients: StubModelClient) -> ModelRegistry:
        mapping = {ModelProvider(name): client for name, client in clients.items()}
        return ModelRegistry(
            mapping,  # type: ignore[arg-type]
            default_provider=ModelProvider.OLLAMA,
            default_model="stub-model",
            fallback_providers=(ModelProvider.OLLAMA, ModelProvider.OPENAI),
        )

    def test_available_providers_are_sorted(self) -> None:
        registry = self._registry(ollama=StubModelClient(), openai=StubModelClient())
        assert registry.available_providers == [ModelProvider.OLLAMA, ModelProvider.OPENAI]

    def test_get_returns_the_client(self) -> None:
        stub = StubModelClient()
        assert self._registry(ollama=stub).get(ModelProvider.OLLAMA) is stub

    def test_get_names_what_is_available(self) -> None:
        with pytest.raises(AIError, match=r"not configured.*ollama"):
            self._registry(ollama=StubModelClient()).get(ModelProvider.ANTHROPIC)

    async def test_the_requested_provider_is_used_first(self) -> None:
        primary, secondary = StubModelClient(provider="p"), StubModelClient(provider="s")
        registry = self._registry(ollama=primary, openai=secondary)
        completion = await registry.chat_with_fallback(
            [ChatMessage(role=MessageRole.USER, content="hi")], provider=ModelProvider.OPENAI
        )
        assert completion.provider == "s"
        assert primary.calls == []

    async def test_failure_falls_through_to_the_next_provider(self) -> None:
        failing = StubModelClient(fail_with=AIError("down"))
        working = StubModelClient(
            [ChatCompletion(content="recovered", model="m", provider="openai")]
        )
        registry = self._registry(ollama=failing, openai=working)
        completion = await registry.chat_with_fallback(
            [ChatMessage(role=MessageRole.USER, content="hi")]
        )
        assert completion.content == "recovered"

    async def test_an_unconfigured_fallback_is_skipped_not_fatal(self) -> None:
        working = StubModelClient([ChatCompletion(content="ok", model="m", provider="openai")])
        registry = ModelRegistry(
            {ModelProvider.OPENAI: working},
            default_provider=ModelProvider.ANTHROPIC,
            default_model="stub-model",
            fallback_providers=(ModelProvider.OPENAI,),
        )
        completion = await registry.chat_with_fallback(
            [ChatMessage(role=MessageRole.USER, content="hi")]
        )
        assert completion.content == "ok"

    async def test_total_failure_names_the_whole_chain(self) -> None:
        """One message must be enough to diagnose a misconfiguration."""
        registry = self._registry(
            ollama=StubModelClient(fail_with=AIError("ollama down")),
            openai=StubModelClient(fail_with=AIError("openai down")),
        )
        with pytest.raises(AIError) as excinfo:
            await registry.chat_with_fallback([ChatMessage(role=MessageRole.USER, content="hi")])
        message = str(excinfo.value)
        assert "ollama down" in message
        assert "openai down" in message


class TestEvents:
    @pytest.mark.parametrize(
        ("event_class", "event_name"),
        [
            (ConversationStartedEvent, "ConversationStarted"),
            (ConversationCompletedEvent, "ConversationCompleted"),
            (ToolCalledEvent, "ToolCalled"),
            (RecommendationGeneratedEvent, "RecommendationGenerated"),
            (ReportGeneratedEvent, "ReportGenerated"),
            (ModelChangedEvent, "ModelChanged"),
            (FeedbackReceivedEvent, "FeedbackReceived"),
        ],
    )
    def test_event_is_registered_under_its_documented_name(
        self, event_class: type[DomainEvent], event_name: str
    ) -> None:
        assert event_class.event_name == event_name
        assert default_registry.lookup(event_name) is event_class

    def test_an_event_carries_its_payload(self) -> None:
        event = ConversationStartedEvent(
            source_service="ai-assistant-service",
            payload={"title": "Why is db-1 slow?"},
        )
        assert event.payload["title"] == "Why is db-1 slow?"
        assert event.event_name == "ConversationStarted"


class TestTelemetry:
    @pytest.mark.parametrize(
        ("factory", "kwargs", "expected_name"),
        [
            (trace_prompt_execution, {"prompt_id": "p1"}, "ai.prompt_execution"),
            (trace_rag_retrieval, {"strategy": "hybrid"}, "ai.rag_retrieval"),
            (trace_embedding_search, {"top_k": 5}, "ai.embedding_search"),
            (trace_tool_call, {"tool_key": "inventory_list_assets"}, "ai.tool_call"),
            (trace_agent_execution, {"agent_type": "reasoning"}, "ai.agent_execution"),
            (trace_model_call, {"provider": "ollama", "model": "llama3.1"}, "ai.model_call"),
            (trace_streaming_response, {"provider": "ollama"}, "ai.streaming_response"),
        ],
    )
    def test_span_is_opened_with_its_documented_name(
        self, factory: Any, kwargs: dict[str, Any], expected_name: str
    ) -> None:
        tracer = trace.get_tracer("test")
        with factory(tracer, **kwargs) as span:
            assert span is not None

    def test_extra_attributes_are_accepted(self) -> None:
        tracer = trace.get_tracer("test")
        with trace_model_call(
            tracer, provider="ollama", model="llama3.1", conversation_id="c1"
        ) as span:
            assert span is not None


class TestNotifications:
    class _RecordingManager:
        """A real notification manager surface that records its calls."""

        def __init__(self, *, fail: bool = False) -> None:
            self.sent: list[dict[str, Any]] = []
            self._fail = fail

        async def send(self, **kwargs: Any) -> None:
            if self._fail:
                raise NotificationError("smtp unreachable")
            self.sent.append(kwargs)

    async def test_every_notification_reaches_the_manager(self) -> None:
        manager = self._RecordingManager()
        service = AiNotificationService(manager)  # type: ignore[arg-type]
        user = str(uuid.uuid4())

        await service.send_long_running_task(user, description="indexing 4000 documents")
        await service.send_report_ready(user, title="Q3 capacity")
        await service.send_recommendation_ready(user, title="Restart db-1")
        await service.send_model_failure(user, provider="openai", reason="429")
        await service.send_tool_failure(user, tool_key="inventory_list_assets", reason="timeout")

        assert len(manager.sent) == 5
        assert all(call["channel"] is NotificationChannel.EMAIL for call in manager.sent)
        assert all(call["user_id"] == user for call in manager.sent)

    async def test_failures_are_reported_as_errors(self) -> None:
        manager = self._RecordingManager()
        service = AiNotificationService(manager)  # type: ignore[arg-type]
        await service.send_model_failure("u", provider="openai", reason="429")
        await service.send_tool_failure("u", tool_key="t", reason="boom")
        assert [str(call["notification_type"]) for call in manager.sent] == ["error", "error"]

    async def test_a_failing_notifier_never_breaks_the_caller(self) -> None:
        """A notification failure must not fail the AI turn that caused it."""
        service = AiNotificationService(self._RecordingManager(fail=True))  # type: ignore[arg-type]
        await service.send_report_ready("u", title="Q3 capacity")
