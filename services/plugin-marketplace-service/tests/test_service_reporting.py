"""Tests for ``app.services.reporting`` -- ``StatisticsService``,
``ReportService``, and ``AuditService``.
"""

from __future__ import annotations

import uuid
from typing import Any

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.models.enums import AuditAction, ReportKind, ReportStatus
from app.repositories.governance import PluginAuditRepository, PluginStatisticRepository
from app.services.installation import PluginInstallationService
from app.services.plugin import PluginService
from app.services.publisher import PluginPublisherService
from app.services.reporting import AuditService, ReportService, StatisticsService
from app.services.review import PluginReviewService
from tests.conftest import MakePluginFn, ago, soon


def _manifest(version: str = "1.0.0") -> dict[str, Any]:
    from app.manifests.engine import compute_manifest_checksum

    manifest: dict[str, Any] = {
        "name": "Reporting Test Plugin",
        "publisher": "test-publisher",
        "category": "utilities",
        "type": "custom_plugin",
        "version": version,
        "entry_points": ["main:run"],
        "supported_platform_versions": [
            {"platform": "aiios", "version_constraint": ">=1.0.0,<2.0.0"}
        ],
        "permissions_required": [],
        "dependencies": [],
        "api_requirements": [],
        "health_checks": [],
    }
    manifest["checksum"] = compute_manifest_checksum(manifest)
    return manifest


async def _make_published_plugin(
    make_plugin: MakePluginFn,
    plugin_service: PluginService,
    organization_id: uuid.UUID,
    *,
    slug: str,
) -> Any:
    plugin = await make_plugin(slug=slug)
    await plugin_service.submit_manifest(
        organization_id, plugin.id, version_number="1.0.0", manifest=_manifest()
    )
    await plugin_service.publish(organization_id, plugin.id, version_number="1.0.0")
    return await plugin_service.get(organization_id, plugin.id)


# =============================== StatisticsService ============================


async def test_rollup_produces_correct_counts(
    statistics_service: StatisticsService,
    make_plugin: MakePluginFn,
    plugin_service: PluginService,
    installation_service: PluginInstallationService,
    review_service: PluginReviewService,
    organization_id: uuid.UUID,
) -> None:
    plugin = await _make_published_plugin(
        make_plugin, plugin_service, organization_id, slug="stats-plugin"
    )
    await installation_service.install(organization_id, plugin.id)
    await review_service.submit(organization_id, plugin.id, reviewer_id="r1", rating=4)
    await review_service.submit(organization_id, plugin.id, reviewer_id="r2", rating=2)

    window_start = ago(3600)
    window_end = soon(3600)
    stat = await statistics_service.rollup(
        organization_id, window_start=window_start, window_end=window_end
    )

    assert stat.window_start == window_start
    assert stat.window_end == window_end
    assert stat.plugins_published == 1
    assert stat.installations_attempted == 1
    assert stat.installations_succeeded == 1
    assert stat.installations_failed == 0
    assert stat.reviews_submitted == 2
    assert stat.average_rating == pytest.approx(3.0)
    assert stat.by_category.get("utilities") == 1


async def test_rollup_same_window_start_updates_not_duplicates(
    statistics_service: StatisticsService,
    make_plugin: MakePluginFn,
    plugin_service: PluginService,
    statistics_repo: PluginStatisticRepository,
    organization_id: uuid.UUID,
) -> None:
    window_start = ago(3600)
    window_end = soon(3600)

    first = await statistics_service.rollup(
        organization_id, window_start=window_start, window_end=window_end
    )
    assert first.plugins_published == 0

    await _make_published_plugin(
        make_plugin, plugin_service, organization_id, slug="stats-second-plugin"
    )
    second = await statistics_service.rollup(
        organization_id, window_start=window_start, window_end=window_end
    )

    assert second.id == first.id
    assert second.plugins_published == 1

    rows = await statistics_repo.list_since(organization_id, since=window_start)
    matching = [row for row in rows if row.window_start == window_start]
    assert len(matching) == 1


async def test_dashboard_reflects_latest_window(
    statistics_service: StatisticsService, organization_id: uuid.UUID
) -> None:
    assert (await statistics_service.dashboard(organization_id))["latest_window"][
        "computed_through"
    ] is None

    early = await statistics_service.rollup(
        organization_id, window_start=ago(7200), window_end=ago(3600)
    )
    late = await statistics_service.rollup(
        organization_id, window_start=ago(3600), window_end=soon(3600)
    )
    assert early.window_end < late.window_end

    dashboard = await statistics_service.dashboard(organization_id)
    assert dashboard["latest_window"]["computed_through"] == late.window_end.isoformat()


async def test_trend_returns_windows_since_n_days_oldest_first(
    statistics_service: StatisticsService, organization_id: uuid.UUID
) -> None:
    older = await statistics_service.rollup(
        organization_id, window_start=ago(172_800), window_end=ago(86_400)
    )
    newer = await statistics_service.rollup(
        organization_id, window_start=ago(3600), window_end=soon(3600)
    )

    trend = await statistics_service.trend(organization_id, since_days=30)

    assert [row.id for row in trend] == [older.id, newer.id]


# =============================== ReportService =================================


async def test_generate_marketplace_report(
    report_service: ReportService,
    make_plugin: MakePluginFn,
    plugin_service: PluginService,
    organization_id: uuid.UUID,
) -> None:
    published = await _make_published_plugin(
        make_plugin, plugin_service, organization_id, slug="report-marketplace-published"
    )
    unpublished = await make_plugin(slug="report-marketplace-unpublished")

    report = await report_service.generate(organization_id, kind=ReportKind.MARKETPLACE)

    assert report.status == ReportStatus.COMPLETED
    assert report.row_count == 2
    assert report.generated_at is not None
    assert report.duration_ms is not None
    rows_by_name = {row["name"]: row for row in report.content["rows"]}
    assert rows_by_name[published.name]["current_version_number"] == "1.0.0"
    assert rows_by_name[published.name]["status"] == "published"
    assert rows_by_name[unpublished.name]["current_version_number"] is None
    assert rows_by_name[unpublished.name]["status"] == "registered"


async def test_generate_publisher_report(
    report_service: ReportService,
    publisher_service: PluginPublisherService,
    organization_id: uuid.UUID,
) -> None:
    await publisher_service.register(
        organization_id, slug="report-publisher", display_name="Report Publisher Inc."
    )

    report = await report_service.generate(organization_id, kind=ReportKind.PUBLISHER)

    assert report.status == ReportStatus.COMPLETED
    assert report.row_count == 1
    row = report.content["rows"][0]
    assert row["display_name"] == "Report Publisher Inc."
    assert row["verification_status"] == "unverified"
    assert row["published_plugin_count"] == 0


async def test_generate_installation_report(
    report_service: ReportService,
    make_plugin: MakePluginFn,
    plugin_service: PluginService,
    installation_service: PluginInstallationService,
    organization_id: uuid.UUID,
) -> None:
    plugin = await _make_published_plugin(
        make_plugin, plugin_service, organization_id, slug="report-installation-plugin"
    )
    installation = await installation_service.install(organization_id, plugin.id)

    report = await report_service.generate(organization_id, kind=ReportKind.INSTALLATION)

    assert report.status == ReportStatus.COMPLETED
    assert report.row_count == 1
    row = report.content["rows"][0]
    assert row["plugin_id"] == str(plugin.id)
    assert row["status"] == "installed"
    assert row["installed_version_number"] == "1.0.0"
    assert row["installed_at"] == installation.installed_at.isoformat()


async def test_generate_audit_report(
    report_service: ReportService,
    audit_service: AuditService,
    organization_id: uuid.UUID,
) -> None:
    await audit_service.record(
        organization_id,
        action=AuditAction.PLUGIN_INSTALLED,
        entity_type="plugin_installation",
        summary="Installed for report test.",
        actor_id="reporter-1",
    )

    report = await report_service.generate(organization_id, kind=ReportKind.AUDIT)

    assert report.status == ReportStatus.COMPLETED
    assert report.row_count == 1
    row = report.content["rows"][0]
    assert row["action"] == "plugin_installed"
    assert row["entity_type"] == "plugin_installation"
    assert row["actor_id"] == "reporter-1"
    assert row["succeeded"] is True


@pytest.mark.parametrize(
    "kind", [ReportKind.PLUGIN_HEALTH, ReportKind.COMPATIBILITY, ReportKind.SECURITY]
)
async def test_generate_kinds_without_builder_completes_with_zero_rows(
    report_service: ReportService, organization_id: uuid.UUID, kind: ReportKind
) -> None:
    report = await report_service.generate(organization_id, kind=kind)

    assert report.status == ReportStatus.COMPLETED
    assert report.row_count == 0
    assert report.content == {"rows": []}
    assert report.error is None


async def test_require_in_org_and_list_for_org(
    report_service: ReportService, organization_id: uuid.UUID
) -> None:
    first = await report_service.generate(organization_id, kind=ReportKind.MARKETPLACE)
    second = await report_service.generate(organization_id, kind=ReportKind.AUDIT)

    fetched = await report_service.require_in_org(organization_id, first.id)
    assert fetched.id == first.id

    all_reports = await report_service.list_for_org(organization_id)
    assert {r.id for r in all_reports} == {first.id, second.id}


async def test_require_in_org_missing_report_raises_not_found(
    report_service: ReportService, organization_id: uuid.UUID
) -> None:
    from shared_core.exceptions.not_found import NotFoundError

    with pytest.raises(NotFoundError):
        await report_service.require_in_org(organization_id, uuid.uuid4())


def test_to_csv_empty_content_returns_empty_string() -> None:
    assert ReportService.to_csv({"rows": []}) == ""


def test_to_csv_non_empty_content() -> None:
    content = {"rows": [{"a": 1, "b": 2}, {"a": 3, "b": 4}]}

    csv_text = ReportService.to_csv(content)

    assert csv_text == "a,b\r\n1,2\r\n3,4\r\n"


def test_to_markdown_empty_content() -> None:
    markdown = ReportService.to_markdown({"rows": []}, title="Empty Report")

    assert markdown == "# Empty Report\n\nNo rows."


def test_to_markdown_non_empty_content() -> None:
    content = {"rows": [{"a": 1, "b": 2}, {"a": 3, "b": 4}]}

    markdown = ReportService.to_markdown(content, title="My Report")

    assert markdown == (
        "# My Report\n\n| a | b |\n| --- | --- |\n| 1 | 2 |\n| 3 | 4 |"
    )


# =============================== AuditService ==================================


async def test_record_creates_row_with_correct_fields(
    audit_service: AuditService, organization_id: uuid.UUID
) -> None:
    entity_id = uuid.uuid4()

    entry = await audit_service.record(
        organization_id,
        action=AuditAction.PLUGIN_ACTIVATED,
        entity_type="plugin_installation",
        summary="Activated the plugin.",
        entity_id=entity_id,
        entity_reference="activate-1",
        actor_id="user-3",
        actor_type="service",
        succeeded=True,
        changes={"status": "active"},
        context={"trigger": "manual"},
        request_id="req-2",
        ip_address="127.0.0.1",
    )

    assert entry.organization_id == organization_id
    assert entry.action == AuditAction.PLUGIN_ACTIVATED
    assert entry.entity_type == "plugin_installation"
    assert entry.entity_id == entity_id
    assert entry.entity_reference == "activate-1"
    assert entry.actor_id == "user-3"
    assert entry.actor_type == "service"
    assert entry.succeeded is True
    assert entry.changes == {"status": "active"}
    assert entry.context == {"trigger": "manual"}
    assert entry.request_id == "req-2"
    assert entry.ip_address == "127.0.0.1"
    assert entry.occurred_at is not None


async def test_record_failure_without_session_factory_behaves_like_record_with_succeeded_false(
    audit_service: AuditService,
    audit_repo: PluginAuditRepository,
    organization_id: uuid.UUID,
) -> None:
    await audit_service.record_failure(
        organization_id,
        action=AuditAction.PLUGIN_REMOVED,
        entity_type="plugin_installation",
        summary="Remove refused.",
        entity_reference="remove-attempt-1",
        actor_id="user-2",
        request_id="req-1",
        context={"reason": "not_found"},
    )

    entries = await audit_repo.list_for_org(organization_id)
    matching = [e for e in entries if e.entity_reference == "remove-attempt-1"]
    assert len(matching) == 1
    assert matching[0].succeeded is False
    assert matching[0].actor_id == "user-2"
    assert matching[0].action == AuditAction.PLUGIN_REMOVED
    assert matching[0].request_id == "req-1"
    assert matching[0].context == {"reason": "not_found"}


async def test_record_failure_with_session_factory_commits_via_fresh_session(
    audit_repo: PluginAuditRepository,
    db_session_factory: async_sessionmaker[AsyncSession],
    organization_id: uuid.UUID,
) -> None:
    service = AuditService(audit_repo, session_factory=db_session_factory)

    await service.record_failure(
        organization_id,
        action=AuditAction.PLUGIN_INSTALLED,
        entity_type="plugin_installation",
        summary="Install refused: dependency not installed.",
        entity_reference="install-attempt-1",
        actor_id="user-1",
        request_id="req-99",
        context={"reason": "missing_dependency"},
    )

    # Prove the row landed via a genuinely *different* session on the same
    # SAVEPOINT-isolated connection, not merely sitting in the original
    # session's own pending/identity-map state.
    async with db_session_factory() as fresh_session:
        fresh_repo = PluginAuditRepository(fresh_session)
        entries = await fresh_repo.list_for_org(organization_id)

    matching = [e for e in entries if e.entity_reference == "install-attempt-1"]
    assert len(matching) == 1
    entry = matching[0]
    assert entry.succeeded is False
    assert entry.action == AuditAction.PLUGIN_INSTALLED
    assert entry.entity_type == "plugin_installation"
    assert entry.actor_id == "user-1"
    assert entry.actor_type == "user"
    assert entry.request_id == "req-99"
    assert entry.context == {"reason": "missing_dependency"}


async def test_list_entries_with_action_filter(
    audit_service: AuditService, organization_id: uuid.UUID
) -> None:
    await audit_service.record(
        organization_id,
        action=AuditAction.PLUGIN_INSTALLED,
        entity_type="plugin_installation",
        summary="installed",
    )
    await audit_service.record(
        organization_id,
        action=AuditAction.PLUGIN_REMOVED,
        entity_type="plugin_installation",
        summary="removed",
    )

    installed_entries = await audit_service.list_entries(
        organization_id, action=AuditAction.PLUGIN_INSTALLED
    )
    assert len(installed_entries) == 1
    assert installed_entries[0].action == AuditAction.PLUGIN_INSTALLED

    all_entries = await audit_service.list_entries(organization_id)
    assert len(all_entries) == 2


async def test_summary_counts_by_action(
    audit_service: AuditService, organization_id: uuid.UUID
) -> None:
    await audit_service.record(
        organization_id,
        action=AuditAction.PLUGIN_INSTALLED,
        entity_type="plugin_installation",
        summary="a",
    )
    await audit_service.record(
        organization_id,
        action=AuditAction.PLUGIN_INSTALLED,
        entity_type="plugin_installation",
        summary="b",
    )
    await audit_service.record(
        organization_id,
        action=AuditAction.PLUGIN_REMOVED,
        entity_type="plugin_installation",
        summary="c",
    )

    summary = await audit_service.summary(organization_id, days=30)

    assert summary["total"] == 3
    assert summary["by_action"]["plugin_installed"] == 2
    assert summary["by_action"]["plugin_removed"] == 1
    assert "since" in summary
