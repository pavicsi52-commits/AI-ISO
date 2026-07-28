"""Saved report definitions ("GET/POST/PUT/DELETE /reports")."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from app.events.report_events import SOURCE_SERVICE, ReportCreatedEvent
from app.filters.engine import parse_clauses
from app.models.enums import ExportFormat, ReportCategory, ReportType
from app.models.report_favorite import ReportFavorite
from app.models.report_history import ReportHistory
from app.models.report_job import ReportJob
from app.repositories.report_favorite import ReportFavoriteRepository
from app.repositories.report_history import ReportHistoryRepository
from app.repositories.report_job import ReportJobRepository
from app.types import EventPublisher


class ReportJobService:
    """Creates, reads, updates, and deletes saved reports."""

    def __init__(
        self,
        jobs: ReportJobRepository,
        history: ReportHistoryRepository,
        favorites: ReportFavoriteRepository,
        *,
        publish_event: EventPublisher,
    ) -> None:
        self._jobs = jobs
        self._history = history
        self._favorites = favorites
        self._publish_event = publish_event

    async def get_by_id(self, job_id: UUID) -> ReportJob:
        """Return one saved report.

        Raises:
            NotFoundError: If no such report exists.
        """
        return await self._jobs.require_by_id(job_id)

    async def list_for_org(
        self,
        organization_id: UUID,
        *,
        category: ReportCategory | None = None,
        enabled_only: bool = False,
    ) -> list[ReportJob]:
        """Saved reports for an organization."""
        return await self._jobs.list_for_org(
            organization_id, category=category, enabled_only=enabled_only
        )

    async def create(
        self,
        *,
        organization_id: UUID,
        project_id: UUID | None,
        name: str,
        description: str | None,
        category: ReportCategory,
        report_type: ReportType,
        template_id: UUID | None,
        default_format: ExportFormat = ExportFormat.PDF,
        parameter_values: dict[str, Any] | None = None,
        filters: list[dict[str, Any]] | None = None,
        owner_id: UUID | None = None,
    ) -> ReportJob:
        """Create a saved report.

        Filters are parsed on write, so a malformed clause is rejected
        here rather than at 03:00 inside a scheduled run.

        Raises:
            ValidationError: If a filter clause is malformed.
        """
        parse_clauses(filters or [])
        job = await self._jobs.create(
            ReportJob(
                organization_id=organization_id,
                project_id=project_id,
                template_id=template_id,
                name=name,
                description=description,
                category=category,
                report_type=report_type,
                default_format=default_format,
                parameter_values=parameter_values or {},
                filters=filters or [],
                owner_id=owner_id,
            )
        )
        await self._history.create(
            ReportHistory(
                organization_id=organization_id,
                project_id=project_id,
                job_id=job.id,
                event="created",
                summary=f"Report {name!r} created.",
                details={"category": str(category), "report_type": str(report_type)},
                actor_id=owner_id,
                occurred_at=datetime.now(UTC),
            )
        )
        await self._publish_event(
            ReportCreatedEvent(
                source_service=SOURCE_SERVICE,
                payload={"job_id": str(job.id), "name": name, "category": str(category)},
            )
        )
        return job

    async def update(
        self,
        job_id: UUID,
        *,
        name: str | None = None,
        description: str | None = None,
        default_format: ExportFormat | None = None,
        parameter_values: dict[str, Any] | None = None,
        filters: list[dict[str, Any]] | None = None,
        enabled: bool | None = None,
    ) -> ReportJob:
        """Update a saved report in place.

        Raises:
            NotFoundError: If no such report exists.
            ValidationError: If a filter clause is malformed.
        """
        job = await self._jobs.require_by_id(job_id)
        if filters is not None:
            parse_clauses(filters)
            job.filters = filters
        if name is not None:
            job.name = name
        if description is not None:
            job.description = description
        if default_format is not None:
            job.default_format = default_format
        if parameter_values is not None:
            job.parameter_values = parameter_values
        if enabled is not None:
            job.enabled = enabled
        return await self._jobs.update(job)

    async def delete(self, job_id: UUID, *, deleted_by: UUID | None = None) -> None:
        """Soft-delete a saved report.

        Soft rather than hard: executions, exports, and archives
        reference it, and an audit trail that dangles is worse than one
        pointing at a retired row.

        Raises:
            NotFoundError: If no such report exists.
        """
        await self._jobs.require_by_id(job_id)
        await self._jobs.delete(job_id, deleted_by=deleted_by)

    async def list_history(self, job_id: UUID, *, limit: int = 100) -> list[ReportHistory]:
        """Activity on one report."""
        return await self._history.list_for_job(job_id, limit=limit)

    async def list_org_history(
        self, organization_id: UUID, *, limit: int = 200
    ) -> list[ReportHistory]:
        """Activity across every report in an organization."""
        return await self._history.list_for_org(organization_id, limit=limit)

    async def favorite(self, organization_id: UUID, user_id: UUID, job_id: UUID) -> ReportFavorite:
        """Pin a report for one user; idempotent.

        Returns the existing row when already favourited rather than
        raising, because clicking a star twice is not an error.
        """
        existing = await self._favorites.get_for_user_job(user_id, job_id)
        if existing is not None:
            return existing
        return await self._favorites.create(
            ReportFavorite(organization_id=organization_id, user_id=user_id, job_id=job_id)
        )

    async def unfavorite(self, user_id: UUID, job_id: UUID) -> bool:
        """Unpin a report; returns whether anything was removed."""
        existing = await self._favorites.get_for_user_job(user_id, job_id)
        if existing is None:
            return False
        await self._favorites.purge(existing.id)
        return True

    async def list_favorites(self, organization_id: UUID, user_id: UUID) -> list[ReportJob]:
        """The reports one user has pinned.

        Resolved sequentially: an ``AsyncSession`` is not safe for
        concurrent use even for reads.
        """
        pinned = await self._favorites.list_for_user(organization_id, user_id)
        jobs: list[ReportJob] = []
        for favorite in pinned:
            job = await self._jobs.get_by_id(favorite.job_id)
            if job is not None:
                jobs.append(job)
        return jobs


__all__ = ["ReportJobService"]
