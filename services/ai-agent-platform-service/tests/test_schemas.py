"""Direct, HTTP-free schema tests for ``app.schemas.*``.

Everything the golden-path smoke test and the HTTP-level edge-case
tests already exercise through real requests is not repeated here --
this file covers field defaults, boundary validation, and
serialization shape by constructing each schema directly with real
data, per this service's own division of labour between test files.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest
from pydantic import BaseModel, ValidationError

from app.models.enums import (
    AgentLifecycleStatus,
    AgentType,
    BenchmarkStatus,
    ModelProvider,
    PermissionCategory,
    ReasoningMode,
    ReportFormat,
    ReportKind,
    ReportStatus,
    RoutingStrategy,
    TaskPriority,
    TaskStatus,
    ToolKind,
)
from app.schemas.agent import (
    AgentExecuteRequest,
    AgentExecutionResponse,
    AgentRegisterRequest,
    AgentResponse,
    AgentUpdateRequest,
    ProfilePayload,
)
from app.schemas.governance import (
    BenchmarkResponse,
    EvaluationResponse,
    ReportResponse,
    StatisticResponse,
)
from app.schemas.health import HealthStatus, LivenessStatus, ReadinessCheck, ReadinessStatus
from app.schemas.response import ResponseMeta, SuccessResponse
from app.schemas.task import TaskCreateRequest, TaskResponse
from app.schemas.tool import ToolRegisterRequest, ToolResponse

# ---- app.schemas.agent -----------------------------------------------------


class TestProfilePayload:
    def test_defaults(self) -> None:
        payload = ProfilePayload()
        assert payload.system_prompt is None
        assert payload.model_provider == ModelProvider.OLLAMA
        assert payload.model_name == "llama3"
        assert payload.temperature == pytest.approx(0.2)
        assert payload.max_tokens == 2_048
        assert payload.reasoning_mode == ReasoningMode.TOOL_BASED
        assert payload.routing_strategy == RoutingStrategy.FALLBACK
        assert payload.fallback_providers == []
        assert payload.allowed_tool_keys == []
        assert payload.max_reasoning_steps == 8
        assert payload.extra_config == {}

    @pytest.mark.parametrize("temperature", [0.0, 2.0, 1.0])
    def test_temperature_within_bounds(self, temperature: float) -> None:
        assert ProfilePayload(temperature=temperature).temperature == temperature

    @pytest.mark.parametrize("temperature", [-0.01, 2.01, -5.0, 10.0])
    def test_temperature_out_of_bounds_rejected(self, temperature: float) -> None:
        with pytest.raises(ValidationError):
            ProfilePayload(temperature=temperature)

    @pytest.mark.parametrize("max_tokens", [1, 200_000])
    def test_max_tokens_within_bounds(self, max_tokens: int) -> None:
        assert ProfilePayload(max_tokens=max_tokens).max_tokens == max_tokens

    @pytest.mark.parametrize("max_tokens", [0, -1, 200_001])
    def test_max_tokens_out_of_bounds_rejected(self, max_tokens: int) -> None:
        with pytest.raises(ValidationError):
            ProfilePayload(max_tokens=max_tokens)

    @pytest.mark.parametrize("steps", [1, 64])
    def test_max_reasoning_steps_within_bounds(self, steps: int) -> None:
        assert ProfilePayload(max_reasoning_steps=steps).max_reasoning_steps == steps

    @pytest.mark.parametrize("steps", [0, 65])
    def test_max_reasoning_steps_out_of_bounds_rejected(self, steps: int) -> None:
        with pytest.raises(ValidationError):
            ProfilePayload(max_reasoning_steps=steps)

    def test_fallback_providers_accepts_enum_list(self) -> None:
        payload = ProfilePayload(fallback_providers=[ModelProvider.OPENAI, "ollama"])
        assert payload.fallback_providers == [ModelProvider.OPENAI, ModelProvider.OLLAMA]

    def test_invalid_model_provider_rejected(self) -> None:
        with pytest.raises(ValidationError):
            ProfilePayload(model_provider="not-a-real-provider")


class TestAgentRegisterRequest:
    def test_minimal_valid_request(self) -> None:
        request = AgentRegisterRequest(slug="my-agent", name="My Agent", agent_type="executor")
        assert request.agent_type == AgentType.EXECUTOR
        assert request.description is None
        assert request.owner_id is None
        assert request.tags == []
        assert isinstance(request.profile, ProfilePayload)

    def test_missing_required_fields_rejected(self) -> None:
        with pytest.raises(ValidationError):
            AgentRegisterRequest(name="My Agent", agent_type="executor")  # type: ignore[call-arg]

    def test_empty_slug_rejected(self) -> None:
        with pytest.raises(ValidationError):
            AgentRegisterRequest(slug="", name="My Agent", agent_type="executor")

    def test_slug_too_long_rejected(self) -> None:
        with pytest.raises(ValidationError):
            AgentRegisterRequest(slug="x" * 65, name="My Agent", agent_type="executor")

    def test_slug_max_length_accepted(self) -> None:
        request = AgentRegisterRequest(slug="x" * 64, name="My Agent", agent_type="executor")
        assert len(request.slug) == 64

    def test_empty_name_rejected(self) -> None:
        with pytest.raises(ValidationError):
            AgentRegisterRequest(slug="my-agent", name="", agent_type="executor")

    def test_name_too_long_rejected(self) -> None:
        with pytest.raises(ValidationError):
            AgentRegisterRequest(slug="my-agent", name="x" * 129, agent_type="executor")

    def test_invalid_agent_type_rejected(self) -> None:
        with pytest.raises(ValidationError):
            AgentRegisterRequest(slug="my-agent", name="My Agent", agent_type="not-a-real-type")

    def test_nested_profile_payload_accepted(self) -> None:
        request = AgentRegisterRequest(
            slug="my-agent",
            name="My Agent",
            agent_type="executor",
            profile={"temperature": 0.9, "model_name": "gpt-4o"},
        )
        assert request.profile.temperature == pytest.approx(0.9)
        assert request.profile.model_name == "gpt-4o"


class TestAgentUpdateRequest:
    def test_all_none_is_valid(self) -> None:
        request = AgentUpdateRequest()
        assert request.name is None
        assert request.description is None
        assert request.owner_id is None
        assert request.tags is None

    def test_empty_name_rejected_when_provided(self) -> None:
        with pytest.raises(ValidationError):
            AgentUpdateRequest(name="")

    def test_name_too_long_rejected(self) -> None:
        with pytest.raises(ValidationError):
            AgentUpdateRequest(name="x" * 129)

    def test_partial_update_fields(self) -> None:
        request = AgentUpdateRequest(description="new description")
        assert request.name is None
        assert request.description == "new description"


class TestAgentExecuteRequest:
    def test_defaults(self) -> None:
        request = AgentExecuteRequest(request="Do the thing.")
        assert request.session_id is None
        assert request.task_id is None
        assert request.allow_mutating is False

    def test_empty_request_rejected(self) -> None:
        with pytest.raises(ValidationError):
            AgentExecuteRequest(request="")

    def test_missing_request_rejected(self) -> None:
        with pytest.raises(ValidationError):
            AgentExecuteRequest()  # type: ignore[call-arg]


class TestAgentResponse:
    def _kwargs(self, **overrides: object) -> dict[str, object]:
        base: dict[str, object] = {
            "id": uuid.uuid4(),
            "organization_id": uuid.uuid4(),
            "slug": "my-agent",
            "name": "My Agent",
            "description": None,
            "agent_type": AgentType.EXECUTOR,
            "status": AgentLifecycleStatus.ACTIVE,
            "current_version_number": "1.0.0",
            "tags": ["a", "b"],
            "owner_id": None,
            "consecutive_failures": 0,
            "last_executed_at": None,
            "created_at": datetime.now(UTC),
        }
        base.update(overrides)
        return base

    def test_round_trips_all_fields(self) -> None:
        kwargs = self._kwargs()
        response = AgentResponse(**kwargs)
        assert response.slug == "my-agent"
        assert response.status == AgentLifecycleStatus.ACTIVE
        assert response.tags == ["a", "b"]

    def test_from_attributes_reads_orm_style_object(self) -> None:
        class _OrmLike:
            def __init__(self, **fields: object) -> None:
                for key, value in fields.items():
                    setattr(self, key, value)

        row = _OrmLike(**self._kwargs())
        response = AgentResponse.model_validate(row)
        assert response.name == "My Agent"

    def test_missing_field_rejected(self) -> None:
        kwargs = self._kwargs()
        del kwargs["slug"]
        with pytest.raises(ValidationError):
            AgentResponse(**kwargs)


class TestAgentExecutionResponse:
    def test_round_trips_all_fields(self) -> None:
        response = AgentExecutionResponse(
            id=uuid.uuid4(),
            agent_id=uuid.uuid4(),
            task_id=None,
            session_id=None,
            status="completed",
            reasoning_mode="tool_based",
            model_provider="ollama",
            model_name="llama3",
            prompt_tokens=10,
            completion_tokens=20,
            total_tokens=30,
            tool_calls_made=1,
            reasoning_steps=2,
            latency_ms=123.4,
            cost_usd=0.0,
            input_summary="hi",
            output_summary="hello",
            trace=[{"type": "tool_call", "tool_key": "x"}],
            started_at=datetime.now(UTC),
            completed_at=datetime.now(UTC),
            error=None,
        )
        assert response.total_tokens == 30
        assert response.trace[0]["tool_key"] == "x"


# ---- app.schemas.governance -------------------------------------------------


class TestEvaluationResponse:
    def test_round_trips_with_optional_fields_none(self) -> None:
        response = EvaluationResponse(
            id=uuid.uuid4(),
            agent_id=uuid.uuid4(),
            execution_id=uuid.uuid4(),
            task_accuracy=None,
            execution_quality=None,
            reasoning_quality=None,
            tool_success_rate=None,
            latency_ms=None,
            cost_usd=None,
            human_feedback_score=None,
            is_regression_test=False,
            notes=None,
            evaluated_by=None,
            evaluated_at=datetime.now(UTC),
        )
        assert response.is_regression_test is False
        assert response.task_accuracy is None


class TestBenchmarkResponse:
    def test_round_trips(self) -> None:
        response = BenchmarkResponse(
            id=uuid.uuid4(),
            agent_id=uuid.uuid4(),
            name="nightly-suite",
            status=BenchmarkStatus.COMPLETED,
            total_cases=10,
            passed_cases=9,
            failed_cases=1,
            score=0.9,
            results=[{"case": 1, "passed": True}],
            started_at=datetime.now(UTC),
            completed_at=datetime.now(UTC),
            triggered_by="scheduler",
            error=None,
        )
        assert response.status == BenchmarkStatus.COMPLETED
        assert response.results[0]["passed"] is True


class TestStatisticResponse:
    def test_round_trips(self) -> None:
        response = StatisticResponse(
            id=uuid.uuid4(),
            window_start=datetime.now(UTC),
            window_end=datetime.now(UTC),
            active_agents=3,
            task_count=5,
            executions_succeeded=4,
            executions_failed=1,
            total_tokens=1000,
            average_cost_usd=0.02,
            average_latency_ms=250.0,
            memory_rows_created=7,
            by_agent_type={"executor": 3},
            by_model_provider={"ollama": 4},
            by_tool={"http": 2},
        )
        assert response.by_agent_type == {"executor": 3}
        assert response.average_cost_usd == pytest.approx(0.02)


class TestReportResponse:
    def test_round_trips(self) -> None:
        response = ReportResponse(
            id=uuid.uuid4(),
            kind=ReportKind.USAGE,
            report_format=ReportFormat.JSON,
            title="Usage report",
            status=ReportStatus.COMPLETED,
            content={"rows": []},
            row_count=0,
            generated_by="tester",
            generated_at=datetime.now(UTC),
            duration_ms=12.3,
            error=None,
        )
        assert response.kind == ReportKind.USAGE
        assert response.content == {"rows": []}


# ---- app.schemas.health -----------------------------------------------------


class TestHealthStatus:
    def test_valid_status(self) -> None:
        status = HealthStatus(
            status="healthy", service="svc", version="1.0.0", environment="development"
        )
        assert status.status == "healthy"

    def test_invalid_status_literal_rejected(self) -> None:
        with pytest.raises(ValidationError):
            HealthStatus(status="not-a-status", service="svc", version="1.0.0", environment="dev")


class TestLivenessStatus:
    def test_alive(self) -> None:
        assert LivenessStatus(status="alive").status == "alive"

    def test_other_value_rejected(self) -> None:
        with pytest.raises(ValidationError):
            LivenessStatus(status="dead")


class TestReadinessCheck:
    def test_detail_defaults_to_none(self) -> None:
        check = ReadinessCheck(name="database", status="ok")
        assert check.detail is None

    def test_status_literal_enforced(self) -> None:
        with pytest.raises(ValidationError):
            ReadinessCheck(name="database", status="degraded")


class TestReadinessStatus:
    def test_round_trips_checks(self) -> None:
        status = ReadinessStatus(
            status="ready",
            checks=[
                ReadinessCheck(name="database", status="ok", detail="1.0ms"),
                ReadinessCheck(name="cache", status="failed", detail="unreachable"),
            ],
        )
        assert len(status.checks) == 2
        assert status.checks[1].status == "failed"

    def test_invalid_status_literal_rejected(self) -> None:
        with pytest.raises(ValidationError):
            ReadinessStatus(status="pending", checks=[])


# ---- app.schemas.response ---------------------------------------------------


class TestResponseMeta:
    def test_timestamp_defaults_to_now_utc(self) -> None:
        before = datetime.now(UTC)
        meta = ResponseMeta(request_id="abc-123")
        after = datetime.now(UTC)
        assert meta.request_id == "abc-123"
        assert meta.timestamp.tzinfo is not None
        assert before <= meta.timestamp <= after

    def test_explicit_timestamp_preserved(self) -> None:
        fixed = datetime(2024, 1, 1, tzinfo=UTC)
        meta = ResponseMeta(request_id="abc-123", timestamp=fixed)
        assert meta.timestamp == fixed


class TestSuccessResponse:
    def test_default_success_flag_true(self) -> None:
        response = SuccessResponse[int](message="ok", data=5, meta=ResponseMeta(request_id="r-1"))
        assert response.success is True
        assert response.data == 5

    def test_success_flag_can_be_overridden(self) -> None:
        response = SuccessResponse[int](
            success=False, message="ok", data=5, meta=ResponseMeta(request_id="r-1")
        )
        assert response.success is False

    def test_generic_with_list_data(self) -> None:
        response = SuccessResponse[list[int]](
            message="listed", data=[1, 2, 3], meta=ResponseMeta(request_id="r-2")
        )
        assert response.data == [1, 2, 3]

    def test_generic_with_optional_none_data(self) -> None:
        response = SuccessResponse[int | None](
            message="nothing yet", data=None, meta=ResponseMeta(request_id="r-3")
        )
        assert response.data is None

    def test_serialization_shape(self) -> None:
        response = SuccessResponse[int](message="ok", data=1, meta=ResponseMeta(request_id="r-4"))
        dumped = response.model_dump(mode="json")
        assert set(dumped.keys()) == {"success", "message", "data", "meta"}
        assert set(dumped["meta"].keys()) == {"request_id", "timestamp"}

    def test_nested_pydantic_model_as_data(self) -> None:
        class _Inner(BaseModel):
            value: int

        response = SuccessResponse[_Inner](
            message="ok", data=_Inner(value=42), meta=ResponseMeta(request_id="r-5")
        )
        assert response.data.value == 42


# ---- app.schemas.task -------------------------------------------------------


class TestTaskCreateRequest:
    def test_defaults(self) -> None:
        request = TaskCreateRequest(task_type="do-thing")
        assert request.payload == {}
        assert request.agent_id is None
        assert request.parent_task_id is None
        assert request.priority == TaskPriority.NORMAL
        assert request.scheduled_at is None
        assert request.max_retries == 3
        assert request.timeout_seconds == pytest.approx(300.0)

    def test_empty_task_type_rejected(self) -> None:
        with pytest.raises(ValidationError):
            TaskCreateRequest(task_type="")

    def test_task_type_too_long_rejected(self) -> None:
        with pytest.raises(ValidationError):
            TaskCreateRequest(task_type="x" * 65)

    @pytest.mark.parametrize("max_retries", [0, 20])
    def test_max_retries_within_bounds(self, max_retries: int) -> None:
        assert TaskCreateRequest(task_type="t", max_retries=max_retries).max_retries == max_retries

    @pytest.mark.parametrize("max_retries", [-1, 21])
    def test_max_retries_out_of_bounds_rejected(self, max_retries: int) -> None:
        with pytest.raises(ValidationError):
            TaskCreateRequest(task_type="t", max_retries=max_retries)

    def test_timeout_seconds_must_be_positive(self) -> None:
        with pytest.raises(ValidationError):
            TaskCreateRequest(task_type="t", timeout_seconds=0)

    def test_timeout_seconds_negative_rejected(self) -> None:
        with pytest.raises(ValidationError):
            TaskCreateRequest(task_type="t", timeout_seconds=-1.0)

    def test_invalid_priority_rejected(self) -> None:
        with pytest.raises(ValidationError):
            TaskCreateRequest(task_type="t", priority="urgent")


class TestTaskResponse:
    def test_round_trips(self) -> None:
        response = TaskResponse(
            id=uuid.uuid4(),
            organization_id=uuid.uuid4(),
            agent_id=None,
            parent_task_id=None,
            task_type="do-thing",
            status=TaskStatus.PENDING,
            priority=TaskPriority.NORMAL,
            payload={"note": "hi"},
            result=None,
            retry_count=0,
            max_retries=3,
            timeout_seconds=300.0,
            scheduled_at=datetime.now(UTC),
            started_at=None,
            completed_at=None,
            error=None,
            requested_by="tester",
            created_at=datetime.now(UTC),
        )
        assert response.status == TaskStatus.PENDING
        assert response.payload == {"note": "hi"}


# ---- app.schemas.tool -------------------------------------------------------


class TestToolRegisterRequest:
    def test_defaults(self) -> None:
        request = ToolRegisterRequest(tool_key="my.tool", name="My Tool", tool_kind="rest")
        assert request.description is None
        assert request.category == "general"
        assert request.parameters_schema == {}
        assert request.required_permission == PermissionCategory.TOOL_INVOCATION
        assert request.is_mutating is False
        assert request.metadata == {}

    def test_empty_tool_key_rejected(self) -> None:
        with pytest.raises(ValidationError):
            ToolRegisterRequest(tool_key="", name="My Tool", tool_kind="rest")

    def test_tool_key_too_long_rejected(self) -> None:
        with pytest.raises(ValidationError):
            ToolRegisterRequest(tool_key="x" * 129, name="My Tool", tool_kind="rest")

    def test_empty_name_rejected(self) -> None:
        with pytest.raises(ValidationError):
            ToolRegisterRequest(tool_key="my.tool", name="", tool_kind="rest")

    def test_invalid_tool_kind_rejected(self) -> None:
        with pytest.raises(ValidationError):
            ToolRegisterRequest(tool_key="my.tool", name="My Tool", tool_kind="not-a-real-kind")

    def test_invalid_required_permission_rejected(self) -> None:
        with pytest.raises(ValidationError):
            ToolRegisterRequest(
                tool_key="my.tool",
                name="My Tool",
                tool_kind="rest",
                required_permission="not-a-real-permission",
            )


class TestToolResponse:
    def test_round_trips(self) -> None:
        response = ToolResponse(
            id=uuid.uuid4(),
            organization_id=uuid.uuid4(),
            tool_key="my.tool",
            name="My Tool",
            description=None,
            tool_kind=ToolKind.REST,
            category="general",
            parameters_schema={"type": "object"},
            required_permission=PermissionCategory.TOOL_INVOCATION,
            is_mutating=False,
            version_number="1.0.0",
            enabled=True,
            is_deprecated=False,
            health_status="unknown",
            created_at=datetime.now(UTC),
        )
        assert response.tool_kind == ToolKind.REST
        assert response.enabled is True
