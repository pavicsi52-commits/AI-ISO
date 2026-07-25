"""Construction tests for the request/response schemas backing internal
concerns that have no dedicated top-level REST endpoint of their own
(approvals, audit, execution plans, execution steps, outputs,
parameters, results, retry history, rollbacks, schedules, targets,
variables) -- docs/040's own REST list names only the 17 literal
endpoints ``app/api``'s five routers implement; every other schema is
consumed internally (e.g. by
:class:`~app.services.execution.AutomationExecutionService`) or
reserved for a future prompt's own router, the same "schemas exist
ahead of their own router" precedent
``services/configuration-management-service``'s own
``test_schemas_unrouted.py`` established.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from app.models.enums import (
    ApprovalStatus,
    ApprovalType,
    AuditOutcome,
    ConnectorType,
    ExecutionStepStatus,
    ExecutionTargetType,
    FailureClassification,
    RetryStrategy,
    RollbackStatus,
    RollbackType,
    VariableScope,
)
from app.schemas.approval import (
    AutomationApprovalCreateRequest,
    AutomationApprovalDecisionRequest,
    AutomationApprovalResponse,
)
from app.schemas.audit import AutomationAuditResponse
from app.schemas.execution_plan import (
    AutomationExecutionPlanCreateRequest,
    AutomationExecutionPlanResponse,
)
from app.schemas.execution_step import AutomationExecutionStepResponse
from app.schemas.output import AutomationOutputResponse
from app.schemas.parameter import AutomationParameterCreateRequest, AutomationParameterResponse
from app.schemas.result import AutomationResultResponse
from app.schemas.retry_history import AutomationRetryHistoryResponse
from app.schemas.rollback import AutomationRollbackCreateRequest, AutomationRollbackResponse
from app.schemas.schedule import AutomationScheduleCreateRequest, AutomationScheduleResponse
from app.schemas.target import AutomationTargetCreateRequest, AutomationTargetResponse
from app.schemas.variable import AutomationVariableCreateRequest, AutomationVariableResponse


def test_approval_schemas() -> None:
    create = AutomationApprovalCreateRequest(level=2)
    assert create.level == 2

    decision = AutomationApprovalDecisionRequest(status=ApprovalStatus.APPROVED)
    assert decision.status == ApprovalStatus.APPROVED

    response = AutomationApprovalResponse(
        id=uuid.uuid4(),
        execution_id=uuid.uuid4(),
        approval_type=ApprovalType.SINGLE,
        status=ApprovalStatus.PENDING,
        level=1,
        requested_by=None,
        approver_id=None,
        comments=None,
        expires_at=None,
        decided_at=None,
    )
    assert response.status == ApprovalStatus.PENDING


def test_audit_response() -> None:
    response = AutomationAuditResponse(
        id=uuid.uuid4(),
        job_id=uuid.uuid4(),
        execution_id=None,
        actor_id=None,
        action="create",
        outcome=AuditOutcome.SUCCESS,
        reason="",
        before=None,
        after={"name": "deploy-web"},
    )
    assert response.action == "create"


def test_execution_plan_schemas() -> None:
    create = AutomationExecutionPlanCreateRequest(organization_id=uuid.uuid4(), name="rollout")
    assert create.name == "rollout"

    response = AutomationExecutionPlanResponse(
        id=uuid.uuid4(),
        organization_id=uuid.uuid4(),
        job_id=None,
        name="rollout",
        steps=[{"phase": "pre_check"}],
        approval_gates=[],
        rollback_plan=None,
    )
    assert response.steps[0]["phase"] == "pre_check"


def test_execution_step_response() -> None:
    response = AutomationExecutionStepResponse(
        id=uuid.uuid4(),
        execution_id=uuid.uuid4(),
        step_index=0,
        name="local",
        status=ExecutionStepStatus.COMPLETED,
        target_id=None,
        started_at=datetime.now(UTC),
        completed_at=datetime.now(UTC),
        output={"exit_code": 0},
        error_message=None,
    )
    assert response.status == ExecutionStepStatus.COMPLETED


def test_output_response() -> None:
    response = AutomationOutputResponse(
        id=uuid.uuid4(), execution_id=uuid.uuid4(), step_id=None, key="exit_code", value=0
    )
    assert response.key == "exit_code"


def test_parameter_schemas() -> None:
    create = AutomationParameterCreateRequest(name="hostname")
    assert create.parameter_type == "string"

    response = AutomationParameterResponse(
        id=uuid.uuid4(),
        job_id=uuid.uuid4(),
        name="hostname",
        parameter_type="string",
        required=True,
        default_value=None,
        description=None,
    )
    assert response.required is True


def test_result_response() -> None:
    response = AutomationResultResponse(
        id=uuid.uuid4(),
        execution_id=uuid.uuid4(),
        success=True,
        summary="All targets succeeded.",
        metrics={},
        completed_at=datetime.now(UTC),
    )
    assert response.success is True


def test_retry_history_response() -> None:
    response = AutomationRetryHistoryResponse(
        id=uuid.uuid4(),
        execution_id=uuid.uuid4(),
        step_id=None,
        attempt_number=1,
        strategy=RetryStrategy.EXPONENTIAL_BACKOFF,
        classification=FailureClassification.TRANSIENT,
        succeeded=False,
        attempted_at=datetime.now(UTC),
    )
    assert response.classification == FailureClassification.TRANSIENT


def test_rollback_schemas() -> None:
    create = AutomationRollbackCreateRequest(reason="bad deploy")
    assert create.rollback_type == RollbackType.MANUAL

    response = AutomationRollbackResponse(
        id=uuid.uuid4(),
        execution_id=uuid.uuid4(),
        rollback_type=RollbackType.AUTOMATIC,
        status=RollbackStatus.PENDING,
        initiated_by=None,
        reason=None,
        completed_at=None,
    )
    assert response.status == RollbackStatus.PENDING


def test_schedule_schemas() -> None:
    create = AutomationScheduleCreateRequest(cron_expression="0 * * * *")
    assert create.enabled is True

    response = AutomationScheduleResponse(
        id=uuid.uuid4(),
        job_id=uuid.uuid4(),
        cron_expression="0 * * * *",
        enabled=True,
        next_run_at=None,
        last_run_at=None,
    )
    assert response.cron_expression == "0 * * * *"


def test_target_schemas() -> None:
    create = AutomationTargetCreateRequest(
        organization_id=uuid.uuid4(),
        name="web-1",
        target_type=ExecutionTargetType.VIRTUAL_MACHINE,
        connector_type=ConnectorType.SSH,
        address="10.0.0.5",
    )
    assert create.connector_type == ConnectorType.SSH

    response = AutomationTargetResponse(
        id=uuid.uuid4(),
        organization_id=uuid.uuid4(),
        project_id=None,
        name="web-1",
        target_type=ExecutionTargetType.VIRTUAL_MACHINE,
        connector_type=ConnectorType.SSH,
        address="10.0.0.5",
        port=22,
        username="deploy",
        inventory_asset_id=None,
        labels={},
        tags=[],
        metadata={},
    )
    assert response.name == "web-1"


def test_variable_schemas() -> None:
    create = AutomationVariableCreateRequest(
        organization_id=uuid.uuid4(), scope=VariableScope.GLOBAL, key="region", value="us-east-1"
    )
    assert create.is_secret_reference is False

    response = AutomationVariableResponse(
        id=uuid.uuid4(),
        organization_id=uuid.uuid4(),
        scope=VariableScope.GLOBAL,
        scope_ref_id=None,
        key="region",
        value="us-east-1",
        is_secret_reference=False,
    )
    assert response.key == "region"


__all__: list[str] = []
