"""Policy CRUD, publishing, and rollback (docs/050 "REST APIs").

``POST /policies/evaluate`` is the endpoint the whole platform depends
on, so its handler is worth reading twice -- and it is the one place here
that answers ``200`` for a refusal. A denial is a *successful* decision:
the caller asked whether something was permitted and got a correct
answer. Returning ``403`` would conflate "you may not do that" with "you
may not ask", and every caller would have to distinguish an
authorization outcome from an authorization failure by parsing a body.
"""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Query, status
from shared_core.logging.context import get_log_context

from app.api.deps import (
    ApprovalSvc,
    AuditSvc,
    CurrentUserId,
    DecisionSvc,
    PolicySvc,
    SimulationSvc,
)
from app.attributes.resolver import EvaluationContext
from app.models.enums import (
    AuditAction,
    PolicyCategory,
    PolicyEffect,
    PolicyStatus,
    PolicyType,
)
from app.rules.engine import Condition, Rule
from app.schemas.policy import (
    DecisionResponse,
    EvaluateRequest,
    PolicyCreateRequest,
    PolicyResponse,
    PolicyUpdateRequest,
    PolicyVersionResponse,
    PublishRequest,
    RollbackRequest,
    RulePayload,
    RuleTreeRequest,
    SimulateRequest,
    SimulationResponse,
    TransitionRequest,
)
from app.schemas.response import ResponseMeta, SuccessResponse
from app.services.decision import DecisionRequest
from app.services.simulation import request_from_payload

router = APIRouter(prefix="/policies", tags=["Policies"])


def _meta() -> ResponseMeta:
    return ResponseMeta(request_id=get_log_context().request_id or "unknown")


def _rule_from_payload(payload: RulePayload) -> Rule:
    """Convert an API rule payload into the engine's own shape."""
    return Rule(
        name=payload.name,
        logical_operator=payload.logical_operator,
        conditions=[
            Condition(
                source=one.source,
                path=one.path,
                operator=one.operator,
                value=one.value,
                negate=one.negate,
                description=one.description or "",
                value_source=one.value_source,
                value_path=one.value_path,
            )
            for one in payload.conditions
        ],
        children=[_rule_from_payload(one) for one in payload.children],
        negate=payload.negate,
        description=payload.description or "",
    )


# ---- evaluation (literal segments first; see app/api/__init__.py) ------


@router.post(
    "/evaluate",
    response_model=SuccessResponse[DecisionResponse],
    summary="Decide whether an operation is permitted",
)
async def evaluate_request(
    organization_id: UUID,
    body: EvaluateRequest,
    decisions: DecisionSvc,
    approvals: ApprovalSvc,
    audit: AuditSvc,
    caller: CurrentUserId,
) -> SuccessResponse[DecisionResponse]:
    """Answer one authorization question.

    **Always ``200``, including for a refusal.** A denial is a successful
    decision -- the caller asked whether something was permitted and got
    a correct answer. Answering ``403`` would conflate "you may not do
    that" with "you may not ask", and force every caller to tell an
    authorization *outcome* apart from an authorization *failure* by
    reading a body.

    A ``require_approval`` effect raises the pending obligation before
    returning, so the caller gets an approval id it can point somebody
    at rather than a refusal with no route forward.
    """
    decision, stored = await decisions.decide(
        DecisionRequest(
            organization_id=organization_id,
            subject_type=body.subject_type,
            subject_id=body.subject_id,
            resource_type=body.resource_type,
            action=body.action,
            resource_id=body.resource_id,
            project_id=body.project_id,
            request_id=body.request_id,
            quota_amount=body.quota_amount,
            quota_resource=body.quota_resource,
            context=EvaluationContext(
                subject=dict(body.attributes.subject),
                resource=dict(body.attributes.resource),
                action=dict(body.attributes.action),
                context=dict(body.attributes.context),
                environment=dict(body.attributes.environment),
                organization=dict(body.attributes.organization),
                project=dict(body.attributes.project),
                custom=dict(body.attributes.custom),
            ),
        ),
        actor_id=caller,
        record=body.record,
        consume_quota=body.consume_quota,
    )

    payload = decision.as_dict()
    payload["decision_id"] = str(stored.id) if stored is not None else None

    if decision.effect is PolicyEffect.REQUIRE_APPROVAL:
        raised = await approvals.raise_for_decision(
            organization_id,
            policy_id=(UUID(decision.deciding_policy_id) if decision.deciding_policy_id else None),
            decision_id=stored.id if stored is not None else None,
            subject_type=body.subject_type,
            subject_id=body.subject_id,
            resource_type=body.resource_type,
            resource_id=body.resource_id,
            action=body.action,
            obligations=decision.obligations,
            risk_score=decision.risk_score,
            context=dict(body.attributes.context),
            actor_id=caller,
        )
        payload["obligations"] = {
            **payload["obligations"],
            "approval_id": str(raised.id),
            "approval_expires_at": raised.expires_at.isoformat(),
            "required_levels": raised.required_levels,
        }

    if decision.denied:
        # Audited as DENIED, in its own transaction. This request does
        # not raise, so the entry would survive either way -- but the
        # denial audit path has to be the same one a refusal at
        # authoring time uses, or only one of them gets tested.
        await audit.record_denied(
            organization_id=organization_id,
            action=AuditAction.DECISION_MADE,
            entity_type="decision",
            entity_id=body.resource_id,
            reason=decision.reason,
            actor_id=caller,
            context={
                "subject_id": body.subject_id,
                "resource_type": str(body.resource_type),
                "action": str(body.action),
                "effect": str(decision.effect),
            },
        )

    return SuccessResponse(
        message=("Permitted." if decision.permitted else f"Not permitted: {decision.reason}"),
        data=DecisionResponse.model_validate(payload),
        meta=_meta(),
    )


@router.post(
    "/simulate",
    response_model=SuccessResponse[dict[str, object]],
    summary="Rehearse a policy change",
)
async def simulate_change(
    organization_id: UUID,
    body: SimulateRequest,
    simulations: SimulationSvc,
    caller: CurrentUserId,
) -> SuccessResponse[dict[str, object]]:
    """Run requests against the live catalogue and a candidate one.

    Reports what would **break** rather than only what would differ.
    Anyone can predict what a new deny does; nobody can predict which of
    six thousand requests a week it quietly refuses.
    """
    requests = [
        request_from_payload(one.model_dump(), index=index)
        for index, one in enumerate(body.requests)
    ]

    if not body.store:
        return SuccessResponse(
            message="Simulation complete.",
            data=await simulations.preview(
                organization_id,
                requests=requests,
                draft_policy_ids=body.draft_policy_ids,
                excluded_policy_ids=body.excluded_policy_ids,
            ),
            meta=_meta(),
        )

    stored = await simulations.run(
        organization_id,
        label=body.label,
        requests=requests,
        kind=body.kind,
        draft_policy_ids=body.draft_policy_ids,
        excluded_policy_ids=body.excluded_policy_ids,
        actor_id=caller,
    )
    return SuccessResponse(
        message=stored.summary or "Simulation complete.",
        data={
            "simulation_id": str(stored.id),
            **(stored.results or {}),
        },
        meta=_meta(),
    )


@router.get(
    "/simulations",
    response_model=SuccessResponse[list[SimulationResponse]],
    summary="List stored simulations",
)
async def list_simulations(
    organization_id: UUID,
    simulations: SimulationSvc,
    caller: CurrentUserId,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
) -> SuccessResponse[list[SimulationResponse]]:
    """Stored simulations, most recent first."""
    del caller
    rows = await simulations.list_simulations(organization_id, limit=limit)
    return SuccessResponse(
        message=f"Found {len(rows)} simulations.",
        data=[SimulationResponse.model_validate(one) for one in rows],
        meta=_meta(),
    )


@router.get(
    "/conflicts",
    response_model=SuccessResponse[list[dict[str, object]]],
    summary="Detect contradicting policies",
)
async def detect_conflicts(
    organization_id: UUID, simulations: SimulationSvc, caller: CurrentUserId
) -> SuccessResponse[list[dict[str, object]]]:
    """Find policy pairs that could contradict each other.

    Reports *potential* conflicts. Proving two rule trees can both be
    satisfied is a satisfiability problem, so this surfaces the pairs
    worth a human look rather than claiming more certainty than the
    analysis has.
    """
    del caller
    conflicts = await simulations.detect_conflicts(organization_id)
    return SuccessResponse(
        message=f"{len(conflicts)} potential conflict(s) detected.",
        data=conflicts,
        meta=_meta(),
    )


@router.post(
    "/publish",
    response_model=SuccessResponse[PolicyResponse],
    summary="Compile and publish a policy",
)
async def publish_policy(
    organization_id: UUID,
    policy_id: UUID,
    body: PublishRequest,
    policies: PolicySvc,
    audit: AuditSvc,
    caller: CurrentUserId,
) -> SuccessResponse[PolicyResponse]:
    """Make a policy's authored rules live.

    The only operation that changes live authorization. Compilation
    validates first, so a policy that cannot be evaluated is refused
    here -- while somebody is waiting for an answer -- rather than at
    03:00 inside a decision nobody is watching.
    """
    published = await policies.publish(
        organization_id,
        policy_id,
        change_summary=body.change_summary,
        breaking=body.breaking,
        feature=body.feature,
        actor_id=caller,
    )
    await audit.record(
        organization_id=organization_id,
        action=AuditAction.POLICY_CHANGED,
        entity_type="policy",
        entity_id=published.slug,
        actor_id=caller,
        after={"version": published.semantic_version, "status": str(published.status)},
        context={"published": True, "change_summary": body.change_summary},
    )
    return SuccessResponse(
        message=f"Policy {published.slug!r} published as version {published.semantic_version}.",
        data=PolicyResponse.model_validate(published),
        meta=_meta(),
    )


@router.post(
    "/rollback",
    response_model=SuccessResponse[PolicyResponse],
    summary="Restore an earlier published version",
)
async def rollback_policy(
    organization_id: UUID,
    policy_id: UUID,
    body: RollbackRequest,
    policies: PolicySvc,
    audit: AuditSvc,
    caller: CurrentUserId,
) -> SuccessResponse[PolicyResponse]:
    """Restore a stored version.

    Refuses a version whose checksum no longer matches: that content was
    changed by something that bypassed publishing, and restoring it would
    make that change live.
    """
    restored = await policies.rollback(
        organization_id, policy_id, version=body.version, actor_id=caller
    )
    await audit.record(
        organization_id=organization_id,
        action=AuditAction.POLICY_CHANGED,
        entity_type="policy",
        entity_id=restored.slug,
        actor_id=caller,
        after={"version": restored.semantic_version},
        context={"rolled_back": True},
    )
    return SuccessResponse(
        message=f"Policy {restored.slug!r} rolled back to version {restored.semantic_version}.",
        data=PolicyResponse.model_validate(restored),
        meta=_meta(),
    )


@router.post(
    "/guardrails/seed",
    response_model=SuccessResponse[list[PolicyResponse]],
    summary="Install the platform's baseline guardrails",
)
async def seed_guardrails(
    organization_id: UUID, policies: PolicySvc, audit: AuditSvc, caller: CurrentUserId
) -> SuccessResponse[list[PolicyResponse]]:
    """Install the shipped guardrails, published.

    Idempotent by slug, so re-running adds only what is missing. Seeded
    published rather than draft: a guardrail sitting in draft is a
    guardrail that is not guarding.
    """
    created = await policies.seed_guardrails(organization_id, actor_id=caller)
    await audit.record(
        organization_id=organization_id,
        action=AuditAction.ADMINISTRATIVE,
        entity_type="guardrails",
        actor_id=caller,
        context={"seeded": [one.slug for one in created]},
    )
    return SuccessResponse(
        message=f"Seeded {len(created)} guardrail(s).",
        data=[PolicyResponse.model_validate(one) for one in created],
        meta=_meta(),
    )


# ---- catalogue --------------------------------------------------------


@router.get(
    "",
    response_model=SuccessResponse[list[PolicyResponse]],
    summary="List policies",
)
async def list_policies(
    organization_id: UUID,
    policies: PolicySvc,
    caller: CurrentUserId,
    policy_status: PolicyStatus | None = None,
    category: PolicyCategory | None = None,
    policy_type: PolicyType | None = None,
    limit: Annotated[int, Query(ge=1, le=1_000)] = 200,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> SuccessResponse[list[PolicyResponse]]:
    """Policies for one organization, highest priority first."""
    del caller
    rows = await policies.list_policies(
        organization_id,
        status=policy_status,
        category=category,
        policy_type=policy_type,
        limit=limit,
        offset=offset,
    )
    return SuccessResponse(
        message=f"Found {len(rows)} policies.",
        data=[PolicyResponse.model_validate(one) for one in rows],
        meta=_meta(),
    )


@router.post(
    "",
    response_model=SuccessResponse[PolicyResponse],
    status_code=status.HTTP_201_CREATED,
    summary="Create a policy",
)
async def create_policy(
    organization_id: UUID,
    body: PolicyCreateRequest,
    policies: PolicySvc,
    audit: AuditSvc,
    caller: CurrentUserId,
) -> SuccessResponse[PolicyResponse]:
    """Author a new policy, always in DRAFT.

    There is no way to create one already published: that would let the
    review pipeline be bypassed by one extra field.
    """
    created = await policies.create_policy(
        organization_id,
        slug=body.slug,
        name=body.name,
        effect=body.effect,
        category=body.category,
        policy_type=body.policy_type,
        description=body.description,
        priority=body.priority,
        subject_types=[str(one) for one in body.subject_types],
        resource_types=[str(one) for one in body.resource_types],
        actions=[str(one) for one in body.actions],
        obligations=body.obligations,
        risk_weight=body.risk_weight,
        tags=body.tags,
        actor_id=caller,
    )
    await audit.record(
        organization_id=organization_id,
        action=AuditAction.POLICY_CHANGED,
        entity_type="policy",
        entity_id=created.slug,
        actor_id=caller,
        after={"effect": str(created.effect), "status": str(created.status)},
    )
    return SuccessResponse(
        message=f"Policy {created.slug!r} created in draft.",
        data=PolicyResponse.model_validate(created),
        meta=_meta(),
    )


@router.get(
    "/{policy_id}",
    response_model=SuccessResponse[PolicyResponse],
    summary="Get one policy",
)
async def get_policy(
    organization_id: UUID, policy_id: UUID, policies: PolicySvc, caller: CurrentUserId
) -> SuccessResponse[PolicyResponse]:
    """One policy by id."""
    del caller
    found = await policies.get_policy(organization_id, policy_id)
    return SuccessResponse(
        message="Policy retrieved.",
        data=PolicyResponse.model_validate(found),
        meta=_meta(),
    )


@router.put(
    "/{policy_id}",
    response_model=SuccessResponse[PolicyResponse],
    summary="Update a policy",
)
async def update_policy(
    organization_id: UUID,
    policy_id: UUID,
    body: PolicyUpdateRequest,
    policies: PolicySvc,
    audit: AuditSvc,
    caller: CurrentUserId,
) -> SuccessResponse[PolicyResponse]:
    """Change a policy's metadata.

    Does not publish. Live decisions keep using the last published
    content until somebody publishes deliberately.
    """
    changes = body.model_dump(exclude_unset=True, exclude_none=True)
    for key in ("subject_types", "resource_types", "actions"):
        if key in changes:
            changes[key] = [str(one) for one in changes[key]]

    updated = await policies.update_policy(
        organization_id, policy_id, changes=changes, actor_id=caller
    )
    await audit.record(
        organization_id=organization_id,
        action=AuditAction.POLICY_CHANGED,
        entity_type="policy",
        entity_id=updated.slug,
        actor_id=caller,
        after={"fields": sorted(changes)},
    )
    return SuccessResponse(
        message=(f"Policy {updated.slug!r} updated. Publish to make the change live."),
        data=PolicyResponse.model_validate(updated),
        meta=_meta(),
    )


@router.delete(
    "/{policy_id}",
    response_model=SuccessResponse[dict[str, bool]],
    summary="Archive a policy",
)
async def delete_policy(
    organization_id: UUID,
    policy_id: UUID,
    policies: PolicySvc,
    audit: AuditSvc,
    caller: CurrentUserId,
) -> SuccessResponse[dict[str, bool]]:
    """Archive a policy.

    Archived rather than deleted: a policy that produced ten thousand
    decisions is the explanation for all of them, and removing the row
    makes every one of those traces unreadable.
    """
    found = await policies.get_policy(organization_id, policy_id)
    await policies.delete_policy(organization_id, policy_id, actor_id=caller)
    await audit.record(
        organization_id=organization_id,
        action=AuditAction.POLICY_CHANGED,
        entity_type="policy",
        entity_id=found.slug,
        actor_id=caller,
        context={"archived": True},
    )
    return SuccessResponse(
        message=f"Policy {found.slug!r} archived.",
        data={"archived": True},
        meta=_meta(),
    )


@router.put(
    "/{policy_id}/rules",
    response_model=SuccessResponse[dict[str, int]],
    summary="Replace a policy's rule tree",
)
async def set_rules(
    organization_id: UUID,
    policy_id: UUID,
    body: RuleTreeRequest,
    policies: PolicySvc,
    audit: AuditSvc,
    caller: CurrentUserId,
) -> SuccessResponse[dict[str, int]]:
    """Replace the authored rules with one tree.

    Replaces rather than merges: half a boolean tree is a different tree,
    and reconciling node by node would produce trees nobody authored.
    """
    written = await policies.set_rule_tree(
        organization_id, policy_id, _rule_from_payload(body.rule), actor_id=caller
    )
    await audit.record(
        organization_id=organization_id,
        action=AuditAction.RULE_CHANGED,
        entity_type="policy",
        entity_id=str(policy_id),
        actor_id=caller,
        context={"conditions": written},
    )
    return SuccessResponse(
        message=f"{written} condition(s) written. Publish to make them live.",
        data={"conditions": written},
        meta=_meta(),
    )


@router.post(
    "/{policy_id}/transition",
    response_model=SuccessResponse[PolicyResponse],
    summary="Move a policy through its lifecycle",
)
async def transition_policy(
    organization_id: UUID,
    policy_id: UUID,
    body: TransitionRequest,
    policies: PolicySvc,
    caller: CurrentUserId,
) -> SuccessResponse[PolicyResponse]:
    """Advance or return a policy's lifecycle state.

    A draft cannot move straight to published: the review states exist so
    somebody other than the author looks at a rule before it starts
    refusing people's work.
    """
    moved = await policies.transition(
        organization_id, policy_id, target=body.target, actor_id=caller
    )
    return SuccessResponse(
        message=f"Policy {moved.slug!r} is now {moved.status!s}.",
        data=PolicyResponse.model_validate(moved),
        meta=_meta(),
    )


@router.get(
    "/{policy_id}/versions",
    response_model=SuccessResponse[list[PolicyVersionResponse]],
    summary="List a policy's published versions",
)
async def list_versions(
    organization_id: UUID,
    policy_id: UUID,
    policies: PolicySvc,
    caller: CurrentUserId,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
) -> SuccessResponse[list[PolicyVersionResponse]]:
    """Published versions, newest first."""
    del caller
    rows = await policies.versions(organization_id, policy_id, limit=limit)
    return SuccessResponse(
        message=f"Found {len(rows)} versions.",
        data=[PolicyVersionResponse.model_validate(one) for one in rows],
        meta=_meta(),
    )


@router.get(
    "/{policy_id}/verify",
    response_model=SuccessResponse[dict[str, object]],
    summary="Verify a policy's integrity",
)
async def verify_policy(
    organization_id: UUID, policy_id: UUID, policies: PolicySvc, caller: CurrentUserId
) -> SuccessResponse[dict[str, object]]:
    """Check a live policy against the digest of its published version.

    A mismatch means the stored rule changed without going through
    publishing -- which for the service that authorizes every protected
    operation is the one tampering signal worth having.
    """
    del caller
    result = await policies.verify(organization_id, policy_id)
    return SuccessResponse(
        message=(
            "Integrity verified."
            if result["verified"]
            else f"Integrity check failed: {result.get('reason')}"
        ),
        data=result,
        meta=_meta(),
    )


__all__ = ["router"]
