"""Tests for :mod:`app.workers` -- the four leader-elected background
sweeps plus their ``shared_core.scheduler`` registration.

**Everything runs against real infrastructure.** Each worker is
constructed with the real SAVEPOINT-isolated ``db_session_factory``
(workers take a *factory*, not a session, because each of them
deliberately opens one session per unit of work) and driven by calling
its own real ``tick()``/``_dispatch_one()``/``_resume_one()``/
``_sweep_org()``/``_recompute()`` against real seeded PostgreSQL rows.
The scheduler registration tests use a real ``SchedulerManager`` built
by the real factory on top of a real RabbitMQ connection and a real
Redis client.

The wiring itself -- that ``SchedulerManager``'s own timer really does
fire these jobs -- was verified live, out of band, against a real
seeded due task and a real seeded stuck workflow. What is under test
here is each worker's own sweep logic.

**Two real model endpoints, never a mocked registry.**

- ``unreachable_model_registry`` -- a real ``ModelRegistry`` whose
  provider base URLs point at ``127.0.0.1:1``, a loopback port nothing
  listens on. Every provider in the chain fails with a real, immediate
  connection refusal, so "the model was unavailable" is deterministic
  rather than dependent on whether this machine happens to be running
  Ollama.
- ``reachable_model_registry`` -- a real ``ModelRegistry`` pointed at a
  genuine local ``http.server`` speaking Ollama's own documented
  ``POST /api/chat`` contract over real sockets. This is what makes the
  *success* branches (a task actually completing, a benchmark case
  actually passing) reachable without a live LLM.
"""

from __future__ import annotations

import json
import threading
import uuid
from collections.abc import AsyncIterator, Iterator
from datetime import UTC, datetime, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

import httpx
import pytest
import pytest_asyncio
from shared_core.queue.factory import create_queue_framework
from shared_core.scheduler import Job, JobType, SchedulerManager
from shared_core.scheduler import ScheduleType as FrameworkScheduleType
from shared_core.scheduler.factory import create_scheduler_framework
from shared_core.workflow.exceptions import InvalidWorkflowDefinitionError
from shared_core.workflow.parser import parse_dict
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.clients.registry import ModelRegistry, build_model_clients
from app.config.settings import AiAgentPlatformServiceSettings
from app.models.agent import Agent
from app.models.benchmark import AgentBenchmark
from app.models.enums import (
    AgentLifecycleStatus,
    AgentType,
    BenchmarkStatus,
    ExecutionStatus,
    MemoryScope,
    ModelProvider,
    ReasoningMode,
    TaskStatus,
    WorkflowRunStatus,
)
from app.models.execution import AgentExecution
from app.models.memory import AgentMemory
from app.models.task import AgentTask
from app.models.workflow import AgentWorkflow
from app.repositories.agent import AgentRepository, AgentVersionRepository
from app.repositories.benchmark import AgentBenchmarkRepository
from app.repositories.execution import AgentExecutionRepository
from app.repositories.governance import AgentAuditRepository, AgentStatisticRepository
from app.repositories.memory import AgentMemoryRepository
from app.repositories.profile import AgentProfileRepository
from app.repositories.task import AgentTaskRepository
from app.repositories.workflow import AgentWorkflowRepository
from app.sandbox.policy import AgentSandboxPolicy
from app.services.agent import AgentService, ProfileFields
from app.workers.benchmark_sweep import BenchmarkSweepWorker
from app.workers.checkpoint_recovery_sweep import CheckpointRecoverySweepWorker
from app.workers.registrar import (
    BENCHMARK_SWEEP_JOB_ID,
    CHECKPOINT_RECOVERY_SWEEP_JOB_ID,
    STATISTICS_ROLLUP_JOB_ID,
    TASK_DISPATCH_SWEEP_JOB_ID,
    _register,
    register_benchmark_sweep,
    register_checkpoint_recovery_sweep,
    register_statistics_rollup,
    register_task_dispatch_sweep,
)
from app.workers.statistics_rollup import StatisticsRollupWorker
from app.workers.task_dispatch_sweep import TaskDispatchSweepWorker
from tests.conftest import (
    UNREACHABLE_ERRORS,
    MakeAgentFn,
    RecordingPublisher,
    ago,
    rabbitmq_test_settings,
    soon,
    utcnow,
)

DEAD_PORT_BASE_URL = "http://127.0.0.1:1"
"""A real loopback port nothing listens on: a genuine, immediate refusal."""

TRIVIAL_GRAPH: dict[str, Any] = {
    "workflow_id": "x",
    "name": "x",
    "version": "1.0.0",
    "nodes": [
        {"node_id": "start", "node_type": "start", "name": "start"},
        {"node_id": "end", "node_type": "end", "name": "end"},
    ],
    "edges": [{"from": "start", "to": "end"}],
}

MODEL_ANSWER = "All systems nominal."


# ---- a real local Ollama-shaped endpoint, not a mocked client -------------------


class LocalOllamaServer:
    """A genuine ``http.server`` on ``127.0.0.1`` speaking Ollama's own
    documented ``POST /api/chat`` contract.

    Real sockets, real HTTP/1.1, real JSON: ``OllamaClient``,
    ``httpx``, and ``ModelRegistry`` are all the production code paths,
    unpatched. Only the daemon on the other end of the socket is
    local to this test run.
    """

    def __init__(self) -> None:
        self.request_count = 0
        outer = self

        class Handler(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def do_POST(self) -> None:
                length = int(self.headers.get("Content-Length") or 0)
                self.rfile.read(length)
                outer.request_count += 1
                payload = json.dumps(
                    {
                        "model": "llama3",
                        "message": {"role": "assistant", "content": MODEL_ANSWER},
                        "prompt_eval_count": 11,
                        "eval_count": 5,
                        "done_reason": "stop",
                    }
                ).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)

            def log_message(self, log_format: str, *args: Any) -> None:
                pass

        self._httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self._thread = threading.Thread(target=self._httpd.serve_forever, daemon=True)
        self._thread.start()

    @property
    def base_url(self) -> str:
        return f"http://127.0.0.1:{self._httpd.server_address[1]}"

    def close(self) -> None:
        self._httpd.shutdown()
        self._httpd.server_close()


@pytest.fixture
def local_model_server() -> Iterator[LocalOllamaServer]:
    server = LocalOllamaServer()
    try:
        yield server
    finally:
        server.close()


def _registry_for(http_client: httpx.AsyncClient, base_url: str) -> ModelRegistry:
    """A real registry whose self-hosted providers all point at *base_url*."""
    settings = AiAgentPlatformServiceSettings(
        ollama_base_url=base_url,
        vllm_base_url=base_url,
        default_provider="ollama",
        default_model="llama3",
    )
    return ModelRegistry(
        build_model_clients(http_client, settings),
        default_provider=ModelProvider.OLLAMA,
        default_model="llama3",
    )


@pytest.fixture
def unreachable_model_registry(http_client: httpx.AsyncClient) -> ModelRegistry:
    """Every provider in the resolved chain refuses the connection for real."""
    return _registry_for(http_client, DEAD_PORT_BASE_URL)


@pytest.fixture
def reachable_model_registry(
    http_client: httpx.AsyncClient, local_model_server: LocalOllamaServer
) -> ModelRegistry:
    return _registry_for(http_client, local_model_server.base_url)


# ---- a real session factory that refuses one checkout ----------------------------


class FailAtNthSessionFactory:
    """A real session factory that refuses to hand out its *nth* session.

    Every session it *does* hand out is the genuine, SAVEPOINT-isolated
    session from ``db_session_factory``; the database itself is never
    mocked or replaced. The nth call raises the way a real connection
    checkout failure would -- which is precisely the class of failure
    each worker's own per-unit ``except`` clause exists to survive, and
    the only one that cannot be provoked through seeded rows alone.
    """

    def __init__(
        self, inner: async_sessionmaker[AsyncSession], *, fail_on: int, error: Exception
    ) -> None:
        self._inner = inner
        self._fail_on = fail_on
        self._error = error
        self.calls = 0

    def __call__(self) -> Any:
        self.calls += 1
        if self.calls == self._fail_on:
            raise self._error
        return self._inner()


# ---- seeding helpers ---------------------------------------------------------------


async def _bare_agent(
    session_factory: async_sessionmaker[AsyncSession],
    organization_id: uuid.UUID,
    *,
    slug: str = "bare",
    status: AgentLifecycleStatus = AgentLifecycleStatus.ACTIVE,
    agent_type: AgentType = AgentType.EXECUTOR,
) -> Agent:
    """An agent row with **no** profile, committed on its own session."""
    async with session_factory() as session:
        agent = await AgentRepository(session).create(
            Agent(
                organization_id=organization_id,
                slug=slug,
                name=f"Agent {slug}",
                agent_type=agent_type,
                status=status,
            )
        )
        await session.commit()
        return agent


async def _read_task(
    session_factory: async_sessionmaker[AsyncSession], task_id: uuid.UUID
) -> AgentTask:
    """Re-read a task on a fresh session, so no stale identity map lies."""
    async with session_factory() as session:
        return await AgentTaskRepository(session).require_by_id(task_id)


async def _read_workflow(
    session_factory: async_sessionmaker[AsyncSession], workflow_id: uuid.UUID
) -> AgentWorkflow:
    async with session_factory() as session:
        return await AgentWorkflowRepository(session).require_by_id(workflow_id)


async def _benchmarks_for_org(
    session_factory: async_sessionmaker[AsyncSession], organization_id: uuid.UUID
) -> list[AgentBenchmark]:
    async with session_factory() as session:
        return await AgentBenchmarkRepository(session).list_for_org(organization_id)


async def _statistic_for_org(
    session_factory: async_sessionmaker[AsyncSession], organization_id: uuid.UUID
) -> Any:
    async with session_factory() as session:
        return await AgentStatisticRepository(session).latest(organization_id)


def _task_dispatch_worker(
    session_factory: Any,
    registry: ModelRegistry,
    *,
    http_client: httpx.AsyncClient,
    sandbox_policy: AgentSandboxPolicy,
    publisher: RecordingPublisher,
    max_tasks_per_tick: int = 100,
) -> TaskDispatchSweepWorker:
    return TaskDispatchSweepWorker(
        session_factory,
        registry,
        http_client=http_client,
        sandbox_policy=sandbox_policy,
        graph_client=None,
        automation_service_base_url=DEAD_PORT_BASE_URL,
        publish_event=publisher,
        max_tasks_per_tick=max_tasks_per_tick,
    )


# =============================================================================
# app/workers/task_dispatch_sweep.py
# =============================================================================


async def test_tick_dispatches_only_the_due_task(
    db_session_factory: async_sessionmaker[AsyncSession],
    db_session: AsyncSession,
    make_agent: MakeAgentFn,
    organization_id: uuid.UUID,
    unreachable_model_registry: ModelRegistry,
    http_client: httpx.AsyncClient,
    sandbox_policy: AgentSandboxPolicy,
    publisher: RecordingPublisher,
) -> None:
    agent = await make_agent(
        "dispatch-due", profile={"reasoning_mode": ReasoningMode.CHAIN_OF_THOUGHT}
    )
    tasks_repo = AgentTaskRepository(db_session)
    due = await tasks_repo.create(
        AgentTask(
            organization_id=organization_id,
            agent_id=agent.id,
            task_type="status-check",
            status=TaskStatus.PENDING,
            payload={"request": "Provide a short status update."},
            scheduled_at=ago(60),
        )
    )
    not_due = await tasks_repo.create(
        AgentTask(
            organization_id=organization_id,
            agent_id=agent.id,
            task_type="status-check",
            status=TaskStatus.QUEUED,
            scheduled_at=soon(3600),
        )
    )
    await db_session.flush()

    worker = _task_dispatch_worker(
        db_session_factory,
        unreachable_model_registry,
        http_client=http_client,
        sandbox_policy=sandbox_policy,
        publisher=publisher,
    )
    attempted = await worker.tick()

    assert attempted == 1
    assert (await _read_task(db_session_factory, due.id)).status != TaskStatus.PENDING
    assert (await _read_task(db_session_factory, not_due.id)).status == TaskStatus.QUEUED


async def test_tick_leaves_an_unassigned_task_pending(
    db_session_factory: async_sessionmaker[AsyncSession],
    db_session: AsyncSession,
    organization_id: uuid.UUID,
    unreachable_model_registry: ModelRegistry,
    http_client: httpx.AsyncClient,
    sandbox_policy: AgentSandboxPolicy,
    publisher: RecordingPublisher,
) -> None:
    """Per the module docstring: this sweep dispatches *already-assigned*
    work; deciding who should take an unassigned task is not its job."""
    unassigned = await AgentTaskRepository(db_session).create(
        AgentTask(
            organization_id=organization_id,
            agent_id=None,
            task_type="unassigned",
            status=TaskStatus.PENDING,
            scheduled_at=ago(60),
        )
    )
    await db_session.flush()

    worker = _task_dispatch_worker(
        db_session_factory,
        unreachable_model_registry,
        http_client=http_client,
        sandbox_policy=sandbox_policy,
        publisher=publisher,
    )
    attempted = await worker.tick()

    assert attempted == 0
    reloaded = await _read_task(db_session_factory, unassigned.id)
    assert reloaded.status == TaskStatus.PENDING
    assert reloaded.started_at is None
    assert publisher.events == []


async def test_tick_returns_zero_when_nothing_is_due(
    db_session_factory: async_sessionmaker[AsyncSession],
    db_session: AsyncSession,
    make_agent: MakeAgentFn,
    organization_id: uuid.UUID,
    unreachable_model_registry: ModelRegistry,
    http_client: httpx.AsyncClient,
    sandbox_policy: AgentSandboxPolicy,
    publisher: RecordingPublisher,
) -> None:
    agent = await make_agent("nothing-due")
    await AgentTaskRepository(db_session).create(
        AgentTask(
            organization_id=organization_id,
            agent_id=agent.id,
            task_type="later",
            status=TaskStatus.PENDING,
            scheduled_at=soon(3600),
        )
    )
    await db_session.flush()

    worker = _task_dispatch_worker(
        db_session_factory,
        unreachable_model_registry,
        http_client=http_client,
        sandbox_policy=sandbox_policy,
        publisher=publisher,
    )

    assert await worker.tick() == 0


async def test_tick_respects_max_tasks_per_tick(
    db_session_factory: async_sessionmaker[AsyncSession],
    db_session: AsyncSession,
    make_agent: MakeAgentFn,
    organization_id: uuid.UUID,
    unreachable_model_registry: ModelRegistry,
    http_client: httpx.AsyncClient,
    sandbox_policy: AgentSandboxPolicy,
    publisher: RecordingPublisher,
) -> None:
    agent = await make_agent("capped", profile={"reasoning_mode": ReasoningMode.CHAIN_OF_THOUGHT})
    tasks_repo = AgentTaskRepository(db_session)
    for index in range(3):
        await tasks_repo.create(
            AgentTask(
                organization_id=organization_id,
                agent_id=agent.id,
                task_type=f"task-{index}",
                status=TaskStatus.PENDING,
                scheduled_at=ago(600 - index),
            )
        )
    await db_session.flush()

    worker = _task_dispatch_worker(
        db_session_factory,
        unreachable_model_registry,
        http_client=http_client,
        sandbox_policy=sandbox_policy,
        publisher=publisher,
        max_tasks_per_tick=2,
    )

    assert await worker.tick() == 2


async def test_dispatch_retries_a_task_when_the_model_is_unreachable(
    db_session_factory: async_sessionmaker[AsyncSession],
    db_session: AsyncSession,
    make_agent: MakeAgentFn,
    organization_id: uuid.UUID,
    unreachable_model_registry: ModelRegistry,
    http_client: httpx.AsyncClient,
    sandbox_policy: AgentSandboxPolicy,
    publisher: RecordingPublisher,
) -> None:
    """``TaskService.fail`` retries while attempts remain -- a real
    provider failure, a real ``RETRYING`` transition."""
    agent = await make_agent("retrying", profile={"reasoning_mode": ReasoningMode.CHAIN_OF_THOUGHT})
    task = await AgentTaskRepository(db_session).create(
        AgentTask(
            organization_id=organization_id,
            agent_id=agent.id,
            task_type="status-check",
            status=TaskStatus.PENDING,
            payload={"request": "Provide a short status update."},
            max_retries=3,
            scheduled_at=ago(60),
        )
    )
    await db_session.flush()

    worker = _task_dispatch_worker(
        db_session_factory,
        unreachable_model_registry,
        http_client=http_client,
        sandbox_policy=sandbox_policy,
        publisher=publisher,
    )
    await worker.tick()

    reloaded = await _read_task(db_session_factory, task.id)
    assert reloaded.status == TaskStatus.RETRYING
    assert reloaded.retry_count == 1
    assert reloaded.error is not None
    assert reloaded.started_at is not None
    assert reloaded.completed_at is None
    # A retry is not a completion, so no TaskCompleted was announced.
    assert "TaskCompleted" not in publisher.names
    assert "AgentFailed" in publisher.names

    async with db_session_factory() as session:
        executions = await AgentExecutionRepository(session).list_for_agent(agent.id)
    assert len(executions) == 1
    assert executions[0].status == ExecutionStatus.FAILED
    assert executions[0].task_id == task.id


async def test_dispatch_fails_a_task_terminally_once_retries_are_exhausted(
    db_session_factory: async_sessionmaker[AsyncSession],
    db_session: AsyncSession,
    make_agent: MakeAgentFn,
    organization_id: uuid.UUID,
    unreachable_model_registry: ModelRegistry,
    http_client: httpx.AsyncClient,
    sandbox_policy: AgentSandboxPolicy,
    publisher: RecordingPublisher,
) -> None:
    agent = await make_agent(
        "exhausted", profile={"reasoning_mode": ReasoningMode.CHAIN_OF_THOUGHT}
    )
    task = await AgentTaskRepository(db_session).create(
        AgentTask(
            organization_id=organization_id,
            agent_id=agent.id,
            task_type="status-check",
            status=TaskStatus.PENDING,
            payload={"request": "Provide a short status update."},
            retry_count=3,
            max_retries=3,
            scheduled_at=ago(60),
        )
    )
    await db_session.flush()

    worker = _task_dispatch_worker(
        db_session_factory,
        unreachable_model_registry,
        http_client=http_client,
        sandbox_policy=sandbox_policy,
        publisher=publisher,
    )
    await worker.tick()

    reloaded = await _read_task(db_session_factory, task.id)
    assert reloaded.status == TaskStatus.FAILED
    assert reloaded.retry_count == 3
    assert reloaded.completed_at is not None
    assert reloaded.error is not None
    assert "TaskCompleted" in publisher.names


async def test_dispatch_completes_a_task_when_the_model_answers(
    db_session_factory: async_sessionmaker[AsyncSession],
    db_session: AsyncSession,
    make_agent: MakeAgentFn,
    organization_id: uuid.UUID,
    reachable_model_registry: ModelRegistry,
    local_model_server: LocalOllamaServer,
    http_client: httpx.AsyncClient,
    sandbox_policy: AgentSandboxPolicy,
    publisher: RecordingPublisher,
) -> None:
    """The success branch, against a real local model endpoint."""
    agent = await make_agent(
        "completing", profile={"reasoning_mode": ReasoningMode.CHAIN_OF_THOUGHT}
    )
    task = await AgentTaskRepository(db_session).create(
        AgentTask(
            organization_id=organization_id,
            agent_id=agent.id,
            task_type="status-check",
            status=TaskStatus.PENDING,
            payload={"request": "Provide a short status update."},
            scheduled_at=ago(60),
        )
    )
    await db_session.flush()

    worker = _task_dispatch_worker(
        db_session_factory,
        reachable_model_registry,
        http_client=http_client,
        sandbox_policy=sandbox_policy,
        publisher=publisher,
    )
    attempted = await worker.tick()

    assert attempted == 1
    assert local_model_server.request_count == 1

    reloaded = await _read_task(db_session_factory, task.id)
    assert reloaded.status == TaskStatus.COMPLETED
    assert reloaded.completed_at is not None
    assert reloaded.retry_count == 0

    async with db_session_factory() as session:
        executions = await AgentExecutionRepository(session).list_for_agent(agent.id)
    assert len(executions) == 1
    execution = executions[0]
    assert execution.status == ExecutionStatus.COMPLETED
    assert execution.output_summary == MODEL_ANSWER
    assert reloaded.result == {"execution_id": str(execution.id)}
    assert "TaskCompleted" in publisher.names
    assert "AgentCompleted" in publisher.names


async def test_dispatch_uses_the_task_type_when_the_payload_has_no_request(
    db_session_factory: async_sessionmaker[AsyncSession],
    db_session: AsyncSession,
    make_agent: MakeAgentFn,
    organization_id: uuid.UUID,
    reachable_model_registry: ModelRegistry,
    http_client: httpx.AsyncClient,
    sandbox_policy: AgentSandboxPolicy,
    publisher: RecordingPublisher,
) -> None:
    agent = await make_agent(
        "no-request", profile={"reasoning_mode": ReasoningMode.CHAIN_OF_THOUGHT}
    )
    task = await AgentTaskRepository(db_session).create(
        AgentTask(
            organization_id=organization_id,
            agent_id=agent.id,
            task_type="daily-digest",
            status=TaskStatus.PENDING,
            payload={},
            scheduled_at=ago(60),
        )
    )
    await db_session.flush()

    worker = _task_dispatch_worker(
        db_session_factory,
        reachable_model_registry,
        http_client=http_client,
        sandbox_policy=sandbox_policy,
        publisher=publisher,
    )
    await worker.tick()

    async with db_session_factory() as session:
        executions = await AgentExecutionRepository(session).list_for_agent(agent.id)
    assert executions[0].input_summary == "daily-digest"
    assert (await _read_task(db_session_factory, task.id)).status == TaskStatus.COMPLETED


async def test_one_failing_dispatch_does_not_stop_the_rest_of_the_sweep(
    db_session_factory: async_sessionmaker[AsyncSession],
    db_session: AsyncSession,
    make_agent: MakeAgentFn,
    organization_id: uuid.UUID,
    reachable_model_registry: ModelRegistry,
    http_client: httpx.AsyncClient,
    sandbox_policy: AgentSandboxPolicy,
    publisher: RecordingPublisher,
) -> None:
    """A task pointing at an agent that belongs to *another* tenant makes
    ``require_in_org`` raise for real; the next task must still run."""
    foreign_org = uuid.uuid4()
    foreign_agent = await _bare_agent(db_session_factory, foreign_org, slug="foreign")
    healthy_agent = await make_agent(
        "healthy", profile={"reasoning_mode": ReasoningMode.CHAIN_OF_THOUGHT}
    )

    tasks_repo = AgentTaskRepository(db_session)
    poisoned = await tasks_repo.create(
        AgentTask(
            organization_id=organization_id,
            agent_id=foreign_agent.id,
            task_type="cross-tenant",
            status=TaskStatus.PENDING,
            scheduled_at=ago(3600),
        )
    )
    healthy = await tasks_repo.create(
        AgentTask(
            organization_id=organization_id,
            agent_id=healthy_agent.id,
            task_type="status-check",
            status=TaskStatus.PENDING,
            payload={"request": "Provide a short status update."},
            scheduled_at=ago(60),
        )
    )
    await db_session.flush()

    worker = _task_dispatch_worker(
        db_session_factory,
        reachable_model_registry,
        http_client=http_client,
        sandbox_policy=sandbox_policy,
        publisher=publisher,
    )
    attempted = await worker.tick()

    assert attempted == 2, "both were assigned, so both were attempted"
    assert (await _read_task(db_session_factory, poisoned.id)).status == TaskStatus.PENDING
    assert (await _read_task(db_session_factory, healthy.id)).status == TaskStatus.COMPLETED


async def test_task_dispatch_run_job_delegates_to_tick(
    db_session_factory: async_sessionmaker[AsyncSession],
    db_session: AsyncSession,
    make_agent: MakeAgentFn,
    organization_id: uuid.UUID,
    reachable_model_registry: ModelRegistry,
    http_client: httpx.AsyncClient,
    sandbox_policy: AgentSandboxPolicy,
    publisher: RecordingPublisher,
) -> None:
    """``run_job`` is the ``JobFn`` the scheduler actually calls."""
    agent = await make_agent(
        "via-run-job", profile={"reasoning_mode": ReasoningMode.CHAIN_OF_THOUGHT}
    )
    task = await AgentTaskRepository(db_session).create(
        AgentTask(
            organization_id=organization_id,
            agent_id=agent.id,
            task_type="status-check",
            status=TaskStatus.PENDING,
            payload={"request": "Provide a short status update."},
            scheduled_at=ago(60),
        )
    )
    await db_session.flush()

    worker = _task_dispatch_worker(
        db_session_factory,
        reachable_model_registry,
        http_client=http_client,
        sandbox_policy=sandbox_policy,
        publisher=publisher,
    )

    assert await worker.run_job(object()) is None
    assert (await _read_task(db_session_factory, task.id)).status == TaskStatus.COMPLETED


# =============================================================================
# app/workers/checkpoint_recovery_sweep.py
# =============================================================================


async def _stuck_workflow(
    session_factory: async_sessionmaker[AsyncSession],
    organization_id: uuid.UUID,
    *,
    graph: dict[str, Any],
    started_at: datetime,
    status: WorkflowRunStatus = WorkflowRunStatus.RUNNING,
) -> AgentWorkflow:
    async with session_factory() as session:
        workflow = await AgentWorkflowRepository(session).create(
            AgentWorkflow(
                organization_id=organization_id,
                status=status,
                graph_definition=graph,
                checkpoint={},
                started_at=started_at,
            )
        )
        await session.commit()
        return workflow


async def test_checkpoint_sweep_resumes_a_stuck_workflow_to_completion(
    db_session_factory: async_sessionmaker[AsyncSession],
    db_session: AsyncSession,
    make_agent: MakeAgentFn,
    organization_id: uuid.UUID,
    unreachable_model_registry: ModelRegistry,
) -> None:
    # A real agent + profile in the org, so the worker's own
    # agents-by-type / profiles-by-agent-id assembly runs for real.
    await make_agent("workflow-participant")
    await db_session.flush()
    workflow = await _stuck_workflow(
        db_session_factory, organization_id, graph=TRIVIAL_GRAPH, started_at=ago(3600)
    )

    worker = CheckpointRecoverySweepWorker(
        db_session_factory, unreachable_model_registry, stuck_after_seconds=60
    )
    resumed = await worker.tick()

    assert resumed == 1
    reloaded = await _read_workflow(db_session_factory, workflow.id)
    assert reloaded.status == WorkflowRunStatus.COMPLETED
    assert reloaded.error is None
    assert reloaded.completed_at is not None
    assert reloaded.current_node_id == "end"
    # The engine checkpoints *inside* its per-level loop and only
    # transitions to COMPLETED after the loop exits, so the last
    # persisted checkpoint is always a mid-run snapshot. The terminal
    # state lives on ``status``, asserted above.
    assert reloaded.checkpoint["state"] == "running"
    assert set(reloaded.checkpoint["completed_node_ids"]) == {"start", "end"}


async def test_checkpoint_sweep_ignores_a_recently_started_run(
    db_session_factory: async_sessionmaker[AsyncSession],
    organization_id: uuid.UUID,
    unreachable_model_registry: ModelRegistry,
) -> None:
    """A run that is merely slow keeps advancing its own checkpoint; only
    one older than the cutoff looks like a crash."""
    workflow = await _stuck_workflow(
        db_session_factory, organization_id, graph=TRIVIAL_GRAPH, started_at=ago(5)
    )

    worker = CheckpointRecoverySweepWorker(
        db_session_factory, unreachable_model_registry, stuck_after_seconds=3600
    )
    resumed = await worker.tick()

    assert resumed == 0
    reloaded = await _read_workflow(db_session_factory, workflow.id)
    assert reloaded.status == WorkflowRunStatus.RUNNING
    assert reloaded.checkpoint == {}
    assert reloaded.completed_at is None


async def test_checkpoint_sweep_ignores_non_running_workflows(
    db_session_factory: async_sessionmaker[AsyncSession],
    organization_id: uuid.UUID,
    unreachable_model_registry: ModelRegistry,
) -> None:
    await _stuck_workflow(
        db_session_factory,
        organization_id,
        graph=TRIVIAL_GRAPH,
        started_at=ago(3600),
        status=WorkflowRunStatus.PAUSED_FOR_APPROVAL,
    )

    worker = CheckpointRecoverySweepWorker(
        db_session_factory, unreachable_model_registry, stuck_after_seconds=60
    )

    assert await worker.tick() == 0


async def test_one_failing_resume_does_not_stop_the_rest_of_the_sweep(
    db_session_factory: async_sessionmaker[AsyncSession],
    organization_id: uuid.UUID,
    unreachable_model_registry: ModelRegistry,
) -> None:
    """A structurally invalid ``graph_definition`` makes the real parser
    raise; the next stuck workflow must still be resumed."""
    broken = await _stuck_workflow(
        db_session_factory, organization_id, graph={"nodes": []}, started_at=ago(7200)
    )
    healthy = await _stuck_workflow(
        db_session_factory, organization_id, graph=TRIVIAL_GRAPH, started_at=ago(3600)
    )

    worker = CheckpointRecoverySweepWorker(
        db_session_factory, unreachable_model_registry, stuck_after_seconds=60
    )
    resumed = await worker.tick()

    assert resumed == 1
    assert (await _read_workflow(db_session_factory, broken.id)).status == WorkflowRunStatus.RUNNING
    assert (
        await _read_workflow(db_session_factory, healthy.id)
    ).status == WorkflowRunStatus.COMPLETED


async def test_resume_one_returns_false_for_an_unknown_workflow(
    db_session_factory: async_sessionmaker[AsyncSession],
    organization_id: uuid.UUID,
    unreachable_model_registry: ModelRegistry,
) -> None:
    """``require_in_org`` raising is swallowed into a ``False``, never
    propagated out of the sweep."""
    worker = CheckpointRecoverySweepWorker(
        db_session_factory, unreachable_model_registry, stuck_after_seconds=60
    )

    assert await worker._resume_one(uuid.uuid4(), organization_id) is False


async def test_checkpoint_sweep_respects_max_workflows_per_tick(
    db_session_factory: async_sessionmaker[AsyncSession],
    organization_id: uuid.UUID,
    unreachable_model_registry: ModelRegistry,
) -> None:
    older = await _stuck_workflow(
        db_session_factory, organization_id, graph=TRIVIAL_GRAPH, started_at=ago(7200)
    )
    newer = await _stuck_workflow(
        db_session_factory, organization_id, graph=TRIVIAL_GRAPH, started_at=ago(3600)
    )

    worker = CheckpointRecoverySweepWorker(
        db_session_factory,
        unreachable_model_registry,
        stuck_after_seconds=60,
        max_workflows_per_tick=1,
    )
    resumed = await worker.tick()

    assert resumed == 1
    assert (await _read_workflow(db_session_factory, older.id)).status == (
        WorkflowRunStatus.COMPLETED
    )
    assert (await _read_workflow(db_session_factory, newer.id)).status == (
        WorkflowRunStatus.RUNNING
    )


async def test_checkpoint_sweep_returns_zero_when_nothing_is_stuck(
    db_session_factory: async_sessionmaker[AsyncSession],
    unreachable_model_registry: ModelRegistry,
) -> None:
    worker = CheckpointRecoverySweepWorker(
        db_session_factory, unreachable_model_registry, stuck_after_seconds=60
    )

    assert await worker.tick() == 0


async def test_checkpoint_sweep_run_job_delegates_to_tick(
    db_session_factory: async_sessionmaker[AsyncSession],
    organization_id: uuid.UUID,
    unreachable_model_registry: ModelRegistry,
) -> None:
    workflow = await _stuck_workflow(
        db_session_factory, organization_id, graph=TRIVIAL_GRAPH, started_at=ago(3600)
    )

    worker = CheckpointRecoverySweepWorker(
        db_session_factory, unreachable_model_registry, stuck_after_seconds=60
    )

    assert await worker.run_job(object()) is None
    assert (await _read_workflow(db_session_factory, workflow.id)).status == (
        WorkflowRunStatus.COMPLETED
    )


def test_a_structurally_invalid_graph_really_does_raise() -> None:
    """The failure the isolation test above depends on is a real one."""
    with pytest.raises(InvalidWorkflowDefinitionError):
        parse_dict({"nodes": []})


# =============================================================================
# app/workers/statistics_rollup.py
# =============================================================================


async def _seed_activity(
    session_factory: async_sessionmaker[AsyncSession],
    organization_id: uuid.UUID,
    *,
    slug: str,
    trace: list[Any] | None = None,
) -> Agent:
    """One ACTIVE agent, one task, two executions, and one memory row."""
    async with session_factory() as session:
        agent = await AgentRepository(session).create(
            Agent(
                organization_id=organization_id,
                slug=slug,
                name=f"Agent {slug}",
                agent_type=AgentType.REPORTING,
                status=AgentLifecycleStatus.ACTIVE,
            )
        )
        await AgentTaskRepository(session).create(
            AgentTask(
                organization_id=organization_id,
                agent_id=agent.id,
                task_type="generic",
                scheduled_at=utcnow(),
            )
        )
        executions_repo = AgentExecutionRepository(session)
        await executions_repo.create(
            AgentExecution(
                organization_id=organization_id,
                agent_id=agent.id,
                status=ExecutionStatus.COMPLETED,
                model_provider=ModelProvider.OLLAMA,
                total_tokens=100,
                cost_usd=0.02,
                latency_ms=200.0,
                trace=[{"type": "tool_call", "tool_key": "crm.lookup"}] if trace is None else trace,
                started_at=ago(60),
            )
        )
        await executions_repo.create(
            AgentExecution(
                organization_id=organization_id,
                agent_id=agent.id,
                status=ExecutionStatus.FAILED,
                model_provider=ModelProvider.OLLAMA,
                total_tokens=40,
                cost_usd=0.04,
                latency_ms=400.0,
                trace=[],
                started_at=ago(30),
            )
        )
        await AgentMemoryRepository(session).create(
            AgentMemory(
                organization_id=organization_id,
                agent_id=agent.id,
                scope=MemoryScope.LONG_TERM,
                key="fact",
            )
        )
        await session.commit()
        return agent


async def test_statistics_rollup_computes_one_real_window(
    db_session_factory: async_sessionmaker[AsyncSession], organization_id: uuid.UUID
) -> None:
    await _seed_activity(db_session_factory, organization_id, slug="stats")

    worker = StatisticsRollupWorker(db_session_factory, window_seconds=3_600)
    done = await worker.tick()

    assert done == 1
    window = await _statistic_for_org(db_session_factory, organization_id)
    assert window is not None
    assert window.active_agents == 1
    assert window.task_count == 1
    assert window.executions_succeeded == 1
    assert window.executions_failed == 1
    assert window.total_tokens == 140
    assert window.average_cost_usd == pytest.approx(0.03)
    assert window.average_latency_ms == pytest.approx(300.0)
    assert window.memory_rows_created == 1
    assert window.by_agent_type == {"reporting": 1}
    assert window.by_model_provider == {"ollama": 2}
    assert window.by_tool == {"crm.lookup": 1}
    assert window.window_end - window.window_start == timedelta(seconds=3_600)


async def test_statistics_rollup_counts_every_organization_separately(
    db_session_factory: async_sessionmaker[AsyncSession], organization_id: uuid.UUID
) -> None:
    other_org = uuid.uuid4()
    await _seed_activity(db_session_factory, organization_id, slug="org-a")
    await _seed_activity(db_session_factory, other_org, slug="org-b")

    worker = StatisticsRollupWorker(db_session_factory, window_seconds=3_600)
    done = await worker.tick()

    assert done == 2
    mine = await _statistic_for_org(db_session_factory, organization_id)
    theirs = await _statistic_for_org(db_session_factory, other_org)
    assert mine.organization_id == organization_id
    assert theirs.organization_id == other_org
    assert mine.task_count == 1
    assert theirs.task_count == 1


async def test_statistics_rollup_excludes_activity_outside_the_window(
    db_session_factory: async_sessionmaker[AsyncSession], organization_id: uuid.UUID
) -> None:
    agent = await _seed_activity(db_session_factory, organization_id, slug="windowed")
    async with db_session_factory() as session:
        await AgentExecutionRepository(session).create(
            AgentExecution(
                organization_id=organization_id,
                agent_id=agent.id,
                status=ExecutionStatus.COMPLETED,
                total_tokens=9_999,
                trace=[],
                started_at=ago(86_400),
            )
        )
        await session.commit()

    worker = StatisticsRollupWorker(db_session_factory, window_seconds=600)
    await worker.tick()

    window = await _statistic_for_org(db_session_factory, organization_id)
    assert window.total_tokens == 140, "the day-old execution is outside a 10-minute window"


async def test_one_failing_organization_does_not_stop_the_rollup(
    db_session_factory: async_sessionmaker[AsyncSession], organization_id: uuid.UUID
) -> None:
    """A trace row that is not a list of objects makes the real rollup
    raise ``AttributeError`` for that tenant only -- a genuine
    data-shaped failure, no mocking involved."""
    poisoned_org = uuid.uuid4()
    await _seed_activity(db_session_factory, poisoned_org, slug="poisoned", trace=["not-an-object"])
    await _seed_activity(db_session_factory, organization_id, slug="healthy")

    worker = StatisticsRollupWorker(db_session_factory, window_seconds=3_600)
    done = await worker.tick()

    assert done == 1
    assert await _statistic_for_org(db_session_factory, poisoned_org) is None
    assert await _statistic_for_org(db_session_factory, organization_id) is not None


async def test_recompute_returns_false_instead_of_raising(
    db_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    poisoned_org = uuid.uuid4()
    await _seed_activity(
        db_session_factory, poisoned_org, slug="poisoned-direct", trace=["not-an-object"]
    )

    worker = StatisticsRollupWorker(db_session_factory, window_seconds=3_600)

    assert await worker._recompute(poisoned_org) is False


async def test_organizations_respects_its_limit(
    db_session_factory: async_sessionmaker[AsyncSession], organization_id: uuid.UUID
) -> None:
    await _seed_activity(db_session_factory, organization_id, slug="limit-a")
    await _seed_activity(db_session_factory, uuid.uuid4(), slug="limit-b")

    worker = StatisticsRollupWorker(
        db_session_factory, window_seconds=3_600, max_organizations_per_tick=1
    )

    assert len(await worker._organizations()) == 1
    assert await worker.tick() == 1


async def test_statistics_rollup_tick_is_a_no_op_with_no_agents(
    db_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    worker = StatisticsRollupWorker(db_session_factory, window_seconds=3_600)

    assert await worker.tick() == 0


async def test_statistics_rollup_run_job_delegates_to_tick(
    db_session_factory: async_sessionmaker[AsyncSession], organization_id: uuid.UUID
) -> None:
    await _seed_activity(db_session_factory, organization_id, slug="rollup-run-job")

    worker = StatisticsRollupWorker(db_session_factory, window_seconds=3_600)

    assert await worker.run_job(object()) is None
    assert await _statistic_for_org(db_session_factory, organization_id) is not None


# =============================================================================
# app/workers/benchmark_sweep.py
# =============================================================================


async def _profiled_agent(
    session_factory: async_sessionmaker[AsyncSession],
    organization_id: uuid.UUID,
    *,
    slug: str,
    agent_type: AgentType = AgentType.EXECUTOR,
) -> Agent:
    """An ACTIVE agent with a real profile, committed on its own session."""
    async with session_factory() as session:
        service = AgentService(
            AgentRepository(session),
            AgentProfileRepository(session),
            AgentVersionRepository(session),
            AgentAuditRepository(session),
            publish_event=RecordingPublisher(),
        )
        agent = await service.register(
            organization_id=organization_id,
            slug=slug,
            name=f"Agent {slug}",
            agent_type=agent_type,
            profile=ProfileFields(reasoning_mode=ReasoningMode.CHAIN_OF_THOUGHT),
        )
        await session.commit()
        return agent


async def test_benchmark_sweep_records_a_completed_run_for_a_due_agent(
    db_session_factory: async_sessionmaker[AsyncSession],
    organization_id: uuid.UUID,
    reachable_model_registry: ModelRegistry,
    local_model_server: LocalOllamaServer,
) -> None:
    agent = await _profiled_agent(db_session_factory, organization_id, slug="benchmark-me")

    worker = BenchmarkSweepWorker(
        db_session_factory, reachable_model_registry, due_after_seconds=86_400
    )
    ran = await worker.tick()

    assert ran == 1
    assert local_model_server.request_count == 1
    benchmarks = await _benchmarks_for_org(db_session_factory, organization_id)
    assert len(benchmarks) == 1
    benchmark = benchmarks[0]
    assert benchmark.agent_id == agent.id
    assert benchmark.name == "scheduled-health-check"
    assert benchmark.triggered_by == "benchmark-sweep"
    assert benchmark.status == BenchmarkStatus.COMPLETED
    assert benchmark.total_cases == 1
    assert benchmark.passed_cases == 1
    assert benchmark.failed_cases == 0
    assert benchmark.score == pytest.approx(1.0)
    assert benchmark.results[0]["name"] == "scheduled-health-check"
    assert benchmark.results[0]["content"] == MODEL_ANSWER
    assert benchmark.completed_at is not None


async def test_benchmark_sweep_records_a_failing_case_when_the_model_is_unreachable(
    db_session_factory: async_sessionmaker[AsyncSession],
    organization_id: uuid.UUID,
    unreachable_model_registry: ModelRegistry,
) -> None:
    """The suite ran to completion, so the *benchmark* is ``COMPLETED``;
    the case itself failed, which is a score, not a run failure."""
    await _profiled_agent(db_session_factory, organization_id, slug="unreachable-model")

    worker = BenchmarkSweepWorker(
        db_session_factory, unreachable_model_registry, due_after_seconds=86_400
    )
    ran = await worker.tick()

    assert ran == 1
    benchmark = (await _benchmarks_for_org(db_session_factory, organization_id))[0]
    assert benchmark.status == BenchmarkStatus.COMPLETED
    assert benchmark.total_cases == 1
    assert benchmark.passed_cases == 0
    assert benchmark.failed_cases == 1
    assert benchmark.score == pytest.approx(0.0)
    assert benchmark.results[0]["error"]


async def test_benchmark_sweep_skips_an_agent_benchmarked_recently(
    db_session_factory: async_sessionmaker[AsyncSession],
    organization_id: uuid.UUID,
    reachable_model_registry: ModelRegistry,
) -> None:
    agent = await _profiled_agent(db_session_factory, organization_id, slug="recently-checked")
    async with db_session_factory() as session:
        await AgentBenchmarkRepository(session).create(
            AgentBenchmark(
                organization_id=organization_id,
                agent_id=agent.id,
                name="scheduled-health-check",
                status=BenchmarkStatus.COMPLETED,
                started_at=ago(60),
            )
        )
        await session.commit()

    worker = BenchmarkSweepWorker(
        db_session_factory, reachable_model_registry, due_after_seconds=3_600
    )
    ran = await worker.tick()

    assert ran == 0
    assert len(await _benchmarks_for_org(db_session_factory, organization_id)) == 1


async def test_benchmark_sweep_benchmarks_again_once_the_window_has_passed(
    db_session_factory: async_sessionmaker[AsyncSession],
    organization_id: uuid.UUID,
    reachable_model_registry: ModelRegistry,
) -> None:
    agent = await _profiled_agent(db_session_factory, organization_id, slug="stale-check")
    async with db_session_factory() as session:
        await AgentBenchmarkRepository(session).create(
            AgentBenchmark(
                organization_id=organization_id,
                agent_id=agent.id,
                name="scheduled-health-check",
                status=BenchmarkStatus.COMPLETED,
                started_at=ago(7_200),
            )
        )
        await session.commit()

    worker = BenchmarkSweepWorker(
        db_session_factory, reachable_model_registry, due_after_seconds=3_600
    )

    assert await worker.tick() == 1
    assert len(await _benchmarks_for_org(db_session_factory, organization_id)) == 2


async def test_benchmark_sweep_skips_agents_that_are_not_active(
    db_session_factory: async_sessionmaker[AsyncSession],
    organization_id: uuid.UUID,
    reachable_model_registry: ModelRegistry,
) -> None:
    await _bare_agent(
        db_session_factory,
        organization_id,
        slug="paused",
        status=AgentLifecycleStatus.PAUSED,
    )

    worker = BenchmarkSweepWorker(
        db_session_factory, reachable_model_registry, due_after_seconds=86_400
    )

    assert await worker.tick() == 0
    assert await _benchmarks_for_org(db_session_factory, organization_id) == []


async def test_benchmark_sweep_skips_an_active_agent_with_no_profile(
    db_session_factory: async_sessionmaker[AsyncSession],
    organization_id: uuid.UUID,
    reachable_model_registry: ModelRegistry,
) -> None:
    """An agent with no configuration profile cannot actually run, so it
    is skipped rather than recorded as a failed benchmark."""
    await _bare_agent(db_session_factory, organization_id, slug="profileless")
    profiled = await _profiled_agent(db_session_factory, organization_id, slug="profiled")

    worker = BenchmarkSweepWorker(
        db_session_factory, reachable_model_registry, due_after_seconds=86_400
    )
    ran = await worker.tick()

    assert ran == 1
    benchmarks = await _benchmarks_for_org(db_session_factory, organization_id)
    assert [row.agent_id for row in benchmarks] == [profiled.id]


async def test_benchmark_sweep_covers_every_organization(
    db_session_factory: async_sessionmaker[AsyncSession],
    organization_id: uuid.UUID,
    reachable_model_registry: ModelRegistry,
) -> None:
    other_org = uuid.uuid4()
    await _profiled_agent(db_session_factory, organization_id, slug="multi-a")
    await _profiled_agent(db_session_factory, other_org, slug="multi-b")

    worker = BenchmarkSweepWorker(
        db_session_factory, reachable_model_registry, due_after_seconds=86_400
    )

    assert await worker.tick() == 2
    assert len(await _benchmarks_for_org(db_session_factory, organization_id)) == 1
    assert len(await _benchmarks_for_org(db_session_factory, other_org)) == 1


async def test_one_failing_organization_does_not_stop_the_benchmark_sweep(
    db_session_factory: async_sessionmaker[AsyncSession],
    organization_id: uuid.UUID,
    reachable_model_registry: ModelRegistry,
) -> None:
    """The first ``_sweep_org`` cannot get a session; the second must
    still produce its benchmark. Call 1 is ``tick``'s own organization
    listing, so failing call 2 targets whichever tenant is swept first.
    """
    other_org = uuid.uuid4()
    await _profiled_agent(db_session_factory, organization_id, slug="iso-a")
    await _profiled_agent(db_session_factory, other_org, slug="iso-b")

    factory = FailAtNthSessionFactory(
        db_session_factory, fail_on=2, error=RuntimeError("connection checkout failed")
    )
    worker = BenchmarkSweepWorker(factory, reachable_model_registry, due_after_seconds=86_400)
    ran = await worker.tick()

    assert ran == 1
    total = len(await _benchmarks_for_org(db_session_factory, organization_id)) + len(
        await _benchmarks_for_org(db_session_factory, other_org)
    )
    assert total == 1


async def test_sweep_org_returns_zero_instead_of_raising(
    db_session_factory: async_sessionmaker[AsyncSession],
    organization_id: uuid.UUID,
    reachable_model_registry: ModelRegistry,
) -> None:
    factory = FailAtNthSessionFactory(
        db_session_factory, fail_on=1, error=RuntimeError("connection checkout failed")
    )
    worker = BenchmarkSweepWorker(factory, reachable_model_registry, due_after_seconds=86_400)

    assert await worker._sweep_org(organization_id) == 0
    assert factory.calls == 1


async def test_benchmark_sweep_tick_is_a_no_op_with_no_agents(
    db_session_factory: async_sessionmaker[AsyncSession],
    reachable_model_registry: ModelRegistry,
) -> None:
    worker = BenchmarkSweepWorker(
        db_session_factory, reachable_model_registry, due_after_seconds=86_400
    )

    assert await worker.tick() == 0


async def test_benchmark_sweep_respects_max_organizations_per_tick(
    db_session_factory: async_sessionmaker[AsyncSession],
    organization_id: uuid.UUID,
    reachable_model_registry: ModelRegistry,
) -> None:
    await _profiled_agent(db_session_factory, organization_id, slug="cap-a")
    await _profiled_agent(db_session_factory, uuid.uuid4(), slug="cap-b")

    worker = BenchmarkSweepWorker(
        db_session_factory,
        reachable_model_registry,
        due_after_seconds=86_400,
        max_organizations_per_tick=1,
    )

    assert await worker.tick() == 1


async def test_benchmark_sweep_run_job_delegates_to_tick(
    db_session_factory: async_sessionmaker[AsyncSession],
    organization_id: uuid.UUID,
    reachable_model_registry: ModelRegistry,
) -> None:
    await _profiled_agent(db_session_factory, organization_id, slug="benchmark-run-job")

    worker = BenchmarkSweepWorker(
        db_session_factory, reachable_model_registry, due_after_seconds=86_400
    )

    assert await worker.run_job(object()) is None
    assert len(await _benchmarks_for_org(db_session_factory, organization_id)) == 1


# =============================================================================
# app/workers/registrar.py
# =============================================================================


@pytest_asyncio.fixture
async def scheduler_manager(cache_framework: Any) -> AsyncIterator[SchedulerManager]:
    """A real ``SchedulerManager`` on real RabbitMQ + real Redis.

    Deliberately never started: registration is a synchronous registry +
    engine operation, and starting the polling loop would add nothing to
    what these tests assert.
    """
    try:
        queue = await create_queue_framework(rabbitmq_test_settings())
    except UNREACHABLE_ERRORS as exc:  # pragma: no cover - environment guard
        pytest.skip(f"RabbitMQ is not reachable: {exc}")
    manager = create_scheduler_framework(
        queue.manager,
        cache_framework.client,
        queue_name="ai_agent_platform_service_test_scheduler_queue",
    )
    try:
        yield manager
    finally:
        await queue.shutdown()


async def _noop_job(_job: Job) -> None:
    """A real ``JobFn``: the right signature, awaitable, does nothing."""


@pytest.mark.parametrize("interval_seconds", [0, -1, -0.5])
def test_register_rejects_a_non_positive_interval(
    scheduler_manager: SchedulerManager, interval_seconds: float
) -> None:
    """Zero would busy-loop the scheduler; negative is meaningless."""
    with pytest.raises(ValueError, match="interval must be positive"):
        _register(
            scheduler_manager,
            _noop_job,
            job_id="whatever",
            interval_seconds=interval_seconds,
            component="whatever",
        )

    assert scheduler_manager.registry.list_jobs() == []


@pytest.mark.parametrize(
    ("register", "expected_job_id"),
    [
        (register_task_dispatch_sweep, TASK_DISPATCH_SWEEP_JOB_ID),
        (register_checkpoint_recovery_sweep, CHECKPOINT_RECOVERY_SWEEP_JOB_ID),
        (register_statistics_rollup, STATISTICS_ROLLUP_JOB_ID),
        (register_benchmark_sweep, BENCHMARK_SWEEP_JOB_ID),
    ],
)
def test_each_register_helper_produces_its_own_deterministic_job(
    scheduler_manager: SchedulerManager, register: Any, expected_job_id: str
) -> None:
    job = register(scheduler_manager, _noop_job, interval_seconds=30)

    assert job.job_id == expected_job_id
    assert job.job_name == expected_job_id
    assert job.job_type == JobType.SYSTEM
    assert job.fn is _noop_job
    assert job.schedule.schedule_type == FrameworkScheduleType.FIXED_RATE
    assert job.schedule.interval == timedelta(seconds=30)
    assert job.metadata == {"component": expected_job_id}
    assert scheduler_manager.registry.get(expected_job_id).job_id == expected_job_id


@pytest.mark.parametrize(
    "register",
    [
        register_task_dispatch_sweep,
        register_checkpoint_recovery_sweep,
        register_statistics_rollup,
        register_benchmark_sweep,
    ],
)
def test_register_rejects_a_non_positive_interval_through_every_helper(
    scheduler_manager: SchedulerManager, register: Any
) -> None:
    with pytest.raises(ValueError, match="interval must be positive"):
        register(scheduler_manager, _noop_job, interval_seconds=0)


def test_the_registered_job_carries_a_computed_first_due_time(
    scheduler_manager: SchedulerManager,
) -> None:
    """``_register`` returns the *manager's* job, not the locally built
    one -- registration is what computes ``next_run``."""
    job = register_task_dispatch_sweep(scheduler_manager, _noop_job, interval_seconds=15)

    assert job.next_run is not None
    assert job.next_run > datetime.now(UTC)
    assert job.next_run == scheduler_manager.registry.get(TASK_DISPATCH_SWEEP_JOB_ID).next_run


def test_the_four_job_ids_are_distinct_and_namespaced() -> None:
    ids = {
        TASK_DISPATCH_SWEEP_JOB_ID,
        CHECKPOINT_RECOVERY_SWEEP_JOB_ID,
        STATISTICS_ROLLUP_JOB_ID,
        BENCHMARK_SWEEP_JOB_ID,
    }

    assert len(ids) == 4
    assert all(job_id.startswith("ai-agent-platform-") for job_id in ids)


def test_reregistering_replaces_rather_than_leaks(
    scheduler_manager: SchedulerManager,
) -> None:
    """Deterministic job ids exist so a restart re-registers in place."""
    register_statistics_rollup(scheduler_manager, _noop_job, interval_seconds=900)
    register_statistics_rollup(scheduler_manager, _noop_job, interval_seconds=1_800)

    jobs = scheduler_manager.registry.list_jobs()
    assert len(jobs) == 1
    assert jobs[0].schedule.interval == timedelta(seconds=1_800)


def test_all_four_jobs_coexist_in_one_registry(scheduler_manager: SchedulerManager) -> None:
    register_task_dispatch_sweep(scheduler_manager, _noop_job, interval_seconds=15)
    register_checkpoint_recovery_sweep(scheduler_manager, _noop_job, interval_seconds=60)
    register_statistics_rollup(scheduler_manager, _noop_job, interval_seconds=900)
    register_benchmark_sweep(scheduler_manager, _noop_job, interval_seconds=3_600)

    assert {job.job_id for job in scheduler_manager.registry.list_jobs()} == {
        TASK_DISPATCH_SWEEP_JOB_ID,
        CHECKPOINT_RECOVERY_SWEEP_JOB_ID,
        STATISTICS_ROLLUP_JOB_ID,
        BENCHMARK_SWEEP_JOB_ID,
    }
