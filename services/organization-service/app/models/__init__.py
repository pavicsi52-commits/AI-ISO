"""SQLAlchemy models for the organization service.

Every model must be imported here so it registers with
:data:`shared_core.database.base.Base.metadata` -- both Alembic
autogenerate and any create_all() call rely on every table being
known before they run.
"""

from __future__ import annotations

from app.models.activity import OrganizationActivityEntry
from app.models.audit import OrganizationAuditEntry
from app.models.business_unit import BusinessUnit
from app.models.department import Department
from app.models.invitation import OrganizationInvitation
from app.models.member import OrganizationMember
from app.models.organization import Organization
from app.models.organization_branding import OrganizationBranding
from app.models.organization_domain import OrganizationDomain
from app.models.organization_license import OrganizationLicense
from app.models.organization_limits import OrganizationLimits
from app.models.organization_metadata import OrganizationMetadataEntry
from app.models.organization_preferences import OrganizationPreferences
from app.models.organization_quota import OrganizationQuota
from app.models.organization_settings import OrganizationSettings
from app.models.organization_subscription import OrganizationSubscription
from app.models.statistics import OrganizationStatistics
from app.models.tag import OrganizationTag
from app.models.team import Team

__all__ = [
    "BusinessUnit",
    "Department",
    "Organization",
    "OrganizationActivityEntry",
    "OrganizationAuditEntry",
    "OrganizationBranding",
    "OrganizationDomain",
    "OrganizationInvitation",
    "OrganizationLicense",
    "OrganizationLimits",
    "OrganizationMember",
    "OrganizationMetadataEntry",
    "OrganizationPreferences",
    "OrganizationQuota",
    "OrganizationSettings",
    "OrganizationStatistics",
    "OrganizationSubscription",
    "OrganizationTag",
    "Team",
]
