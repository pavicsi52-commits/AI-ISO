"""Domain events published by the organization service."""

from __future__ import annotations

from app.events.organization_events import (
    DepartmentCreatedEvent,
    DepartmentDeletedEvent,
    LicenseExpiredEvent,
    OrganizationActivatedEvent,
    OrganizationCreatedEvent,
    OrganizationDeletedEvent,
    OrganizationSuspendedEvent,
    OrganizationUpdatedEvent,
    QuotaExceededEvent,
    SubscriptionChangedEvent,
    TeamCreatedEvent,
)

__all__ = [
    "DepartmentCreatedEvent",
    "DepartmentDeletedEvent",
    "LicenseExpiredEvent",
    "OrganizationActivatedEvent",
    "OrganizationCreatedEvent",
    "OrganizationDeletedEvent",
    "OrganizationSuspendedEvent",
    "OrganizationUpdatedEvent",
    "QuotaExceededEvent",
    "SubscriptionChangedEvent",
    "TeamCreatedEvent",
]
