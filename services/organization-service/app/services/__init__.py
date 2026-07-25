"""Business services for the organization service."""

from __future__ import annotations

from app.services.activity import OrganizationActivityService
from app.services.audit import OrganizationAuditService
from app.services.branding import OrganizationBrandingService
from app.services.business_unit import BusinessUnitService
from app.services.department import DepartmentService
from app.services.domain import OrganizationDomainService
from app.services.invitation import InvitationService
from app.services.license import OrganizationLicenseService
from app.services.limits import OrganizationLimitsService
from app.services.member import OrganizationMemberService
from app.services.metadata import OrganizationMetadataService
from app.services.organization import OrganizationService
from app.services.preferences import OrganizationPreferencesService
from app.services.quota import OrganizationQuotaService
from app.services.settings import OrganizationSettingsService
from app.services.statistics import OrganizationStatisticsService
from app.services.subscription import OrganizationSubscriptionService
from app.services.tag import OrganizationTagService
from app.services.team import TeamService

__all__ = [
    "BusinessUnitService",
    "DepartmentService",
    "InvitationService",
    "OrganizationActivityService",
    "OrganizationAuditService",
    "OrganizationBrandingService",
    "OrganizationDomainService",
    "OrganizationLicenseService",
    "OrganizationLimitsService",
    "OrganizationMemberService",
    "OrganizationMetadataService",
    "OrganizationPreferencesService",
    "OrganizationQuotaService",
    "OrganizationService",
    "OrganizationSettingsService",
    "OrganizationStatisticsService",
    "OrganizationSubscriptionService",
    "OrganizationTagService",
    "TeamService",
]
