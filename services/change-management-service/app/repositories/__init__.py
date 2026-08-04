"""Every repository this service owns.

Each is tenant-scoped. The scoped lookups are named ``require_in_org``
rather than overriding the base ``require_by_id``: two same-named methods
of different arity on one class make an unscoped call look correct, which
is how a cross-tenant read gets written.
"""

from __future__ import annotations

from app.repositories.catalogue import (
    IncidentCategoryRepository,
    IncidentPriorityRepository,
    IncidentStatusRepository,
)
from app.repositories.governance import AuditRepository, ReportRepository, StatisticRepository
from app.repositories.impact import AssetImpactRepository, ImpactRepository, ServiceImpactRepository
from app.repositories.incident import IncidentRepository
from app.repositories.major import (
    MajorIncidentRepository,
    WarRoomParticipantRepository,
    WarRoomRepository,
)
from app.repositories.postmortem import ActionItemRepository, PostmortemRepository
from app.repositories.rca import KnownErrorRepository, ProblemRepository, RootCauseRepository
from app.repositories.sla import EscalationRepository, SlaRepository
from app.repositories.timeline import AssignmentRepository, TimelineRepository, WorklogRepository

__all__ = [
    "ActionItemRepository",
    "AssetImpactRepository",
    "AssignmentRepository",
    "AuditRepository",
    "EscalationRepository",
    "ImpactRepository",
    "IncidentCategoryRepository",
    "IncidentPriorityRepository",
    "IncidentRepository",
    "IncidentStatusRepository",
    "KnownErrorRepository",
    "MajorIncidentRepository",
    "PostmortemRepository",
    "ProblemRepository",
    "ReportRepository",
    "RootCauseRepository",
    "ServiceImpactRepository",
    "SlaRepository",
    "StatisticRepository",
    "TimelineRepository",
    "WarRoomParticipantRepository",
    "WarRoomRepository",
    "WorklogRepository",
]
