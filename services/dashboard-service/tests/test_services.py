"""Service-layer tests against real Postgres.

Every test here runs against the live database with SAVEPOINT
isolation, so persistence, constraints, and -- critically -- what a row
looks like *after a genuine reload* are all exercised for real.

**The enum-identity class of bug is tested by reloading.** A model built
in memory holds a real enum member; a row read back from Postgres holds
a plain ``str``. Tests that never reload cannot tell the difference,
which is exactly why four dead features shipped across this platform
before anyone noticed. Every normaliser here is verified through
``await db_session.refresh(...)``.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from shared_core.database.base import BaseModel
from shared_core.exceptions.authorization import AuthorizationError
from shared_core.exceptions.conflict import ConflictError
from shared_core.exceptions.not_found import NotFoundError
from shared_core.exceptions.validation import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import dashboard as _dashboard_module  # noqa: F401  -- registers mappers
from app.models.dashboard_audit import DashboardAudit
from app.models.dashboard_view import DashboardView
from app.models.enums import (
    AuditAction,
    AuditOutcome,
    DashboardType,
    DashboardVisibility,
    LayoutBreakpoint,
    SharePermission,
    ThemeMode,
    WidgetType,
)
from app.repositories.dashboard import DashboardRepository
from app.repositories.dashboard_audit import DashboardAuditRepository
from app.repositories.dashboard_favorite import DashboardFavoriteRepository
from app.repositories.dashboard_filter import DashboardFilterRepository
from app.repositories.dashboard_history import DashboardHistoryRepository
from app.repositories.dashboard_layout import DashboardLayoutRepository
from app.repositories.dashboard_permission import DashboardPermissionRepository
from app.repositories.dashboard_share import DashboardShareRepository
from app.repositories.dashboard_statistics import DashboardStatisticsRepository
from app.repositories.dashboard_template import DashboardTemplateRepository
from app.repositories.dashboard_theme import DashboardThemeRepository
from app.repositories.dashboard_view import DashboardViewRepository
from app.repositories.dashboard_widget import DashboardWidgetRepository
from app.repositories.dashboard_widget_setting import DashboardWidgetSettingRepository
from app.services.audit import AuditService, action_of, outcome_of
from app.services.dashboard import DashboardService, breakpoint_of, visibility_of
from app.services.preferences import PreferencesService
from app.services.sharing import SharingService, permission_of
from app.services.statistics import StatisticsService, percentile
from app.services.template import TemplateService, type_of
from app.services.theme import SYSTEM_THEMES, ThemeService, mode_of
from app.widgets.resolver import WidgetResolver
from tests.conftest import (
    CHART_WIDGET,
    METRIC_WIDGET,
    TABLE_WIDGET,
    RecordingPublisher,
    make_dashboard,
    make_widget,
)

ORG = uuid.UUID("11111111-1111-1111-1111-111111111111")


def dashboard_service(
    session: AsyncSession, resolver: WidgetResolver, publisher: RecordingPublisher
) -> DashboardService:
    """A fully-wired dashboard service on one session."""
    return DashboardService(
        DashboardRepository(session),
        DashboardWidgetRepository(session),
        DashboardLayoutRepository(session),
        DashboardHistoryRepository(session),
        DashboardViewRepository(session),
        resolver,
        publish_event=publisher,
    )


def sharing_service(session: AsyncSession, publisher: RecordingPublisher) -> SharingService:
    """A fully-wired sharing service on one session."""
    return SharingService(
        DashboardRepository(session),
        DashboardShareRepository(session),
        DashboardPermissionRepository(session),
        publish_event=publisher,
    )


def preferences_service(session: AsyncSession) -> PreferencesService:
    """A fully-wired preferences service on one session."""
    return PreferencesService(
        DashboardRepository(session),
        DashboardWidgetRepository(session),
        DashboardFavoriteRepository(session),
        DashboardFilterRepository(session),
        DashboardWidgetSettingRepository(session),
    )


def statistics_service(session: AsyncSession) -> StatisticsService:
    """A fully-wired analytics service on one session."""
    return StatisticsService(
        DashboardRepository(session),
        DashboardWidgetRepository(session),
        DashboardViewRepository(session),
        DashboardShareRepository(session),
        DashboardStatisticsRepository(session),
    )


class TestEnumPersistence:
    """Every enum normaliser, verified through a genuine reload.

    These are the tests that would have caught the four dead features
    this platform shipped: prompt rendering, alert maintenance windows,
    automation remote dispatch, and GitOps conflict detection. Each
    passed its own suite because nothing ever reloaded the row.
    """

    async def test_visibility_survives_a_reload(self, db_session: AsyncSession) -> None:
        dashboard = await make_dashboard(
            db_session, organization_id=ORG, visibility=DashboardVisibility.ORGANIZATION
        )
        await db_session.commit()
        await db_session.refresh(dashboard)

        assert isinstance(dashboard.visibility, str)
        assert dashboard.visibility is not DashboardVisibility.ORGANIZATION, (
            "a reloaded row holds a plain str, which is the whole reason " "visibility_of() exists"
        )
        assert visibility_of(dashboard) is DashboardVisibility.ORGANIZATION

    async def test_breakpoint_survives_a_reload(
        self, db_session: AsyncSession, resolver: WidgetResolver, publisher: RecordingPublisher
    ) -> None:
        dashboard = await make_dashboard(db_session, organization_id=ORG)
        await make_widget(db_session, dashboard=dashboard)
        service = dashboard_service(db_session, resolver, publisher)
        layout = await service.save_layout(
            dashboard.id,
            breakpoint_=LayoutBreakpoint.MOBILE,
            placements=[{"widget_key": "hosts", "x": 0, "y": 0, "w": 12, "h": 3}],
        )
        await db_session.commit()
        await db_session.refresh(layout)

        assert breakpoint_of(layout) is LayoutBreakpoint.MOBILE

    async def test_share_permission_survives_a_reload(
        self, db_session: AsyncSession, publisher: RecordingPublisher
    ) -> None:
        dashboard = await make_dashboard(db_session, organization_id=ORG)
        sharing = sharing_service(db_session, publisher)
        share = await sharing.share_with_user(
            dashboard, user_id=uuid.uuid4(), permission=SharePermission.EDIT
        )
        await db_session.commit()
        await db_session.refresh(share)

        assert permission_of(share.permission) is SharePermission.EDIT

    async def test_audit_action_and_outcome_survive_a_reload(
        self, db_session: AsyncSession
    ) -> None:
        service = AuditService(DashboardAuditRepository(db_session))
        entry = await service.record_denied(
            organization_id=ORG,
            action=AuditAction.DASHBOARD_VIEWED,
            entity_type="dashboard",
            entity_id=uuid.uuid4(),
            actor_id=uuid.uuid4(),
            reason="no access",
        )
        assert entry is not None
        await db_session.commit()
        await db_session.refresh(entry)

        assert action_of(entry) is AuditAction.DASHBOARD_VIEWED
        assert outcome_of(entry) is AuditOutcome.DENIED

    async def test_theme_mode_survives_a_reload(self, db_session: AsyncSession) -> None:
        service = ThemeService(DashboardThemeRepository(db_session))
        theme, _findings = await service.create(
            organization_id=ORG, slug="corp", name="Corporate", mode=ThemeMode.DARK
        )
        await db_session.commit()
        await db_session.refresh(theme)

        assert mode_of(theme) is ThemeMode.DARK

    async def test_template_type_survives_a_reload(
        self, db_session: AsyncSession, resolver: WidgetResolver, publisher: RecordingPublisher
    ) -> None:
        service = TemplateService(
            DashboardTemplateRepository(db_session),
            dashboard_service(db_session, resolver, publisher),
        )
        template = await service.create(
            organization_id=ORG,
            slug="ops",
            name="Ops",
            definition={"dashboard_type": "operations", "widgets": [TABLE_WIDGET]},
        )
        await db_session.commit()
        await db_session.refresh(template)

        assert type_of(template) is DashboardType.OPERATIONS


class TestBaseColumnShadowing:
    """No model may redeclare a column ``BaseEntityMixin`` already owns.

    Redeclaring ``version`` silently repurposes the platform's
    optimistic-lock counter -- ``BaseRepository.update()`` increments it
    on every write, so a "document version" declared with that name
    walks 1, 2, 3, 4 on its own. That shipped live once in
    ``reporting-service`` and latent once in ``secrets-management``.
    """

    BASE_COLUMNS = frozenset(
        {
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
    )

    def test_no_model_redeclares_a_base_column(self) -> None:
        offenders: list[str] = []
        for model in BaseModel.__subclasses__():
            if not model.__module__.startswith("app.models"):
                continue
            declared = set(model.__dict__.get("__annotations__", {}))
            for column in declared & self.BASE_COLUMNS:
                offenders.append(f"{model.__name__}.{column}")
        assert (
            not offenders
        ), f"These models redeclare a BaseEntityMixin column: {', '.join(sorted(offenders))}"

    async def test_layout_revision_is_not_the_optimistic_lock_counter(
        self, db_session: AsyncSession, resolver: WidgetResolver, publisher: RecordingPublisher
    ) -> None:
        dashboard = await make_dashboard(db_session, organization_id=ORG)
        await make_widget(db_session, dashboard=dashboard)
        service = dashboard_service(db_session, resolver, publisher)

        first = await service.save_layout(
            dashboard.id,
            breakpoint_=LayoutBreakpoint.DESKTOP,
            placements=[{"widget_key": "hosts", "x": 0, "y": 0, "w": 6, "h": 3}],
        )
        second = await service.save_layout(
            dashboard.id,
            breakpoint_=LayoutBreakpoint.DESKTOP,
            placements=[{"widget_key": "hosts", "x": 6, "y": 0, "w": 6, "h": 3}],
        )
        assert (first.revision, second.revision) == (1, 2)
        assert second.version == 1, (
            "a freshly created row has never been updated, so the platform's "
            "own optimistic-lock counter must still be 1"
        )


class TestDashboardService:
    """CRUD, widgets, layouts, and loading."""

    async def test_create_publishes_an_event_and_records_history(
        self, db_session: AsyncSession, resolver: WidgetResolver, publisher: RecordingPublisher
    ) -> None:
        service = dashboard_service(db_session, resolver, publisher)
        dashboard = await service.create(
            organization_id=ORG,
            project_id=None,
            slug="fleet",
            name="Fleet",
            description=None,
            dashboard_type=DashboardType.INFRASTRUCTURE,
        )
        assert publisher.names == ["DashboardCreated"]
        history = await service.list_history(dashboard.id)
        assert [entry.event for entry in history] == ["created"]

    async def test_a_duplicate_slug_is_refused(
        self, db_session: AsyncSession, resolver: WidgetResolver, publisher: RecordingPublisher
    ) -> None:
        service = dashboard_service(db_session, resolver, publisher)
        kwargs: dict[str, Any] = {
            "organization_id": ORG,
            "project_id": None,
            "slug": "fleet",
            "name": "Fleet",
            "description": None,
            "dashboard_type": DashboardType.CUSTOM,
        }
        await service.create(**kwargs)
        with pytest.raises(ConflictError, match="already exists"):
            await service.create(**kwargs)

    async def test_a_malformed_default_filter_is_refused_at_create_time(
        self, db_session: AsyncSession, resolver: WidgetResolver, publisher: RecordingPublisher
    ) -> None:
        service = dashboard_service(db_session, resolver, publisher)
        with pytest.raises(ValidationError, match="unknown operator"):
            await service.create(
                organization_id=ORG,
                project_id=None,
                slug="bad",
                name="Bad",
                description=None,
                dashboard_type=DashboardType.CUSTOM,
                default_filters=[{"field": "env", "operator": "nope", "value": "prod"}],
            )

    async def test_update_changes_settings_and_announces_it(
        self, db_session: AsyncSession, resolver: WidgetResolver, publisher: RecordingPublisher
    ) -> None:
        dashboard = await make_dashboard(db_session, organization_id=ORG)
        service = dashboard_service(db_session, resolver, publisher)
        updated = await service.update(
            dashboard.id, name="Renamed", visibility=DashboardVisibility.ORGANIZATION
        )
        assert updated.name == "Renamed"
        assert visibility_of(updated) is DashboardVisibility.ORGANIZATION
        assert "DashboardUpdated" in publisher.names

    async def test_delete_is_soft_so_the_audit_trail_never_dangles(
        self, db_session: AsyncSession, resolver: WidgetResolver, publisher: RecordingPublisher
    ) -> None:
        dashboard = await make_dashboard(db_session, organization_id=ORG)
        service = dashboard_service(db_session, resolver, publisher)
        await service.delete(dashboard.id)

        with pytest.raises(NotFoundError):
            await service.get_by_id(dashboard.id)
        assert "DashboardDeleted" in publisher.names

    async def test_adding_a_widget_places_it_on_every_existing_layout(
        self, db_session: AsyncSession, resolver: WidgetResolver, publisher: RecordingPublisher
    ) -> None:
        dashboard = await make_dashboard(db_session, organization_id=ORG)
        service = dashboard_service(db_session, resolver, publisher)
        await service.add_widget(dashboard.id, definition=TABLE_WIDGET)
        await service.save_layout(
            dashboard.id,
            breakpoint_=LayoutBreakpoint.DESKTOP,
            placements=[{"widget_key": "hosts", "x": 0, "y": 0, "w": 6, "h": 3}],
        )
        await service.add_widget(dashboard.id, definition=METRIC_WIDGET)

        grid = await service.get_layout(dashboard.id)
        assert grid.widget_keys() == {"hosts", "host_count"}, (
            "a newly added widget must be visible immediately, not invisible "
            "until somebody drags it in"
        )

    async def test_removing_a_widget_leaves_no_hole(
        self, db_session: AsyncSession, resolver: WidgetResolver, publisher: RecordingPublisher
    ) -> None:
        dashboard = await make_dashboard(db_session, organization_id=ORG)
        service = dashboard_service(db_session, resolver, publisher)
        await service.add_widget(dashboard.id, definition=TABLE_WIDGET)
        await service.add_widget(dashboard.id, definition=METRIC_WIDGET)
        await service.save_layout(
            dashboard.id,
            breakpoint_=LayoutBreakpoint.DESKTOP,
            placements=[
                {"widget_key": "hosts", "x": 0, "y": 0, "w": 6, "h": 3},
                {"widget_key": "host_count", "x": 6, "y": 0, "w": 6, "h": 3},
            ],
        )
        await service.remove_widget(dashboard.id, "hosts")

        grid = await service.get_layout(dashboard.id)
        assert grid.widget_keys() == {"host_count"}
        assert "WidgetRemoved" in publisher.names

    async def test_a_widget_that_cannot_render_is_refused(
        self, db_session: AsyncSession, resolver: WidgetResolver, publisher: RecordingPublisher
    ) -> None:
        dashboard = await make_dashboard(db_session, organization_id=ORG)
        service = dashboard_service(db_session, resolver, publisher)
        with pytest.raises(ValidationError, match="Invalid widget definition"):
            await service.add_widget(
                dashboard.id,
                definition={"widget_key": "k", "title": "t", "widget_type": "line_chart"},
            )

    async def test_a_duplicate_widget_key_is_refused(
        self, db_session: AsyncSession, resolver: WidgetResolver, publisher: RecordingPublisher
    ) -> None:
        dashboard = await make_dashboard(db_session, organization_id=ORG)
        service = dashboard_service(db_session, resolver, publisher)
        await service.add_widget(dashboard.id, definition=TABLE_WIDGET)
        with pytest.raises(ConflictError, match="already used"):
            await service.add_widget(dashboard.id, definition=TABLE_WIDGET)

    async def test_the_widget_ceiling_is_enforced(
        self, db_session: AsyncSession, resolver: WidgetResolver, publisher: RecordingPublisher
    ) -> None:
        dashboard = await make_dashboard(db_session, organization_id=ORG)
        service = DashboardService(
            DashboardRepository(db_session),
            DashboardWidgetRepository(db_session),
            DashboardLayoutRepository(db_session),
            DashboardHistoryRepository(db_session),
            DashboardViewRepository(db_session),
            resolver,
            publish_event=publisher,
            max_widgets=1,
        )
        await service.add_widget(dashboard.id, definition=TABLE_WIDGET)
        with pytest.raises(ConflictError, match="maximum of 1 widgets"):
            await service.add_widget(dashboard.id, definition=METRIC_WIDGET)

    async def test_removing_an_absent_widget_is_a_not_found(
        self, db_session: AsyncSession, resolver: WidgetResolver, publisher: RecordingPublisher
    ) -> None:
        dashboard = await make_dashboard(db_session, organization_id=ORG)
        service = dashboard_service(db_session, resolver, publisher)
        with pytest.raises(NotFoundError, match="not on this dashboard"):
            await service.remove_widget(dashboard.id, "ghost")

    async def test_every_layout_save_is_a_new_row_so_undo_is_real(
        self, db_session: AsyncSession, resolver: WidgetResolver, publisher: RecordingPublisher
    ) -> None:
        dashboard = await make_dashboard(db_session, organization_id=ORG)
        await make_widget(db_session, dashboard=dashboard)
        service = dashboard_service(db_session, resolver, publisher)

        await service.save_layout(
            dashboard.id,
            breakpoint_=LayoutBreakpoint.DESKTOP,
            placements=[{"widget_key": "hosts", "x": 0, "y": 0, "w": 6, "h": 3}],
        )
        await service.save_layout(
            dashboard.id,
            breakpoint_=LayoutBreakpoint.DESKTOP,
            placements=[{"widget_key": "hosts", "x": 6, "y": 0, "w": 6, "h": 3}],
        )
        revisions = await service.list_layout_revisions(dashboard.id, LayoutBreakpoint.DESKTOP)
        assert [layout.revision for layout in revisions] == [2, 1]
        assert [layout.is_current for layout in revisions] == [True, False]

    async def test_restoring_points_at_the_earlier_row_rather_than_copying(
        self, db_session: AsyncSession, resolver: WidgetResolver, publisher: RecordingPublisher
    ) -> None:
        dashboard = await make_dashboard(db_session, organization_id=ORG)
        await make_widget(db_session, dashboard=dashboard)
        service = dashboard_service(db_session, resolver, publisher)
        await service.save_layout(
            dashboard.id,
            breakpoint_=LayoutBreakpoint.DESKTOP,
            placements=[{"widget_key": "hosts", "x": 0, "y": 0, "w": 6, "h": 3}],
        )
        await service.save_layout(
            dashboard.id,
            breakpoint_=LayoutBreakpoint.DESKTOP,
            placements=[{"widget_key": "hosts", "x": 6, "y": 0, "w": 6, "h": 3}],
        )
        restored = await service.restore_layout(
            dashboard.id, breakpoint_=LayoutBreakpoint.DESKTOP, revision=1
        )
        assert restored.revision == 1
        assert restored.placements[0]["x"] == 0

        revisions = await service.list_layout_revisions(dashboard.id, LayoutBreakpoint.DESKTOP)
        assert len(revisions) == 2, "restoring must not accumulate duplicate revisions"

    async def test_restoring_a_missing_revision_is_a_not_found(
        self, db_session: AsyncSession, resolver: WidgetResolver, publisher: RecordingPublisher
    ) -> None:
        dashboard = await make_dashboard(db_session, organization_id=ORG)
        service = dashboard_service(db_session, resolver, publisher)
        with pytest.raises(NotFoundError, match="does not exist"):
            await service.restore_layout(
                dashboard.id, breakpoint_=LayoutBreakpoint.DESKTOP, revision=99
            )

    async def test_a_layout_placing_an_unknown_widget_is_refused(
        self, db_session: AsyncSession, resolver: WidgetResolver, publisher: RecordingPublisher
    ) -> None:
        dashboard = await make_dashboard(db_session, organization_id=ORG)
        service = dashboard_service(db_session, resolver, publisher)
        with pytest.raises(ValidationError, match="does not have"):
            await service.save_layout(
                dashboard.id,
                breakpoint_=LayoutBreakpoint.DESKTOP,
                placements=[{"widget_key": "ghost", "x": 0, "y": 0, "w": 4, "h": 2}],
            )

    async def test_a_dashboard_with_no_saved_layout_still_renders(
        self, db_session: AsyncSession, resolver: WidgetResolver, publisher: RecordingPublisher
    ) -> None:
        dashboard = await make_dashboard(db_session, organization_id=ORG)
        await make_widget(db_session, dashboard=dashboard)
        service = dashboard_service(db_session, resolver, publisher)

        grid = await service.get_layout(dashboard.id)
        assert grid.widget_keys() == {
            "hosts"
        }, "a dashboard with widgets and no layout must appear arranged, not empty"

    async def test_load_resolves_every_widget_and_records_a_view(
        self, db_session: AsyncSession, resolver: WidgetResolver, publisher: RecordingPublisher
    ) -> None:
        dashboard = await make_dashboard(db_session, organization_id=ORG)
        await make_widget(db_session, dashboard=dashboard)
        service = dashboard_service(db_session, resolver, publisher)

        loaded = await service.load(dashboard.id, viewer_id=uuid.uuid4())
        assert len(loaded.widgets) == 1
        assert loaded.widgets[0].payload["rows"], "the stubbed source returns real rows"
        assert loaded.failed_widgets == []
        assert loaded.load_ms is not None

        views = await DashboardViewRepository(db_session).list_for_dashboard(dashboard.id)
        assert len(views) == 1
        assert views[0].widget_count == 1

    async def test_one_failing_widget_does_not_fail_the_dashboard(
        self, db_session: AsyncSession, resolver: WidgetResolver, publisher: RecordingPublisher
    ) -> None:
        dashboard = await make_dashboard(db_session, organization_id=ORG)
        await make_widget(db_session, dashboard=dashboard, widget_key="good")
        await make_widget(
            db_session,
            dashboard=dashboard,
            widget_key="broken",
            widget_type=WidgetType.TOPOLOGY_GRAPH,
            options={"topology": {"kind": "neighbors", "depth": 2}},
        )
        service = dashboard_service(db_session, resolver, publisher)

        loaded = await service.load(dashboard.id)
        assert loaded.failed_widgets == ["broken"]
        assert len(loaded.widgets) == 2, "the healthy widget still renders"

    async def test_disabled_widgets_are_skipped_on_load(
        self, db_session: AsyncSession, resolver: WidgetResolver, publisher: RecordingPublisher
    ) -> None:
        dashboard = await make_dashboard(db_session, organization_id=ORG)
        await make_widget(db_session, dashboard=dashboard, widget_key="on")
        await make_widget(db_session, dashboard=dashboard, widget_key="off", enabled=False)
        service = dashboard_service(db_session, resolver, publisher)

        loaded = await service.load(dashboard.id)
        assert [widget.widget_key for widget in loaded.widgets] == ["on"]

    async def test_dashboard_filters_narrow_every_widget_at_once(
        self, db_session: AsyncSession, resolver: WidgetResolver, publisher: RecordingPublisher
    ) -> None:
        dashboard = await make_dashboard(
            db_session,
            organization_id=ORG,
            default_filters=[{"field": "env", "operator": "eq", "value": "prod"}],
        )
        await make_widget(db_session, dashboard=dashboard)
        service = dashboard_service(db_session, resolver, publisher)

        loaded = await service.load(dashboard.id)
        assert loaded.widgets[0].row_count == 3, "one of the four sample rows is dev"

    async def test_listing_by_type_and_enabled(
        self, db_session: AsyncSession, resolver: WidgetResolver, publisher: RecordingPublisher
    ) -> None:
        await make_dashboard(
            db_session, organization_id=ORG, slug="a", dashboard_type=DashboardType.SECURITY
        )
        await make_dashboard(
            db_session, organization_id=ORG, slug="b", dashboard_type=DashboardType.CUSTOM
        )
        service = dashboard_service(db_session, resolver, publisher)

        found = await service.list_for_org(ORG, dashboard_type=DashboardType.SECURITY)
        assert [dashboard.slug for dashboard in found] == ["a"]


class TestSharingService:
    """Access control ("SHARING", "SECURITY")."""

    async def test_the_owner_always_has_manage(
        self, db_session: AsyncSession, publisher: RecordingPublisher
    ) -> None:
        owner = uuid.uuid4()
        dashboard = await make_dashboard(db_session, organization_id=ORG, owner_id=owner)
        access = await sharing_service(db_session, publisher).resolve_access(
            dashboard, user_id=owner
        )
        assert access.can_manage

    async def test_a_private_dashboard_is_denied_to_a_stranger(
        self, db_session: AsyncSession, publisher: RecordingPublisher
    ) -> None:
        dashboard = await make_dashboard(db_session, organization_id=ORG, owner_id=uuid.uuid4())
        access = await sharing_service(db_session, publisher).resolve_access(
            dashboard, user_id=uuid.uuid4()
        )
        assert not access.allowed
        assert not access.can_edit

    async def test_an_organization_dashboard_is_readable_by_anyone(
        self, db_session: AsyncSession, publisher: RecordingPublisher
    ) -> None:
        dashboard = await make_dashboard(
            db_session, organization_id=ORG, visibility=DashboardVisibility.ORGANIZATION
        )
        access = await sharing_service(db_session, publisher).resolve_access(
            dashboard, user_id=uuid.uuid4()
        )
        assert access.allowed
        assert access.permission is SharePermission.VIEW
        assert not access.can_edit

    async def test_the_strongest_grant_wins_regardless_of_evaluation_order(
        self, db_session: AsyncSession, publisher: RecordingPublisher
    ) -> None:
        viewer = uuid.uuid4()
        dashboard = await make_dashboard(
            db_session, organization_id=ORG, visibility=DashboardVisibility.ORGANIZATION
        )
        sharing = sharing_service(db_session, publisher)
        await sharing.share_with_user(dashboard, user_id=viewer, permission=SharePermission.EDIT)
        await sharing.grant_role(dashboard, role="viewer", permission=SharePermission.VIEW)

        access = await sharing.resolve_access(dashboard, user_id=viewer, roles=["viewer"])
        assert (
            access.permission is SharePermission.EDIT
        ), "a direct edit grant must not be masked by a weaker role grant"

    async def test_an_expired_share_grants_nothing(
        self, db_session: AsyncSession, publisher: RecordingPublisher
    ) -> None:
        viewer = uuid.uuid4()
        dashboard = await make_dashboard(db_session, organization_id=ORG)
        sharing = sharing_service(db_session, publisher)
        await sharing.share_with_user(
            dashboard,
            user_id=viewer,
            permission=SharePermission.EDIT,
            expires_at=datetime.now(UTC) - timedelta(minutes=1),
        )
        access = await sharing.resolve_access(dashboard, user_id=viewer)
        assert not access.allowed, "an expires_at nothing checks is decoration"

    async def test_a_revoked_share_grants_nothing(
        self, db_session: AsyncSession, publisher: RecordingPublisher
    ) -> None:
        viewer = uuid.uuid4()
        dashboard = await make_dashboard(db_session, organization_id=ORG)
        sharing = sharing_service(db_session, publisher)
        share = await sharing.share_with_user(dashboard, user_id=viewer)
        await sharing.revoke(share.id)

        access = await sharing.resolve_access(dashboard, user_id=viewer)
        assert not access.allowed

    async def test_revoking_keeps_the_row_for_the_audit_trail(
        self, db_session: AsyncSession, publisher: RecordingPublisher
    ) -> None:
        dashboard = await make_dashboard(db_session, organization_id=ORG)
        sharing = sharing_service(db_session, publisher)
        share = await sharing.share_with_user(dashboard, user_id=uuid.uuid4())
        revoked = await sharing.revoke(share.id)

        assert revoked.is_revoked
        assert revoked.revoked_at is not None
        assert (
            len(await sharing.list_shares(dashboard.id)) == 1
        ), "'who used to have access?' is a question a deleted row cannot answer"

    async def test_revoking_twice_is_refused(
        self, db_session: AsyncSession, publisher: RecordingPublisher
    ) -> None:
        dashboard = await make_dashboard(db_session, organization_id=ORG)
        sharing = sharing_service(db_session, publisher)
        share = await sharing.share_with_user(dashboard, user_id=uuid.uuid4())
        await sharing.revoke(share.id)
        with pytest.raises(ConflictError, match="already revoked"):
            await sharing.revoke(share.id)

    async def test_require_access_names_what_was_missing(
        self, db_session: AsyncSession, publisher: RecordingPublisher
    ) -> None:
        dashboard = await make_dashboard(
            db_session, organization_id=ORG, visibility=DashboardVisibility.ORGANIZATION
        )
        sharing = sharing_service(db_session, publisher)
        with pytest.raises(AuthorizationError, match="needs 'edit' access; you have 'view'"):
            await sharing.require_access(dashboard, user_id=uuid.uuid4(), need=SharePermission.EDIT)

    async def test_require_access_denies_a_stranger_outright(
        self, db_session: AsyncSession, publisher: RecordingPublisher
    ) -> None:
        dashboard = await make_dashboard(db_session, organization_id=ORG)
        with pytest.raises(AuthorizationError, match="do not have access"):
            await sharing_service(db_session, publisher).require_access(
                dashboard, user_id=uuid.uuid4()
            )

    async def test_a_link_resolves_and_counts_its_use(
        self, db_session: AsyncSession, publisher: RecordingPublisher
    ) -> None:
        dashboard = await make_dashboard(db_session, organization_id=ORG)
        sharing = sharing_service(db_session, publisher)
        share, token = await sharing.create_link(dashboard)

        assert len(token) >= 40, "a link token must carry real entropy"
        assert share.permission is SharePermission.VIEW

        resolved = await sharing.resolve_link(token)
        assert resolved.id == dashboard.id
        await db_session.refresh(share)
        assert share.access_count == 1

    async def test_an_unknown_token_is_a_not_found(
        self, db_session: AsyncSession, publisher: RecordingPublisher
    ) -> None:
        with pytest.raises(NotFoundError, match="not valid"):
            await sharing_service(db_session, publisher).resolve_link("nope")

    async def test_an_expired_link_is_refused(
        self, db_session: AsyncSession, publisher: RecordingPublisher
    ) -> None:
        dashboard = await make_dashboard(db_session, organization_id=ORG)
        sharing = SharingService(
            DashboardRepository(db_session),
            DashboardShareRepository(db_session),
            DashboardPermissionRepository(db_session),
            publish_event=publisher,
            link_ttl_seconds=60,
        )
        share, token = await sharing.create_link(dashboard)
        share.expires_at = datetime.now(UTC) - timedelta(seconds=1)
        await DashboardShareRepository(db_session).update(share)

        with pytest.raises(ConflictError, match="has expired"):
            await sharing.resolve_link(token)

    async def test_a_revoked_link_is_refused(
        self, db_session: AsyncSession, publisher: RecordingPublisher
    ) -> None:
        dashboard = await make_dashboard(db_session, organization_id=ORG)
        sharing = sharing_service(db_session, publisher)
        share, token = await sharing.create_link(dashboard)
        await sharing.revoke(share.id)

        with pytest.raises(ConflictError, match="been revoked"):
            await sharing.resolve_link(token)

    async def test_two_links_never_collide(
        self, db_session: AsyncSession, publisher: RecordingPublisher
    ) -> None:
        dashboard = await make_dashboard(db_session, organization_id=ORG)
        sharing = sharing_service(db_session, publisher)
        _first, one = await sharing.create_link(dashboard)
        _second, two = await sharing.create_link(dashboard)
        assert one != two

    async def test_granting_a_role_twice_updates_rather_than_duplicates(
        self, db_session: AsyncSession, publisher: RecordingPublisher
    ) -> None:
        dashboard = await make_dashboard(db_session, organization_id=ORG)
        sharing = sharing_service(db_session, publisher)
        await sharing.grant_role(dashboard, role="ops", permission=SharePermission.VIEW)
        await sharing.grant_role(dashboard, role="ops", permission=SharePermission.MANAGE)

        granted = await sharing.list_role_permissions(dashboard.id)
        assert len(granted) == 1
        assert permission_of(granted[0].permission) is SharePermission.MANAGE

    async def test_revoking_a_role_is_reported_honestly(
        self, db_session: AsyncSession, publisher: RecordingPublisher
    ) -> None:
        dashboard = await make_dashboard(db_session, organization_id=ORG)
        sharing = sharing_service(db_session, publisher)
        assert await sharing.revoke_role(dashboard.id, "ops") is False

        await sharing.grant_role(dashboard, role="ops")
        assert await sharing.revoke_role(dashboard.id, "ops") is True
        assert await sharing.revoke_role(dashboard.id, "ops") is False

    async def test_a_disabled_role_permission_grants_nothing(
        self, db_session: AsyncSession, publisher: RecordingPublisher
    ) -> None:
        dashboard = await make_dashboard(db_session, organization_id=ORG)
        sharing = sharing_service(db_session, publisher)
        await sharing.grant_role(dashboard, role="ops", permission=SharePermission.MANAGE)
        await sharing.revoke_role(dashboard.id, "ops")

        access = await sharing.resolve_access(dashboard, user_id=uuid.uuid4(), roles=["ops"])
        assert not access.allowed

    async def test_getting_a_missing_share_is_a_not_found(
        self, db_session: AsyncSession, publisher: RecordingPublisher
    ) -> None:
        with pytest.raises(NotFoundError):
            await sharing_service(db_session, publisher).get_share(uuid.uuid4())


class TestThemeService:
    """Themes and accessibility."""

    async def test_a_created_theme_reports_its_contrast_shortfalls(
        self, db_session: AsyncSession
    ) -> None:
        service = ThemeService(DashboardThemeRepository(db_session))
        _theme, findings = await service.create(
            organization_id=ORG,
            slug="pale",
            name="Pale",
            definition={"palette": {"text": "#eeeeee", "background": "#ffffff"}},
        )
        assert findings, "a shortfall is reported, not silently accepted"

    async def test_a_duplicate_slug_is_refused(self, db_session: AsyncSession) -> None:
        service = ThemeService(DashboardThemeRepository(db_session))
        await service.create(organization_id=ORG, slug="corp", name="Corp")
        with pytest.raises(ConflictError, match="already exists"):
            await service.create(organization_id=ORG, slug="corp", name="Corp again")

    async def test_a_malformed_palette_is_refused(self, db_session: AsyncSession) -> None:
        service = ThemeService(DashboardThemeRepository(db_session))
        with pytest.raises(ValidationError, match="Invalid theme definition"):
            await service.create(
                organization_id=ORG,
                slug="bad",
                name="Bad",
                definition={"palette": {"text": "rebeccapurple"}},
            )

    async def test_seeding_is_idempotent(self, db_session: AsyncSession) -> None:
        service = ThemeService(DashboardThemeRepository(db_session))
        created = await service.seed_system_themes(ORG)
        assert {theme.slug for theme in created} == set(SYSTEM_THEMES)
        assert await service.seed_system_themes(ORG) == []

    async def test_a_system_theme_cannot_be_edited_or_deleted(
        self, db_session: AsyncSession
    ) -> None:
        service = ThemeService(DashboardThemeRepository(db_session))
        seeded = await service.seed_system_themes(ORG)
        with pytest.raises(ConflictError, match="cannot be edited"):
            await service.update(seeded[0].id, name="Hijacked")
        with pytest.raises(ConflictError, match="cannot be deleted"):
            await service.delete(seeded[0].id)

    async def test_updating_a_theme_re_reports_contrast(self, db_session: AsyncSession) -> None:
        service = ThemeService(DashboardThemeRepository(db_session))
        theme, _findings = await service.create(organization_id=ORG, slug="corp", name="Corp")
        updated, findings = await service.update(
            theme.id, definition={"palette": {"text": "#dddddd", "background": "#ffffff"}}
        )
        assert updated.palette["text"] == "#dddddd"
        assert findings

    async def test_updating_without_a_definition_keeps_the_palette(
        self, db_session: AsyncSession
    ) -> None:
        service = ThemeService(DashboardThemeRepository(db_session))
        theme, _ = await service.create(organization_id=ORG, slug="corp", name="Corp")
        updated, findings = await service.update(theme.id, name="Renamed")
        assert updated.name == "Renamed"
        assert findings == []

    async def test_a_theme_audit_names_the_failing_pairs(self, db_session: AsyncSession) -> None:
        service = ThemeService(DashboardThemeRepository(db_session))
        theme, _ = await service.create(
            organization_id=ORG,
            slug="pale",
            name="Pale",
            definition={"palette": {"text": "#eeeeee", "background": "#ffffff"}},
        )
        report = service.audit(theme)
        assert report["wcag_aa"] is False
        assert report["findings"][0]["pair"]

    async def test_deleting_a_custom_theme_works(self, db_session: AsyncSession) -> None:
        service = ThemeService(DashboardThemeRepository(db_session))
        theme, _ = await service.create(organization_id=ORG, slug="corp", name="Corp")
        await service.delete(theme.id)
        assert await service.get_by_slug(ORG, "corp") is None


class TestTemplateService:
    """Templates ("Template Library")."""

    async def test_applying_a_template_creates_widgets_and_a_layout(
        self, db_session: AsyncSession, resolver: WidgetResolver, publisher: RecordingPublisher
    ) -> None:
        dashboards = dashboard_service(db_session, resolver, publisher)
        service = TemplateService(DashboardTemplateRepository(db_session), dashboards)
        template = await service.create(
            organization_id=ORG,
            slug="ops",
            name="Ops",
            definition={
                "dashboard_type": "operations",
                "widgets": [TABLE_WIDGET, CHART_WIDGET],
                "layouts": [
                    {
                        "breakpoint": "desktop",
                        "grid": {
                            "placements": [
                                {"widget_key": "hosts", "x": 0, "y": 0, "w": 6, "h": 3},
                                {"widget_key": "cpu_by_env", "x": 6, "y": 0, "w": 6, "h": 3},
                            ]
                        },
                    }
                ],
            },
        )
        dashboard = await service.apply(
            template.id, organization_id=ORG, slug="ops-live", name="Ops Live"
        )
        widgets = await dashboards.list_widgets(dashboard.id)
        assert {widget.widget_key for widget in widgets} == {"hosts", "cpu_by_env"}

        grid = await dashboards.get_layout(dashboard.id)
        assert grid.widget_keys() == {"hosts", "cpu_by_env"}
        await db_session.refresh(template)
        assert template.applied_count == 1

    async def test_an_incoherent_template_is_refused_at_write_time(
        self, db_session: AsyncSession, resolver: WidgetResolver, publisher: RecordingPublisher
    ) -> None:
        service = TemplateService(
            DashboardTemplateRepository(db_session),
            dashboard_service(db_session, resolver, publisher),
        )
        with pytest.raises(ValidationError):
            await service.create(
                organization_id=ORG,
                slug="broken",
                name="Broken",
                definition={
                    "widgets": [TABLE_WIDGET],
                    "layouts": [
                        {
                            "breakpoint": "desktop",
                            "grid": {
                                "placements": [
                                    {"widget_key": "ghost", "x": 0, "y": 0, "w": 4, "h": 2}
                                ]
                            },
                        }
                    ],
                },
            )

    async def test_capturing_a_dashboard_produces_an_appliable_template(
        self, db_session: AsyncSession, resolver: WidgetResolver, publisher: RecordingPublisher
    ) -> None:
        dashboards = dashboard_service(db_session, resolver, publisher)
        source = await dashboards.create(
            organization_id=ORG,
            project_id=None,
            slug="source",
            name="Source",
            description=None,
            dashboard_type=DashboardType.MONITORING,
        )
        await dashboards.add_widget(source.id, definition=TABLE_WIDGET)
        await dashboards.save_layout(
            source.id,
            breakpoint_=LayoutBreakpoint.DESKTOP,
            placements=[{"widget_key": "hosts", "x": 0, "y": 0, "w": 8, "h": 4}],
        )

        service = TemplateService(DashboardTemplateRepository(db_session), dashboards)
        template = await service.capture(source.id, slug="captured", name="Captured")
        clone = await service.apply(template.id, organization_id=ORG, slug="clone", name="Clone")
        cloned_grid = await dashboards.get_layout(clone.id)
        assert cloned_grid.widget_keys() == {"hosts"}
        assert cloned_grid.placements[0].w == 8

    async def test_a_duplicate_slug_is_refused(
        self, db_session: AsyncSession, resolver: WidgetResolver, publisher: RecordingPublisher
    ) -> None:
        service = TemplateService(
            DashboardTemplateRepository(db_session),
            dashboard_service(db_session, resolver, publisher),
        )
        await service.create(organization_id=ORG, slug="ops", name="Ops", definition={})
        with pytest.raises(ConflictError, match="already exists"):
            await service.create(organization_id=ORG, slug="ops", name="Ops", definition={})

    async def test_a_system_template_cannot_be_edited_or_deleted(
        self, db_session: AsyncSession, resolver: WidgetResolver, publisher: RecordingPublisher
    ) -> None:
        service = TemplateService(
            DashboardTemplateRepository(db_session),
            dashboard_service(db_session, resolver, publisher),
        )
        template = await service.create(
            organization_id=ORG, slug="builtin", name="Builtin", definition={}, is_system=True
        )
        with pytest.raises(ConflictError, match="cannot be edited"):
            await service.update(template.id, name="Hijacked")
        with pytest.raises(ConflictError, match="cannot be deleted"):
            await service.delete(template.id)

    async def test_updating_a_template_revalidates_its_definition(
        self, db_session: AsyncSession, resolver: WidgetResolver, publisher: RecordingPublisher
    ) -> None:
        service = TemplateService(
            DashboardTemplateRepository(db_session),
            dashboard_service(db_session, resolver, publisher),
        )
        template = await service.create(
            organization_id=ORG, slug="ops", name="Ops", definition={"widgets": [TABLE_WIDGET]}
        )
        updated = await service.update(
            template.id,
            name="Ops v2",
            definition={"dashboard_type": "security", "widgets": [METRIC_WIDGET]},
        )
        assert updated.name == "Ops v2"
        assert type_of(updated) is DashboardType.SECURITY
        assert service.definition_of(updated).widget_keys() == {"host_count"}


class TestPreferencesService:
    """Favourites, saved filters, and per-user widget overrides."""

    async def test_favouriting_twice_is_idempotent(self, db_session: AsyncSession) -> None:
        user = uuid.uuid4()
        dashboard = await make_dashboard(db_session, organization_id=ORG)
        service = preferences_service(db_session)

        first = await service.add_favorite(user_id=user, dashboard_id=dashboard.id)
        second = await service.add_favorite(user_id=user, dashboard_id=dashboard.id)
        assert first.id == second.id

    async def test_unfavouriting_reports_whether_anything_changed(
        self, db_session: AsyncSession
    ) -> None:
        user = uuid.uuid4()
        dashboard = await make_dashboard(db_session, organization_id=ORG)
        service = preferences_service(db_session)

        assert await service.remove_favorite(user_id=user, dashboard_id=dashboard.id) is False
        await service.add_favorite(user_id=user, dashboard_id=dashboard.id)
        assert await service.remove_favorite(user_id=user, dashboard_id=dashboard.id) is True

    async def test_reordering_keeps_unnamed_favourites(self, db_session: AsyncSession) -> None:
        user = uuid.uuid4()
        first = await make_dashboard(db_session, organization_id=ORG, slug="a", name="A")
        second = await make_dashboard(db_session, organization_id=ORG, slug="b", name="B")
        third = await make_dashboard(db_session, organization_id=ORG, slug="c", name="C")
        service = preferences_service(db_session)
        for dashboard in (first, second, third):
            await service.add_favorite(user_id=user, dashboard_id=dashboard.id)

        await service.reorder_favorites(organization_id=ORG, user_id=user, dashboard_ids=[third.id])
        ordered = await service.list_favorites(organization_id=ORG, user_id=user)
        assert [dashboard.slug for dashboard in ordered] == [
            "c",
            "a",
            "b",
        ], "a partial reorder must not silently unpin what was off-screen"

    async def test_reordering_an_unpinned_dashboard_is_refused(
        self, db_session: AsyncSession
    ) -> None:
        user = uuid.uuid4()
        dashboard = await make_dashboard(db_session, organization_id=ORG)
        with pytest.raises(ValidationError, match="not in your favourites"):
            await preferences_service(db_session).reorder_favorites(
                organization_id=ORG, user_id=user, dashboard_ids=[dashboard.id]
            )

    async def test_a_saved_filter_is_validated_on_write(self, db_session: AsyncSession) -> None:
        dashboard = await make_dashboard(db_session, organization_id=ORG)
        with pytest.raises(ValidationError, match="unknown operator"):
            await preferences_service(db_session).save_filter(
                dashboard.id,
                name="Bad",
                clauses=[{"field": "env", "operator": "nope", "value": "x"}],
            )

    async def test_saving_the_same_name_replaces_rather_than_duplicates(
        self, db_session: AsyncSession
    ) -> None:
        user = uuid.uuid4()
        dashboard = await make_dashboard(db_session, organization_id=ORG)
        service = preferences_service(db_session)
        await service.save_filter(
            dashboard.id,
            name="Prod",
            clauses=[{"field": "env", "operator": "eq", "value": "prod"}],
            user_id=user,
        )
        await service.save_filter(
            dashboard.id,
            name="Prod",
            clauses=[{"field": "env", "operator": "eq", "value": "production"}],
            user_id=user,
        )
        saved = await service.list_filters(dashboard.id, user_id=user)
        assert len(saved) == 1
        assert saved[0].clauses[0]["value"] == "production"

    async def test_a_personal_filter_and_a_shared_preset_coexist(
        self, db_session: AsyncSession
    ) -> None:
        user = uuid.uuid4()
        dashboard = await make_dashboard(db_session, organization_id=ORG)
        service = preferences_service(db_session)
        await service.save_filter(dashboard.id, name="Prod", clauses=[], user_id=user)
        await service.save_filter(dashboard.id, name="Prod", clauses=[], user_id=None)

        assert len(await service.list_filters(dashboard.id, user_id=user)) == 2

    async def test_a_user_cannot_delete_a_shared_preset(self, db_session: AsyncSession) -> None:
        dashboard = await make_dashboard(db_session, organization_id=ORG)
        service = preferences_service(db_session)
        preset = await service.save_filter(dashboard.id, name="Shared", clauses=[])
        with pytest.raises(ConflictError, match="shared preset"):
            await service.delete_filter(preset.id, user_id=uuid.uuid4())

    async def test_widget_overrides_are_stored_per_user(self, db_session: AsyncSession) -> None:
        dashboard = await make_dashboard(db_session, organization_id=ORG)
        widget = await make_widget(db_session, dashboard=dashboard)
        service = preferences_service(db_session)

        first = await service.set_widget_setting(widget.id, user_id=uuid.uuid4(), collapsed=True)
        second = await service.set_widget_setting(
            widget.id, user_id=uuid.uuid4(), collapsed=False, hidden=True
        )
        assert first.collapsed is True
        assert (
            second.collapsed is False
        ), "one person's collapse must not change what everyone else sees"
        assert widget.enabled is True, "the shared widget definition is untouched"

    async def test_setting_the_same_widget_twice_updates_in_place(
        self, db_session: AsyncSession
    ) -> None:
        user = uuid.uuid4()
        dashboard = await make_dashboard(db_session, organization_id=ORG)
        widget = await make_widget(db_session, dashboard=dashboard)
        service = preferences_service(db_session)

        await service.set_widget_setting(widget.id, user_id=user, collapsed=True)
        updated = await service.set_widget_setting(
            widget.id, user_id=user, refresh_seconds_override=120
        )
        assert updated.collapsed is True
        assert updated.refresh_seconds_override == 120
        assert len(await service.list_widget_settings(organization_id=ORG, user_id=user)) == 1

    async def test_an_absurd_refresh_override_is_refused(self, db_session: AsyncSession) -> None:
        dashboard = await make_dashboard(db_session, organization_id=ORG)
        widget = await make_widget(db_session, dashboard=dashboard)
        with pytest.raises(ValidationError, match="between 5 seconds"):
            await preferences_service(db_session).set_widget_setting(
                widget.id, user_id=uuid.uuid4(), refresh_seconds_override=1
            )

    async def test_overriding_a_missing_widget_is_a_not_found(
        self, db_session: AsyncSession
    ) -> None:
        with pytest.raises(NotFoundError, match="does not exist"):
            await preferences_service(db_session).set_widget_setting(
                uuid.uuid4(), user_id=uuid.uuid4(), collapsed=True
            )

    async def test_clearing_overrides_reports_whether_anything_changed(
        self, db_session: AsyncSession
    ) -> None:
        user = uuid.uuid4()
        dashboard = await make_dashboard(db_session, organization_id=ORG)
        widget = await make_widget(db_session, dashboard=dashboard)
        service = preferences_service(db_session)

        assert await service.clear_widget_setting(widget.id, user_id=user) is False
        await service.set_widget_setting(widget.id, user_id=user, collapsed=True)
        assert await service.clear_widget_setting(widget.id, user_id=user) is True

    async def test_a_favourite_pointing_at_a_deleted_dashboard_is_skipped(
        self, db_session: AsyncSession, resolver: WidgetResolver, publisher: RecordingPublisher
    ) -> None:
        user = uuid.uuid4()
        kept = await make_dashboard(db_session, organization_id=ORG, slug="kept")
        gone = await make_dashboard(db_session, organization_id=ORG, slug="gone")
        service = preferences_service(db_session)
        await service.add_favorite(user_id=user, dashboard_id=kept.id)
        await service.add_favorite(user_id=user, dashboard_id=gone.id)
        await dashboard_service(db_session, resolver, publisher).delete(gone.id)

        found = await service.list_favorites(organization_id=ORG, user_id=user)
        assert [dashboard.slug for dashboard in found] == ["kept"]


class TestStatisticsService:
    """Usage analytics ("ANALYTICS")."""

    def test_percentile_is_nearest_rank(self) -> None:
        values = [1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0, 9.0, 10.0]
        assert percentile(values, 0.5) == 5.0
        assert percentile(values, 0.95) == 10.0
        assert percentile([], 0.5) == 0.0

    async def test_a_rollup_is_derived_from_the_rows_that_exist(
        self, db_session: AsyncSession
    ) -> None:
        dashboard = await make_dashboard(db_session, organization_id=ORG)
        await make_widget(db_session, dashboard=dashboard)
        viewer = uuid.uuid4()
        for load_ms, failed in ((100.0, 0), (200.0, 1), (900.0, 0)):
            db_session.add(
                DashboardView(
                    organization_id=ORG,
                    dashboard_id=dashboard.id,
                    user_id=viewer,
                    load_ms=load_ms,
                    widget_count=2,
                    failed_widget_count=failed,
                    viewed_at=datetime.now(UTC),
                )
            )
        await db_session.flush()

        summary = await statistics_service(db_session).compute(ORG)
        assert summary.total_dashboards == 1
        assert summary.total_views == 3
        assert summary.unique_viewers == 1
        assert summary.median_load_ms == 200.0
        assert summary.p95_load_ms == 900.0
        assert summary.widget_failure_rate == pytest.approx(1 / 6, abs=0.001)
        assert summary.most_viewed[0]["name"] == "Fleet"
        assert summary.engagement["dashboards_viewed"] == 1
        assert summary.engagement["adoption_rate"] == 1.0

    async def test_an_organization_with_no_activity_reports_zeroes_not_errors(
        self, db_session: AsyncSession
    ) -> None:
        summary = await statistics_service(db_session).compute(uuid.uuid4())
        assert summary.total_views == 0
        assert summary.average_load_ms == 0.0
        assert summary.engagement["adoption_rate"] == 0.0

    async def test_refresh_updates_the_same_row_rather_than_appending(
        self, db_session: AsyncSession
    ) -> None:
        await make_dashboard(db_session, organization_id=ORG)
        service = statistics_service(db_session)

        first = await service.refresh(ORG)
        second = await service.refresh(ORG)
        assert first.id == second.id
        assert len(await DashboardStatisticsRepository(db_session).list_for_org(ORG)) == 1

    async def test_a_stored_rollup_can_be_read_back(self, db_session: AsyncSession) -> None:
        await make_dashboard(db_session, organization_id=ORG)
        service = statistics_service(db_session)
        assert await service.get(ORG) is None
        await service.refresh(ORG)
        stored = await service.get(ORG)
        assert stored is not None
        assert stored.total_dashboards == 1

    async def test_one_dashboard_usage_reports_percentiles(self, db_session: AsyncSession) -> None:
        dashboard = await make_dashboard(db_session, organization_id=ORG)
        for load_ms in (50.0, 150.0):
            db_session.add(
                DashboardView(
                    organization_id=ORG,
                    dashboard_id=dashboard.id,
                    user_id=uuid.uuid4(),
                    load_ms=load_ms,
                    widget_count=1,
                    failed_widget_count=0,
                    viewed_at=datetime.now(UTC),
                )
            )
        await db_session.flush()

        usage = await statistics_service(db_session).dashboard_usage(dashboard.id)
        assert usage["views"] == 2
        assert usage["average_load_ms"] == 100.0
        assert usage["p95_load_ms"] == 150.0
        assert usage["last_viewed_at"] is not None

    async def test_a_dashboard_with_no_views_reports_zeroes(self, db_session: AsyncSession) -> None:
        dashboard = await make_dashboard(db_session, organization_id=ORG)
        usage = await statistics_service(db_session).dashboard_usage(dashboard.id)
        assert usage == {
            "dashboard_id": str(dashboard.id),
            "views": 0,
            "unique_viewers": 0,
            "average_load_ms": 0.0,
            "median_load_ms": 0.0,
            "p95_load_ms": 0.0,
            "widget_failure_rate": 0.0,
            "last_viewed_at": None,
        }

    async def test_a_view_of_a_deleted_dashboard_is_labelled_not_dropped(
        self, db_session: AsyncSession, resolver: WidgetResolver, publisher: RecordingPublisher
    ) -> None:
        # A soft-deleted dashboard keeps its rows but drops out of the
        # name lookup, so the leaderboard would otherwise show a bare id.
        dashboard = await make_dashboard(db_session, organization_id=ORG)
        db_session.add(
            DashboardView(
                organization_id=ORG,
                dashboard_id=dashboard.id,
                user_id=None,
                load_ms=10.0,
                widget_count=1,
                failed_widget_count=0,
                viewed_at=datetime.now(UTC),
            )
        )
        await db_session.flush()
        await dashboard_service(db_session, resolver, publisher).delete(dashboard.id)

        summary = await statistics_service(db_session).compute(ORG)
        assert summary.most_viewed[0]["name"] == "(deleted dashboard)"
        assert summary.engagement["anonymous_views"] == 1


class TestAuditService:
    """The audit trail ("AUDIT")."""

    async def test_a_denial_is_recorded_as_such(self, db_session: AsyncSession) -> None:
        service = AuditService(DashboardAuditRepository(db_session))
        entry = await service.record_denied(
            organization_id=ORG,
            action=AuditAction.DASHBOARD_VIEWED,
            entity_type="dashboard",
            entity_id=uuid.uuid4(),
            actor_id=uuid.uuid4(),
            reason="not shared with you",
        )
        assert entry is not None
        assert outcome_of(entry) is AuditOutcome.DENIED
        assert entry.reason == "not shared with you"

    async def test_entries_come_back_newest_first(self, db_session: AsyncSession) -> None:
        service = AuditService(DashboardAuditRepository(db_session))
        for index in range(3):
            db_session.add(
                DashboardAudit(
                    organization_id=ORG,
                    action=AuditAction.DASHBOARD_VIEWED,
                    entity_type="dashboard",
                    reason=str(index),
                    occurred_at=datetime.now(UTC) + timedelta(seconds=index),
                )
            )
        await db_session.flush()
        entries = await service.list_for_org(ORG)
        assert [entry.reason for entry in entries] == ["2", "1", "0"]

    async def test_filtering_by_action(self, db_session: AsyncSession) -> None:
        service = AuditService(DashboardAuditRepository(db_session))
        await service.record(
            organization_id=ORG,
            action=AuditAction.DASHBOARD_CREATED,
            entity_type="dashboard",
        )
        await service.record(
            organization_id=ORG, action=AuditAction.WIDGET_ADDED, entity_type="widget"
        )
        found = await service.list_for_org(ORG, action=AuditAction.WIDGET_ADDED)
        assert len(found) == 1

    async def test_entity_history_is_scoped(self, db_session: AsyncSession) -> None:
        service = AuditService(DashboardAuditRepository(db_session))
        entity = uuid.uuid4()
        await service.record(
            organization_id=ORG,
            action=AuditAction.DASHBOARD_UPDATED,
            entity_type="dashboard",
            entity_id=entity,
        )
        await service.record(
            organization_id=ORG,
            action=AuditAction.DASHBOARD_UPDATED,
            entity_type="dashboard",
            entity_id=uuid.uuid4(),
        )
        assert len(await service.list_for_entity(entity)) == 1

    async def test_the_summary_counts_by_action_and_outcome(self, db_session: AsyncSession) -> None:
        service = AuditService(DashboardAuditRepository(db_session))
        await service.record(
            organization_id=ORG,
            action=AuditAction.DASHBOARD_VIEWED,
            entity_type="dashboard",
        )
        await service.record_denied(
            organization_id=ORG,
            action=AuditAction.DASHBOARD_VIEWED,
            entity_type="dashboard",
            entity_id=None,
            actor_id=None,
            reason="denied",
        )
        summary = await service.summarise(ORG)
        assert summary["total"] == 2
        assert summary["by_action"]["dashboard.viewed"] == 2
        assert summary["denied"] == 1

    async def test_an_audit_write_failure_never_fails_the_audited_action(
        self, db_session: AsyncSession
    ) -> None:
        class BrokenRepository(DashboardAuditRepository):
            async def create(self, entity: Any, **_kwargs: Any) -> Any:
                raise RuntimeError("the audit table is unavailable")

        service = AuditService(BrokenRepository(db_session))
        assert (
            await service.record(
                organization_id=ORG,
                action=AuditAction.DASHBOARD_VIEWED,
                entity_type="dashboard",
            )
            is None
        ), "a dashboard must still render when the audit insert deadlocks"
