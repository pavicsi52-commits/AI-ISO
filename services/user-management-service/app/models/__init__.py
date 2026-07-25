"""SQLAlchemy models for the user management service.

Every model must be imported here so it registers with
:data:`shared_core.database.base.Base.metadata` -- both Alembic
autogenerate and any create_all() call rely on every table being
known before they run.
"""

from __future__ import annotations

from app.models.activity import UserActivityEntry
from app.models.address import UserAddress
from app.models.avatar import UserAvatar
from app.models.contact import UserContact
from app.models.export_job import UserExportJob
from app.models.import_job import UserImportJob
from app.models.invitation import UserInvitation
from app.models.metadata import UserMetadataEntry
from app.models.note import UserNote
from app.models.preferences import UserPreferences
from app.models.profile import UserProfile
from app.models.settings import UserSettings
from app.models.tag import UserTag
from app.models.user import User

__all__ = [
    "User",
    "UserActivityEntry",
    "UserAddress",
    "UserAvatar",
    "UserContact",
    "UserExportJob",
    "UserImportJob",
    "UserInvitation",
    "UserMetadataEntry",
    "UserNote",
    "UserPreferences",
    "UserProfile",
    "UserSettings",
    "UserTag",
]
