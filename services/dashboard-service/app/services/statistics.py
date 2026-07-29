"""Dashboard usage analytics ("ANALYTICS").

Per docs/048: Dashboard Views, Popular Dashboards, Widget Usage, Load
Time, User Engagement, Feature Adoption.

**The rollup is derived, never incremented.** Every figure here is
recomputed from the ``dashboard_views``, ``dashboard_widgets``, and
``dashboard_shares`` rows that already exist, and the result is written
to the single :class:`~app.models.dashboard_statistics.DashboardStatistics`
row for the organization. A counter bumped on each view drifts the
moment one write is lost or one row is deleted, and there is no way to
tell that it has -- recomputing means the number is always explainable
by rows you can go and look at.

**Load time is reported as a median and a p95, not a mean.** A mean
load time is dominated by a handful of pathological loads and hides the
experience of everyone else; p95 is the figure that actually answers
"is this dashboard slow?".
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

from app.models.dashboard_statistics import DashboardStatistics
from app.models.dashboard_view import DashboardView
from app.repositories.dashboard import DashboardRepository
from app.repositories.dashboard_share import DashboardShareRepository
from app.repositories.dashboard_statistics import DashboardStatisticsRepository
from app.repositories.dashboard_view import DashboardViewRepository
from app.repositories.dashboard_widget import DashboardWidgetRepository

DEFAULT_WINDOW_DAYS = 30
"""How far back a rollup looks by default.

Thirty days rather than all time: "most viewed" should reflect what
people are using now, not a dashboard that was popular two years ago
and has since been abandoned.
"""

TOP_N = 10
"""How many entries the "most viewed" leaderboard carries."""


def percentile(values: list[float], fraction: float) -> float:
    """The *fraction* percentile of *values*, nearest-rank.

    Nearest-rank rather than interpolated: the answer is always an
    observation that genuinely happened, which is the right property for
    a latency figure someone is going to quote in a meeting.

    Returns ``0.0`` for an empty input -- an organization with no views
    has no latency, and inventing one would be worse than saying zero.
    """
    if not values:
        return 0.0
    ordered = sorted(values)
    index = max(0, min(len(ordered) - 1, round(fraction * len(ordered)) - 1))
    return float(ordered[index])


@dataclass(slots=True)
class UsageSummary:
    """Everything one rollup computed, before it is persisted."""

    total_dashboards: int = 0
    total_widgets: int = 0
    total_views: int = 0
    unique_viewers: int = 0
    total_shares: int = 0
    average_load_ms: float = 0.0
    median_load_ms: float = 0.0
    p95_load_ms: float = 0.0
    widget_failure_rate: float = 0.0
    most_viewed: list[dict[str, Any]] = field(default_factory=list)
    widget_usage: dict[str, int] = field(default_factory=dict)
    dashboard_type_usage: dict[str, int] = field(default_factory=dict)
    refresh_usage: dict[str, int] = field(default_factory=dict)
    engagement: dict[str, Any] = field(default_factory=dict)

    def as_columns(self) -> dict[str, Any]:
        """The subset persisted to :class:`DashboardStatistics`.

        ``most_viewed`` carries the latency percentiles alongside the
        leaderboard because the statistics table has no column for them
        and adding two floats to a JSON document beats a migration that
        would need repeating the next time an analytics question changes.
        """
        return {
            "total_dashboards": self.total_dashboards,
            "total_widgets": self.total_widgets,
            "total_views": self.total_views,
            "unique_viewers": self.unique_viewers,
            "total_shares": self.total_shares,
            "average_load_ms": self.average_load_ms,
            "widget_failure_rate": self.widget_failure_rate,
            "most_viewed": {
                "dashboards": self.most_viewed,
                "median_load_ms": self.median_load_ms,
                "p95_load_ms": self.p95_load_ms,
                "engagement": self.engagement,
            },
            "widget_usage": dict(self.widget_usage),
            "dashboard_type_usage": dict(self.dashboard_type_usage),
            "refresh_usage": dict(self.refresh_usage),
        }


class StatisticsService:
    """Computes and stores an organization's dashboard analytics."""

    def __init__(
        self,
        dashboards: DashboardRepository,
        widgets: DashboardWidgetRepository,
        views: DashboardViewRepository,
        shares: DashboardShareRepository,
        statistics: DashboardStatisticsRepository,
    ) -> None:
        self._dashboards = dashboards
        self._widgets = widgets
        self._views = views
        self._shares = shares
        self._statistics = statistics

    async def compute(
        self, organization_id: UUID, *, window_days: int = DEFAULT_WINDOW_DAYS
    ) -> UsageSummary:
        """Compute a rollup without storing it.

        Every read is sequential. An ``AsyncSession`` is not safe for
        concurrent use even for reads, so gathering these would be a
        latent ``InterfaceError`` under load rather than a speed-up.
        """
        since = datetime.now(UTC) - timedelta(days=max(1, window_days))
        dashboards = await self._dashboards.list_for_org(organization_id)
        widgets = await self._widgets.list_for_org(organization_id)
        views = await self._views.list_for_org(organization_id, since=since)
        shares = await self._shares.list_for_org(organization_id)

        names = {dashboard.id: dashboard.name for dashboard in dashboards}
        summary = UsageSummary(
            total_dashboards=len(dashboards),
            total_widgets=len(widgets),
            total_views=len(views),
            total_shares=sum(1 for share in shares if not share.is_revoked),
            unique_viewers=len({view.user_id for view in views if view.user_id is not None}),
            widget_usage=dict(Counter(str(widget.widget_type) for widget in widgets)),
            dashboard_type_usage=dict(
                Counter(str(dashboard.dashboard_type) for dashboard in dashboards)
            ),
            refresh_usage=dict(Counter(str(widget.refresh_mode) for widget in widgets)),
        )
        self._apply_latency(summary, views)
        self._apply_leaderboard(summary, views, names)
        summary.engagement = self._engagement(views, dashboards_total=len(dashboards))
        return summary

    async def refresh(
        self, organization_id: UUID, *, window_days: int = DEFAULT_WINDOW_DAYS
    ) -> DashboardStatistics:
        """Recompute and persist the organization's rollup.

        Updated in place rather than appended: the per-view history any
        trend is computed from already lives in ``dashboard_views``, so a
        second copy of it here would only be another thing to keep
        consistent.
        """
        summary = await self.compute(organization_id, window_days=window_days)
        columns = summary.as_columns()
        existing = await self._statistics.get_for_org(organization_id)
        if existing is not None:
            for column, value in columns.items():
                setattr(existing, column, value)
            existing.computed_at = datetime.now(UTC)
            return await self._statistics.update(existing)
        return await self._statistics.create(
            DashboardStatistics(
                organization_id=organization_id,
                computed_at=datetime.now(UTC),
                **columns,
            )
        )

    async def get(self, organization_id: UUID) -> DashboardStatistics | None:
        """The stored rollup, or ``None`` if none has been computed."""
        return await self._statistics.get_for_org(organization_id)

    async def dashboard_usage(self, dashboard_id: UUID, *, limit: int = 200) -> dict[str, Any]:
        """Usage figures for one dashboard.

        Scoped to a single dashboard so a "this dashboard is slow" claim
        can be checked against that dashboard's own loads rather than an
        organization-wide average it is hidden inside.
        """
        views = await self._views.list_for_dashboard(dashboard_id, limit=limit)
        durations = [view.load_ms for view in views if view.load_ms is not None]
        rendered = sum(view.widget_count for view in views)
        failed = sum(view.failed_widget_count for view in views)
        return {
            "dashboard_id": str(dashboard_id),
            "views": len(views),
            "unique_viewers": len({view.user_id for view in views if view.user_id is not None}),
            "average_load_ms": round(sum(durations) / len(durations), 2) if durations else 0.0,
            "median_load_ms": round(percentile(durations, 0.5), 2),
            "p95_load_ms": round(percentile(durations, 0.95), 2),
            "widget_failure_rate": round(failed / rendered, 4) if rendered else 0.0,
            "last_viewed_at": views[0].viewed_at.isoformat() if views else None,
        }

    @staticmethod
    def _apply_latency(summary: UsageSummary, views: list[DashboardView]) -> None:
        """Fill in the load-time and failure figures."""
        durations = [view.load_ms for view in views if view.load_ms is not None]
        if durations:
            summary.average_load_ms = round(sum(durations) / len(durations), 2)
            summary.median_load_ms = round(percentile(durations, 0.5), 2)
            summary.p95_load_ms = round(percentile(durations, 0.95), 2)

        rendered = sum(view.widget_count for view in views)
        if rendered:
            failed = sum(view.failed_widget_count for view in views)
            summary.widget_failure_rate = round(failed / rendered, 4)

    @staticmethod
    def _apply_leaderboard(
        summary: UsageSummary, views: list[DashboardView], names: dict[UUID, str]
    ) -> None:
        """Fill in the "most viewed" leaderboard."""
        counts = Counter(view.dashboard_id for view in views)
        summary.most_viewed = [
            {
                "dashboard_id": str(dashboard_id),
                "name": names.get(dashboard_id, "(deleted dashboard)"),
                "views": count,
            }
            for dashboard_id, count in counts.most_common(TOP_N)
        ]

    @staticmethod
    def _engagement(views: list[DashboardView], *, dashboards_total: int) -> dict[str, Any]:
        """User-engagement and feature-adoption figures.

        *Adoption* is the share of dashboards anybody actually opened in
        the window. A platform with two hundred dashboards and nine in
        use has a discoverability problem, and no view counter on its own
        makes that visible.
        """
        viewers = Counter(str(view.user_id) for view in views if view.user_id is not None)
        touched = {view.dashboard_id for view in views}
        return {
            "views_per_viewer": round(sum(viewers.values()) / len(viewers), 2) if viewers else 0.0,
            "most_active_viewers": [
                {"user_id": user_id, "views": count} for user_id, count in viewers.most_common(5)
            ],
            "dashboards_viewed": len(touched),
            "adoption_rate": (
                round(len(touched) / dashboards_total, 4) if dashboards_total else 0.0
            ),
            "anonymous_views": sum(1 for view in views if view.user_id is None),
        }


__all__ = [
    "DEFAULT_WINDOW_DAYS",
    "TOP_N",
    "StatisticsService",
    "UsageSummary",
    "percentile",
]
