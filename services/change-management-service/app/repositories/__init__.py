"""Every repository this service owns.

Each is tenant-scoped. The scoped lookups are named ``require_in_org``
rather than overriding the base ``require_by_id``: two same-named methods
of different arity on one class make an unscoped call look correct, which
is how a cross-tenant read gets written.
"""

from __future__ import annotations

from app.repositories.approval import ChangeApprovalRepository
from app.repositories.cab import ChangeCabRepository, ChangeCabVoteRepository
from app.repositories.calendar import ChangeCalendarRepository
from app.repositories.catalogue import (
    ChangeCategoryRepository,
    ChangePriorityRepository,
    ChangeStatusRepository,
    ChangeTypeRepository,
)
from app.repositories.change import ChangeRelationshipRepository, ChangeRequestRepository
from app.repositories.conflict import ChangeConflictRepository
from app.repositories.governance import (
    ChangeAuditRepository,
    ChangeReportRepository,
    ChangeStatisticRepository,
)
from app.repositories.implementation import (
    ChangeImplementationRepository,
    ChangeRollbackRepository,
    ChangeTaskRepository,
    ChangeValidationRepository,
)
from app.repositories.pir import ChangePostReviewActionItemRepository, ChangePostReviewRepository
from app.repositories.risk import ChangeRiskAssessmentRepository

__all__ = [
    "ChangeApprovalRepository",
    "ChangeAuditRepository",
    "ChangeCabRepository",
    "ChangeCabVoteRepository",
    "ChangeCalendarRepository",
    "ChangeCategoryRepository",
    "ChangeConflictRepository",
    "ChangeImplementationRepository",
    "ChangePostReviewActionItemRepository",
    "ChangePostReviewRepository",
    "ChangePriorityRepository",
    "ChangeRelationshipRepository",
    "ChangeReportRepository",
    "ChangeRequestRepository",
    "ChangeRiskAssessmentRepository",
    "ChangeRollbackRepository",
    "ChangeStatisticRepository",
    "ChangeStatusRepository",
    "ChangeTaskRepository",
    "ChangeTypeRepository",
    "ChangeValidationRepository",
]
