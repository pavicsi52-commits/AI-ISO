"""``/ai/recommendations``, ``/ai/reports``, ``/ai/feedback``,
``/ai/memory``, and ``/ai/statistics``.
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter
from shared_core.logging.context import get_log_context

from app.api.deps import (
    CurrentUserId,
    DbSession,
    FeedbackSvc,
    MemoryDep,
    RecommendationSvc,
    ReportSvc,
    StatisticsSvc,
)
from app.models.ai_memory import AiMemory
from app.models.ai_recommendation import AiRecommendation
from app.models.ai_report import AiReport
from app.models.enums import AiReportType, RecommendationType
from app.repositories.ai_memory import AiMemoryRepository
from app.schemas.insight import (
    AiReportRequest,
    AiReportResponse,
    AiStatisticsResponse,
    FeedbackRequest,
    FeedbackResponse,
    MemoryCreateRequest,
    MemoryResponse,
    RecommendationDecisionRequest,
    RecommendationRequest,
    RecommendationResponse,
)
from app.schemas.response import ResponseMeta, SuccessResponse

router = APIRouter(prefix="/ai", tags=["AI Insights"])

_RECOMMENDATION_BRIEFS: dict[RecommendationType, str] = {
    RecommendationType.PLAYBOOK: "Recommend the most suitable automation playbook.",
    RecommendationType.WORKFLOW: "Recommend a workflow to handle this.",
    RecommendationType.AUTOMATION: "Recommend how to automate this safely.",
    RecommendationType.REMEDIATION: "Recommend concrete remediation steps.",
    RecommendationType.ROOT_CAUSE: "Identify the most likely root cause and the evidence for it.",
    RecommendationType.CAPACITY: "Recommend capacity changes and when they will be needed.",
    RecommendationType.CONFIGURATION: "Recommend configuration changes and their risk.",
    RecommendationType.RISK: "Assess the risk of the proposed change.",
}


def _meta() -> ResponseMeta:
    return ResponseMeta(request_id=get_log_context().request_id or "unknown")


def recommendation_to_response(record: AiRecommendation) -> RecommendationResponse:
    """Map a recommendation row onto its own response schema."""
    return RecommendationResponse(
        id=record.id,
        organization_id=record.organization_id,
        conversation_id=record.conversation_id,
        recommendation_type=record.recommendation_type,
        title=record.title,
        body=record.body,
        rationale=record.rationale,
        citations=record.citations,
        confidence=record.confidence,
        status=record.status,
        decided_by=record.decided_by,
    )


def report_to_response(record: AiReport) -> AiReportResponse:
    """Map a report row onto its own response schema."""
    return AiReportResponse(
        id=record.id,
        organization_id=record.organization_id,
        conversation_id=record.conversation_id,
        report_type=record.report_type,
        title=record.title,
        body=record.body,
        parameters=record.parameters,
        citations=record.citations,
        generated_by=record.generated_by,
        generated_at=record.generated_at,
    )


def memory_to_response(record: AiMemory) -> MemoryResponse:
    """Map a memory row onto its own response schema."""
    return MemoryResponse(
        id=record.id,
        scope=record.scope,
        scope_reference=record.scope_reference,
        key=record.key,
        value=record.value,
        importance=record.importance,
        expires_at=record.expires_at,
    )


@router.post(
    "/recommendations", response_model=SuccessResponse[RecommendationResponse], status_code=201
)
async def generate_recommendation(
    body: RecommendationRequest,
    reports: ReportSvc,
    recommendations: RecommendationSvc,
    caller: CurrentUserId,
) -> SuccessResponse[RecommendationResponse]:
    """Generate a grounded recommendation for review.

    Reuses the report generator to produce the prose, so a
    recommendation carries the same citations a report would -- an
    operator asked to act on it can see what it was based on.

    Raises:
        AIError: If every model provider in the fallback chain failed.
    """
    brief = _RECOMMENDATION_BRIEFS[body.recommendation_type]
    generated = await reports.generate(
        organization_id=body.organization_id,
        project_id=body.project_id,
        report_type=AiReportType.NATURAL_LANGUAGE,
        subject=f"{brief}\n\nContext: {body.subject}",
        conversation_id=body.conversation_id,
        generated_by=caller,
    )
    recommendation = await recommendations.create(
        organization_id=body.organization_id,
        project_id=body.project_id,
        conversation_id=body.conversation_id,
        recommendation_type=body.recommendation_type,
        title=body.subject[:200],
        body=generated.body,
        rationale=brief,
        citations=generated.citations,
    )
    return SuccessResponse(
        message="Recommendation generated.",
        data=recommendation_to_response(recommendation),
        meta=_meta(),
    )


@router.get("/recommendations", response_model=SuccessResponse[list[RecommendationResponse]])
async def list_recommendations(
    organization_id: UUID, recommendations: RecommendationSvc, _caller: CurrentUserId
) -> SuccessResponse[list[RecommendationResponse]]:
    """Every recommendation for an organization."""
    records = await recommendations.list_for_org(organization_id)
    return SuccessResponse(
        message="Recommendations retrieved.",
        data=[recommendation_to_response(record) for record in records],
        meta=_meta(),
    )


@router.post(
    "/recommendations/{recommendation_id}/decide",
    response_model=SuccessResponse[RecommendationResponse],
)
async def decide_recommendation(
    recommendation_id: UUID,
    body: RecommendationDecisionRequest,
    recommendations: RecommendationSvc,
    caller: CurrentUserId,
) -> SuccessResponse[RecommendationResponse]:
    """Accept or reject a proposed recommendation.

    Raises:
        NotFoundError: If no such recommendation exists.
        ConflictError: If it has already been decided.
    """
    record = await recommendations.decide(recommendation_id, accept=body.accept, decided_by=caller)
    return SuccessResponse(
        message="Recommendation decided.",
        data=recommendation_to_response(record),
        meta=_meta(),
    )


@router.post("/reports", response_model=SuccessResponse[AiReportResponse], status_code=201)
async def generate_report(
    body: AiReportRequest, reports: ReportSvc, caller: CurrentUserId
) -> SuccessResponse[AiReportResponse]:
    """Generate an AI-written report grounded in retrieved context.

    Raises:
        AIError: If every model provider in the fallback chain failed.
    """
    report = await reports.generate(
        organization_id=body.organization_id,
        project_id=body.project_id,
        report_type=body.report_type,
        subject=body.subject,
        conversation_id=body.conversation_id,
        parameters=body.parameters,
        generated_by=caller,
    )
    return SuccessResponse(
        message="Report generated.", data=report_to_response(report), meta=_meta()
    )


@router.get("/reports", response_model=SuccessResponse[list[AiReportResponse]])
async def list_reports(
    organization_id: UUID,
    reports: ReportSvc,
    _caller: CurrentUserId,
    report_type: AiReportType | None = None,
) -> SuccessResponse[list[AiReportResponse]]:
    """Previously generated reports, optionally filtered by type."""
    records = await reports.list_for_org(organization_id, report_type=report_type)
    return SuccessResponse(
        message="Reports retrieved.",
        data=[report_to_response(record) for record in records],
        meta=_meta(),
    )


@router.post("/feedback", response_model=SuccessResponse[FeedbackResponse], status_code=201)
async def submit_feedback(
    body: FeedbackRequest, feedback: FeedbackSvc, caller: CurrentUserId
) -> SuccessResponse[FeedbackResponse]:
    """Rate an assistant turn."""
    record = await feedback.submit(
        organization_id=body.organization_id,
        project_id=body.project_id,
        message_id=body.message_id,
        rating=body.rating,
        comment=body.comment,
        submitted_by=caller,
    )
    return SuccessResponse(
        message="Feedback recorded.",
        data=FeedbackResponse(
            id=record.id,
            message_id=record.message_id,
            rating=record.rating,
            comment=record.comment,
            submitted_by=record.submitted_by,
        ),
        meta=_meta(),
    )


@router.post("/memory", response_model=SuccessResponse[MemoryResponse], status_code=201)
async def remember(
    body: MemoryCreateRequest, memory: MemoryDep, _caller: CurrentUserId
) -> SuccessResponse[MemoryResponse]:
    """Store or update one remembered fact."""
    record = await memory.remember(
        organization_id=body.organization_id,
        project_id=body.project_id,
        scope=body.scope,
        scope_reference=body.scope_reference,
        key=body.key,
        value=body.value,
        importance=body.importance,
        expires_at=body.expires_at,
    )
    return SuccessResponse(message="Memory stored.", data=memory_to_response(record), meta=_meta())


@router.get("/memory", response_model=SuccessResponse[list[MemoryResponse]])
async def list_memory(
    organization_id: UUID, session: DbSession, _caller: CurrentUserId
) -> SuccessResponse[list[MemoryResponse]]:
    """Every remembered fact for an organization."""
    records = await AiMemoryRepository(session).list_for_org(organization_id)
    return SuccessResponse(
        message="Memories retrieved.",
        data=[memory_to_response(record) for record in records],
        meta=_meta(),
    )


@router.get("/statistics", response_model=SuccessResponse[AiStatisticsResponse])
async def get_statistics(
    organization_id: UUID,
    statistics: StatisticsSvc,
    _caller: CurrentUserId,
    recompute: bool = False,
) -> SuccessResponse[AiStatisticsResponse]:
    """An organization's own AI analytics rollup."""
    snapshot = (
        await statistics.recompute(organization_id)
        if recompute
        else await statistics.get_for_org(organization_id)
    )
    return SuccessResponse(
        message="AI statistics retrieved.",
        data=AiStatisticsResponse(
            total_conversations=snapshot.total_conversations,
            total_messages=snapshot.total_messages,
            total_tool_calls=snapshot.total_tool_calls,
            total_prompt_tokens=snapshot.total_prompt_tokens,
            total_completion_tokens=snapshot.total_completion_tokens,
            estimated_cost_usd=snapshot.estimated_cost_usd,
            average_latency_ms=snapshot.average_latency_ms,
            positive_feedback_rate=snapshot.positive_feedback_rate,
            recommendation_acceptance_rate=snapshot.recommendation_acceptance_rate,
            tool_usage=snapshot.tool_usage,
            agent_usage=snapshot.agent_usage,
            model_usage=snapshot.model_usage,
            computed_at=snapshot.computed_at,
        ),
        meta=_meta(),
    )


__all__ = [
    "memory_to_response",
    "recommendation_to_response",
    "report_to_response",
    "router",
]
