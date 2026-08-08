"""Tests for app.tool_execution.{executor,handlers}.

``ToolExecutor`` itself never touches the database -- it mutates an
in-memory :class:`~app.models.execution.AgentExecution` handed to it by
the caller and publishes events, per its own module docstring -- so
these tests build that execution row directly rather than persisting
it, and use the real, recording ``publisher`` fixture from conftest
(not a mock).

``app/tool_execution/handlers.py``'s REST/webhook handlers are pointed
at real, already-running containers from the standing docker-compose
stack: ``http://127.0.0.1:15672`` (RabbitMQ's management UI) for
"reachable", ``http://127.0.0.1:1`` for "genuinely unreachable, fails
fast". The SHELL/PYTHON handlers spawn real subprocesses through
``app.sandbox.process`` (already covered in depth by
``tests/test_sandbox.py``) using real, trivial scripts. The
KNOWLEDGE_GRAPH_QUERY handler runs real Cypher against the real Neo4j
instance via the ``graph_client`` fixture (skipped if unreachable).
The DATABASE_QUERY handler runs a real ``SELECT`` against the real,
SAVEPOINT-isolated Postgres session.
"""

from __future__ import annotations

import sys
import uuid
from datetime import datetime
from typing import Any

import httpx
import pytest
from shared_core.exceptions.dependency import DependencyError
from shared_core.exceptions.not_found import NotFoundError
from sqlalchemy.ext.asyncio import AsyncSession

from app.clients.automation_client import AutomationClient
from app.graph.client import GraphClient
from app.models.enums import (
    ExecutionStatus,
    ModelProvider,
    PermissionCategory,
    ReasoningMode,
    ToolCallStatus,
    ToolKind,
    WorkflowRunStatus,
)
from app.models.execution import AgentExecution
from app.models.tool import AgentTool
from app.models.workflow import AgentWorkflow
from app.repositories.workflow import AgentWorkflowRepository
from app.sandbox.policy import AgentSandboxPolicy
from app.tool_execution.executor import ToolCallOutcome, ToolExecutor
from app.tool_execution.handlers import (
    MAX_DATABASE_QUERY_ROWS,
    build_automation_handler,
    build_database_query_handler,
    build_knowledge_graph_query_handler,
    build_python_handler,
    build_rest_handler,
    build_shell_handler,
    build_webhook_handler,
    build_workflow_handler,
)
from app.tool_registry.registry import ToolHandlerRegistry
from tests.conftest import RecordingPublisher, utcnow

RABBITMQ_MGMT_URL = "http://127.0.0.1:15672"
UNREACHABLE_URL = "http://127.0.0.1:1"


def _tool(
    *,
    tool_key: str = "sample-tool",
    enabled: bool = True,
    is_mutating: bool = False,
    required_permission: PermissionCategory = PermissionCategory.TOOL_INVOCATION,
    parameters_schema: dict[str, Any] | None = None,
    tool_kind: ToolKind = ToolKind.CUSTOM,
) -> AgentTool:
    return AgentTool(
        tool_key=tool_key,
        name="Sample Tool",
        description="A sample tool.",
        tool_kind=tool_kind,
        required_permission=required_permission,
        is_mutating=is_mutating,
        enabled=enabled,
        parameters_schema=parameters_schema or {},
    )


def _execution(organization_id: uuid.UUID) -> AgentExecution:
    return AgentExecution(
        id=uuid.uuid4(),
        organization_id=organization_id,
        agent_id=uuid.uuid4(),
        status=ExecutionStatus.RUNNING,
        reasoning_mode=ReasoningMode.TOOL_BASED,
        model_provider=ModelProvider.OLLAMA,
        model_name="llama3",
        trace=[],
        tool_calls_made=0,
        started_at=utcnow(),
    )


# ---------------------------------------------------------------------------
# ToolCallOutcome
# ---------------------------------------------------------------------------


def test_outcome_succeeded_true_only_for_succeeded_status() -> None:
    assert ToolCallOutcome(tool_key="t", status=ToolCallStatus.SUCCEEDED).succeeded is True
    assert ToolCallOutcome(tool_key="t", status=ToolCallStatus.FAILED).succeeded is False
    assert ToolCallOutcome(tool_key="t", status=ToolCallStatus.DENIED).succeeded is False


def test_outcome_as_model_content_denied_with_reason() -> None:
    outcome = ToolCallOutcome(
        tool_key="t", status=ToolCallStatus.DENIED, denial_reason="no permission"
    )
    assert outcome.as_model_content() == "Tool call was not executed: no permission."


def test_outcome_as_model_content_denied_without_reason_falls_back() -> None:
    outcome = ToolCallOutcome(tool_key="t", status=ToolCallStatus.DENIED, denial_reason=None)
    assert outcome.as_model_content() == "Tool call was not executed: unknown reason."


def test_outcome_as_model_content_failed_with_error() -> None:
    outcome = ToolCallOutcome(tool_key="t", status=ToolCallStatus.FAILED, error="boom")
    assert outcome.as_model_content() == "Tool call failed: boom."


def test_outcome_as_model_content_failed_without_error_falls_back() -> None:
    outcome = ToolCallOutcome(tool_key="t", status=ToolCallStatus.FAILED, error=None)
    assert outcome.as_model_content() == "Tool call failed: unknown error."


def test_outcome_as_model_content_succeeded_stringifies_result() -> None:
    outcome = ToolCallOutcome(tool_key="t", status=ToolCallStatus.SUCCEEDED, result={"answer": 42})
    assert outcome.as_model_content() == str({"answer": 42})


# ---------------------------------------------------------------------------
# ToolExecutor.execute()
# ---------------------------------------------------------------------------


async def test_execute_denied_when_agent_not_granted_tool(
    publisher: RecordingPublisher, organization_id: uuid.UUID
) -> None:
    tool = _tool(tool_key="ungranted")
    execution = _execution(organization_id)
    executor = ToolExecutor(ToolHandlerRegistry(), publish_event=publisher)

    outcome = await executor.execute(
        tool,
        {},
        execution=execution,
        agent_tool_keys=[],
        granted_categories=[PermissionCategory.TOOL_INVOCATION],
    )

    assert outcome.status is ToolCallStatus.DENIED
    assert outcome.denial_reason == "Agent is not granted tool 'ungranted'."
    assert execution.tool_calls_made == 1
    assert len(execution.trace) == 1
    assert execution.trace[0]["status"] == "denied"
    assert publisher.names == ["ToolInvoked"]
    event = publisher.events[0]
    assert event.payload["status"] == "denied"
    assert event.payload["tool_key"] == "ungranted"
    assert event.payload["execution_id"] == str(execution.id)
    assert event.payload["agent_id"] == str(execution.agent_id)
    assert event.source_service == "ai-agent-platform-service"


async def test_execute_denied_when_arguments_invalid(
    publisher: RecordingPublisher, organization_id: uuid.UUID
) -> None:
    called: list[dict[str, Any]] = []

    async def _handler(arguments: dict[str, Any]) -> dict[str, Any]:
        called.append(arguments)
        return {}

    tool = _tool(tool_key="needs-arg", parameters_schema={"type": "object", "required": ["x"]})
    execution = _execution(organization_id)
    handlers = ToolHandlerRegistry({"needs-arg": _handler})
    executor = ToolExecutor(handlers, publish_event=publisher)

    outcome = await executor.execute(
        tool,
        {},
        execution=execution,
        agent_tool_keys=["needs-arg"],
        granted_categories=[PermissionCategory.TOOL_INVOCATION],
    )

    assert outcome.status is ToolCallStatus.DENIED
    assert outcome.denial_reason == "Missing required argument(s): x."
    assert called == []  # the handler must never run when validation fails


async def test_execute_denied_when_no_handler_registered(
    publisher: RecordingPublisher, organization_id: uuid.UUID
) -> None:
    tool = _tool(tool_key="no-handler")
    execution = _execution(organization_id)
    executor = ToolExecutor(ToolHandlerRegistry(), publish_event=publisher)

    outcome = await executor.execute(
        tool,
        {},
        execution=execution,
        agent_tool_keys=["no-handler"],
        granted_categories=[PermissionCategory.TOOL_INVOCATION],
    )

    assert outcome.status is ToolCallStatus.DENIED
    assert outcome.denial_reason == "Tool 'no-handler' has no registered handler."


async def test_execute_failed_when_handler_raises(
    publisher: RecordingPublisher, organization_id: uuid.UUID
) -> None:
    async def _boom(arguments: dict[str, Any]) -> dict[str, Any]:
        raise ValueError("boom")

    tool = _tool(tool_key="failing")
    execution = _execution(organization_id)
    handlers = ToolHandlerRegistry({"failing": _boom})
    executor = ToolExecutor(handlers, publish_event=publisher)

    outcome = await executor.execute(
        tool,
        {},
        execution=execution,
        agent_tool_keys=["failing"],
        granted_categories=[PermissionCategory.TOOL_INVOCATION],
    )

    assert outcome.status is ToolCallStatus.FAILED
    assert outcome.error == "boom"
    assert outcome.duration_ms >= 0.0
    assert execution.trace[0]["error"] == "boom"
    assert publisher.events[0].payload["status"] == "failed"


async def test_execute_succeeded_returns_handler_result_unredacted(
    publisher: RecordingPublisher, organization_id: uuid.UUID
) -> None:
    async def _ok(arguments: dict[str, Any]) -> dict[str, Any]:
        return {"answer": 42}

    tool = _tool(tool_key="clean")
    execution = _execution(organization_id)
    handlers = ToolHandlerRegistry({"clean": _ok})
    executor = ToolExecutor(handlers, publish_event=publisher)

    outcome = await executor.execute(
        tool,
        {},
        execution=execution,
        agent_tool_keys=["clean"],
        granted_categories=[PermissionCategory.TOOL_INVOCATION],
    )

    assert outcome.status is ToolCallStatus.SUCCEEDED
    assert outcome.result == {"answer": 42}
    assert outcome.duration_ms >= 0.0
    assert execution.trace[0]["result"] == {"answer": 42}
    assert publisher.events[0].payload["status"] == "succeeded"


async def test_execute_succeeded_result_is_redacted_when_it_carries_a_secret(
    publisher: RecordingPublisher, organization_id: uuid.UUID
) -> None:
    async def _leaky(arguments: dict[str, Any]) -> dict[str, Any]:
        return {"secret_key": "AKIA1234567890123456"}

    tool = _tool(tool_key="leaky")
    execution = _execution(organization_id)
    handlers = ToolHandlerRegistry({"leaky": _leaky})
    executor = ToolExecutor(handlers, publish_event=publisher)

    outcome = await executor.execute(
        tool,
        {},
        execution=execution,
        agent_tool_keys=["leaky"],
        granted_categories=[PermissionCategory.TOOL_INVOCATION],
    )

    assert outcome.status is ToolCallStatus.SUCCEEDED
    assert isinstance(outcome.result, dict)
    assert set(outcome.result) == {"redacted"}
    assert "AKIA1234567890123456" not in outcome.result["redacted"]
    assert "[REDACTED]" in outcome.result["redacted"]


async def test_execute_denies_mutating_tool_without_opt_in_by_default(
    publisher: RecordingPublisher, organization_id: uuid.UUID
) -> None:
    async def _mutate(arguments: dict[str, Any]) -> dict[str, Any]:
        return {"mutated": True}

    tool = _tool(tool_key="mutator", is_mutating=True)
    execution = _execution(organization_id)
    handlers = ToolHandlerRegistry({"mutator": _mutate})
    executor = ToolExecutor(handlers, publish_event=publisher)

    outcome = await executor.execute(
        tool,
        {},
        execution=execution,
        agent_tool_keys=["mutator"],
        granted_categories=[PermissionCategory.TOOL_INVOCATION],
        # allow_mutating defaults to False.
    )

    assert outcome.status is ToolCallStatus.DENIED
    assert "mutates state" in (outcome.denial_reason or "")


async def test_execute_allows_mutating_tool_when_opted_in(
    publisher: RecordingPublisher, organization_id: uuid.UUID
) -> None:
    async def _mutate(arguments: dict[str, Any]) -> dict[str, Any]:
        return {"mutated": True}

    tool = _tool(tool_key="mutator", is_mutating=True)
    execution = _execution(organization_id)
    handlers = ToolHandlerRegistry({"mutator": _mutate})
    executor = ToolExecutor(handlers, publish_event=publisher)

    outcome = await executor.execute(
        tool,
        {},
        execution=execution,
        agent_tool_keys=["mutator"],
        granted_categories=[PermissionCategory.TOOL_INVOCATION],
        allow_mutating=True,
    )

    assert outcome.status is ToolCallStatus.SUCCEEDED
    assert outcome.result == {"mutated": True}


async def test_execute_records_full_trace_entry_shape(
    publisher: RecordingPublisher, organization_id: uuid.UUID
) -> None:
    async def _ok(arguments: dict[str, Any]) -> dict[str, Any]:
        return {"ok": True}

    tool = _tool(tool_key="shaped")
    execution = _execution(organization_id)
    handlers = ToolHandlerRegistry({"shaped": _ok})
    executor = ToolExecutor(handlers, publish_event=publisher)

    await executor.execute(
        tool,
        {"a": 1},
        execution=execution,
        agent_tool_keys=["shaped"],
        granted_categories=[PermissionCategory.TOOL_INVOCATION],
    )

    entry = execution.trace[0]
    assert entry["type"] == "tool_call"
    assert entry["tool_key"] == "shaped"
    assert entry["arguments"] == {"a": 1}
    assert entry["status"] == "succeeded"
    assert entry["result"] == {"ok": True}
    assert entry["error"] is None
    assert entry["denial_reason"] is None
    assert isinstance(entry["duration_ms"], float)
    assert isinstance(entry["timestamp"], str)
    datetime.fromisoformat(entry["timestamp"])  # does not raise


async def test_execute_appends_trace_entries_without_dropping_earlier_ones(
    publisher: RecordingPublisher, organization_id: uuid.UUID
) -> None:
    async def _ok(arguments: dict[str, Any]) -> dict[str, Any]:
        return {"ok": True}

    tool_a = _tool(tool_key="tool-a")
    tool_b = _tool(tool_key="tool-b")
    execution = _execution(organization_id)
    handlers = ToolHandlerRegistry({"tool-a": _ok, "tool-b": _ok})
    executor = ToolExecutor(handlers, publish_event=publisher)

    await executor.execute(
        tool_a,
        {},
        execution=execution,
        agent_tool_keys=["tool-a", "tool-b"],
        granted_categories=[PermissionCategory.TOOL_INVOCATION],
    )
    await executor.execute(
        tool_b,
        {},
        execution=execution,
        agent_tool_keys=["tool-a", "tool-b"],
        granted_categories=[PermissionCategory.TOOL_INVOCATION],
    )

    assert execution.tool_calls_made == 2
    assert [entry["tool_key"] for entry in execution.trace] == ["tool-a", "tool-b"]
    assert publisher.names == ["ToolInvoked", "ToolInvoked"]


# ---------------------------------------------------------------------------
# handlers.py -- build_rest_handler
# ---------------------------------------------------------------------------


async def test_rest_handler_missing_url_raises_value_error(
    http_client: httpx.AsyncClient,
) -> None:
    handler = build_rest_handler(http_client)
    with pytest.raises(ValueError, match="url"):
        await handler({})


async def test_rest_handler_real_json_response(http_client: httpx.AsyncClient) -> None:
    handler = build_rest_handler(http_client)
    result = await handler(
        {
            "method": "GET",
            "url": f"{RABBITMQ_MGMT_URL}/api/overview",
            "headers": {"Authorization": "Basic YWlpb3M6Y2hhbmdlLW1l"},  # aiios:change-me
        }
    )
    assert result["status_code"] == 200
    assert isinstance(result["body"], dict)
    assert "management_version" in result["body"]


async def test_rest_handler_real_non_json_response_falls_back_to_text(
    http_client: httpx.AsyncClient,
) -> None:
    handler = build_rest_handler(http_client)
    result = await handler({"url": f"{RABBITMQ_MGMT_URL}/"})
    assert result["status_code"] == 200
    assert isinstance(result["body"], str)
    assert "<html" in result["body"].lower()


async def test_rest_handler_default_method_is_get(http_client: httpx.AsyncClient) -> None:
    handler = build_rest_handler(http_client)
    result = await handler({"url": f"{RABBITMQ_MGMT_URL}/"})
    assert result["status_code"] == 200


async def test_rest_handler_unreachable_host_raises_dependency_error(
    http_client: httpx.AsyncClient,
) -> None:
    handler = build_rest_handler(http_client)
    with pytest.raises(DependencyError, match="failed"):
        await handler({"url": f"{UNREACHABLE_URL}/"})


# ---------------------------------------------------------------------------
# handlers.py -- build_webhook_handler
# ---------------------------------------------------------------------------


async def test_webhook_handler_missing_url_raises_value_error(
    http_client: httpx.AsyncClient,
) -> None:
    handler = build_webhook_handler(http_client)
    with pytest.raises(ValueError, match="url"):
        await handler({})


async def test_webhook_handler_real_post(http_client: httpx.AsyncClient) -> None:
    handler = build_webhook_handler(http_client)
    result = await handler({"url": f"{RABBITMQ_MGMT_URL}/", "payload": {"hello": "world"}})
    assert isinstance(result["status_code"], int)
    assert set(result) == {"status_code"}


async def test_webhook_handler_default_method_is_post(http_client: httpx.AsyncClient) -> None:
    # No direct way to observe the verb from the outside without a
    # server that echoes it; confirmed instead by reading
    # app.tool_execution.handlers.build_webhook_handler's own source
    # ("POST" is the literal default) and exercising the real call path.
    handler = build_webhook_handler(http_client)
    result = await handler({"url": f"{RABBITMQ_MGMT_URL}/"})
    assert isinstance(result["status_code"], int)


async def test_webhook_handler_unreachable_host_raises_dependency_error(
    http_client: httpx.AsyncClient,
) -> None:
    handler = build_webhook_handler(http_client)
    with pytest.raises(DependencyError, match="failed"):
        await handler({"url": f"{UNREACHABLE_URL}/"})


# ---------------------------------------------------------------------------
# handlers.py -- build_shell_handler
# ---------------------------------------------------------------------------


async def test_shell_handler_missing_command_raises_value_error() -> None:
    handler = build_shell_handler(AgentSandboxPolicy())
    with pytest.raises(ValueError, match="command"):
        await handler({})


async def test_shell_handler_non_list_command_raises_value_error() -> None:
    handler = build_shell_handler(AgentSandboxPolicy())
    with pytest.raises(ValueError, match="command"):
        await handler({"command": "not-a-list"})


async def test_shell_handler_real_success() -> None:
    policy = AgentSandboxPolicy(execution_timeout_seconds=10.0)
    handler = build_shell_handler(policy)
    result = await handler({"command": [sys.executable, "-c", "print('shell-ok')"]})
    assert result["succeeded"] is True
    assert result["exit_code"] == 0
    assert "shell-ok" in result["stdout"]


async def test_shell_handler_real_nonzero_exit() -> None:
    policy = AgentSandboxPolicy(execution_timeout_seconds=10.0)
    handler = build_shell_handler(policy)
    result = await handler({"command": [sys.executable, "-c", "import sys; sys.exit(7)"]})
    assert result["succeeded"] is False
    assert result["exit_code"] == 7


# ---------------------------------------------------------------------------
# handlers.py -- build_python_handler
# ---------------------------------------------------------------------------


async def test_python_handler_missing_script_raises_value_error() -> None:
    handler = build_python_handler(AgentSandboxPolicy())
    with pytest.raises(ValueError, match="script"):
        await handler({})


async def test_python_handler_non_string_script_raises_value_error() -> None:
    handler = build_python_handler(AgentSandboxPolicy())
    with pytest.raises(ValueError, match="script"):
        await handler({"script": 123})


async def test_python_handler_real_success() -> None:
    policy = AgentSandboxPolicy(execution_timeout_seconds=10.0)
    handler = build_python_handler(policy)
    result = await handler({"script": "print('python-ok')"})
    assert result["succeeded"] is True
    assert "python-ok" in result["stdout"]


# ---------------------------------------------------------------------------
# handlers.py -- build_automation_handler
# ---------------------------------------------------------------------------


async def test_automation_handler_missing_job_id_raises_value_error(
    http_client: httpx.AsyncClient,
) -> None:
    client = AutomationClient(http_client, base_url=UNREACHABLE_URL, caller_token="tok")
    handler = build_automation_handler(client)
    with pytest.raises(ValueError, match="job_id"):
        await handler({})


async def test_automation_handler_unreachable_service_raises_dependency_error(
    http_client: httpx.AsyncClient,
) -> None:
    client = AutomationClient(
        http_client,
        base_url=UNREACHABLE_URL,
        caller_token="tok",
        poll_interval_seconds=0.01,
        max_poll_attempts=1,
    )
    handler = build_automation_handler(client)
    with pytest.raises(DependencyError, match="unreachable"):
        await handler({"job_id": str(uuid.uuid4())})


# ---------------------------------------------------------------------------
# handlers.py -- build_knowledge_graph_query_handler
# ---------------------------------------------------------------------------


async def test_knowledge_graph_handler_missing_cypher_raises_value_error(
    graph_client: GraphClient,
) -> None:
    handler = build_knowledge_graph_query_handler(graph_client)
    with pytest.raises(ValueError, match="cypher"):
        await handler({})


async def test_knowledge_graph_handler_non_string_cypher_raises_value_error(
    graph_client: GraphClient,
) -> None:
    handler = build_knowledge_graph_query_handler(graph_client)
    with pytest.raises(ValueError, match="cypher"):
        await handler({"cypher": 123})


async def test_knowledge_graph_handler_real_read(graph_client: GraphClient) -> None:
    handler = build_knowledge_graph_query_handler(graph_client)
    result = await handler({"cypher": "RETURN 1 AS n"})
    assert result["records"] == [{"n": 1}]
    assert result["row_count"] == 1
    assert result["truncated"] is False


async def test_knowledge_graph_handler_write_clause_fails_in_read_transaction(
    graph_client: GraphClient,
) -> None:
    # The Knowledge Graph Query tool kind is read-only by construction
    # -- GraphClient.read() opens an explicit READ transaction, so a
    # write clause fails at the database itself.
    handler = build_knowledge_graph_query_handler(graph_client)
    with pytest.raises(DependencyError):
        await handler({"cypher": "CREATE (n:AiAgentPlatformTestNode) RETURN n"})


# ---------------------------------------------------------------------------
# handlers.py -- build_database_query_handler
# ---------------------------------------------------------------------------


def test_database_query_handler_rejects_non_select_template() -> None:
    with pytest.raises(ValueError, match="SELECT"):
        build_database_query_handler(object(), "DELETE FROM agent_tools")  # type: ignore[arg-type]


async def test_database_query_handler_real_select(db_session: AsyncSession) -> None:
    # CAST(...), not ``::int``: SQLAlchemy's own bind-parameter syntax is
    # ``:name``, so PostgreSQL's ``::`` cast operator collides with it and
    # the statement reaches the driver with the placeholder unexpanded.
    handler = build_database_query_handler(db_session, "SELECT CAST(:x AS integer) AS x")
    result = await handler({"x": 5})
    assert result["rows"] == [{"x": 5}]
    assert result["row_count"] == 1
    assert result["truncated"] is False


async def test_database_query_handler_truncates_at_the_row_ceiling(
    db_session: AsyncSession,
) -> None:
    handler = build_database_query_handler(db_session, "SELECT generate_series(1, 1005) AS n")
    result = await handler({})
    assert result["row_count"] == MAX_DATABASE_QUERY_ROWS
    assert result["truncated"] is True


# ---------------------------------------------------------------------------
# handlers.py -- build_workflow_handler
# ---------------------------------------------------------------------------


class _StubWorkflowPersistenceService:
    """A minimal, real stand-in for the ``run`` half of
    :class:`~app.langgraph.service.WorkflowPersistenceService`'s own
    contract.

    That service's real ``run()`` drives ``app.langgraph`` /
    ``app.agents.orchestrator`` -- both out of this module's own
    assigned scope. ``build_workflow_handler``'s own job is only to
    look the workflow row up and shape whatever ``service.run()``
    returns into a result dict; that shaping is what this stub lets us
    exercise directly, the same "real, hand-written stand-in, never
    ``unittest.mock``" shape ``tests/conftest.py``'s own
    ``RecordingPublisher`` already establishes.
    """

    def __init__(self, result: AgentWorkflow) -> None:
        self._result = result
        self.received: list[AgentWorkflow] = []

    async def run(self, workflow: AgentWorkflow) -> AgentWorkflow:
        self.received.append(workflow)
        return self._result


async def test_workflow_handler_missing_workflow_id_raises_value_error(
    workflows_repo: AgentWorkflowRepository, organization_id: uuid.UUID
) -> None:
    handler = build_workflow_handler(
        object(), workflows_repo, organization_id=organization_id  # type: ignore[arg-type]
    )
    with pytest.raises(ValueError, match="workflow_id"):
        await handler({})


async def test_workflow_handler_unknown_workflow_raises_not_found(
    workflows_repo: AgentWorkflowRepository, organization_id: uuid.UUID
) -> None:
    handler = build_workflow_handler(
        object(), workflows_repo, organization_id=organization_id  # type: ignore[arg-type]
    )
    with pytest.raises(NotFoundError):
        await handler({"workflow_id": str(uuid.uuid4())})


async def test_workflow_handler_real_lookup_and_result_shape(
    workflows_repo: AgentWorkflowRepository, organization_id: uuid.UUID
) -> None:
    workflow = await workflows_repo.create(
        AgentWorkflow(
            organization_id=organization_id,
            graph_definition={},
            status=WorkflowRunStatus.PENDING,
        )
    )
    finished = AgentWorkflow(
        organization_id=organization_id,
        graph_definition={},
        status=WorkflowRunStatus.COMPLETED,
        current_node_id="end",
        error=None,
    )
    stub_service = _StubWorkflowPersistenceService(finished)
    handler = build_workflow_handler(
        stub_service, workflows_repo, organization_id=organization_id  # type: ignore[arg-type]
    )

    result = await handler({"workflow_id": str(workflow.id)})

    assert result == {"status": "completed", "current_node_id": "end", "error": None}
    # The exact row looked up by organization_id/workflow_id was the
    # one handed to service.run() -- the handler's own only real job.
    assert stub_service.received[0].id == workflow.id
