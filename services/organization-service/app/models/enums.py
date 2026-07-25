"""Enumerations for the organization service's persisted domain.

Per docs/033 "ORGANIZATION STATUS"/"SUBSCRIPTIONS"/etc.
"""

from __future__ import annotations

from enum import StrEnum


class OrganizationStatus(StrEnum):
    """Per docs/033 "ORGANIZATION STATUS" (9 values, verbatim)."""

    PENDING = "pending"
    TRIAL = "trial"
    ACTIVE = "active"
    SUSPENDED = "suspended"
    MAINTENANCE = "maintenance"
    EXPIRED = "expired"
    DISABLED = "disabled"
    ARCHIVED = "archived"
    DELETED = "deleted"


class SubscriptionPlan(StrEnum):
    """Per docs/033 "SUBSCRIPTIONS" (5 values, verbatim)."""

    TRIAL = "trial"
    COMMUNITY = "community"
    PROFESSIONAL = "professional"
    ENTERPRISE = "enterprise"
    CUSTOM = "custom"


class SubscriptionStatus(StrEnum):
    ACTIVE = "active"
    PENDING_RENEWAL = "pending_renewal"
    EXPIRED = "expired"
    CANCELLED = "cancelled"


class LicenseStatus(StrEnum):
    PENDING_ACTIVATION = "pending_activation"
    ACTIVE = "active"
    GRACE_PERIOD = "grace_period"
    EXPIRED = "expired"
    REVOKED = "revoked"


class DomainVerificationStatus(StrEnum):
    PENDING = "pending"
    VERIFIED = "verified"
    FAILED = "failed"


class InvitationStatus(StrEnum):
    PENDING = "pending"
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    EXPIRED = "expired"


class MemberRole(StrEnum):
    OWNER = "owner"
    ADMIN = "admin"
    MEMBER = "member"


class MemberStatus(StrEnum):
    ACTIVE = "active"
    SUSPENDED = "suspended"
    INACTIVE = "inactive"


class OrganizationActivityType(StrEnum):
    """Per docs/033 "EVENTS"/"AUDIT": the narrative operations this service tracks."""

    ORGANIZATION_CREATED = "organization_created"
    ORGANIZATION_UPDATED = "organization_updated"
    ORGANIZATION_ACTIVATED = "organization_activated"
    ORGANIZATION_SUSPENDED = "organization_suspended"
    SETTINGS_CHANGED = "settings_changed"
    BRANDING_CHANGED = "branding_changed"
    DEPARTMENT_CREATED = "department_created"
    DEPARTMENT_DELETED = "department_deleted"
    BUSINESS_UNIT_CREATED = "business_unit_created"
    BUSINESS_UNIT_DELETED = "business_unit_deleted"
    TEAM_CREATED = "team_created"
    TEAM_DELETED = "team_deleted"
    MEMBER_INVITED = "member_invited"
    MEMBER_JOINED = "member_joined"
    MEMBER_REMOVED = "member_removed"
    SUBSCRIPTION_CHANGED = "subscription_changed"
    LICENSE_CHANGED = "license_changed"
    QUOTA_CHANGED = "quota_changed"
    QUOTA_EXCEEDED = "quota_exceeded"


class AuditOutcome(StrEnum):
    SUCCESS = "success"
    FAILURE = "failure"


__all__ = [
    "AuditOutcome",
    "DomainVerificationStatus",
    "InvitationStatus",
    "LicenseStatus",
    "MemberRole",
    "MemberStatus",
    "OrganizationActivityType",
    "OrganizationStatus",
    "SubscriptionPlan",
    "SubscriptionStatus",
]
