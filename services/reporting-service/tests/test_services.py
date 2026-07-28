"""Service-layer tests against real Postgres.

Templates, generation, scheduling, distribution, archive, analytics,
audit, and the scheduled-report worker -- all exercised through real
rows, real rendering, and real export bytes.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
import pytest
from shared_core.database.base import BaseModel
from shared_core.exceptions.conflict import ConflictError
from shared_core.exceptions.dependency import DependencyError
from shared_core.exceptions.not_found import NotFoundError
from shared_core.exceptions.validation import ValidationError
from shared_core.storage.wrapper import StorageWrapper
from sqlalchemy.ext.asyncio import AsyncSession

import app.models as models_package
from app.ai.summaries import AiSummaryClient, build_context
from app.clients.platform import PlatformSourceClient, SourceEndpoints, unwrap
from app.distribution.channels import DistributionDispatcher
from app.export.engine import ExportedArtifact
from app.models.enums import (
    ArchiveStatus,
    AuditAction,
    AuditOutcome,
    DataSource,
    DistributionChannel,
    DistributionStatus,
    ExportFormat,
    ReportCategory,
    ReportExecutionStatus,
    ReportType,
    ScheduleFrequency,
    TemplateStatus,
)
from app.models.report_category import ReportCategoryRecord
from app.models.report_execution import ReportExecution
from app.renderer.engine import ReportRenderer
from app.repositories.report_archive import ReportArchiveRepository
from app.repositories.report_audit import ReportAuditRepository
from app.repositories.report_category import ReportCategoryRepository
from app.repositories.report_distribution import ReportDistributionRepository
from app.repositories.report_execution import ReportExecutionRepository
from app.repositories.report_export import ReportExportRepository
from app.repositories.report_favorite import ReportFavoriteRepository
from app.repositories.report_history import ReportHistoryRepository
from app.repositories.report_job import ReportJobRepository
from app.repositories.report_parameter import ReportParameterRepository
from app.repositories.report_recipient import ReportRecipientRepository
from app.repositories.report_schedule import ReportScheduleRepository
from app.repositories.report_statistics import ReportStatisticsRepository
from app.repositories.report_template import ReportTemplateRepository
from app.services.archive import ReportArchiveService
from app.services.audit import ReportAuditService
from app.services.distribution import ReportDistributionService
from app.services.generation import ReportGenerationService
from app.services.job import ReportJobService
from app.services.schedule import ReportScheduleService
from app.services.statistics import ReportStatisticsService
from app.services.template import ReportTemplateService
from tests.conftest import (
    SAMPLE_ROWS,
    SIMPLE_DEFINITION,
    RecordingPublisher,
    make_export,
    make_job,
    make_template,
    source_handler,
)


def templates_of(db_session: AsyncSession) -> ReportTemplateService:
    return ReportTemplateService(
        ReportTemplateRepository(db_session), ReportParameterRepository(db_session)
    )


def jobs_of(
    db_session: AsyncSession, publisher: RecordingPublisher | None = None
) -> ReportJobService:
    return ReportJobService(
        ReportJobRepository(db_session),
        ReportHistoryRepository(db_session),
        ReportFavoriteRepository(db_session),
        publish_event=publisher or RecordingPublisher(),
    )


def generation_of(
    db_session: AsyncSession,
    renderer: ReportRenderer,
    publisher: RecordingPublisher | None = None,
) -> ReportGenerationService:
    return ReportGenerationService(
        ReportJobRepository(db_session),
        ReportExecutionRepository(db_session),
        ReportExportRepository(db_session),
        ReportHistoryRepository(db_session),
        templates_of(db_session),
        renderer,
        publish_event=publisher or RecordingPublisher(),
    )


class TestTemplateService:
    async def test_create_makes_a_draft_with_parameters(self, db_session: AsyncSession) -> None:
        template, parameters = await templates_of(db_session).create(
            organization_id=uuid.uuid4(),
            project_id=None,
            name="Fleet",
            description=None,
            category=ReportCategory.INFRASTRUCTURE,
            report_type=ReportType.SUMMARY,
            definition=SIMPLE_DEFINITION,
            parameters=[{"key": "environment", "label": "Environment", "kind": "string"}],
        )
        assert template.version_number == "1.0.0"
        assert template.status is TemplateStatus.DRAFT
        assert [parameter.key for parameter in parameters] == ["environment"]

    async def test_a_malformed_definition_is_rejected(self, db_session: AsyncSession) -> None:
        """Rejected at authoring time, not inside a scheduled run."""
        with pytest.raises(ValidationError, match="Invalid report definition"):
            await templates_of(db_session).create(
                organization_id=uuid.uuid4(),
                project_id=None,
                name="Broken",
                description=None,
                category=ReportCategory.CUSTOM,
                report_type=ReportType.TABULAR,
                definition={"title": "T", "sections": [{"key": "t", "kind": "table"}]},
            )

    async def test_a_duplicate_name_is_a_conflict(self, db_session: AsyncSession) -> None:
        org = uuid.uuid4()
        service = templates_of(db_session)
        common: dict[str, Any] = {
            "organization_id": org,
            "project_id": None,
            "name": "Fleet",
            "description": None,
            "category": ReportCategory.INFRASTRUCTURE,
            "report_type": ReportType.SUMMARY,
            "definition": SIMPLE_DEFINITION,
        }
        await service.create(**common)
        with pytest.raises(ConflictError, match="already exists"):
            await service.create(**common)

    async def test_versions_accumulate_and_bump(self, db_session: AsyncSession) -> None:
        service = templates_of(db_session)
        template, _parameters = await service.create(
            organization_id=uuid.uuid4(),
            project_id=None,
            name="Fleet",
            description=None,
            category=ReportCategory.INFRASTRUCTURE,
            report_type=ReportType.SUMMARY,
            definition=SIMPLE_DEFINITION,
        )
        version, _params = await service.add_version(template.id, definition=SIMPLE_DEFINITION)
        assert version.version_number == "1.1.0"
        assert len(await service.list_versions(template.organization_id, "Fleet")) == 2

    async def test_an_unapproved_template_cannot_be_used(self, db_session: AsyncSession) -> None:
        """Running an unreviewed template against production is what the gate stops."""
        template = await make_template(db_session, status=TemplateStatus.DRAFT)
        with pytest.raises(ConflictError, match="not approved"):
            await templates_of(db_session).resolve_for_execution(template.id)

    async def test_an_approved_template_resolves(self, db_session: AsyncSession) -> None:
        template = await make_template(db_session, status=TemplateStatus.DRAFT)
        service = templates_of(db_session)
        await service.approve(template.id, approved_by=uuid.uuid4())
        resolved = await service.resolve_for_execution(template.id)
        assert resolved.id == template.id

    async def test_an_archived_version_cannot_be_approved(self, db_session: AsyncSession) -> None:
        template = await make_template(db_session, status=TemplateStatus.ARCHIVED)
        with pytest.raises(ConflictError, match="archived"):
            await templates_of(db_session).approve(template.id, approved_by=None)

    async def test_approval_survives_a_fresh_session(self, db_session_factory: Any) -> None:
        """Regression: enum columns come back from Postgres as ``str``.

        Comparing with ``is`` is ``False`` for every stored row, which
        shipped three dead features elsewhere in this platform. Reading
        back through a **second session** is the only thing that makes
        that visible, so this test deliberately does not reuse the
        ``db_session`` fixture.
        """
        org = uuid.uuid4()
        async with db_session_factory() as writer:
            template = await make_template(writer, organization_id=org, status=TemplateStatus.DRAFT)
            await templates_of(writer).approve(template.id, approved_by=None)
            await writer.commit()
            template_id = template.id

        async with db_session_factory() as reader:
            stored = await ReportTemplateRepository(reader).require_by_id(template_id)
            assert not isinstance(stored.status, TemplateStatus), (
                "The column really does return a raw str; if this ever becomes "
                "a true enum, the normalisation can be dropped."
            )
            resolved = await templates_of(reader).resolve_for_execution(template_id)
            assert resolved.id == template_id

    async def test_latest_approved_ignores_drafts(self, db_session: AsyncSession) -> None:
        org = uuid.uuid4()
        await make_template(db_session, organization_id=org, version_number="1.0.0")
        await make_template(
            db_session,
            organization_id=org,
            version_number="1.1.0",
            status=TemplateStatus.DRAFT,
        )
        latest = await templates_of(db_session).latest_approved(org, "Fleet Report")
        assert latest.version_number == "1.0.0"

    async def test_no_approved_version_raises(self, db_session: AsyncSession) -> None:
        org = uuid.uuid4()
        await make_template(db_session, organization_id=org, status=TemplateStatus.DRAFT)
        with pytest.raises(NotFoundError, match="No approved version"):
            await templates_of(db_session).latest_approved(org, "Fleet Report")

    async def test_parameters_are_replaced_not_merged(self, db_session: AsyncSession) -> None:
        """A removed parameter must genuinely disappear, not linger."""
        service = templates_of(db_session)
        template, _p = await service.create(
            organization_id=uuid.uuid4(),
            project_id=None,
            name="Fleet",
            description=None,
            category=ReportCategory.INFRASTRUCTURE,
            report_type=ReportType.SUMMARY,
            definition=SIMPLE_DEFINITION,
            parameters=[
                {"key": "a", "label": "A", "kind": "string"},
                {"key": "b", "label": "B", "kind": "string"},
            ],
        )
        version, params = await service.add_version(
            template.id,
            definition=SIMPLE_DEFINITION,
            parameters=[{"key": "a", "label": "A", "kind": "string"}],
        )
        assert [parameter.key for parameter in params] == ["a"]
        assert len(await service.list_parameters(version.id)) == 1

    async def test_duplicate_parameter_keys_are_rejected(self, db_session: AsyncSession) -> None:
        with pytest.raises(ValidationError, match="Duplicate report parameter"):
            await templates_of(db_session).create(
                organization_id=uuid.uuid4(),
                project_id=None,
                name="Fleet",
                description=None,
                category=ReportCategory.INFRASTRUCTURE,
                report_type=ReportType.SUMMARY,
                definition=SIMPLE_DEFINITION,
                parameters=[
                    {"key": "a", "label": "A", "kind": "string"},
                    {"key": "a", "label": "A2", "kind": "string"},
                ],
            )

    async def test_an_unknown_parameter_kind_is_rejected(self, db_session: AsyncSession) -> None:
        with pytest.raises(ValidationError, match="unknown kind"):
            await templates_of(db_session).create(
                organization_id=uuid.uuid4(),
                project_id=None,
                name="Fleet",
                description=None,
                category=ReportCategory.INFRASTRUCTURE,
                report_type=ReportType.SUMMARY,
                definition=SIMPLE_DEFINITION,
                parameters=[{"key": "a", "label": "A", "kind": "quaternion"}],
            )

    async def test_a_parameter_without_a_key_is_rejected(self, db_session: AsyncSession) -> None:
        with pytest.raises(ValidationError, match="requires a 'key'"):
            await templates_of(db_session).create(
                organization_id=uuid.uuid4(),
                project_id=None,
                name="Fleet",
                description=None,
                category=ReportCategory.INFRASTRUCTURE,
                report_type=ReportType.SUMMARY,
                definition=SIMPLE_DEFINITION,
                parameters=[{"label": "A", "kind": "string"}],
            )


class TestJobService:
    async def test_create_records_history_and_publishes(self, db_session: AsyncSession) -> None:
        publisher = RecordingPublisher()
        service = jobs_of(db_session, publisher)
        job = await service.create(
            organization_id=uuid.uuid4(),
            project_id=None,
            name="Nightly",
            description=None,
            category=ReportCategory.INFRASTRUCTURE,
            report_type=ReportType.SUMMARY,
            template_id=None,
        )
        assert publisher.names == ["ReportCreated"]
        history = await service.list_history(job.id)
        assert [entry.event for entry in history] == ["created"]

    async def test_a_malformed_filter_is_rejected_on_write(self, db_session: AsyncSession) -> None:
        """Rejected here, not at 03:00 inside a scheduled run."""
        with pytest.raises(ValidationError):
            await jobs_of(db_session).create(
                organization_id=uuid.uuid4(),
                project_id=None,
                name="Bad",
                description=None,
                category=ReportCategory.CUSTOM,
                report_type=ReportType.TABULAR,
                template_id=None,
                filters=[{"operator": "eq", "value": "x"}],
            )

    async def test_update_is_partial(self, db_session: AsyncSession) -> None:
        job = await make_job(db_session, name="Original")
        updated = await jobs_of(db_session).update(job.id, description="Now described")
        assert updated.name == "Original"
        assert updated.description == "Now described"

    async def test_update_validates_new_filters(self, db_session: AsyncSession) -> None:
        job = await make_job(db_session)
        with pytest.raises(ValidationError):
            await jobs_of(db_session).update(job.id, filters=[{"operator": "eq"}])

    async def test_delete_is_soft(self, db_session: AsyncSession) -> None:
        """Executions and archives reference it; a dangling audit trail is worse."""
        job = await make_job(db_session)
        service = jobs_of(db_session)
        await service.delete(job.id)
        assert await ReportJobRepository(db_session).get_by_id(job.id) is None
        assert (
            await ReportJobRepository(db_session).get_by_id(job.id, include_deleted=True)
            is not None
        )

    async def test_listing_filters_by_category_and_enabled(self, db_session: AsyncSession) -> None:
        org = uuid.uuid4()
        await make_job(db_session, organization_id=org, name="A")
        disabled = await make_job(db_session, organization_id=org, name="B")
        await jobs_of(db_session).update(disabled.id, enabled=False)

        service = jobs_of(db_session)
        assert len(await service.list_for_org(org)) == 2
        assert len(await service.list_for_org(org, enabled_only=True)) == 1
        assert len(await service.list_for_org(org, category=ReportCategory.INFRASTRUCTURE)) == 2
        assert len(await service.list_for_org(org, category=ReportCategory.SECURITY)) == 0

    async def test_favouriting_is_idempotent(self, db_session: AsyncSession) -> None:
        """Clicking a star twice is not an error."""
        org, user = uuid.uuid4(), uuid.uuid4()
        job = await make_job(db_session, organization_id=org)
        service = jobs_of(db_session)
        first = await service.favorite(org, user, job.id)
        second = await service.favorite(org, user, job.id)
        assert first.id == second.id
        assert len(await service.list_favorites(org, user)) == 1

    async def test_unfavouriting_reports_whether_it_did_anything(
        self, db_session: AsyncSession
    ) -> None:
        org, user = uuid.uuid4(), uuid.uuid4()
        job = await make_job(db_session, organization_id=org)
        service = jobs_of(db_session)
        assert await service.unfavorite(user, job.id) is False
        await service.favorite(org, user, job.id)
        assert await service.unfavorite(user, job.id) is True

    async def test_org_history_spans_every_report(self, db_session: AsyncSession) -> None:
        org = uuid.uuid4()
        service = jobs_of(db_session)
        for name in ("A", "B"):
            await service.create(
                organization_id=org,
                project_id=None,
                name=name,
                description=None,
                category=ReportCategory.INFRASTRUCTURE,
                report_type=ReportType.SUMMARY,
                template_id=None,
            )
        assert len(await service.list_org_history(org)) == 2


class TestGeneration:
    async def test_a_full_run_persists_execution_and_exports(
        self, db_session: AsyncSession, renderer: ReportRenderer
    ) -> None:
        org = uuid.uuid4()
        template = await make_template(db_session, organization_id=org)
        job = await make_job(db_session, organization_id=org, template_id=template.id)
        publisher = RecordingPublisher()

        result = await generation_of(db_session, renderer, publisher).generate(
            job, export_formats=[ExportFormat.CSV, ExportFormat.JSON]
        )
        assert result.succeeded
        assert result.execution.row_count == len(SAMPLE_ROWS)
        assert result.execution.section_count == 2
        assert result.execution.duration_ms is not None
        assert {str(record.export_format) for record in result.exports} == {"csv", "json"}
        assert all(record.checksum_sha256 for record in result.exports)
        assert publisher.names == ["ReportGenerated"]

    async def test_filters_narrow_the_rows(
        self, db_session: AsyncSession, renderer: ReportRenderer
    ) -> None:
        org = uuid.uuid4()
        template = await make_template(db_session, organization_id=org)
        job = await make_job(
            db_session,
            organization_id=org,
            template_id=template.id,
            filters=[{"field": "env", "operator": "eq", "value": "prod"}],
        )
        result = await generation_of(db_session, renderer).generate(job)
        assert result.execution.row_count == 3

    async def test_overrides_merge_over_stored_values(
        self, db_session: AsyncSession, renderer: ReportRenderer
    ) -> None:
        """An ad-hoc run should not have to restate the whole parameter set."""
        org = uuid.uuid4()
        definition = {
            "title": "Fleet {{ environment }} / {{ region }}",
            "sections": [{"key": "t", "kind": "text", "text": "{{ environment }}"}],
        }
        service = templates_of(db_session)
        template, _p = await service.create(
            organization_id=org,
            project_id=None,
            name="Parametrised",
            description=None,
            category=ReportCategory.INFRASTRUCTURE,
            report_type=ReportType.SUMMARY,
            definition=definition,
            parameters=[
                {"key": "environment", "label": "Env", "kind": "string"},
                {"key": "region", "label": "Region", "kind": "string"},
            ],
        )
        await service.approve(template.id, approved_by=None)
        job = await make_job(
            db_session,
            organization_id=org,
            template_id=template.id,
            parameter_values={"environment": "prod", "region": "eu"},
        )
        result = await generation_of(db_session, renderer).generate(
            job, parameter_overrides={"region": "us"}
        )
        assert result.report is not None
        assert result.report.title == "Fleet prod / us"

    async def test_an_unapproved_template_refuses_to_run(
        self, db_session: AsyncSession, renderer: ReportRenderer
    ) -> None:
        org = uuid.uuid4()
        template = await make_template(db_session, organization_id=org, status=TemplateStatus.DRAFT)
        job = await make_job(db_session, organization_id=org, template_id=template.id)
        with pytest.raises(ConflictError, match="not approved"):
            await generation_of(db_session, renderer).generate(job)

    async def test_a_job_without_a_template_is_rejected(
        self, db_session: AsyncSession, renderer: ReportRenderer
    ) -> None:
        job = await make_job(db_session, template_id=None)
        with pytest.raises(ValidationError, match="no template"):
            await generation_of(db_session, renderer).generate(job)

    async def test_an_unreachable_source_degrades_rather_than_failing(
        self, db_session: AsyncSession, source_endpoints: SourceEndpoints
    ) -> None:
        """A report with an honest gap beats no report at all."""
        org = uuid.uuid4()
        template = await make_template(db_session, organization_id=org)
        job = await make_job(db_session, organization_id=org, template_id=template.id)

        async with httpx.AsyncClient(
            transport=httpx.MockTransport(source_handler(status_code=503))
        ) as http_client:
            failing = ReportRenderer(
                PlatformSourceClient(http_client, source_endpoints, caller_token="t"), None
            )
            result = await generation_of(db_session, failing).generate(job)

        assert result.succeeded
        assert result.degraded_sections == ["hosts"]
        assert result.execution.row_count == 0

    async def test_a_render_failure_is_persisted_before_re_raising(
        self, db_session: AsyncSession, renderer: ReportRenderer
    ) -> None:
        """A report that died halfway must leave a record explaining why."""
        org = uuid.uuid4()
        template = await make_template(
            db_session,
            organization_id=org,
            definition={
                "title": "Broken {{ missing }}",
                "sections": [{"key": "t", "kind": "text", "text": "x"}],
            },
        )
        job = await make_job(db_session, organization_id=org, template_id=template.id)
        publisher = RecordingPublisher()

        with pytest.raises(ValidationError):
            await generation_of(db_session, renderer, publisher).generate(job)

        executions = await ReportExecutionRepository(db_session).list_for_job(job.id)
        assert executions[0].status == ReportExecutionStatus.FAILED
        assert executions[0].error_message
        assert publisher.names == ["ReportFailed"]

        history = await ReportHistoryRepository(db_session).list_for_job(job.id)
        assert history[0].event == "failed"

    async def test_a_signed_and_encrypted_pdf_is_produced(
        self, db_session: AsyncSession, renderer: ReportRenderer
    ) -> None:
        org = uuid.uuid4()
        template = await make_template(db_session, organization_id=org)
        job = await make_job(db_session, organization_id=org, template_id=template.id)
        result = await generation_of(db_session, renderer).generate(
            job,
            export_formats=[ExportFormat.PDF],
            signed_by="ops@example.com",
            pdf_password="s3cret",
        )
        assert b"/Encrypt" in result.exports[0].content

    async def test_the_default_format_is_used_when_none_is_given(
        self, db_session: AsyncSession, renderer: ReportRenderer
    ) -> None:
        org = uuid.uuid4()
        template = await make_template(db_session, organization_id=org)
        job = await make_job(
            db_session,
            organization_id=org,
            template_id=template.id,
            default_format=ExportFormat.MARKDOWN,
        )
        result = await generation_of(db_session, renderer).generate(job)
        assert str(result.exports[0].export_format) == "markdown"


class TestScheduling:
    def _service(self, db_session: AsyncSession, publisher: Any = None) -> ReportScheduleService:
        return ReportScheduleService(
            ReportScheduleRepository(db_session), publish_event=publisher or RecordingPublisher()
        )

    async def test_create_computes_the_first_run(self, db_session: AsyncSession) -> None:
        job = await make_job(db_session)
        publisher = RecordingPublisher()
        schedule = await self._service(db_session, publisher).create(
            organization_id=job.organization_id,
            project_id=None,
            job_id=job.id,
            frequency=ScheduleFrequency.DAILY,
            starts_at=datetime.now(UTC) - timedelta(days=1),
        )
        assert schedule.next_run_at is not None
        assert schedule.next_run_at > datetime.now(UTC)
        assert publisher.names == ["ReportScheduled"]

    async def test_an_invalid_cadence_is_rejected(self, db_session: AsyncSession) -> None:
        job = await make_job(db_session)
        with pytest.raises(ValidationError):
            await self._service(db_session).create(
                organization_id=job.organization_id,
                project_id=None,
                job_id=job.id,
                frequency=ScheduleFrequency.CRON,
                starts_at=datetime.now(UTC),
            )

    async def test_due_schedules_are_found_and_others_are_not(
        self, db_session: AsyncSession
    ) -> None:
        job = await make_job(db_session)
        service = self._service(db_session)
        due = await service.create(
            organization_id=job.organization_id,
            project_id=None,
            job_id=job.id,
            frequency=ScheduleFrequency.HOURLY,
            starts_at=datetime.now(UTC) - timedelta(hours=2),
        )
        due.next_run_at = datetime.now(UTC) - timedelta(minutes=1)
        await ReportScheduleRepository(db_session).update(due)

        await service.create(
            organization_id=job.organization_id,
            project_id=None,
            job_id=job.id,
            frequency=ScheduleFrequency.DAILY,
            starts_at=datetime.now(UTC) + timedelta(days=1),
        )
        found = await service.list_due()
        assert [schedule.id for schedule in found] == [due.id]

    async def test_success_advances_and_clears_failures(self, db_session: AsyncSession) -> None:
        job = await make_job(db_session)
        service = self._service(db_session)
        schedule = await service.create(
            organization_id=job.organization_id,
            project_id=None,
            job_id=job.id,
            frequency=ScheduleFrequency.HOURLY,
            starts_at=datetime.now(UTC) - timedelta(hours=2),
        )
        schedule.consecutive_failures = 2
        advanced = await service.mark_succeeded(schedule)
        assert advanced.consecutive_failures == 0
        assert advanced.last_error is None
        assert advanced.next_run_at is not None

    async def test_repeated_failure_disables_the_schedule(self, db_session: AsyncSession) -> None:
        """An unreachable source would otherwise fail every minute forever."""
        job = await make_job(db_session)
        service = self._service(db_session)
        schedule = await service.create(
            organization_id=job.organization_id,
            project_id=None,
            job_id=job.id,
            frequency=ScheduleFrequency.HOURLY,
            starts_at=datetime.now(UTC) - timedelta(hours=2),
            max_retries=2,
        )
        schedule = await service.mark_failed(schedule, "source down")
        assert schedule.enabled is True
        assert schedule.next_run_at is not None

        schedule = await service.mark_failed(schedule, "source down")
        assert schedule.enabled is False
        assert schedule.next_run_at is None

    async def test_a_one_time_schedule_does_not_advance(self, db_session: AsyncSession) -> None:
        job = await make_job(db_session)
        service = self._service(db_session)
        schedule = await service.create(
            organization_id=job.organization_id,
            project_id=None,
            job_id=job.id,
            frequency=ScheduleFrequency.ONE_TIME,
            starts_at=datetime.now(UTC) + timedelta(hours=1),
        )
        assert (await service.mark_succeeded(schedule)).next_run_at is None

    async def test_changing_cadence_recomputes_the_next_run(self, db_session: AsyncSession) -> None:
        """An edited schedule must not keep firing on its old cadence."""
        job = await make_job(db_session)
        service = self._service(db_session)
        schedule = await service.create(
            organization_id=job.organization_id,
            project_id=None,
            job_id=job.id,
            frequency=ScheduleFrequency.DAILY,
            starts_at=datetime.now(UTC) - timedelta(days=1),
        )
        original = schedule.next_run_at
        updated = await service.update(schedule.id, frequency=ScheduleFrequency.HOURLY)
        assert updated.next_run_at != original

    async def test_re_enabling_clears_the_failure_streak(self, db_session: AsyncSession) -> None:
        """Otherwise one more failure would immediately re-disable it."""
        job = await make_job(db_session)
        service = self._service(db_session)
        schedule = await service.create(
            organization_id=job.organization_id,
            project_id=None,
            job_id=job.id,
            frequency=ScheduleFrequency.HOURLY,
            starts_at=datetime.now(UTC) - timedelta(hours=2),
            max_retries=1,
        )
        await service.mark_failed(schedule, "down")
        re_enabled = await service.update(schedule.id, enabled=True)
        assert re_enabled.consecutive_failures == 0
        assert re_enabled.enabled is True

    async def test_delete(self, db_session: AsyncSession) -> None:
        job = await make_job(db_session)
        service = self._service(db_session)
        schedule = await service.create(
            organization_id=job.organization_id,
            project_id=None,
            job_id=job.id,
            frequency=ScheduleFrequency.DAILY,
            starts_at=datetime.now(UTC),
        )
        await service.delete(schedule.id)
        with pytest.raises(NotFoundError):
            await service.get_by_id(schedule.id)


class _RecordingNotifier:
    """A notification manager surface that records rather than sends."""

    def __init__(self) -> None:
        self.sent: list[dict[str, Any]] = []

    async def send(self, **kwargs: Any) -> None:
        self.sent.append(kwargs)


class TestDistribution:
    def _service(
        self,
        db_session: AsyncSession,
        http_client: httpx.AsyncClient,
        *,
        storage: StorageWrapper | None = None,
        publisher: Any = None,
        secret: str = "",
    ) -> ReportDistributionService:
        return ReportDistributionService(
            ReportDistributionRepository(db_session),
            ReportRecipientRepository(db_session),
            ReportExportRepository(db_session),
            DistributionDispatcher(
                http_client,
                _RecordingNotifier(),  # type: ignore[arg-type]
                storage,
                bucket="reports",
                share_link_ttl_seconds=3600,
                webhook_timeout_seconds=5.0,
                webhook_secret=secret,
            ),
            publish_event=publisher or RecordingPublisher(),
        )

    async def _artifact(self, db_session: AsyncSession) -> tuple[Any, Any, Any]:
        org = uuid.uuid4()
        job = await make_job(db_session, organization_id=org)
        execution = await ReportExecutionRepository(db_session).create(
            ReportExecution(
                organization_id=org,
                job_id=job.id,
                status=ReportExecutionStatus.SUCCEEDED,
            )
        )
        record = await make_export(db_session, execution_id=execution.id, organization_id=org)
        artifact = ExportedArtifact(
            export_format=ExportFormat.CSV,
            filename="report.csv",
            content_type="text/csv; charset=utf-8",
            content=record.content,
        )
        return record, artifact, job

    async def test_download_delivery_is_recorded(self, db_session: AsyncSession) -> None:
        record, artifact, _job = await self._artifact(db_session)
        async with httpx.AsyncClient() as http_client:
            delivery = await self._service(db_session, http_client).deliver(
                record,
                artifact,
                channel=DistributionChannel.DOWNLOAD,
                target="n/a",
                report_title="Fleet",
            )
        assert delivery.status is DistributionStatus.DELIVERED

    async def test_email_delivery_reaches_the_notifier(self, db_session: AsyncSession) -> None:
        record, artifact, _job = await self._artifact(db_session)
        publisher = RecordingPublisher()
        async with httpx.AsyncClient() as http_client:
            delivery = await self._service(db_session, http_client, publisher=publisher).deliver(
                record,
                artifact,
                channel=DistributionChannel.EMAIL,
                target="ops@example.com",
                report_title="Fleet",
            )
        assert delivery.status is DistributionStatus.DELIVERED
        assert publisher.names == ["ReportDelivered"]

    async def test_webhook_delivery_posts_and_signs(self, db_session: AsyncSession) -> None:
        record, artifact, _job = await self._artifact(db_session)
        seen: dict[str, Any] = {}

        def handler(request: httpx.Request) -> httpx.Response:
            seen["headers"] = dict(request.headers)
            seen["body"] = request.content
            return httpx.Response(200, json={"ok": True})

        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http_client:
            delivery = await self._service(db_session, http_client, secret="topsecret").deliver(
                record,
                artifact,
                channel=DistributionChannel.WEBHOOK,
                target="https://hooks.example.com/report",
                report_title="Fleet",
            )
        assert delivery.status is DistributionStatus.DELIVERED
        assert seen["headers"]["x-aiios-signature"].startswith("sha256=")
        assert b"content_base64" in seen["body"]

    async def test_a_failing_webhook_is_recorded_not_raised(self, db_session: AsyncSession) -> None:
        """A delivery that silently vanished is indistinguishable from none."""
        record, artifact, _job = await self._artifact(db_session)

        def handler(_request: httpx.Request) -> httpx.Response:
            return httpx.Response(500, json={"error": "boom"})

        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http_client:
            delivery = await self._service(db_session, http_client).deliver(
                record,
                artifact,
                channel=DistributionChannel.WEBHOOK,
                target="https://hooks.example.com/report",
                report_title="Fleet",
            )
        assert delivery.status is DistributionStatus.FAILED
        assert "HTTP 500" in (delivery.error_message or "")

    async def test_an_unreachable_webhook_is_recorded(self, db_session: AsyncSession) -> None:
        record, artifact, _job = await self._artifact(db_session)

        def handler(_request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("refused")

        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http_client:
            delivery = await self._service(db_session, http_client).deliver(
                record,
                artifact,
                channel=DistributionChannel.WEBHOOK,
                target="https://hooks.example.com/report",
                report_title="Fleet",
            )
        assert delivery.status is DistributionStatus.FAILED
        assert "unreachable" in (delivery.error_message or "")

    async def test_object_storage_without_a_backend_fails_cleanly(
        self, db_session: AsyncSession
    ) -> None:
        record, artifact, _job = await self._artifact(db_session)
        async with httpx.AsyncClient() as http_client:
            delivery = await self._service(db_session, http_client, storage=None).deliver(
                record,
                artifact,
                channel=DistributionChannel.OBJECT_STORAGE,
                target="bucket",
                report_title="Fleet",
            )
        assert delivery.status is DistributionStatus.FAILED
        assert "not configured" in (delivery.error_message or "")

    async def test_a_share_link_can_be_redeemed(self, db_session: AsyncSession) -> None:
        record, artifact, _job = await self._artifact(db_session)
        async with httpx.AsyncClient() as http_client:
            service = self._service(db_session, http_client)
            delivery = await service.deliver(
                record,
                artifact,
                channel=DistributionChannel.SHARED_LINK,
                target="link",
                report_title="Fleet",
            )
            assert delivery.share_token is not None
            resolved = await service.resolve_share_token(delivery.share_token)
        assert resolved.id == record.id

    async def test_an_expired_share_link_stops_working(self, db_session: AsyncSession) -> None:
        """Storing an expiry nothing checks makes the link time-limited in name only."""
        record, artifact, _job = await self._artifact(db_session)
        async with httpx.AsyncClient() as http_client:
            service = self._service(db_session, http_client)
            delivery = await service.deliver(
                record,
                artifact,
                channel=DistributionChannel.SHARED_LINK,
                target="link",
                report_title="Fleet",
            )
            delivery.expires_at = datetime.now(UTC) - timedelta(seconds=1)
            await ReportDistributionRepository(db_session).update(delivery)
            assert delivery.share_token is not None
            with pytest.raises(ConflictError, match="expired"):
                await service.resolve_share_token(delivery.share_token)

    async def test_an_unknown_share_token_is_not_found(self, db_session: AsyncSession) -> None:
        async with httpx.AsyncClient() as http_client:
            with pytest.raises(NotFoundError):
                await self._service(db_session, http_client).resolve_share_token("nope")

    async def test_standing_recipients_each_get_their_own_row(
        self, db_session: AsyncSession
    ) -> None:
        """One failing recipient must not stop the others."""
        record, artifact, job = await self._artifact(db_session)
        async with httpx.AsyncClient() as http_client:
            service = self._service(db_session, http_client)
            for target in ("a@example.com", "b@example.com"):
                await service.add_recipient(
                    organization_id=record.organization_id,
                    project_id=None,
                    job_id=job.id,
                    channel=DistributionChannel.EMAIL,
                    target=target,
                )
            deliveries = await service.deliver_to_recipients(
                record, artifact, job_id=job.id, report_title="Fleet"
            )
        assert len(deliveries) == 2

    async def test_an_invalid_recipient_target_is_refused(self, db_session: AsyncSession) -> None:
        async with httpx.AsyncClient() as http_client:
            with pytest.raises(ValidationError):
                await self._service(db_session, http_client).add_recipient(
                    organization_id=uuid.uuid4(),
                    project_id=None,
                    job_id=uuid.uuid4(),
                    channel=DistributionChannel.EMAIL,
                    target="not-an-email",
                )


class TestArchive:
    def _service(
        self, db_session: AsyncSession, publisher: Any = None, *, retention_days: int = 365
    ) -> ReportArchiveService:
        return ReportArchiveService(
            ReportArchiveRepository(db_session),
            ReportExportRepository(db_session),
            publish_event=publisher or RecordingPublisher(),
            retention_days=retention_days,
        )

    async def _export(self, db_session: AsyncSession, org: uuid.UUID) -> Any:
        job = await make_job(db_session, organization_id=org)
        execution = await ReportExecutionRepository(db_session).create(
            ReportExecution(
                organization_id=org, job_id=job.id, status=ReportExecutionStatus.SUCCEEDED
            )
        )
        return await make_export(db_session, execution_id=execution.id, organization_id=org)

    async def test_archiving_versions_and_publishes(self, db_session: AsyncSession) -> None:
        org = uuid.uuid4()
        record = await self._export(db_session, org)
        publisher = RecordingPublisher()
        service = self._service(db_session, publisher)

        first = await service.archive_export(record, title="Fleet")
        second = await service.archive_export(record, title="Fleet")
        assert (first.archive_version, second.archive_version) == (1, 2)
        assert publisher.names == ["ReportArchived", "ReportArchived"]
        assert first.retention_until is not None

    async def test_versions_survive_a_purged_predecessor(self, db_session: AsyncSession) -> None:
        """``MAX(version) + 1`` rather than a count, so ids cannot collide."""
        org = uuid.uuid4()
        record = await self._export(db_session, org)
        service = self._service(db_session, retention_days=1)
        first = await service.archive_export(record, title="Fleet", retention_days=1)
        first.retention_until = datetime.now(UTC) - timedelta(days=1)
        await ReportArchiveRepository(db_session).update(first)
        await service.purge(first.id)

        third = await service.archive_export(record, title="Fleet")
        assert third.archive_version == 2

    async def test_download_verifies_integrity(self, db_session: AsyncSession) -> None:
        org = uuid.uuid4()
        record = await self._export(db_session, org)
        service = self._service(db_session)
        archive = await service.archive_export(record, title="Fleet")
        assert (await service.download(archive.id)).size_bytes == record.size_bytes

    async def test_a_corrupted_archive_is_not_served(self, db_session: AsyncSession) -> None:
        """Serving content that fails its own checksum hands an auditor a lie."""
        org = uuid.uuid4()
        record = await self._export(db_session, org)
        service = self._service(db_session)
        archive = await service.archive_export(record, title="Fleet")
        archive.content = b"tampered"
        await ReportArchiveRepository(db_session).update(archive)
        with pytest.raises(ConflictError, match="integrity check"):
            await service.download(archive.id)

    async def test_purging_inside_retention_is_refused(self, db_session: AsyncSession) -> None:
        org = uuid.uuid4()
        record = await self._export(db_session, org)
        service = self._service(db_session)
        archive = await service.archive_export(record, title="Fleet")
        with pytest.raises(ConflictError, match="retained until"):
            await service.purge(archive.id)

    async def test_purging_keeps_the_row_and_drops_the_bytes(
        self, db_session: AsyncSession
    ) -> None:
        """Deleting the row would erase the evidence it ever existed."""
        org = uuid.uuid4()
        record = await self._export(db_session, org)
        service = self._service(db_session)
        archive = await service.archive_export(record, title="Fleet", retention_days=1)
        archive.retention_until = datetime.now(UTC) - timedelta(days=1)
        await ReportArchiveRepository(db_session).update(archive)

        purged = await service.purge(archive.id, reason="policy")
        assert purged.status is ArchiveStatus.PURGED
        assert purged.content == b""
        assert purged.size_bytes == 0
        assert purged.title == "Fleet"

    async def test_a_purged_archive_cannot_be_downloaded(self, db_session: AsyncSession) -> None:
        org = uuid.uuid4()
        record = await self._export(db_session, org)
        service = self._service(db_session)
        archive = await service.archive_export(record, title="Fleet", retention_days=1)
        archive.retention_until = datetime.now(UTC) - timedelta(days=1)
        await ReportArchiveRepository(db_session).update(archive)
        await service.purge(archive.id)
        with pytest.raises(ConflictError, match="purged"):
            await service.download(archive.id)

    async def test_restore_creates_a_new_export(self, db_session: AsyncSession) -> None:
        """A restore must not silently overwrite current state."""
        org = uuid.uuid4()
        record = await self._export(db_session, org)
        service = self._service(db_session)
        archive = await service.archive_export(record, title="Fleet")
        restored = await service.restore(archive.id)
        assert restored.id != record.id
        assert restored.checksum_sha256 == record.checksum_sha256

    async def test_search_and_listing(self, db_session: AsyncSession) -> None:
        org = uuid.uuid4()
        record = await self._export(db_session, org)
        service = self._service(db_session)
        await service.archive_export(record, title="Quarterly Capacity")
        await service.archive_export(record, title="Nightly Fleet")

        assert len(await service.list_for_org(org)) == 2
        assert len(await service.search(org, "capacity")) == 1
        assert len(await service.search(org, "CAPACITY")) == 1
        assert len(await service.list_versions(org, "Nightly Fleet")) == 1

    async def test_purge_expired_sweeps(self, db_session: AsyncSession) -> None:
        org = uuid.uuid4()
        record = await self._export(db_session, org)
        service = self._service(db_session)
        archive = await service.archive_export(record, title="Fleet", retention_days=1)
        archive.retention_until = datetime.now(UTC) - timedelta(days=1)
        await ReportArchiveRepository(db_session).update(archive)
        assert await service.purge_expired() == 1


class TestStatisticsAndAudit:
    def _statistics(self, db_session: AsyncSession) -> ReportStatisticsService:
        return ReportStatisticsService(
            ReportStatisticsRepository(db_session),
            ReportJobRepository(db_session),
            ReportExecutionRepository(db_session),
            ReportExportRepository(db_session),
            ReportDistributionRepository(db_session),
            ReportScheduleRepository(db_session),
            ReportTemplateRepository(db_session),
        )

    async def test_an_empty_organization_is_all_zeroes(self, db_session: AsyncSession) -> None:
        snapshot = await self._statistics(db_session).get_for_org(uuid.uuid4())
        assert snapshot.total_reports == 0
        assert snapshot.average_duration_ms == 0.0

    async def test_a_real_run_is_counted(
        self, db_session: AsyncSession, renderer: ReportRenderer
    ) -> None:
        org = uuid.uuid4()
        template = await make_template(db_session, organization_id=org)
        job = await make_job(db_session, organization_id=org, template_id=template.id)
        await generation_of(db_session, renderer).generate(job, export_formats=[ExportFormat.CSV])

        snapshot = await self._statistics(db_session).recompute(org)
        assert snapshot.total_reports == 1
        assert snapshot.total_executions == 1
        assert snapshot.successful_executions == 1
        assert snapshot.average_duration_ms > 0
        assert snapshot.export_format_usage == {"csv": 1}
        assert snapshot.popular_reports == {"Nightly Fleet": 1}
        assert snapshot.template_usage == {"Fleet Report": 1}

    async def test_recompute_updates_in_place(self, db_session: AsyncSession) -> None:
        org = uuid.uuid4()
        service = self._statistics(db_session)
        first = await service.recompute(org)
        await make_job(db_session, organization_id=org)
        second = await service.recompute(org)
        assert first.id == second.id
        assert second.total_reports == 1

    async def test_audit_records_and_filters(self, db_session: AsyncSession) -> None:
        org, entity = uuid.uuid4(), uuid.uuid4()
        service = ReportAuditService(ReportAuditRepository(db_session))
        await service.record(
            organization_id=org,
            action=AuditAction.REPORT_GENERATED,
            entity_type="ReportExecution",
            entity_id=entity,
            actor_id=uuid.uuid4(),
        )
        await service.record(
            organization_id=org,
            action=AuditAction.REPORT_DOWNLOADED,
            entity_type="ReportExport",
            outcome=AuditOutcome.DENIED,
            reason="No permission.",
        )
        assert len(await service.list_for_org(org)) == 2
        assert len(await service.list_for_org(org, action=AuditAction.REPORT_GENERATED)) == 1
        assert len(await service.list_for_entity(entity)) == 1

    async def test_a_denied_action_is_recorded(self, db_session: AsyncSession) -> None:
        """An attempt to export without rights is what an auditor most wants."""
        service = ReportAuditService(ReportAuditRepository(db_session))
        entry = await service.record(
            organization_id=uuid.uuid4(),
            action=AuditAction.REPORT_EXPORTED,
            entity_type="ReportExport",
            outcome=AuditOutcome.DENIED,
        )
        assert entry.outcome is AuditOutcome.DENIED


class TestCategoriesRepository:
    async def test_slug_lookup_and_ordering(self, db_session: AsyncSession) -> None:
        org = uuid.uuid4()
        repository = ReportCategoryRepository(db_session)
        await repository.create(
            ReportCategoryRecord(
                organization_id=org,
                category=ReportCategory.SECURITY,
                slug="sec",
                name="Security",
                display_order=2,
            )
        )
        await repository.create(
            ReportCategoryRecord(
                organization_id=org,
                category=ReportCategory.CAPACITY,
                slug="cap",
                name="Capacity",
                display_order=1,
            )
        )
        listed = await repository.list_for_org(org)
        assert [record.slug for record in listed] == ["cap", "sec"]
        assert (await repository.get_by_slug(org, "sec")) is not None
        assert (await repository.get_by_slug(org, "nope")) is None


class TestSourceClient:
    async def test_the_platform_envelope_is_unwrapped(self) -> None:
        assert unwrap({"success": True, "data": [{"a": 1}]}, None) == [{"a": 1}]

    async def test_a_single_object_becomes_one_row(self) -> None:
        """A "current statistics" endpoint returns one object legitimately."""
        assert unwrap({"data": {"checks": 12}}, None) == [{"checks": 12}]

    async def test_a_nested_result_path_is_followed(self) -> None:
        assert unwrap({"data": {"items": [{"a": 1}]}}, "data.items") == [{"a": 1}]

    async def test_a_bare_list_is_accepted(self) -> None:
        assert unwrap([{"a": 1}], None) == [{"a": 1}]

    async def test_scalars_are_wrapped(self) -> None:
        assert unwrap({"data": [1, 2]}, None) == [{"value": 1}, {"value": 2}]

    async def test_a_missing_path_yields_nothing(self) -> None:
        assert unwrap({"data": {}}, "data.nope") == []

    async def test_the_caller_token_is_forwarded(self, source_endpoints: SourceEndpoints) -> None:
        """RBAC stays with the service owning the data."""
        seen: dict[str, Any] = {}

        def handler(request: httpx.Request) -> httpx.Response:
            seen["auth"] = request.headers.get("Authorization")
            return httpx.Response(200, json={"data": []})

        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http_client:
            client = PlatformSourceClient(
                http_client, source_endpoints, caller_token="caller-token"
            )
            await client.fetch(DataSource.INVENTORY, "/inventory/assets")
        assert seen["auth"] == "Bearer caller-token"

    @pytest.mark.parametrize("status", [401, 403, 404, 500, 503])
    async def test_error_statuses_become_dependency_errors(
        self, source_endpoints: SourceEndpoints, status: int
    ) -> None:
        async with httpx.AsyncClient(
            transport=httpx.MockTransport(source_handler(status_code=status))
        ) as http_client:
            client = PlatformSourceClient(http_client, source_endpoints, caller_token="t")
            with pytest.raises(DependencyError, match=f"HTTP {status}"):
                await client.fetch(DataSource.INVENTORY, "/inventory/assets")

    async def test_an_unreachable_source(self, source_endpoints: SourceEndpoints) -> None:
        def handler(_request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("refused")

        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http_client:
            client = PlatformSourceClient(http_client, source_endpoints, caller_token="t")
            with pytest.raises(DependencyError, match="unreachable"):
                await client.fetch(DataSource.INVENTORY, "/inventory/assets")

    async def test_a_non_json_body(self, source_endpoints: SourceEndpoints) -> None:
        def handler(_request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, text="<html>not json</html>")

        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http_client:
            client = PlatformSourceClient(http_client, source_endpoints, caller_token="t")
            with pytest.raises(DependencyError, match="non-JSON"):
                await client.fetch(DataSource.INVENTORY, "/inventory/assets")

    async def test_the_row_ceiling_is_enforced(self, source_endpoints: SourceEndpoints) -> None:
        """A million rows would exhaust memory for everyone."""
        rows = [{"n": index} for index in range(20)]
        async with httpx.AsyncClient(
            transport=httpx.MockTransport(source_handler(rows))
        ) as http_client:
            client = PlatformSourceClient(
                http_client, source_endpoints, caller_token="t", max_rows=5
            )
            with pytest.raises(DependencyError, match="row ceiling"):
                await client.fetch(DataSource.INVENTORY, "/inventory/assets")

    @pytest.mark.parametrize("path", ["file:///etc/passwd", "/relative/path", "ftp://host/x"])
    async def test_a_custom_api_must_be_an_absolute_http_url(
        self, source_endpoints: SourceEndpoints, path: str
    ) -> None:
        """A template is user-authored; it must not aim the service anywhere."""
        async with httpx.AsyncClient() as http_client:
            client = PlatformSourceClient(http_client, source_endpoints, caller_token="t")
            with pytest.raises(ValidationError, match="absolute http"):
                await client.fetch(DataSource.CUSTOM_API, path)

    async def test_a_valid_custom_api_url_is_used_verbatim(
        self, source_endpoints: SourceEndpoints
    ) -> None:
        seen: dict[str, Any] = {}

        def handler(request: httpx.Request) -> httpx.Response:
            seen["url"] = str(request.url)
            return httpx.Response(200, json={"data": []})

        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http_client:
            client = PlatformSourceClient(http_client, source_endpoints, caller_token="t")
            await client.fetch(DataSource.CUSTOM_API, "https://third.party/api/rows")
        assert seen["url"].startswith("https://third.party/api/rows")


class TestAiSummaries:
    def test_context_is_bounded_and_says_so(self) -> None:
        rows = [{"n": index, "v": "x" * 40} for index in range(500)]
        context = build_context(rows, limit=10)
        assert "showing" in context
        assert len(context) < 6_500

    def test_empty_rows_yield_empty_context(self) -> None:
        assert build_context([]) == ""

    async def test_a_summary_carries_its_citations(self) -> None:
        def handler(_request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                201,
                json={
                    "success": True,
                    "data": {
                        "body": "The fleet is stable.",
                        "citations": [{"title": "Runbook", "score": 0.9}],
                    },
                },
            )

        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http_client:
            client = AiSummaryClient(http_client, base_url="http://ai.internal", caller_token="t")
            summary = await client.summarise(organization_id=uuid.uuid4(), instruction="Summarise.")
        assert summary.text == "The fleet is stable."
        assert summary.citations[0]["title"] == "Runbook"

    async def test_a_disabled_deployment_refuses_clearly(self) -> None:
        async with httpx.AsyncClient() as http_client:
            client = AiSummaryClient(
                http_client, base_url="http://ai.internal", caller_token="t", enabled=False
            )
            assert client.enabled is False
            with pytest.raises(DependencyError, match="disabled"):
                await client.summarise(organization_id=uuid.uuid4(), instruction="x")

    @pytest.mark.parametrize(
        ("status", "payload", "problem"),
        [
            (500, {"error": "boom"}, "HTTP 500"),
            (201, {"success": True, "data": {"body": "   "}}, "empty summary"),
        ],
    )
    async def test_assistant_failures_surface(
        self, status: int, payload: dict[str, Any], problem: str
    ) -> None:
        def handler(_request: httpx.Request) -> httpx.Response:
            return httpx.Response(status, json=payload)

        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http_client:
            client = AiSummaryClient(http_client, base_url="http://ai.internal", caller_token="t")
            with pytest.raises(DependencyError, match=problem):
                await client.summarise(organization_id=uuid.uuid4(), instruction="x")

    async def test_an_ai_section_degrades_rather_than_failing_the_report(
        self, db_session: AsyncSession, source_endpoints: SourceEndpoints
    ) -> None:
        """A capacity report with correct numbers is worth having."""
        org = uuid.uuid4()
        definition = {
            "title": "With AI",
            "sections": [
                {"key": "sum", "kind": "ai_summary", "title": "Summary", "ai_prompt": "Sum up."}
            ],
        }
        template = await make_template(db_session, organization_id=org, definition=definition)
        job = await make_job(db_session, organization_id=org, template_id=template.id)

        def handler(_request: httpx.Request) -> httpx.Response:
            return httpx.Response(503, json={"error": "down"})

        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http_client:
            renderer = ReportRenderer(
                PlatformSourceClient(http_client, source_endpoints, caller_token="t"),
                AiSummaryClient(http_client, base_url="http://ai.internal", caller_token="t"),
            )
            result = await generation_of(db_session, renderer).generate(job)

        assert result.succeeded
        assert result.degraded_sections == ["sum"]

    async def test_an_ai_section_renders_prose_and_citations(
        self, db_session: AsyncSession, source_endpoints: SourceEndpoints
    ) -> None:
        org = uuid.uuid4()
        definition = {
            "title": "With AI",
            "sections": [
                {"key": "sum", "kind": "ai_summary", "title": "Summary", "ai_prompt": "Sum up."}
            ],
        }
        template = await make_template(db_session, organization_id=org, definition=definition)
        job = await make_job(db_session, organization_id=org, template_id=template.id)

        def handler(_request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                201,
                json={
                    "success": True,
                    "data": {"body": "Stable.", "citations": [{"title": "Runbook", "score": 1}]},
                },
            )

        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http_client:
            renderer = ReportRenderer(
                PlatformSourceClient(http_client, source_endpoints, caller_token="t"),
                AiSummaryClient(http_client, base_url="http://ai.internal", caller_token="t"),
            )
            result = await generation_of(db_session, renderer).generate(job)

        assert result.report is not None
        section = result.report.sections[0]
        assert section.text == "Stable."
        assert section.rows[0]["title"] == "Runbook"

    async def test_ai_without_a_configured_client_is_reported(
        self, db_session: AsyncSession, renderer: ReportRenderer
    ) -> None:
        org = uuid.uuid4()
        definition = {
            "title": "With AI",
            "sections": [{"key": "sum", "kind": "ai_summary", "ai_prompt": "Sum up."}],
        }
        template = await make_template(db_session, organization_id=org, definition=definition)
        job = await make_job(db_session, organization_id=org, template_id=template.id)
        result = await generation_of(db_session, renderer).generate(job)
        assert result.degraded_sections == ["sum"]


class TestBaseColumnShadowing:
    """Regression: a domain column must never shadow a base column.

    :class:`shared_core.base.BaseEntityMixin` owns ``version`` for
    optimistic locking, and ``BaseRepository.update()`` increments it on
    every write. A model that redeclares ``version`` for its own meaning
    therefore gets that meaning silently corrupted by unrelated updates,
    *and* loses optimistic locking.

    This shipped here as a live bug -- archive generations jumped from
    1 to 4 across two updates -- and the same collision was found
    (latent) in ``services/secrets-management-service``'s encryption
    keys, where it would have corrupted key-rotation ordering.
    """

    async def test_archive_generation_is_untouched_by_updates(
        self, db_session: AsyncSession
    ) -> None:
        org = uuid.uuid4()
        job = await make_job(db_session, organization_id=org)
        execution = await ReportExecutionRepository(db_session).create(
            ReportExecution(
                organization_id=org, job_id=job.id, status=ReportExecutionStatus.SUCCEEDED
            )
        )
        record = await make_export(db_session, execution_id=execution.id, organization_id=org)
        service = ReportArchiveService(
            ReportArchiveRepository(db_session),
            ReportExportRepository(db_session),
            publish_event=RecordingPublisher(),
            retention_days=365,
        )
        archive = await service.archive_export(record, title="Fleet")
        assert archive.archive_version == 1

        repository = ReportArchiveRepository(db_session)
        for _ in range(3):
            await repository.update(archive)

        assert archive.archive_version == 1, "an unrelated update advanced the generation"
        assert archive.version > 1, "optimistic locking must still be advancing"

    async def test_no_reporting_model_shadows_a_base_column(self) -> None:
        """A static guard, so the next model cannot reintroduce this."""

        owned = {
            "id",
            "created_at",
            "updated_at",
            "deleted_at",
            "created_by",
            "updated_by",
            "deleted_by",
            "version",
            "is_active",
            "organization_id",
            "project_id",
        }
        offenders: list[str] = []
        for name in models_package.__all__:
            model = getattr(models_package, name)
            if not issubclass(model, BaseModel):
                continue
            # The class's *own* annotations, not the mapped attributes
            # SQLAlchemy installs -- those include every inherited
            # column and would flag all of them.
            declared = model.__dict__.get("__annotations__", {})
            offenders.extend(f"{name}.{column}" for column in sorted(owned & set(declared)))
        assert offenders == [], f"models shadowing a base column: {offenders}"
