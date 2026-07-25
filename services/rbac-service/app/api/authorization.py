"""``POST /authorization/evaluate``. Per docs/032 REST list.

Requires only authentication, not an additional permission check --
this endpoint *is* the authorization primitive every other check in
this package (including :mod:`app.authorization.guard`'s own
self-protection) is built from, so gating it behind itself would be
circular. Other AI-IOS services call this endpoint directly (with
their own service-account identity) to ask "can user X do Y."
"""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, Request
from shared_core.logging.context import get_log_context

from app.api.deps import CurrentUserId, EvaluatorSvc
from app.schemas.authorization import EvaluateRequest, EvaluateResponse
from app.schemas.response import ResponseMeta, SuccessResponse

router = APIRouter(prefix="/authorization", tags=["Authorization"])


def _meta() -> ResponseMeta:
    return ResponseMeta(request_id=get_log_context().request_id or "unknown")


@router.post("/evaluate", response_model=SuccessResponse[EvaluateResponse])
async def evaluate(
    body: EvaluateRequest, evaluator: EvaluatorSvc, _caller: CurrentUserId, request: Request
) -> SuccessResponse[EvaluateResponse]:
    """Decide whether ``body.user_id`` may perform ``body.action`` on
    ``body.resource_type``[/``body.resource_id``] ("Authorization Evaluation").
    """
    result = await evaluator.evaluate(
        user_id=body.user_id,
        action=body.action,
        resource_type=body.resource_type,
        resource_id=body.resource_id,
        organization_id=body.organization_id,
        project_id=body.project_id,
        context=body.context,
        ip_address=request.client.host if request.client else None,
    )
    data = EvaluateResponse(
        decision=result.decision,
        reason=result.reason,
        matched_permission_code=result.matched_permission_code,
        matched_policy_code=result.matched_policy_code,
        evaluated_at=datetime.now(UTC),
    )
    return SuccessResponse(message="Authorization evaluated.", data=data, meta=_meta())


__all__ = ["router"]
