"""Enums specific to the user management service's own database schema."""

from __future__ import annotations

from enum import StrEnum


class UserStatus(StrEnum):
    """Per docs/031 "USER STATUS". Transitions are validated -- see
    :mod:`app.services.lifecycle`'s ``_VALID_TRANSITIONS`` table.
    """

    PENDING = "pending"
    INVITED = "invited"
    ACTIVE = "active"
    INACTIVE = "inactive"
    LOCKED = "locked"
    DISABLED = "disabled"
    DELETED = "deleted"
    ARCHIVED = "archived"
    SUSPENDED = "suspended"


class AddressType(StrEnum):
    """The kind of address one ``user_addresses`` row represents."""

    HOME = "home"
    WORK = "work"
    BILLING = "billing"
    SHIPPING = "shipping"
    OTHER = "other"


class ContactType(StrEnum):
    """The kind of contact method one ``user_contacts`` row represents.

    Distinct from ``users.email``/``users.phone_number`` (the primary
    contact channels) -- this table is for secondary/additional ones.
    """

    EMAIL = "email"
    PHONE = "phone"
    MOBILE = "mobile"
    FAX = "fax"
    OTHER = "other"


class InvitationStatus(StrEnum):
    """The lifecycle state of one ``user_invitations`` row."""

    PENDING = "pending"
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    EXPIRED = "expired"
    REVOKED = "revoked"


class ActivityType(StrEnum):
    """The kind of event one ``user_activity`` row records.

    Per docs/031 "USER ACTIVITY": "Profile Updates, Status Changes,
    Preference Changes, Invitation Events, Import, Export, Last
    Active, Login History Reference."
    """

    PROFILE_UPDATED = "profile_updated"
    STATUS_CHANGED = "status_changed"
    PREFERENCES_UPDATED = "preferences_updated"
    SETTINGS_UPDATED = "settings_updated"
    INVITATION_SENT = "invitation_sent"
    INVITATION_ACCEPTED = "invitation_accepted"
    INVITATION_REJECTED = "invitation_rejected"
    IMPORTED = "imported"
    EXPORTED = "exported"
    AVATAR_UPDATED = "avatar_updated"
    LAST_ACTIVE = "last_active"


class ImportFormat(StrEnum):
    """The file format one ``user_import_jobs`` row was submitted as."""

    CSV = "csv"
    EXCEL = "excel"
    JSON = "json"


class ExportFormat(StrEnum):
    """The file format one ``user_export_jobs`` row produces."""

    CSV = "csv"
    EXCEL = "excel"
    JSON = "json"
    PDF = "pdf"


__all__ = [
    "ActivityType",
    "AddressType",
    "ContactType",
    "ExportFormat",
    "ImportFormat",
    "InvitationStatus",
    "UserStatus",
]
