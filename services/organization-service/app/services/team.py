"""Team management. Per docs/033 "TEAMS": CRUD, Team Leads, Metadata."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any
from uuid import UUID

from shared_core.events.base import DomainEvent

from app.events.organization_events import TeamCreatedEvent
from app.models.enums import OrganizationActivityType
from app.models.team import Team
from app.repositories.team import TeamRepository
from app.services.activity import OrganizationActivityService

EventPublisher = Callable[[DomainEvent], Awaitable[None]]


class TeamService:
    """Creates, updates, deletes, and lists teams within an organization."""

    def __init__(
        self,
        teams: TeamRepository,
        activity: OrganizationActivityService,
        *,
        publish_event: EventPublisher | None = None,
    ) -> None:
        self._teams = teams
        self._activity = activity
        self._publish_event = publish_event

    async def _publish(self, event: DomainEvent) -> None:
        if self._publish_event is not None:
            await self._publish_event(event)

    async def get_by_id(self, team_id: UUID) -> Team:
        """Return the team identified by *team_id*.

        Raises:
            NotFoundError: If no such team exists.
        """
        return await self._teams.require_by_id(team_id)

    async def list_for_org(self, organization_id: UUID) -> list[Team]:
        """Every team in *organization_id* ("Team Management": list)."""
        return await self._teams.list_for_org(organization_id)

    async def create(
        self,
        organization_id: UUID,
        *,
        name: str,
        code: str,
        description: str | None,
        department_id: UUID | None,
        business_unit_id: UUID | None,
        team_lead_id: UUID | None,
        metadata: dict[str, Any],
    ) -> Team:
        """Create a new team ("Create")."""
        team = await self._teams.create(
            Team(
                organization_id=organization_id,
                name=name,
                code=code,
                description=description,
                department_id=department_id,
                business_unit_id=business_unit_id,
                team_lead_id=team_lead_id,
                metadata_=metadata,
            )
        )
        await self._activity.record(
            organization_id, activity_type=OrganizationActivityType.TEAM_CREATED
        )
        await self._publish(
            TeamCreatedEvent(
                source_service="organization-service", payload={"team_id": str(team.id)}
            )
        )
        return team

    async def update(
        self,
        team_id: UUID,
        *,
        name: str,
        description: str | None,
        department_id: UUID | None,
        business_unit_id: UUID | None,
        team_lead_id: UUID | None,
        metadata: dict[str, Any],
    ) -> Team:
        """Update a team's mutable fields ("Update")."""
        team = await self.get_by_id(team_id)
        team.name = name
        team.description = description
        team.department_id = department_id
        team.business_unit_id = business_unit_id
        team.team_lead_id = team_lead_id
        team.metadata_ = metadata
        return team

    async def delete(self, team_id: UUID) -> None:
        """Delete a team ("Delete")."""
        team = await self.get_by_id(team_id)
        organization_id = team.organization_id
        await self._teams.delete(team_id)
        await self._activity.record(
            organization_id, activity_type=OrganizationActivityType.TEAM_DELETED
        )


__all__ = ["TeamService"]
