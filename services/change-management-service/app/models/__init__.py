"""Every table this service owns.

Imported as a package by Alembic's ``env.py``, which is what registers
each model with ``Base.metadata`` before autogenerate runs. A model not
re-exported here is a table the migration will not know about.
"""

from __future__ import annotations

from app.models.approval import ChangeApproval
from app.models.cab import ChangeCab, ChangeCabVote
from app.models.calendar import ChangeCalendarEntry
from app.models.catalogue import (
    ChangeCategoryRecord,
    ChangePriorityRecord,
    ChangeStatusRecord,
    ChangeTypeRecord,
)
from app.models.change import ChangeRelationship, ChangeRequest
from app.models.conflict import ChangeConflict
from app.models.governance import ChangeAudit, ChangeReport, ChangeStatistic
from app.models.implementation import (
    ChangeImplementation,
    ChangeRollback,
    ChangeTask,
    ChangeValidation,
)
from app.models.pir import ChangePostReview, ChangePostReviewActionItem
from app.models.risk import ChangeRiskAssessment

__all__ = [
    "ChangeApproval",
    "ChangeAudit",
    "ChangeCab",
    "ChangeCabVote",
    "ChangeCalendarEntry",
    "ChangeCategoryRecord",
    "ChangeConflict",
    "ChangeImplementation",
    "ChangePostReview",
    "ChangePostReviewActionItem",
    "ChangePriorityRecord",
    "ChangeRelationship",
    "ChangeReport",
    "ChangeRequest",
    "ChangeRiskAssessment",
    "ChangeRollback",
    "ChangeStatistic",
    "ChangeStatusRecord",
    "ChangeTask",
    "ChangeTypeRecord",
    "ChangeValidation",
]
