"""Integration flows (docs/058 "INTEGRATION FLOWS")."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter
from shared_core.logging.context import get_log_context

from app.api.deps import AuditSvc, CurrentUserId, FlowSvc
from app.models.enums import AuditAction
from app.schemas.hub import FlowCreateRequest, FlowResponse, FlowRunRequest, FlowRunResultResponse
from app.schemas.response import ResponseMeta, SuccessResponse

router = APIRouter(prefix="/integrations/flows", tags=["Flows"])


def _meta() -> ResponseMeta:
    return ResponseMeta(request_id=get_log_context().request_id or "unknown")


@router.get("", response_model=SuccessResponse[list[FlowResponse]], summary="List flows")
async def list_flows(organization_id: UUID, flows: FlowSvc) -> SuccessResponse[list[FlowResponse]]:
    """Flows in this organization."""
    rows = await flows.list_for_org(organization_id)
    return SuccessResponse(
        message="Flows listed.", data=[FlowResponse.model_validate(r) for r in rows], meta=_meta()
    )


@router.get("/{flow_id}", response_model=SuccessResponse[FlowResponse], summary="Get a flow")
async def get_flow(
    organization_id: UUID, flow_id: UUID, flows: FlowSvc
) -> SuccessResponse[FlowResponse]:
    """One flow."""
    found = await flows.get(organization_id, flow_id)
    return SuccessResponse(
        message="Flow found.", data=FlowResponse.model_validate(found), meta=_meta()
    )


@router.post(
    "", response_model=SuccessResponse[FlowResponse], status_code=201, summary="Create a flow"
)
async def create_flow(
    organization_id: UUID, body: FlowCreateRequest, flows: FlowSvc
) -> SuccessResponse[FlowResponse]:
    """Register a new flow definition, in ``DRAFT``."""
    created = await flows.create(
        organization_id,
        name=body.name,
        definition=body.definition,
        connector_id=body.connector_id,
        description=body.description,
        trigger=body.trigger,
        schedule_interval_seconds=body.schedule_interval_seconds,
    )
    return SuccessResponse(
        message="Flow created.", data=FlowResponse.model_validate(created), meta=_meta()
    )


@router.post(
    "/{flow_id}/activate", response_model=SuccessResponse[FlowResponse], summary="Activate a flow"
)
async def activate_flow(
    organization_id: UUID, flow_id: UUID, flows: FlowSvc
) -> SuccessResponse[FlowResponse]:
    """Move a flow into ``ACTIVE``."""
    activated = await flows.activate(organization_id, flow_id)
    return SuccessResponse(
        message="Flow activated.", data=FlowResponse.model_validate(activated), meta=_meta()
    )


@router.post(
    "/{flow_id}/disable", response_model=SuccessResponse[FlowResponse], summary="Disable a flow"
)
async def disable_flow(
    organization_id: UUID, flow_id: UUID, flows: FlowSvc
) -> SuccessResponse[FlowResponse]:
    """Disable a flow."""
    disabled = await flows.disable(organization_id, flow_id)
    return SuccessResponse(
        message="Flow disabled.", data=FlowResponse.model_validate(disabled), meta=_meta()
    )


@router.post(
    "/{flow_id}/run", response_model=SuccessResponse[FlowRunResultResponse], summary="Run a flow"
)
async def run_flow(
    organization_id: UUID,
    flow_id: UUID,
    body: FlowRunRequest,
    flows: FlowSvc,
    audit: AuditSvc,
    caller: CurrentUserId,
) -> SuccessResponse[FlowRunResultResponse]:
    """Execute a flow's own definition."""
    flow = await flows.get(organization_id, flow_id)
    context = {**body.context, "organization_id": str(organization_id)}
    result = await flows.run(organization_id, flow, context=context)
    await audit.record(
        organization_id,
        action=AuditAction.FLOW_EXECUTED,
        entity_type="flow",
        entity_id=flow_id,
        actor_id=str(caller),
        summary=f"Ran flow {flow.name!r} (status={result.status}).",
    )
    return SuccessResponse(
        message="Flow run.",
        data=FlowRunResultResponse(
            status=result.status,
            context=result.context,
            steps_executed=result.steps_executed,
            error=result.error,
            awaiting_step=result.awaiting_step,
        ),
        meta=_meta(),
    )


@router.post(
    "/{flow_id}/approve/{step_id}",
    response_model=SuccessResponse[FlowRunResultResponse],
    summary="Approve an awaiting-approval step and resume",
)
async def approve_flow_step(
    organization_id: UUID,
    flow_id: UUID,
    step_id: str,
    body: FlowRunRequest,
    flows: FlowSvc,
) -> SuccessResponse[FlowRunResultResponse]:
    """Resume a flow paused at an ``APPROVAL`` step."""
    flow = await flows.get(organization_id, flow_id)
    context = {
        **body.context,
        "organization_id": str(organization_id),
        f"_approved_{step_id}": True,
    }
    result = await flows.run(organization_id, flow, context=context)
    return SuccessResponse(
        message="Flow resumed.",
        data=FlowRunResultResponse(
            status=result.status,
            context=result.context,
            steps_executed=result.steps_executed,
            error=result.error,
            awaiting_step=result.awaiting_step,
        ),
        meta=_meta(),
    )


__all__ = ["router"]
