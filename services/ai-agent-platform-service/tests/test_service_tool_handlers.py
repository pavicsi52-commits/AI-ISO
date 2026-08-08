"""Tests for :mod:`app.services.tool_handlers` -- ``HandlerDependencies``
and ``build_handler_registry``.

The module's own load-bearing rule is that a tool whose kind has no
client configured on this deployment is **skipped**, never registered
with a handler that could only fail, because
:meth:`~app.tool_registry.registry.ToolHandlerRegistry.get` already
reports "no registered handler" as a clean denial. Every kind is
checked here in both states -- dependency present and dependency
absent -- and the handlers that do get registered are proved to work by
really running them: real HTTP against the standing RabbitMQ management
endpoint, and real SQL against the SAVEPOINT-isolated Postgres session.

Tool rows are registered for real through ``ToolService`` rather than
built in memory, so ``tool_kind`` is exercised both as the enum the
caller passed and as the plain ``str`` a row loaded back out of
Postgres actually carries.
"""

from __future__ import annotations

import sys

import httpx
import pytest

from app.clients.automation_client import AutomationClient
from app.graph.client import GraphClient
from app.models.enums import ToolKind
from app.services.tool_handlers import HandlerDependencies, build_handler_registry

RABBITMQ_MGMT_URL = "http://127.0.0.1:15672"
"""A real, already-running container from the standing compose stack."""

UNREACHABLE_URL = "http://127.0.0.1:1"
"""A real loopback port nothing listens on: fails fast, never mocked."""


@pytest.fixture
def automation_client(http_client: httpx.AsyncClient) -> AutomationClient:
    """A real client; no call is made in these tests, only wiring."""
    return AutomationClient(http_client, base_url=UNREACHABLE_URL, caller_token="caller-token")


@pytest.fixture
def disabled_graph_client() -> GraphClient:
    """A real ``GraphClient`` with no driver -- genuinely unconfigured."""
    return GraphClient(None)


def _registry(tools, *, http_client, sandbox_policy, **overrides):
    """Build a registry with everything unconfigured unless overridden."""
    return build_handler_registry(
        tools,
        http_client=http_client,
        sandbox_policy=sandbox_policy,
        automation_client=overrides.get("automation_client"),
        graph_client=overrides.get("graph_client"),
        session=overrides.get("session"),
    )


async def _tool(tool_service, organization_id, tool_key, kind, *, metadata=None):
    return await tool_service.register_tool(
        organization_id=organization_id,
        tool_key=tool_key,
        name=tool_key.title(),
        tool_kind=kind,
        metadata=metadata,
    )


# ---------------------------------------------------------------------------
# HandlerDependencies
# ---------------------------------------------------------------------------


class TestHandlerDependencies:
    def test_carries_every_dependency(
        self, http_client, sandbox_policy, automation_client, disabled_graph_client, db_session
    ) -> None:
        deps = HandlerDependencies(
            http_client=http_client,
            sandbox_policy=sandbox_policy,
            automation_client=automation_client,
            graph_client=disabled_graph_client,
            session=db_session,
        )

        assert deps.http_client is http_client
        assert deps.sandbox_policy is sandbox_policy
        assert deps.automation_client is automation_client
        assert deps.graph_client is disabled_graph_client
        assert deps.session is db_session

    def test_is_frozen(self, http_client, sandbox_policy) -> None:
        deps = HandlerDependencies(
            http_client=http_client,
            sandbox_policy=sandbox_policy,
            automation_client=None,
            graph_client=None,
            session=None,
        )

        with pytest.raises(AttributeError):
            deps.session = None  # type: ignore[misc]


# ---------------------------------------------------------------------------
# the four kinds whose dependency is always present
# ---------------------------------------------------------------------------


class TestAlwaysAvailableKinds:
    @pytest.mark.parametrize(
        "kind", [ToolKind.REST, ToolKind.WEBHOOK, ToolKind.SHELL, ToolKind.PYTHON]
    )
    async def test_each_kind_gets_a_handler(
        self, tool_service, http_client, sandbox_policy, kind, organization_id
    ) -> None:
        tool = await _tool(tool_service, organization_id, "sample", kind)

        registry = _registry([tool], http_client=http_client, sandbox_policy=sandbox_policy)

        assert registry.registered_keys == ["sample"]
        assert registry.get("sample") is not None

    async def test_the_rest_handler_really_makes_the_call(
        self, tool_service, http_client, sandbox_policy, organization_id
    ) -> None:
        tool = await _tool(tool_service, organization_id, "probe", ToolKind.REST)
        registry = _registry([tool], http_client=http_client, sandbox_policy=sandbox_policy)

        handler = registry.get("probe")
        assert handler is not None
        result = await handler({"url": RABBITMQ_MGMT_URL, "method": "GET"})

        assert result["status_code"] == 200

    async def test_the_webhook_handler_really_makes_the_call(
        self, tool_service, http_client, sandbox_policy, organization_id
    ) -> None:
        tool = await _tool(tool_service, organization_id, "notify", ToolKind.WEBHOOK)
        registry = _registry([tool], http_client=http_client, sandbox_policy=sandbox_policy)

        handler = registry.get("notify")
        assert handler is not None
        result = await handler({"url": RABBITMQ_MGMT_URL, "method": "GET", "payload": {}})

        assert result["status_code"] == 200

    async def test_the_python_handler_really_runs_a_script(
        self, tool_service, http_client, sandbox_policy, organization_id
    ) -> None:
        tool = await _tool(tool_service, organization_id, "compute", ToolKind.PYTHON)
        registry = _registry([tool], http_client=http_client, sandbox_policy=sandbox_policy)

        handler = registry.get("compute")
        assert handler is not None
        result = await handler({"script": "print(6 * 7)"})

        assert result["succeeded"] is True
        assert result["stdout"].strip() == "42"

    async def test_the_shell_handler_really_runs_a_command(
        self, tool_service, http_client, sandbox_policy, organization_id
    ) -> None:
        tool = await _tool(tool_service, organization_id, "run", ToolKind.SHELL)
        registry = _registry([tool], http_client=http_client, sandbox_policy=sandbox_policy)

        handler = registry.get("run")
        assert handler is not None
        result = await handler({"command": [sys.executable, "-c", "print('hello')"]})

        assert result["succeeded"] is True
        assert result["stdout"].strip() == "hello"


# ---------------------------------------------------------------------------
# AUTOMATION / CONNECTOR_SDK
# ---------------------------------------------------------------------------


class TestAutomationKinds:
    @pytest.mark.parametrize("kind", [ToolKind.AUTOMATION, ToolKind.CONNECTOR_SDK])
    async def test_skipped_when_no_automation_client_is_configured(
        self, tool_service, http_client, sandbox_policy, kind, organization_id
    ) -> None:
        tool = await _tool(tool_service, organization_id, "job", kind)

        registry = _registry([tool], http_client=http_client, sandbox_policy=sandbox_policy)

        assert registry.registered_keys == []
        assert registry.get("job") is None

    @pytest.mark.parametrize("kind", [ToolKind.AUTOMATION, ToolKind.CONNECTOR_SDK])
    async def test_registered_when_an_automation_client_is_configured(
        self, tool_service, http_client, sandbox_policy, automation_client, kind, organization_id
    ) -> None:
        tool = await _tool(tool_service, organization_id, "job", kind)

        registry = _registry(
            [tool],
            http_client=http_client,
            sandbox_policy=sandbox_policy,
            automation_client=automation_client,
        )

        assert registry.registered_keys == ["job"]


# ---------------------------------------------------------------------------
# KNOWLEDGE_GRAPH_QUERY
# ---------------------------------------------------------------------------


class TestKnowledgeGraphKind:
    async def test_skipped_when_no_graph_client_is_configured(
        self, tool_service, http_client, sandbox_policy, organization_id
    ) -> None:
        tool = await _tool(tool_service, organization_id, "cypher", ToolKind.KNOWLEDGE_GRAPH_QUERY)

        registry = _registry([tool], http_client=http_client, sandbox_policy=sandbox_policy)

        assert registry.registered_keys == []

    async def test_skipped_when_the_graph_client_is_disabled(
        self, tool_service, http_client, sandbox_policy, disabled_graph_client, organization_id
    ) -> None:
        tool = await _tool(tool_service, organization_id, "cypher", ToolKind.KNOWLEDGE_GRAPH_QUERY)

        registry = _registry(
            [tool],
            http_client=http_client,
            sandbox_policy=sandbox_policy,
            graph_client=disabled_graph_client,
        )

        assert disabled_graph_client.enabled is False
        assert registry.registered_keys == []

    async def test_registered_and_working_against_the_real_graph(
        self, tool_service, http_client, sandbox_policy, graph_client, organization_id
    ) -> None:
        tool = await _tool(tool_service, organization_id, "cypher", ToolKind.KNOWLEDGE_GRAPH_QUERY)

        registry = _registry(
            [tool],
            http_client=http_client,
            sandbox_policy=sandbox_policy,
            graph_client=graph_client,
        )

        handler = registry.get("cypher")
        assert handler is not None
        result = await handler({"cypher": "RETURN 1 AS answer"})

        assert result["records"] == [{"answer": 1}]
        assert result["row_count"] == 1
        assert result["truncated"] is False


# ---------------------------------------------------------------------------
# DATABASE_QUERY
# ---------------------------------------------------------------------------


class TestDatabaseQueryKind:
    async def test_skipped_when_no_session_is_configured(
        self, tool_service, http_client, sandbox_policy, organization_id
    ) -> None:
        tool = await _tool(
            tool_service,
            organization_id,
            "lookup",
            ToolKind.DATABASE_QUERY,
            metadata={"sql_template": "SELECT 1 AS answer"},
        )

        registry = _registry([tool], http_client=http_client, sandbox_policy=sandbox_policy)

        assert registry.registered_keys == []

    async def test_skipped_when_the_tool_carries_no_sql_template(
        self, tool_service, http_client, sandbox_policy, db_session, organization_id
    ) -> None:
        tool = await _tool(tool_service, organization_id, "lookup", ToolKind.DATABASE_QUERY)

        registry = _registry(
            [tool], http_client=http_client, sandbox_policy=sandbox_policy, session=db_session
        )

        assert tool.metadata_ == {}
        assert registry.registered_keys == []

    async def test_skipped_when_the_sql_template_is_not_a_select(
        self, tool_service, http_client, sandbox_policy, db_session, organization_id
    ) -> None:
        tool = await _tool(
            tool_service,
            organization_id,
            "mutator",
            ToolKind.DATABASE_QUERY,
            metadata={"sql_template": "DELETE FROM agents"},
        )

        registry = _registry(
            [tool], http_client=http_client, sandbox_policy=sandbox_policy, session=db_session
        )

        assert registry.registered_keys == []

    async def test_one_rejected_template_does_not_take_the_other_tools_down(
        self, tool_service, http_client, sandbox_policy, db_session, organization_id
    ) -> None:
        bad = await _tool(
            tool_service,
            organization_id,
            "mutator",
            ToolKind.DATABASE_QUERY,
            metadata={"sql_template": "DROP TABLE agents"},
        )
        good = await _tool(tool_service, organization_id, "probe", ToolKind.REST)

        registry = _registry(
            [bad, good],
            http_client=http_client,
            sandbox_policy=sandbox_policy,
            session=db_session,
        )

        assert registry.registered_keys == ["probe"]

    async def test_registered_and_working_against_the_real_database(
        self, tool_service, http_client, sandbox_policy, db_session, organization_id
    ) -> None:
        tool = await _tool(
            tool_service,
            organization_id,
            "lookup",
            ToolKind.DATABASE_QUERY,
            metadata={"sql_template": "SELECT 1 AS answer"},
        )

        registry = _registry(
            [tool], http_client=http_client, sandbox_policy=sandbox_policy, session=db_session
        )

        handler = registry.get("lookup")
        assert handler is not None
        result = await handler({})

        assert result["rows"] == [{"answer": 1}]
        assert result["row_count"] == 1
        assert result["truncated"] is False

    async def test_bind_parameters_come_from_the_arguments(
        self, tool_service, http_client, sandbox_policy, db_session, organization_id
    ) -> None:
        tool = await _tool(
            tool_service,
            organization_id,
            "echo",
            ToolKind.DATABASE_QUERY,
            metadata={"sql_template": "SELECT :value AS echoed"},
        )

        registry = _registry(
            [tool], http_client=http_client, sandbox_policy=sandbox_policy, session=db_session
        )

        handler = registry.get("echo")
        assert handler is not None
        result = await handler({"value": "from-the-model"})

        assert result["rows"] == [{"echoed": "from-the-model"}]


# ---------------------------------------------------------------------------
# kinds with no generic handler at all
# ---------------------------------------------------------------------------


class TestUnhandledKinds:
    @pytest.mark.parametrize("kind", [ToolKind.WORKFLOW, ToolKind.CUSTOM])
    async def test_skipped_even_with_every_dependency_configured(
        self,
        tool_service,
        http_client,
        sandbox_policy,
        automation_client,
        graph_client,
        db_session,
        kind,
        organization_id,
    ) -> None:
        tool = await _tool(tool_service, organization_id, "special", kind)

        registry = _registry(
            [tool],
            http_client=http_client,
            sandbox_policy=sandbox_policy,
            automation_client=automation_client,
            graph_client=graph_client,
            session=db_session,
        )

        assert registry.registered_keys == []


# ---------------------------------------------------------------------------
# whole-registry behaviour
# ---------------------------------------------------------------------------


class TestRegistryAssembly:
    async def test_no_tools_produces_an_empty_registry(self, http_client, sandbox_policy) -> None:
        registry = _registry([], http_client=http_client, sandbox_policy=sandbox_policy)

        assert registry.registered_keys == []

    async def test_only_the_supported_kinds_survive(
        self, tool_service, http_client, sandbox_policy, organization_id
    ) -> None:
        tools = [
            await _tool(tool_service, organization_id, "rest-tool", ToolKind.REST),
            await _tool(tool_service, organization_id, "shell-tool", ToolKind.SHELL),
            await _tool(tool_service, organization_id, "automation-tool", ToolKind.AUTOMATION),
            await _tool(
                tool_service, organization_id, "graph-tool", ToolKind.KNOWLEDGE_GRAPH_QUERY
            ),
            await _tool(tool_service, organization_id, "db-tool", ToolKind.DATABASE_QUERY),
            await _tool(tool_service, organization_id, "custom-tool", ToolKind.CUSTOM),
        ]

        registry = _registry(tools, http_client=http_client, sandbox_policy=sandbox_policy)

        assert registry.registered_keys == ["rest-tool", "shell-tool"]

    async def test_a_loaded_rows_string_kind_is_coerced(
        self, tool_service, tools_repo, http_client, sandbox_policy, db_session, organization_id
    ) -> None:
        tool = await _tool(tool_service, organization_id, "reloaded", ToolKind.REST)
        tool_id = tool.id
        db_session.expire_all()
        reloaded = await tools_repo.require_in_org(organization_id, tool_id)

        registry = _registry([reloaded], http_client=http_client, sandbox_policy=sandbox_policy)

        assert isinstance(reloaded.tool_kind, str)
        assert not isinstance(reloaded.tool_kind, ToolKind)
        assert registry.registered_keys == ["reloaded"]

    async def test_a_later_tool_with_the_same_key_replaces_the_earlier_handler(
        self, tool_service, http_client, sandbox_policy, organization_id
    ) -> None:
        first = await _tool(tool_service, organization_id, "shared", ToolKind.REST)
        second = await _tool(tool_service, organization_id, "shared-2", ToolKind.SHELL)
        second.tool_key = "shared"

        registry = _registry(
            [first, second], http_client=http_client, sandbox_policy=sandbox_policy
        )

        handler = registry.get("shared")
        assert handler is not None
        assert registry.registered_keys == ["shared"]
        result = await handler({"command": [sys.executable, "-c", "print('second')"]})
        assert result["stdout"].strip() == "second"
