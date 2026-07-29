"""Per-user dashboard preferences.

Covers docs/048's "Favorites", "Saved Filters", and the per-user widget
overrides that make a shared dashboard usable by more than one person.

**A preference never changes what anyone else sees.** A shared
dashboard has one definition and many viewers, so collapsing a widget,
slowing its refresh, or pinning the dashboard is stored against the
user, not the dashboard. Writing any of these back onto
:class:`~app.models.dashboard_widget.DashboardWidget` would let one
person's convenience silently reconfigure a dashboard an entire
operations team is watching.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from shared_core.exceptions.conflict import ConflictError
from shared_core.exceptions.not_found import NotFoundError
from shared_core.exceptions.validation import ValidationError

from app.filters.engine import parse_clauses
from app.models.dashboard import Dashboard
from app.models.dashboard_favorite import DashboardFavorite
from app.models.dashboard_filter import DashboardFilter
from app.models.dashboard_widget_setting import DashboardWidgetSetting
from app.repositories.dashboard import DashboardRepository
from app.repositories.dashboard_favorite import DashboardFavoriteRepository
from app.repositories.dashboard_filter import DashboardFilterRepository
from app.repositories.dashboard_widget import DashboardWidgetRepository
from app.repositories.dashboard_widget_setting import DashboardWidgetSettingRepository

MIN_REFRESH_SECONDS = 5
"""The fastest a user may set one widget to refresh.

Below this, a single dashboard left open overnight becomes a sustained
denial-of-service against the thirteen source services it queries.
"""

MAX_REFRESH_SECONDS = 86_400
"""The slowest useful refresh -- beyond a day, the page reload wins."""


class PreferencesService:
    """Favourites, saved filters, and per-user widget overrides."""

    def __init__(
        self,
        dashboards: DashboardRepository,
        widgets: DashboardWidgetRepository,
        favorites: DashboardFavoriteRepository,
        filters: DashboardFilterRepository,
        settings: DashboardWidgetSettingRepository,
    ) -> None:
        self._dashboards = dashboards
        self._widgets = widgets
        self._favorites = favorites
        self._filters = filters
        self._settings = settings

    # ---- favourites ------------------------------------------------

    async def add_favorite(self, *, user_id: UUID, dashboard_id: UUID) -> DashboardFavorite:
        """Pin a dashboard for one user.

        Idempotent: favouriting twice returns the existing row rather
        than raising. A star that errors when you click it twice is a
        worse experience than one that simply stays starred, and the
        unique constraint guarantees the outcome either way.

        Raises:
            NotFoundError: If the dashboard does not exist.
        """
        dashboard = await self._dashboards.require_by_id(dashboard_id)
        existing = await self._favorites.get_for_user_dashboard(user_id, dashboard_id)
        if existing is not None:
            return existing

        pinned = await self._favorites.list_for_user(dashboard.organization_id, user_id)
        return await self._favorites.create(
            DashboardFavorite(
                organization_id=dashboard.organization_id,
                project_id=dashboard.project_id,
                user_id=user_id,
                dashboard_id=dashboard_id,
                display_order=len(pinned),
            )
        )

    async def remove_favorite(self, *, user_id: UUID, dashboard_id: UUID) -> bool:
        """Unpin a dashboard; returns whether anything was removed."""
        existing = await self._favorites.get_for_user_dashboard(user_id, dashboard_id)
        if existing is None:
            return False
        await self._favorites.purge(existing.id)
        return True

    async def list_favorites(self, *, organization_id: UUID, user_id: UUID) -> list[Dashboard]:
        """The dashboards one user has pinned, in their own order.

        Favourites pointing at a dashboard that has since been deleted
        are skipped rather than surfaced as broken tiles.
        """
        found: list[Dashboard] = []
        for favorite in await self._favorites.list_for_user(organization_id, user_id):
            dashboard = await self._dashboards.get_by_id(favorite.dashboard_id)
            if dashboard is not None:
                found.append(dashboard)
        return found

    async def reorder_favorites(
        self, *, organization_id: UUID, user_id: UUID, dashboard_ids: list[UUID]
    ) -> list[DashboardFavorite]:
        """Set the order of one user's favourites.

        Dashboards named in *dashboard_ids* take that order; anything
        pinned but unnamed keeps its relative position after them, so a
        partial reorder from a drag-and-drop UI cannot silently unpin
        what was off-screen.

        Raises:
            ValidationError: If an id is not among the user's favourites.
        """
        pinned = await self._favorites.list_for_user(organization_id, user_id)
        by_dashboard = {favorite.dashboard_id: favorite for favorite in pinned}
        unknown = [str(one) for one in dashboard_ids if one not in by_dashboard]
        if unknown:
            raise ValidationError(
                f"These dashboards are not in your favourites: {', '.join(unknown)}."
            )

        ordered = [by_dashboard[one] for one in dashboard_ids]
        ordered += [favorite for favorite in pinned if favorite.dashboard_id not in dashboard_ids]
        updated: list[DashboardFavorite] = []
        for position, favorite in enumerate(ordered):
            favorite.display_order = position
            updated.append(await self._favorites.update(favorite))
        return updated

    # ---- saved filters ---------------------------------------------

    async def save_filter(
        self,
        dashboard_id: UUID,
        *,
        name: str,
        clauses: list[dict[str, Any]],
        user_id: UUID | None = None,
        is_default: bool = False,
    ) -> DashboardFilter:
        """Save or replace a named filter set.

        Clauses are parsed here, so a malformed filter is refused at save
        time rather than by every widget the next time it is applied.

        Raises:
            NotFoundError: If the dashboard does not exist.
            ValidationError: If a clause is malformed.
        """
        dashboard = await self._dashboards.require_by_id(dashboard_id)
        parse_clauses(clauses)

        for existing in await self._filters.list_for_dashboard(dashboard_id, user_id=user_id):
            if existing.name == name and existing.user_id == user_id:
                existing.clauses = clauses
                existing.is_default = is_default
                return await self._filters.update(existing)

        return await self._filters.create(
            DashboardFilter(
                organization_id=dashboard.organization_id,
                project_id=dashboard.project_id,
                dashboard_id=dashboard_id,
                user_id=user_id,
                name=name,
                clauses=clauses,
                is_default=is_default,
            )
        )

    async def list_filters(
        self, dashboard_id: UUID, *, user_id: UUID | None = None
    ) -> list[DashboardFilter]:
        """Saved filters a user can pick from on one dashboard."""
        return await self._filters.list_for_dashboard(dashboard_id, user_id=user_id)

    async def delete_filter(self, filter_id: UUID, *, user_id: UUID | None = None) -> None:
        """Delete a saved filter.

        Raises:
            NotFoundError: If no such filter exists.
            ConflictError: If a user tries to delete a shared preset.
        """
        saved = await self._filters.require_by_id(filter_id)
        if saved.user_id is None and user_id is not None:
            raise ConflictError(
                "That is a shared preset for the dashboard, not your own saved filter."
            )
        await self._filters.purge(filter_id)

    # ---- widget settings -------------------------------------------

    async def set_widget_setting(
        self,
        widget_id: UUID,
        *,
        user_id: UUID,
        collapsed: bool | None = None,
        hidden: bool | None = None,
        refresh_seconds_override: int | None = None,
        options_override: dict[str, Any] | None = None,
    ) -> DashboardWidgetSetting:
        """Store one user's overrides for one widget.

        Raises:
            NotFoundError: If the widget does not exist.
            ValidationError: If the refresh override is out of range.
        """
        widget = await self._widgets.get_by_id(widget_id)
        if widget is None:
            raise NotFoundError("That widget does not exist.")
        if refresh_seconds_override is not None and not (
            MIN_REFRESH_SECONDS <= refresh_seconds_override <= MAX_REFRESH_SECONDS
        ):
            raise ValidationError(
                f"A refresh override must be between {MIN_REFRESH_SECONDS} seconds and "
                f"{MAX_REFRESH_SECONDS} seconds."
            )

        setting = await self._settings.get_for_user(widget_id, user_id)
        if setting is None:
            setting = DashboardWidgetSetting(
                organization_id=widget.organization_id,
                project_id=widget.project_id,
                widget_id=widget_id,
                user_id=user_id,
            )
            created = True
        else:
            created = False

        if collapsed is not None:
            setting.collapsed = collapsed
        if hidden is not None:
            setting.hidden = hidden
        if refresh_seconds_override is not None:
            setting.refresh_seconds_override = refresh_seconds_override
        if options_override is not None:
            setting.options_override = options_override

        if created:
            return await self._settings.create(setting)
        return await self._settings.update(setting)

    async def list_widget_settings(
        self, *, organization_id: UUID, user_id: UUID
    ) -> list[DashboardWidgetSetting]:
        """Every override one user has, for applying in bulk on load."""
        return await self._settings.list_for_user(organization_id, user_id)

    async def clear_widget_setting(self, widget_id: UUID, *, user_id: UUID) -> bool:
        """Drop one user's overrides; returns whether anything changed."""
        setting = await self._settings.get_for_user(widget_id, user_id)
        if setting is None:
            return False
        await self._settings.purge(setting.id)
        return True


__all__ = ["MAX_REFRESH_SECONDS", "MIN_REFRESH_SECONDS", "PreferencesService"]
