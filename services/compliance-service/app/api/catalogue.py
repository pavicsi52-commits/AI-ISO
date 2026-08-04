"""Framework, control, and mapping endpoints (docs/051 "REST APIs")."""

from __future__ import annotations

from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Query, status
from shared_core.logging.context import get_log_context

from app.api.deps import AuditSvc, CatalogueSvc, CurrentUserId
from app.models.enums import (
    AuditAction,
    ControlCategory,
    ControlSeverity,
    ControlStatus,
    FrameworkStatus,
)
from app.rules.engine import Check, Rule
from app.schemas.compliance import (
    ControlCreateRequest,
    ControlMappingRequest,
    ControlMappingResponse,
    ControlResponse,
    ControlRuleRequest,
    ControlUpdateRequest,
    FrameworkCreateRequest,
    FrameworkResponse,
    FrameworkUpdateRequest,
    RulePayload,
)
from app.schemas.response import ResponseMeta, SuccessResponse

router = APIRouter(prefix="/compliance", tags=["catalogue"])


def _meta() -> ResponseMeta:
    """Response metadata carrying this request's id.

    The id is what ties a response a caller is holding to the log lines
    the request produced -- without it, "my assessment returned the
    wrong number" is unanswerable.
    """
    return ResponseMeta(request_id=get_log_context().request_id or "unknown")


def rule_from_payload(payload: RulePayload) -> Rule:
    """Build a :class:`Rule` from its API shape."""
    return Rule(
        name=payload.name,
        logical_operator=payload.logical_operator,
        checks=[
            Check(
                path=one.path,
                operator=one.operator,
                value=one.value,
                negate=one.negate,
                description=one.description or "",
            )
            for one in payload.checks
        ],
        children=[rule_from_payload(one) for one in payload.children],
        negate=payload.negate,
        description=payload.description or "",
    )


@router.get(
    "/frameworks",
    response_model=SuccessResponse[list[FrameworkResponse]],
    summary="List compliance frameworks",
)
async def list_frameworks(
    organization_id: UUID,
    catalogue: CatalogueSvc,
    status_filter: Annotated[FrameworkStatus | None, Query(alias="status")] = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 200,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> SuccessResponse[list[FrameworkResponse]]:
    """Every framework an organization tracks."""
    rows = await catalogue.list_frameworks(
        organization_id, status=status_filter, limit=limit, offset=offset
    )
    return SuccessResponse(
        meta=_meta(),
        data=[FrameworkResponse.model_validate(one) for one in rows],
        message="Frameworks listed.",
    )


@router.post(
    "/frameworks",
    response_model=SuccessResponse[FrameworkResponse],
    status_code=status.HTTP_201_CREATED,
    summary="Register a compliance framework",
)
async def create_framework(
    organization_id: UUID,
    body: FrameworkCreateRequest,
    catalogue: CatalogueSvc,
    audit: AuditSvc,
    caller: CurrentUserId,
) -> SuccessResponse[FrameworkResponse]:
    """Register a framework to measure against."""
    created = await catalogue.create_framework(
        organization_id,
        slug=body.slug,
        name=body.name,
        code=body.code,
        kind=body.kind,
        description=body.description,
        publisher=body.publisher,
        framework_version=body.framework_version,
        reference_url=body.reference_url,
        weight=body.weight,
        tags=body.tags,
        actor_id=caller,
    )
    await audit.record(
        organization_id,
        action=AuditAction.FRAMEWORK_CREATED,
        entity_type="framework",
        entity_id=created.id,
        entity_reference=created.slug,
        actor_id=str(caller),
        summary=f"Registered framework {created.slug!r}.",
    )
    return SuccessResponse(
        meta=_meta(),
        data=FrameworkResponse.model_validate(created),
        message="Framework registered.",
    )


@router.post(
    "/frameworks/seed",
    response_model=SuccessResponse[list[FrameworkResponse]],
    summary="Install the built-in frameworks",
)
async def seed_frameworks(
    organization_id: UUID,
    catalogue: CatalogueSvc,
    audit: AuditSvc,
    caller: CurrentUserId,
) -> SuccessResponse[list[FrameworkResponse]]:
    """Install CIS, NIST 800-53, ISO 27001, IEC 62443, SOC 2, and their mappings.

    Idempotent: re-running adds only what is missing. Answers 200 rather
    than 201 because the common case is "nothing was missing", and a 201
    for an empty list would be a lie about what happened.
    """
    seeded = await catalogue.seed_builtin(organization_id, actor_id=caller)
    if seeded:
        await audit.record(
            organization_id,
            action=AuditAction.ADMINISTRATIVE,
            entity_type="framework",
            actor_id=str(caller),
            summary=f"Seeded {len(seeded)} built-in framework(s).",
            changes={"seeded": [one.slug for one in seeded]},
        )
    return SuccessResponse(
        meta=_meta(),
        data=[FrameworkResponse.model_validate(one) for one in seeded],
        message=f"Seeded {len(seeded)} framework(s).",
    )


@router.get(
    "/frameworks/{framework_id}",
    response_model=SuccessResponse[FrameworkResponse],
    summary="Read one framework",
)
async def get_framework(
    organization_id: UUID, framework_id: UUID, catalogue: CatalogueSvc
) -> SuccessResponse[FrameworkResponse]:
    """One framework."""
    found = await catalogue.get_framework(organization_id, framework_id)
    return SuccessResponse(
        meta=_meta(), data=FrameworkResponse.model_validate(found), message="Framework read."
    )


@router.put(
    "/frameworks/{framework_id}",
    response_model=SuccessResponse[FrameworkResponse],
    summary="Update a framework",
)
async def update_framework(
    organization_id: UUID,
    framework_id: UUID,
    body: FrameworkUpdateRequest,
    catalogue: CatalogueSvc,
    audit: AuditSvc,
    caller: CurrentUserId,
) -> SuccessResponse[FrameworkResponse]:
    """Change a framework's metadata."""
    updated = await catalogue.update_framework(
        organization_id,
        framework_id,
        name=body.name,
        description=body.description,
        status=body.status,
        weight=body.weight,
        tags=body.tags,
        actor_id=caller,
    )
    await audit.record(
        organization_id,
        action=AuditAction.FRAMEWORK_UPDATED,
        entity_type="framework",
        entity_id=framework_id,
        entity_reference=updated.slug,
        actor_id=str(caller),
        summary=f"Updated framework {updated.slug!r}.",
        changes=body.model_dump(exclude_none=True),
    )
    return SuccessResponse(
        meta=_meta(), data=FrameworkResponse.model_validate(updated), message="Framework updated."
    )


@router.delete(
    "/frameworks/{framework_id}",
    response_model=SuccessResponse[FrameworkResponse],
    summary="Archive a framework",
)
async def archive_framework(
    organization_id: UUID,
    framework_id: UUID,
    catalogue: CatalogueSvc,
    audit: AuditSvc,
    caller: CurrentUserId,
) -> SuccessResponse[FrameworkResponse]:
    """Take a framework out of scoring.

    Archived, never deleted: every historical finding, result, and score
    points at it, and a report that cannot name the framework it measured
    is not a report.
    """
    archived = await catalogue.archive_framework(organization_id, framework_id, actor_id=caller)
    await audit.record(
        organization_id,
        action=AuditAction.FRAMEWORK_UPDATED,
        entity_type="framework",
        entity_id=framework_id,
        entity_reference=archived.slug,
        actor_id=str(caller),
        summary=f"Archived framework {archived.slug!r}.",
    )
    return SuccessResponse(
        meta=_meta(), data=FrameworkResponse.model_validate(archived), message="Framework archived."
    )


@router.get(
    "/controls",
    response_model=SuccessResponse[list[ControlResponse]],
    summary="List controls",
)
async def list_controls(
    organization_id: UUID,
    catalogue: CatalogueSvc,
    framework_id: UUID | None = None,
    category: ControlCategory | None = None,
    severity: ControlSeverity | None = None,
    status_filter: Annotated[ControlStatus | None, Query(alias="status")] = None,
    owner_id: Annotated[str | None, Query(max_length=255)] = None,
    limit: Annotated[int, Query(ge=1, le=2_000)] = 200,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> SuccessResponse[list[ControlResponse]]:
    """Controls matching a caller's filters."""
    rows = await catalogue.list_controls(
        organization_id,
        framework_id=framework_id,
        category=category,
        severity=severity,
        status=status_filter,
        owner_id=owner_id,
        limit=limit,
        offset=offset,
    )
    return SuccessResponse(
        meta=_meta(),
        data=[ControlResponse.model_validate(one) for one in rows],
        message="Controls listed.",
    )


@router.post(
    "/controls",
    response_model=SuccessResponse[ControlResponse],
    status_code=status.HTTP_201_CREATED,
    summary="Add a control to a framework",
)
async def create_control(
    organization_id: UUID,
    framework_id: UUID,
    body: ControlCreateRequest,
    catalogue: CatalogueSvc,
    audit: AuditSvc,
    caller: CurrentUserId,
) -> SuccessResponse[ControlResponse]:
    """Add a control."""
    created = await catalogue.create_control(
        organization_id,
        framework_id,
        code=body.code,
        title=body.title,
        description=body.description,
        guidance=body.guidance,
        category=body.category,
        severity=body.severity,
        status=body.status,
        owner_id=body.owner_id,
        owner_team=body.owner_team,
        rule=rule_from_payload(body.rule) if body.rule else None,
        remediation_guidance=body.remediation_guidance,
        references=body.references,
        tags=body.tags,
        actor_id=caller,
    )
    await audit.record(
        organization_id,
        action=AuditAction.CONTROL_CREATED,
        entity_type="control",
        entity_id=created.id,
        entity_reference=created.code,
        actor_id=str(caller),
        summary=f"Added control {created.code!r}.",
    )
    return SuccessResponse(
        meta=_meta(), data=ControlResponse.model_validate(created), message="Control added."
    )


@router.get(
    "/controls/{control_id}",
    response_model=SuccessResponse[ControlResponse],
    summary="Read one control",
)
async def get_control(
    organization_id: UUID, control_id: UUID, catalogue: CatalogueSvc
) -> SuccessResponse[ControlResponse]:
    """One control."""
    found = await catalogue.get_control(organization_id, control_id)
    return SuccessResponse(
        meta=_meta(), data=ControlResponse.model_validate(found), message="Control read."
    )


@router.put(
    "/controls/{control_id}",
    response_model=SuccessResponse[ControlResponse],
    summary="Update a control",
)
async def update_control(
    organization_id: UUID,
    control_id: UUID,
    body: ControlUpdateRequest,
    catalogue: CatalogueSvc,
    audit: AuditSvc,
    caller: CurrentUserId,
) -> SuccessResponse[ControlResponse]:
    """Change a control's metadata, ownership, or applicability."""
    updated = await catalogue.update_control(
        organization_id,
        control_id,
        title=body.title,
        description=body.description,
        severity=body.severity,
        status=body.status,
        owner_id=body.owner_id,
        owner_team=body.owner_team,
        remediation_guidance=body.remediation_guidance,
        tags=body.tags,
        actor_id=caller,
    )
    await audit.record(
        organization_id,
        action=AuditAction.CONTROL_UPDATED,
        entity_type="control",
        entity_id=control_id,
        entity_reference=updated.code,
        actor_id=str(caller),
        summary=f"Updated control {updated.code!r}.",
        changes=body.model_dump(exclude_none=True),
    )
    return SuccessResponse(
        meta=_meta(), data=ControlResponse.model_validate(updated), message="Control updated."
    )


@router.put(
    "/controls/{control_id}/rule",
    response_model=SuccessResponse[ControlResponse],
    summary="Set a control's machine-checkable rule",
)
async def set_control_rule(
    organization_id: UUID,
    control_id: UUID,
    body: ControlRuleRequest,
    catalogue: CatalogueSvc,
    audit: AuditSvc,
    caller: CurrentUserId,
) -> SuccessResponse[ControlResponse]:
    """Make a control automatable."""
    updated = await catalogue.set_control_rule(
        organization_id, control_id, rule_from_payload(body.rule), actor_id=caller
    )
    await audit.record(
        organization_id,
        action=AuditAction.CONTROL_UPDATED,
        entity_type="control",
        entity_id=control_id,
        entity_reference=updated.code,
        actor_id=str(caller),
        summary=f"Set the rule for control {updated.code!r}.",
    )
    return SuccessResponse(
        meta=_meta(), data=ControlResponse.model_validate(updated), message="Rule set."
    )


@router.get(
    "/controls/{control_id}/related",
    response_model=SuccessResponse[list[dict[str, Any]]],
    summary="List controls mapped to this one",
)
async def related_controls(
    organization_id: UUID, control_id: UUID, catalogue: CatalogueSvc
) -> SuccessResponse[list[dict[str, Any]]]:
    """What else this control answers, in either direction."""
    related = await catalogue.related_controls(organization_id, control_id)
    return SuccessResponse(meta=_meta(), data=related, message="Related controls listed.")


@router.post(
    "/controls/map",
    response_model=SuccessResponse[ControlMappingResponse],
    status_code=status.HTTP_201_CREATED,
    summary="Map two controls to each other",
)
async def map_controls(
    organization_id: UUID,
    body: ControlMappingRequest,
    catalogue: CatalogueSvc,
    audit: AuditSvc,
    caller: CurrentUserId,
) -> SuccessResponse[ControlMappingResponse]:
    """Record that two controls ask related questions."""
    created = await catalogue.map_controls(
        organization_id,
        source_control_id=body.source_control_id,
        target_control_id=body.target_control_id,
        relation=body.relation,
        confidence=body.confidence,
        note=body.note,
        actor_id=caller,
    )
    await audit.record(
        organization_id,
        action=AuditAction.CONTROL_MAPPED,
        entity_type="control_mapping",
        entity_id=created.id,
        actor_id=str(caller),
        summary=(
            f"Mapped control {body.source_control_id} to {body.target_control_id} "
            f"as {str(body.relation)!r}."
        ),
    )
    return SuccessResponse(
        meta=_meta(),
        data=ControlMappingResponse.model_validate(created),
        message="Controls mapped.",
    )


@router.get(
    "/controls/summary/implementation",
    response_model=SuccessResponse[dict[str, Any]],
    summary="How far through its control programme an organization is",
)
async def implementation_summary(
    organization_id: UUID, catalogue: CatalogueSvc
) -> SuccessResponse[dict[str, Any]]:
    """Implemented over *applicable*, not over total.

    A control formally scoped out is not outstanding work, and counting
    it as such makes a finished programme look permanently incomplete.
    """
    return SuccessResponse(
        meta=_meta(),
        data=await catalogue.implementation_summary(organization_id),
        message="Implementation summary computed.",
    )
