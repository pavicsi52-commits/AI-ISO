"""Report generation -- this service's own central pipeline.

One generation run flows through, in this order:

1. Resolve the job and its (approved) template.
2. Bind parameters and parse filters.
3. Open an execution row, so a crash mid-render is still visible.
4. Render the definition (network fetches concurrent, bounded).
5. Export to the requested format(s) and persist each artifact.
6. Record history, publish the outcome event, notify.

**Every database write is sequential.** Only the renderer's data-source
fetches overlap, and those touch no session -- an ``AsyncSession`` is
not safe for concurrent use even for reads, the rule every AI-IOS
service has followed since ``services/validation-service``.

**A failed run is persisted, not swallowed.** The execution row is
created *before* rendering starts and updated with the failure, so a
report that died halfway leaves a record explaining why rather than
vanishing.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from shared_core.exceptions.validation import ValidationError
from shared_core.logging.logger import get_logger

from app.events.report_events import (
    SOURCE_SERVICE,
    ReportFailedEvent,
    ReportGeneratedEvent,
)
from app.export.engine import ExportedArtifact, export, export_pdf_protected
from app.filters.engine import parse_clauses
from app.models.enums import ExportFormat, ReportExecutionStatus
from app.models.report_execution import ReportExecution
from app.models.report_export import ReportExport
from app.models.report_history import ReportHistory
from app.models.report_job import ReportJob
from app.parameters.binding import bind
from app.renderer.document import RenderedReport
from app.renderer.engine import ReportRenderer
from app.repositories.report_execution import ReportExecutionRepository
from app.repositories.report_export import ReportExportRepository
from app.repositories.report_history import ReportHistoryRepository
from app.repositories.report_job import ReportJobRepository
from app.services.template import ReportTemplateService, validate_definition
from app.types import EventPublisher

logger = get_logger("app.services.generation")


@dataclass(slots=True)
class GenerationResult:
    """Everything one generation run produced."""

    execution: ReportExecution
    report: RenderedReport | None
    exports: list[ReportExport] = field(default_factory=list)
    artifacts: list[ExportedArtifact] = field(default_factory=list)

    @property
    def succeeded(self) -> bool:
        """Whether the run completed successfully."""
        return self.execution.status == ReportExecutionStatus.SUCCEEDED

    @property
    def degraded_sections(self) -> list[str]:
        """Sections that could not be resolved but did not fail the run."""
        return [section.key for section in (self.report.failed_sections if self.report else [])]


class ReportGenerationService:
    """Runs a report job end to end."""

    def __init__(
        self,
        jobs: ReportJobRepository,
        executions: ReportExecutionRepository,
        exports: ReportExportRepository,
        history: ReportHistoryRepository,
        templates: ReportTemplateService,
        renderer: ReportRenderer,
        *,
        publish_event: EventPublisher,
    ) -> None:
        self._jobs = jobs
        self._executions = executions
        self._exports = exports
        self._history = history
        self._templates = templates
        self._renderer = renderer
        self._publish_event = publish_event

    async def generate(
        self,
        job: ReportJob,
        *,
        export_formats: list[ExportFormat] | None = None,
        parameter_overrides: dict[str, Any] | None = None,
        filter_overrides: list[dict[str, Any]] | None = None,
        triggered_by: UUID | None = None,
        schedule_id: UUID | None = None,
        signed_by: str | None = None,
        pdf_password: str | None = None,
    ) -> GenerationResult:
        """Generate one report and persist every artifact.

        Overrides are merged over the job's stored values rather than
        replacing them, so an ad-hoc run can change one parameter
        without having to restate the whole set.

        Raises:
            NotFoundError: If the job's template does not exist.
            ConflictError: If the template version is not approved.
            ValidationError: If parameters or filters are invalid.
        """
        started = time.monotonic()
        formats = export_formats or [
            (
                job.default_format
                if isinstance(job.default_format, ExportFormat)
                else ExportFormat(job.default_format)
            )
        ]

        if job.template_id is None:
            raise ValidationError(f"Report {job.name!r} has no template and cannot be generated.")
        template = await self._templates.resolve_for_execution(job.template_id)
        definition = validate_definition(template.definition)
        declared = await self._templates.list_parameters(template.id)

        supplied = {**job.parameter_values, **(parameter_overrides or {})}
        parameters = bind(declared, supplied)
        clauses = parse_clauses(filter_overrides if filter_overrides is not None else job.filters)

        execution = await self._executions.create(
            ReportExecution(
                organization_id=job.organization_id,
                project_id=job.project_id,
                job_id=job.id,
                schedule_id=schedule_id,
                status=ReportExecutionStatus.RUNNING,
                parameter_values={key: str(value) for key, value in parameters.values.items()},
                filters=filter_overrides if filter_overrides is not None else job.filters,
                triggered_by=triggered_by,
                started_at=datetime.now(UTC),
            )
        )

        try:
            report = await self._renderer.render(
                definition,
                organization_id=job.organization_id,
                parameters=parameters,
                filters=clauses,
                project_id=job.project_id,
            )
        except Exception as exc:
            await self._fail(execution, job, str(exc), started)
            raise

        artifacts = [
            (
                export_pdf_protected(report, signed_by=signed_by, password=pdf_password)
                if export_format is ExportFormat.PDF and (signed_by or pdf_password)
                else export(report, export_format)
            )
            for export_format in formats
        ]

        stored: list[ReportExport] = []
        for artifact in artifacts:
            stored.append(
                await self._exports.create(
                    ReportExport(
                        organization_id=job.organization_id,
                        project_id=job.project_id,
                        execution_id=execution.id,
                        export_format=artifact.export_format,
                        filename=artifact.filename,
                        content_type=artifact.content_type,
                        size_bytes=artifact.size_bytes,
                        checksum_sha256=artifact.checksum_sha256,
                        content=artifact.content,
                    )
                )
            )

        execution.status = ReportExecutionStatus.SUCCEEDED
        execution.row_count = report.total_rows
        execution.section_count = len(report.sections)
        execution.duration_ms = (time.monotonic() - started) * 1000
        execution.finished_at = datetime.now(UTC)
        execution = await self._executions.update(execution)

        degraded = [section.key for section in report.failed_sections]
        await self._record_history(
            job,
            execution,
            event="generated",
            summary=(
                f"Generated {report.total_rows:,} row(s) across "
                f"{len(report.sections)} section(s)."
            ),
            details={
                "formats": [str(artifact.export_format) for artifact in artifacts],
                "degraded_sections": degraded,
            },
            actor_id=triggered_by,
        )
        await self._publish_event(
            ReportGeneratedEvent(
                source_service=SOURCE_SERVICE,
                payload={
                    "execution_id": str(execution.id),
                    "job_id": str(job.id),
                    "row_count": report.total_rows,
                    "degraded_sections": degraded,
                },
            )
        )
        if degraded:
            logger.warning(
                "Report generated with degraded sections.",
                extra={"extra_fields": {"job": str(job.id), "sections": degraded}},
            )
        return GenerationResult(
            execution=execution, report=report, exports=stored, artifacts=artifacts
        )

    async def _fail(
        self, execution: ReportExecution, job: ReportJob, reason: str, started: float
    ) -> None:
        """Persist a failed run, then let the caller re-raise."""
        execution.status = ReportExecutionStatus.FAILED
        execution.error_message = reason
        execution.duration_ms = (time.monotonic() - started) * 1000
        execution.finished_at = datetime.now(UTC)
        await self._executions.update(execution)
        await self._record_history(
            job,
            execution,
            event="failed",
            summary=f"Generation failed: {reason}"[:1024],
            details={"error": reason},
            actor_id=execution.triggered_by,
        )
        await self._publish_event(
            ReportFailedEvent(
                source_service=SOURCE_SERVICE,
                payload={
                    "execution_id": str(execution.id),
                    "job_id": str(job.id),
                    "error": reason,
                },
            )
        )

    async def _record_history(
        self,
        job: ReportJob,
        execution: ReportExecution | None,
        *,
        event: str,
        summary: str,
        details: dict[str, Any],
        actor_id: UUID | None,
    ) -> ReportHistory:
        """Append one user-visible history entry."""
        return await self._history.create(
            ReportHistory(
                organization_id=job.organization_id,
                project_id=job.project_id,
                job_id=job.id,
                execution_id=execution.id if execution else None,
                event=event,
                summary=summary,
                details=details,
                actor_id=actor_id,
                occurred_at=datetime.now(UTC),
            )
        )


__all__ = ["GenerationResult", "ReportGenerationService"]
