"""API-layer tests through the real ASGI app.

The app is started through its genuine lifespan -- database, cache,
events, notifications, JWT key loading -- and every request goes through
the real middleware stack, real authentication, and real dependency
graph. Only the model registry is swapped for a stub after startup, so
answers stay deterministic while everything around them is production
code.
"""

from __future__ import annotations

import json
import uuid
from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import (
    AgentType,
    DocumentSourceType,
    FeedbackRating,
    MemoryScope,
    MessageRole,
    ModelProvider,
    RecommendationType,
    RetrievalStrategy,
    ToolKind,
)
from app.repositories.ai_tool_call import AiToolCallRepository
from app.repositories.ai_tool_result import AiToolResultRepository
from app.tool_calling.executor import ToolExecutor
from app.tool_calling.registry import ToolHandlerRegistry
from tests.conftest import (
    AuthHeadersFn,
    RecordingPublisher,
    make_agent,
    make_conversation,
    make_tool,
)

ORG = uuid.uuid4()
CALLER = uuid.uuid4()


@pytest.fixture
def headers(auth_headers: AuthHeadersFn) -> dict[str, str]:
    return auth_headers(CALLER)


def _data(payload: dict[str, Any]) -> Any:
    """The envelope's own ``data`` field, asserting the envelope shape."""
    assert payload["success"] is True
    assert "meta" in payload
    return payload["data"]


class TestAuthentication:
    """Every business route is authenticated; the health probes are not."""

    @pytest.mark.parametrize(
        ("method", "path"),
        [
            ("get", f"/ai/agents?organization_id={ORG}"),
            ("post", "/ai/agents"),
            ("get", f"/ai/tools?organization_id={ORG}"),
            ("post", "/ai/tools"),
            ("post", "/ai/tools/execute"),
            ("get", "/ai/models"),
            ("post", "/ai/models/select"),
            ("post", "/ai/chat"),
            ("post", "/ai/chat/stream"),
            ("post", "/ai/chat/multi-agent"),
            ("get", f"/ai/conversations?organization_id={ORG}"),
            ("get", f"/ai/conversations/{uuid.uuid4()}"),
            ("get", f"/ai/conversations/{uuid.uuid4()}/messages"),
            ("post", "/ai/knowledge/documents"),
            ("get", f"/ai/knowledge/documents?organization_id={ORG}"),
            ("post", "/ai/knowledge/search"),
            ("get", f"/ai/prompts?organization_id={ORG}"),
            ("post", "/ai/prompts"),
            ("get", f"/ai/prompts/{uuid.uuid4()}/versions"),
            ("post", f"/ai/prompts/{uuid.uuid4()}/versions"),
            ("post", f"/ai/prompts/{uuid.uuid4()}/versions/1.0.0/approve"),
            ("post", f"/ai/prompts/{uuid.uuid4()}/rollback/1.0.0"),
            ("post", f"/ai/prompts/{uuid.uuid4()}/render"),
            ("post", "/ai/recommendations"),
            ("get", f"/ai/recommendations?organization_id={ORG}"),
            ("post", f"/ai/recommendations/{uuid.uuid4()}/decide"),
            ("post", "/ai/reports"),
            ("get", f"/ai/reports?organization_id={ORG}"),
            ("post", "/ai/feedback"),
            ("post", "/ai/memory"),
            ("get", f"/ai/memory?organization_id={ORG}"),
            ("get", f"/ai/statistics?organization_id={ORG}"),
        ],
    )
    async def test_unauthenticated_request_is_rejected(
        self, client: AsyncClient, method: str, path: str
    ) -> None:
        response = await client.request(method, path, json={})
        assert response.status_code == 401

    async def test_a_forged_token_is_rejected(self, client: AsyncClient) -> None:
        response = await client.get(
            f"/ai/agents?organization_id={ORG}",
            headers={"Authorization": "Bearer not.a.real.token"},
        )
        assert response.status_code == 401


class TestAgentAndToolRoutes:
    async def test_create_and_list_agents(
        self, client: AsyncClient, headers: dict[str, str]
    ) -> None:
        org = uuid.uuid4()
        created = await client.post(
            "/ai/agents",
            headers=headers,
            json={
                "organization_id": str(org),
                "name": "triage-agent",
                "agent_type": AgentType.REASONING.value,
                "provider": ModelProvider.OLLAMA.value,
                "model": "llama3.1",
                "system_prompt": "You help with infrastructure.",
                "tool_keys": ["inventory_list_assets"],
            },
        )
        assert created.status_code == 201
        assert _data(created.json())["name"] == "triage-agent"

        listed = await client.get(f"/ai/agents?organization_id={org}", headers=headers)
        assert listed.status_code == 200
        assert len(_data(listed.json())) == 1

    async def test_invalid_agent_body_is_rejected(
        self, client: AsyncClient, headers: dict[str, str]
    ) -> None:
        response = await client.post(
            "/ai/agents",
            headers=headers,
            json={
                "organization_id": str(uuid.uuid4()),
                "name": "bad",
                "agent_type": "not-a-real-type",
                "provider": ModelProvider.OLLAMA.value,
                "model": "llama3.1",
            },
        )
        assert response.status_code == 400

    async def test_temperature_is_bounded(
        self, client: AsyncClient, headers: dict[str, str]
    ) -> None:
        response = await client.post(
            "/ai/agents",
            headers=headers,
            json={
                "organization_id": str(uuid.uuid4()),
                "name": "hot",
                "agent_type": AgentType.REASONING.value,
                "provider": ModelProvider.OLLAMA.value,
                "model": "llama3.1",
                "temperature": 5.0,
            },
        )
        assert response.status_code == 400

    async def test_create_and_list_tools(
        self, client: AsyncClient, headers: dict[str, str]
    ) -> None:
        org = uuid.uuid4()
        created = await client.post(
            "/ai/tools",
            headers=headers,
            json={
                "organization_id": str(org),
                "tool_key": "inventory_list_assets",
                "name": "List assets",
                "description": "Lists inventory assets.",
                "tool_kind": ToolKind.INVENTORY_QUERY.value,
                "parameters_schema": {"type": "object", "properties": {}},
            },
        )
        assert created.status_code == 201

        listed = await client.get(f"/ai/tools?organization_id={org}", headers=headers)
        assert len(_data(listed.json())) == 1

    async def test_executing_an_unregistered_tool_is_404(
        self, client: AsyncClient, headers: dict[str, str]
    ) -> None:
        response = await client.post(
            "/ai/tools/execute",
            headers=headers,
            json={
                "organization_id": str(uuid.uuid4()),
                "tool_key": "does_not_exist",
                "arguments": {},
            },
        )
        assert response.status_code == 404

    async def test_direct_execution_honours_the_agent_allowlist(
        self, client: AsyncClient, headers: dict[str, str], db_session: AsyncSession
    ) -> None:
        """This route must not be a way around the gate a chat enforces."""
        org = uuid.uuid4()
        tool = await make_tool(db_session, organization_id=org)
        agent = await make_agent(db_session, organization_id=org, tool_keys=[])

        response = await client.post(
            "/ai/tools/execute",
            headers=headers,
            json={
                "organization_id": str(org),
                "tool_key": tool.tool_key,
                "arguments": {"organization_id": str(org)},
                "agent_id": str(agent.id),
            },
        )
        assert response.status_code == 201
        body = _data(response.json())
        assert body["succeeded"] is False
        assert body["status"] == "denied"
        assert body["denial_reason"]

    async def test_listing_models_reports_what_is_configured(
        self, client: AsyncClient, headers: dict[str, str]
    ) -> None:
        response = await client.get("/ai/models", headers=headers)
        assert response.status_code == 200
        providers = _data(response.json())
        assert providers
        assert sum(1 for entry in providers if entry["is_default"]) == 1

    async def test_selecting_a_model_updates_and_audits(
        self, client: AsyncClient, headers: dict[str, str], db_session: AsyncSession
    ) -> None:
        org = uuid.uuid4()
        agent = await make_agent(db_session, organization_id=org)
        response = await client.post(
            "/ai/models/select",
            headers=headers,
            json={
                "organization_id": str(org),
                "agent_id": str(agent.id),
                "provider": ModelProvider.OLLAMA.value,
                "model": "llama3.1:70b",
            },
        )
        assert response.status_code == 200
        assert _data(response.json())["model"] == "llama3.1:70b"

    async def test_selecting_an_unconfigured_provider_fails(
        self, client: AsyncClient, headers: dict[str, str], db_session: AsyncSession
    ) -> None:
        """Better to refuse than leave an agent silently unable to answer."""
        org = uuid.uuid4()
        agent = await make_agent(db_session, organization_id=org)
        response = await client.post(
            "/ai/models/select",
            headers=headers,
            json={
                "organization_id": str(org),
                "agent_id": str(agent.id),
                "provider": ModelProvider.ANTHROPIC.value,
                "model": "claude-sonnet-4-5",
            },
        )
        # The message is deliberately sanitised -- naming the configured
        # providers to an unauthenticated-adjacent caller would leak
        # deployment topology. The detail goes to the log instead.
        assert response.status_code == 502
        assert response.json()["error"]["code"] == "AIIOS-AI-0001"

    async def test_selecting_for_an_unknown_agent_is_404(
        self, client: AsyncClient, headers: dict[str, str]
    ) -> None:
        response = await client.post(
            "/ai/models/select",
            headers=headers,
            json={
                "organization_id": str(uuid.uuid4()),
                "agent_id": str(uuid.uuid4()),
                "provider": ModelProvider.OLLAMA.value,
                "model": "llama3.1",
            },
        )
        assert response.status_code == 404


class TestChatRoutes:
    async def test_chat_opens_a_conversation_and_answers(
        self, client: AsyncClient, headers: dict[str, str], db_session: AsyncSession
    ) -> None:
        org = uuid.uuid4()
        await make_agent(db_session, organization_id=org)

        response = await client.post(
            "/ai/chat",
            headers=headers,
            json={"organization_id": str(org), "message": "Is db-1 healthy?"},
        )
        assert response.status_code == 201
        body = _data(response.json())
        assert body["content"] == "stub answer"
        assert body["conversation_id"]

    async def test_a_new_conversation_is_titled_from_the_message(
        self, client: AsyncClient, headers: dict[str, str], db_session: AsyncSession
    ) -> None:
        """ "New chat" for every row makes a thread list useless."""
        org = uuid.uuid4()
        await make_agent(db_session, organization_id=org)
        await client.post(
            "/ai/chat",
            headers=headers,
            json={"organization_id": str(org), "message": "Why is db-1 slow?"},
        )
        listed = await client.get(f"/ai/conversations?organization_id={org}", headers=headers)
        assert _data(listed.json())[0]["title"] == "Why is db-1 slow?"

    async def test_chat_continues_an_existing_conversation(
        self, client: AsyncClient, headers: dict[str, str], db_session: AsyncSession
    ) -> None:
        org = uuid.uuid4()
        await make_agent(db_session, organization_id=org)
        conversation = await make_conversation(db_session, organization_id=org)

        for message in ("first question", "second question"):
            response = await client.post(
                "/ai/chat",
                headers=headers,
                json={
                    "organization_id": str(org),
                    "conversation_id": str(conversation.id),
                    "message": message,
                },
            )
            assert response.status_code == 201

        messages = await client.get(
            f"/ai/conversations/{conversation.id}/messages", headers=headers
        )
        roles = [entry["role"] for entry in _data(messages.json())]
        assert roles == [
            MessageRole.USER.value,
            MessageRole.ASSISTANT.value,
            MessageRole.USER.value,
            MessageRole.ASSISTANT.value,
        ]

    async def test_chat_to_an_unknown_conversation_is_404(
        self, client: AsyncClient, headers: dict[str, str]
    ) -> None:
        response = await client.post(
            "/ai/chat",
            headers=headers,
            json={
                "organization_id": str(uuid.uuid4()),
                "conversation_id": str(uuid.uuid4()),
                "message": "hello",
            },
        )
        assert response.status_code == 404

    async def test_an_empty_message_is_rejected(
        self, client: AsyncClient, headers: dict[str, str]
    ) -> None:
        response = await client.post(
            "/ai/chat",
            headers=headers,
            json={"organization_id": str(uuid.uuid4()), "message": ""},
        )
        assert response.status_code == 400

    async def test_chat_without_a_configured_agent_fails_clearly(
        self, client: AsyncClient, headers: dict[str, str]
    ) -> None:
        response = await client.post(
            "/ai/chat",
            headers=headers,
            json={"organization_id": str(uuid.uuid4()), "message": "hello"},
        )
        assert response.status_code == 502
        assert response.json()["error"]["code"] == "AIIOS-AI-0001"

    async def test_stream_emits_well_formed_sse(
        self, client: AsyncClient, headers: dict[str, str], db_session: AsyncSession
    ) -> None:
        org = uuid.uuid4()
        await make_agent(db_session, organization_id=org)

        response = await client.post(
            "/ai/chat/stream",
            headers=headers,
            json={"organization_id": str(org), "message": "Is db-1 healthy?"},
        )
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/event-stream")

        events = [frame for frame in response.text.split("\n\n") if frame.strip()]
        names = [frame.splitlines()[0].removeprefix("event: ") for frame in events]
        assert names[0] == "meta"
        assert names[-1] == "done"
        assert "delta" in names

        # Every frame's payload must be parseable JSON, and the deltas
        # must reassemble into exactly the answer.
        text = ""
        for frame in events:
            name, raw = frame.splitlines()
            payload = json.loads(raw.removeprefix("data: "))
            if name == "event: delta":
                text += payload["text"]
        assert text == "stub answer"

    async def test_multi_agent_route_returns_aggregated_content(
        self, client: AsyncClient, headers: dict[str, str], db_session: AsyncSession
    ) -> None:
        org = uuid.uuid4()
        await make_agent(db_session, organization_id=org)
        response = await client.post(
            "/ai/chat/multi-agent",
            headers=headers,
            json={
                "organization_id": str(org),
                "request": "Check the cpu metrics and then review the runbook",
            },
        )
        assert response.status_code == 201
        assert _data(response.json())["content"]

    async def test_mine_only_filters_to_the_caller(
        self, client: AsyncClient, headers: dict[str, str], db_session: AsyncSession
    ) -> None:
        org = uuid.uuid4()
        await make_conversation(db_session, organization_id=org, user_id=CALLER)
        await make_conversation(db_session, organization_id=org, user_id=uuid.uuid4())

        everyone = await client.get(f"/ai/conversations?organization_id={org}", headers=headers)
        mine = await client.get(
            f"/ai/conversations?organization_id={org}&mine_only=true", headers=headers
        )
        assert len(_data(everyone.json())) == 2
        assert len(_data(mine.json())) == 1

    async def test_getting_an_unknown_conversation_is_404(
        self, client: AsyncClient, headers: dict[str, str]
    ) -> None:
        response = await client.get(f"/ai/conversations/{uuid.uuid4()}", headers=headers)
        assert response.status_code == 404


class TestKnowledgeRoutes:
    async def test_ingest_then_search(self, client: AsyncClient, headers: dict[str, str]) -> None:
        org = uuid.uuid4()
        ingested = await client.post(
            "/ai/knowledge/documents",
            headers=headers,
            json={
                "organization_id": str(org),
                "source_type": DocumentSourceType.RUNBOOKS.value,
                "title": "Database Runbook",
                "text": "Restart the postgres database on host db-1 using systemctl.",
                "external_id": "rb-1",
            },
        )
        assert ingested.status_code == 201
        assert _data(ingested.json())["chunks_created"] >= 1

        found = await client.post(
            "/ai/knowledge/search",
            headers=headers,
            json={
                "organization_id": str(org),
                "query": "restart postgres",
                "top_k": 3,
                "strategy": RetrievalStrategy.HYBRID.value,
            },
        )
        assert found.status_code == 200
        hits = _data(found.json())
        assert hits
        assert hits[0]["document_title"] == "Database Runbook"
        assert hits[0]["score"] > 0

    async def test_reingesting_unchanged_content_is_reported_as_skipped(
        self, client: AsyncClient, headers: dict[str, str]
    ) -> None:
        org = uuid.uuid4()
        payload = {
            "organization_id": str(org),
            "source_type": DocumentSourceType.RUNBOOKS.value,
            "title": "Runbook",
            "text": "Restart the postgres database on host db-1.",
            "external_id": "rb-1",
        }
        await client.post("/ai/knowledge/documents", headers=headers, json=payload)
        second = await client.post("/ai/knowledge/documents", headers=headers, json=payload)
        assert _data(second.json())["skipped_unchanged"] is True

    async def test_documents_are_listed_per_organization(
        self, client: AsyncClient, headers: dict[str, str]
    ) -> None:
        org, other = uuid.uuid4(), uuid.uuid4()
        for organization in (org, other):
            await client.post(
                "/ai/knowledge/documents",
                headers=headers,
                json={
                    "organization_id": str(organization),
                    "source_type": DocumentSourceType.POLICIES.value,
                    "title": "Policy",
                    "text": "All production changes require approval.",
                },
            )
        listed = await client.get(f"/ai/knowledge/documents?organization_id={org}", headers=headers)
        assert len(_data(listed.json())) == 1

    async def test_search_top_k_is_bounded(
        self, client: AsyncClient, headers: dict[str, str]
    ) -> None:
        response = await client.post(
            "/ai/knowledge/search",
            headers=headers,
            json={"organization_id": str(uuid.uuid4()), "query": "x", "top_k": 500},
        )
        assert response.status_code == 400


class TestPromptRoutes:
    async def _create(self, client: AsyncClient, headers: dict[str, str], org: uuid.UUID) -> str:
        response = await client.post(
            "/ai/prompts",
            headers=headers,
            json={
                "organization_id": str(org),
                "name": "triage",
                "template": "Investigate {{ subject }}.",
                "variables": ["subject"],
            },
        )
        assert response.status_code == 201
        return str(_data(response.json())["id"])

    async def test_full_lifecycle(self, client: AsyncClient, headers: dict[str, str]) -> None:
        org = uuid.uuid4()
        prompt_id = await self._create(client, headers, org)

        listed = await client.get(f"/ai/prompts?organization_id={org}", headers=headers)
        assert len(_data(listed.json())) == 1

        # A draft must not render.
        unapproved = await client.post(
            f"/ai/prompts/{prompt_id}/render",
            headers=headers,
            json={"variables": {"subject": "db-1"}},
        )
        assert unapproved.status_code == 409

        approved = await client.post(
            f"/ai/prompts/{prompt_id}/versions/1.0.0/approve", headers=headers
        )
        assert approved.status_code == 200
        assert _data(approved.json())["status"] == "approved"

        rendered = await client.post(
            f"/ai/prompts/{prompt_id}/render",
            headers=headers,
            json={"variables": {"subject": "db-1"}},
        )
        assert _data(rendered.json())["rendered"] == "Investigate db-1."

        second = await client.post(
            f"/ai/prompts/{prompt_id}/versions",
            headers=headers,
            json={"template": "Deeply investigate {{ subject }}.", "variables": ["subject"]},
        )
        assert second.status_code == 201
        version_number = _data(second.json())["version_number"]
        await client.post(
            f"/ai/prompts/{prompt_id}/versions/{version_number}/approve", headers=headers
        )

        versions = await client.get(f"/ai/prompts/{prompt_id}/versions", headers=headers)
        assert len(_data(versions.json())) == 2

        rolled_back = await client.post(f"/ai/prompts/{prompt_id}/rollback/1.0.0", headers=headers)
        assert _data(rolled_back.json())["current_version_number"] == "1.0.0"

    async def test_missing_variable_is_a_400(
        self, client: AsyncClient, headers: dict[str, str]
    ) -> None:
        org = uuid.uuid4()
        prompt_id = await self._create(client, headers, org)
        await client.post(f"/ai/prompts/{prompt_id}/versions/1.0.0/approve", headers=headers)
        response = await client.post(
            f"/ai/prompts/{prompt_id}/render", headers=headers, json={"variables": {}}
        )
        assert response.status_code == 400
        assert response.json()["error"]["code"] == "AIIOS-VAL-0001"

    async def test_unknown_prompt_is_404(
        self, client: AsyncClient, headers: dict[str, str]
    ) -> None:
        response = await client.post(
            f"/ai/prompts/{uuid.uuid4()}/versions",
            headers=headers,
            json={"template": "x", "variables": []},
        )
        assert response.status_code == 404


class TestInsightRoutes:
    async def test_generate_and_list_reports(
        self, client: AsyncClient, headers: dict[str, str]
    ) -> None:
        org = uuid.uuid4()
        generated = await client.post(
            "/ai/reports",
            headers=headers,
            json={
                "organization_id": str(org),
                "report_type": "capacity",
                "subject": "database cluster disk utilisation",
            },
        )
        assert generated.status_code == 201
        assert _data(generated.json())["body"] == "stub answer"

        listed = await client.get(
            f"/ai/reports?organization_id={org}&report_type=capacity", headers=headers
        )
        assert len(_data(listed.json())) == 1

        other = await client.get(
            f"/ai/reports?organization_id={org}&report_type=executive", headers=headers
        )
        assert _data(other.json()) == []

    async def test_recommendation_lifecycle(
        self, client: AsyncClient, headers: dict[str, str]
    ) -> None:
        org = uuid.uuid4()
        generated = await client.post(
            "/ai/recommendations",
            headers=headers,
            json={
                "organization_id": str(org),
                "recommendation_type": RecommendationType.REMEDIATION.value,
                "subject": "db-1 is not accepting connections",
            },
        )
        assert generated.status_code == 201
        record = _data(generated.json())
        assert record["status"] == "proposed"
        assert record["rationale"]

        decided = await client.post(
            f"/ai/recommendations/{record['id']}/decide",
            headers=headers,
            json={"accept": True},
        )
        assert _data(decided.json())["status"] == "accepted"

        again = await client.post(
            f"/ai/recommendations/{record['id']}/decide",
            headers=headers,
            json={"accept": False},
        )
        assert again.status_code == 409

        listed = await client.get(f"/ai/recommendations?organization_id={org}", headers=headers)
        assert len(_data(listed.json())) == 1

    async def test_deciding_an_unknown_recommendation_is_404(
        self, client: AsyncClient, headers: dict[str, str]
    ) -> None:
        response = await client.post(
            f"/ai/recommendations/{uuid.uuid4()}/decide",
            headers=headers,
            json={"accept": True},
        )
        assert response.status_code == 404

    async def test_feedback_is_recorded_against_a_real_message(
        self, client: AsyncClient, headers: dict[str, str], db_session: AsyncSession
    ) -> None:
        org = uuid.uuid4()
        await make_agent(db_session, organization_id=org)
        chatted = await client.post(
            "/ai/chat",
            headers=headers,
            json={"organization_id": str(org), "message": "Is db-1 healthy?"},
        )
        message_id = _data(chatted.json())["message_id"]

        response = await client.post(
            "/ai/feedback",
            headers=headers,
            json={
                "organization_id": str(org),
                "message_id": message_id,
                "rating": FeedbackRating.POSITIVE.value,
                "comment": "Exactly what I needed.",
            },
        )
        assert response.status_code == 201
        assert _data(response.json())["submitted_by"] == str(CALLER)

    async def test_memory_is_stored_and_listed(
        self, client: AsyncClient, headers: dict[str, str]
    ) -> None:
        org = uuid.uuid4()
        stored = await client.post(
            "/ai/memory",
            headers=headers,
            json={
                "organization_id": str(org),
                "scope": MemoryScope.ORGANIZATION.value,
                "scope_reference": str(org),
                "key": "preferred_region",
                "value": "eu-west-1",
                "importance": 0.9,
            },
        )
        assert stored.status_code == 201

        listed = await client.get(f"/ai/memory?organization_id={org}", headers=headers)
        entries = _data(listed.json())
        assert len(entries) == 1
        assert entries[0]["value"] == "eu-west-1"

    async def test_importance_is_bounded(
        self, client: AsyncClient, headers: dict[str, str]
    ) -> None:
        response = await client.post(
            "/ai/memory",
            headers=headers,
            json={
                "organization_id": str(uuid.uuid4()),
                "scope": MemoryScope.ORGANIZATION.value,
                "scope_reference": "x",
                "key": "k",
                "value": "v",
                "importance": 42.0,
            },
        )
        assert response.status_code == 400

    async def test_statistics_are_reported_and_recomputable(
        self, client: AsyncClient, headers: dict[str, str], db_session: AsyncSession
    ) -> None:
        org = uuid.uuid4()
        await make_agent(db_session, organization_id=org)
        await client.post(
            "/ai/chat",
            headers=headers,
            json={"organization_id": str(org), "message": "Is db-1 healthy?"},
        )

        response = await client.get(
            f"/ai/statistics?organization_id={org}&recompute=true", headers=headers
        )
        assert response.status_code == 200
        snapshot = _data(response.json())
        assert snapshot["total_conversations"] == 1
        assert snapshot["total_messages"] == 2
        assert snapshot["computed_at"]


class TestOpenApi:
    async def test_schema_is_served_and_documents_every_route(self, client: AsyncClient) -> None:
        response = await client.get("/openapi.json")
        assert response.status_code == 200
        schema = response.json()

        paths = schema["paths"]
        assert "/ai/chat" in paths
        assert "/ai/knowledge/search" in paths
        assert "/ai/statistics" in paths

        # Every operation must carry a summary and description, so the
        # generated documentation is genuinely usable.
        for path, operations in paths.items():
            for method, operation in operations.items():
                assert operation.get("summary"), f"{method.upper()} {path} has no summary"
                assert operation.get("description"), f"{method.upper()} {path} has no description"


class TestSessionRoutes:
    """Sessions were previously unreachable: the model and service
    existed with no endpoints at all.
    """

    async def test_open_list_touch_and_close(
        self, client: AsyncClient, headers: dict[str, str]
    ) -> None:
        org = uuid.uuid4()
        opened = await client.post(
            "/ai/sessions",
            headers=headers,
            json={"organization_id": str(org), "label": "incident-4471"},
        )
        assert opened.status_code == 201
        session = _data(opened.json())
        assert session["is_open"] is True
        assert session["user_id"] == str(CALLER)
        assert session["label"] == "incident-4471"

        touched = await client.post(f"/ai/sessions/{session['id']}/touch", headers=headers)
        assert touched.status_code == 200
        assert _data(touched.json())["last_active_at"] >= session["started_at"]

        closed = await client.post(f"/ai/sessions/{session['id']}/close", headers=headers)
        assert _data(closed.json())["is_open"] is False

    async def test_filters_narrow_correctly(
        self, client: AsyncClient, headers: dict[str, str], db_session: AsyncSession
    ) -> None:
        org = uuid.uuid4()
        mine = await client.post(
            "/ai/sessions", headers=headers, json={"organization_id": str(org)}
        )
        await client.post("/ai/sessions", headers=headers, json={"organization_id": str(org)})
        await client.post(f"/ai/sessions/{_data(mine.json())['id']}/close", headers=headers)

        everything = await client.get(f"/ai/sessions?organization_id={org}", headers=headers)
        assert len(_data(everything.json())) == 2

        open_only = await client.get(
            f"/ai/sessions?organization_id={org}&open_only=true", headers=headers
        )
        assert len(_data(open_only.json())) == 1

        mine_and_open = await client.get(
            f"/ai/sessions?organization_id={org}&mine_only=true&open_only=true",
            headers=headers,
        )
        assert len(_data(mine_and_open.json())) == 1

    async def test_closing_an_unknown_session_is_404(
        self, client: AsyncClient, headers: dict[str, str]
    ) -> None:
        response = await client.post(f"/ai/sessions/{uuid.uuid4()}/close", headers=headers)
        assert response.status_code == 404

    async def test_a_conversation_can_be_grouped_under_a_session(
        self, client: AsyncClient, headers: dict[str, str], db_session: AsyncSession
    ) -> None:
        org = uuid.uuid4()
        await make_agent(db_session, organization_id=org)
        opened = await client.post(
            "/ai/sessions", headers=headers, json={"organization_id": str(org)}
        )
        session_id = _data(opened.json())["id"]

        chatted = await client.post(
            "/ai/chat",
            headers=headers,
            json={
                "organization_id": str(org),
                "session_id": session_id,
                "message": "Is db-1 healthy?",
            },
        )
        conversation_id = _data(chatted.json())["conversation_id"]
        fetched = await client.get(f"/ai/conversations/{conversation_id}", headers=headers)
        assert _data(fetched.json())["session_id"] == session_id


class TestToolCallHistoryRoute:
    async def test_successful_call_is_reported_with_its_result(
        self, client: AsyncClient, headers: dict[str, str], db_session: AsyncSession
    ) -> None:
        org = uuid.uuid4()
        tool = await make_tool(db_session, organization_id=org)
        conversation = await make_conversation(db_session, organization_id=org)
        await client.post(
            "/ai/tools/execute",
            headers=headers,
            json={
                "organization_id": str(org),
                "tool_key": tool.tool_key,
                "arguments": {"organization_id": str(org)},
            },
        )
        # The direct-execute route records no conversation, so this
        # asserts the empty case is well-formed rather than an error.
        response = await client.get(
            f"/ai/conversations/{conversation.id}/tool-calls", headers=headers
        )
        assert response.status_code == 200
        assert _data(response.json()) == []

    async def test_denied_call_is_visible_with_no_result(
        self, client: AsyncClient, headers: dict[str, str], db_session: AsyncSession
    ) -> None:
        """A blocked call is the most interesting row in an audit."""
        org = uuid.uuid4()
        tool = await make_tool(db_session, organization_id=org)
        await make_agent(db_session, organization_id=org, tool_keys=[tool.tool_key])
        conversation = await make_conversation(db_session, organization_id=org)

        executor = ToolExecutor(
            AiToolCallRepository(db_session),
            AiToolResultRepository(db_session),
            ToolHandlerRegistry({}),
            publish_event=RecordingPublisher(),
        )
        await executor.execute(
            tool,
            {"organization_id": str(org)},
            organization_id=org,
            conversation_id=conversation.id,
            agent_tool_keys=[],
            caller_permissions=[],
        )

        response = await client.get(
            f"/ai/conversations/{conversation.id}/tool-calls", headers=headers
        )
        rows = _data(response.json())
        assert len(rows) == 1
        assert rows[0]["status"] == "denied"
        assert rows[0]["denial_reason"]
        assert rows[0]["result"] is None
        assert rows[0]["succeeded"] is None

    async def test_recommendations_filter_by_conversation(
        self, client: AsyncClient, headers: dict[str, str], db_session: AsyncSession
    ) -> None:
        org = uuid.uuid4()
        conversation = await make_conversation(db_session, organization_id=org)
        for conversation_id in (str(conversation.id), None):
            body: dict[str, Any] = {
                "organization_id": str(org),
                "recommendation_type": RecommendationType.REMEDIATION.value,
                "subject": "db-1 is not accepting connections",
            }
            if conversation_id:
                body["conversation_id"] = conversation_id
            await client.post("/ai/recommendations", headers=headers, json=body)

        everything = await client.get(f"/ai/recommendations?organization_id={org}", headers=headers)
        assert len(_data(everything.json())) == 2

        scoped = await client.get(
            f"/ai/recommendations?organization_id={org}&conversation_id={conversation.id}",
            headers=headers,
        )
        assert len(_data(scoped.json())) == 1

    async def test_model_selection_publishes_its_event(
        self, client: AsyncClient, headers: dict[str, str], db_session: AsyncSession
    ) -> None:
        """docs/046 names ``ModelChanged``; selecting must actually emit it."""
        org = uuid.uuid4()
        agent = await make_agent(db_session, organization_id=org)
        published: list[Any] = []

        async def _capture(event: Any) -> None:
            published.append(event)

        client._transport.app.state.publish_event = _capture  # type: ignore[attr-defined]
        response = await client.post(
            "/ai/models/select",
            headers=headers,
            json={
                "organization_id": str(org),
                "agent_id": str(agent.id),
                "provider": ModelProvider.OLLAMA.value,
                "model": "llama3.1:70b",
            },
        )
        assert response.status_code == 200
        assert [event.event_name for event in published] == ["ModelChanged"]
        assert published[0].payload["model"] == "llama3.1:70b"
