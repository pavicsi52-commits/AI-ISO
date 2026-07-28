"""Natural-language report generation ("REPORT GENERATION").

Every report type here is genuinely model-written prose grounded in
retrieved context, not a template with numbers substituted in -- that
is the whole point of an *AI* report and the reason this lives in this
service rather than in a reporting service.

Grounding matters: the retrieved passages are supplied as context and
the citations are stored on the report, so a reader can check what the
prose was based on instead of taking it on faith.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from app.clients.base import ChatMessage
from app.clients.registry import ModelRegistry
from app.events.ai_events import ReportGeneratedEvent
from app.guardrails.engine import screen_model_output
from app.models.ai_report import AiReport
from app.models.enums import AiReportType, MessageRole, ModelProvider, RetrievalStrategy
from app.rag.pipeline import RagPipeline
from app.repositories.ai_report import AiReportRepository
from app.types import EventPublisher

_REPORT_BRIEFS: dict[AiReportType, str] = {
    AiReportType.EXECUTIVE: (
        "Write a concise executive summary for a non-technical leadership audience. "
        "Lead with impact and risk, avoid jargon, and keep it under 400 words."
    ),
    AiReportType.OPERATIONAL: (
        "Write an operational report for the on-call engineering team. Be specific "
        "about systems, symptoms, and next actions."
    ),
    AiReportType.INCIDENT_SUMMARY: (
        "Summarise the incident: what happened, when, what was affected, what was "
        "done, and what remains open."
    ),
    AiReportType.HEALTH_SUMMARY: (
        "Summarise current infrastructure health, calling out anything degraded or "
        "trending badly."
    ),
    AiReportType.CAPACITY: (
        "Assess capacity: current utilisation, growth trend, and where headroom runs " "out first."
    ),
    AiReportType.AUTOMATION: (
        "Report on automation activity: what ran, what succeeded or failed, and where "
        "manual effort remains."
    ),
    AiReportType.VALIDATION: (
        "Report on validation results: what passed, what failed, and what the failures "
        "have in common."
    ),
    AiReportType.COMPLIANCE: (
        "Report on compliance posture: which controls are met, which are not, and the "
        "exposure from each gap."
    ),
    AiReportType.NATURAL_LANGUAGE: (
        "Answer the request directly in clear prose, grounded in the supplied context."
    ),
}
"""One brief per report type.

Kept as data rather than nine near-identical methods: the types differ
only in audience and emphasis, and a table makes that obvious and easy
to tune.
"""


class AiReportService:
    """Generates and lists AI-written reports."""

    def __init__(
        self,
        reports: AiReportRepository,
        rag: RagPipeline,
        registry: ModelRegistry,
        *,
        default_provider: ModelProvider,
        default_model: str,
        rag_top_k: int,
        publish_event: EventPublisher,
    ) -> None:
        self._reports = reports
        self._rag = rag
        self._registry = registry
        self._publish_event = publish_event
        self._default_provider = default_provider
        self._default_model = default_model
        self._rag_top_k = rag_top_k

    async def list_for_org(
        self, organization_id: UUID, *, report_type: AiReportType | None = None
    ) -> list[AiReport]:
        """Previously generated reports, optionally filtered by type."""
        if report_type is not None:
            return await self._reports.list_by_type(organization_id, report_type)
        return await self._reports.list_for_org(organization_id)

    async def generate(
        self,
        *,
        organization_id: UUID,
        project_id: UUID | None,
        report_type: AiReportType,
        subject: str,
        conversation_id: UUID | None = None,
        parameters: dict[str, Any] | None = None,
        generated_by: UUID | None = None,
    ) -> AiReport:
        """Generate one report, grounded in retrieved context.

        Raises:
            AIError: If every model provider in the fallback chain failed.
        """
        passages = await self._rag.retrieve(
            organization_id,
            subject,
            top_k=self._rag_top_k,
            strategy=RetrievalStrategy.HYBRID,
            conversation_id=conversation_id,
        )
        context = "\n\n".join(
            f"[{index + 1}] {passage.document_title}\n{passage.content}"
            for index, passage in enumerate(passages)
        )

        brief = _REPORT_BRIEFS[report_type]
        instruction = (
            f"{brief}\n\nSubject: {subject}\n\n"
            + (f"Context:\n{context}\n\n" if context else "")
            + "If the context does not support a claim, say so rather than inferring it."
        )

        completion = await self._registry.chat_with_fallback(
            [
                ChatMessage(
                    role=MessageRole.SYSTEM,
                    content=(
                        "You write factual infrastructure reports. Ground every claim in "
                        "the supplied context and never invent specifics."
                    ),
                ),
                ChatMessage(role=MessageRole.USER, content=instruction),
            ],
            provider=self._default_provider,
            model=self._default_model,
        )
        screened = screen_model_output(completion.content)

        report = await self._reports.create(
            AiReport(
                organization_id=organization_id,
                project_id=project_id,
                conversation_id=conversation_id,
                report_type=report_type,
                title=subject,
                body=screened.text,
                parameters=parameters or {},
                citations=[passage.as_citation() for passage in passages],
                generated_by=generated_by,
                generated_at=datetime.now(UTC),
            )
        )
        await self._publish_event(
            ReportGeneratedEvent(
                source_service="ai-assistant-service",
                payload={
                    "report_id": str(report.id),
                    "report_type": str(report_type),
                    "title": subject,
                },
            )
        )
        return report


__all__ = ["AiReportService"]
