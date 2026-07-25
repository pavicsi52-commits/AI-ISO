"""Repositories for the user management service, one per entity."""

from __future__ import annotations

from app.repositories.activity import UserActivityRepository
from app.repositories.address import UserAddressRepository
from app.repositories.avatar import UserAvatarRepository
from app.repositories.contact import UserContactRepository
from app.repositories.export_job import UserExportJobRepository
from app.repositories.import_job import UserImportJobRepository
from app.repositories.invitation import UserInvitationRepository
from app.repositories.metadata import UserMetadataRepository
from app.repositories.note import UserNoteRepository
from app.repositories.preferences import UserPreferencesRepository
from app.repositories.profile import UserProfileRepository
from app.repositories.settings import UserSettingsRepository
from app.repositories.tag import UserTagRepository
from app.repositories.user import UserRepository

__all__ = [
    "UserActivityRepository",
    "UserAddressRepository",
    "UserAvatarRepository",
    "UserContactRepository",
    "UserExportJobRepository",
    "UserImportJobRepository",
    "UserInvitationRepository",
    "UserMetadataRepository",
    "UserNoteRepository",
    "UserPreferencesRepository",
    "UserProfileRepository",
    "UserRepository",
    "UserSettingsRepository",
    "UserTagRepository",
]
