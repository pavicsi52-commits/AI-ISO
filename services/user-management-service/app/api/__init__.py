"""REST API routers for the user management service."""

from __future__ import annotations

from app.api.activity import router as activity_router
from app.api.address import router as address_router
from app.api.avatar import router as avatar_router
from app.api.contact import router as contact_router
from app.api.export import router as export_router
from app.api.health import router as health_router
from app.api.import_ import router as import_router
from app.api.invitation import router as invitation_router
from app.api.metadata import router as metadata_router
from app.api.note import router as note_router
from app.api.preferences import router as preferences_router
from app.api.profile import router as profile_router
from app.api.settings import router as settings_router
from app.api.tag import router as tag_router
from app.api.user import router as user_router

__all__ = [
    "activity_router",
    "address_router",
    "avatar_router",
    "contact_router",
    "export_router",
    "health_router",
    "import_router",
    "invitation_router",
    "metadata_router",
    "note_router",
    "preferences_router",
    "profile_router",
    "settings_router",
    "tag_router",
    "user_router",
]
