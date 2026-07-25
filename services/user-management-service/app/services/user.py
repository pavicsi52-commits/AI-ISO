"""User CRUD, status lifecycle, and search orchestration.

Ties together the repository, status-transition validation
(:mod:`app.services.lifecycle`), activity tracking, notifications, and
domain events into the platform's core "manage a user" operations
(docs/031 "OBJECTIVE": User Lifecycle, Account Status).
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Sequence
from uuid import UUID

from shared_core.database.filtering import Filter
from shared_core.database.pagination import PaginatedResult
from shared_core.database.sorting import SortField
from shared_core.events.base import DomainEvent
from shared_core.exceptions.conflict import ConflictError

from app.constants import DEFAULT_ORGANIZATION_ID
from app.events.user_events import (
    AvatarUpdatedEvent,
    UserActivatedEvent,
    UserCreatedEvent,
    UserDeactivatedEvent,
    UserDeletedEvent,
    UserUpdatedEvent,
)
from app.models.enums import ActivityType, UserStatus
from app.models.user import User
from app.notifications.user_notifications import UserNotificationService
from app.repositories.user import UserRepository
from app.services.activity import UserActivityService
from app.services.lifecycle import ACTIVE_STATUS, validate_transition

EventPublisher = Callable[[DomainEvent], Awaitable[None]]


class UserService:
    """Creates, updates, transitions, and searches for users."""

    def __init__(
        self,
        users: UserRepository,
        activity: UserActivityService,
        notifications: UserNotificationService,
        *,
        publish_event: EventPublisher | None = None,
    ) -> None:
        self._users = users
        self._activity = activity
        self._notifications = notifications
        self._publish_event = publish_event

    async def _publish(self, event: DomainEvent) -> None:
        if self._publish_event is not None:
            await self._publish_event(event)

    async def create(
        self,
        *,
        username: str,
        email: str,
        display_name: str | None,
        first_name: str | None,
        middle_name: str | None,
        last_name: str | None,
        phone_number: str | None,
        timezone: str,
        language: str,
        locale: str,
        status: UserStatus = UserStatus.PENDING,
    ) -> User:
        """Create a new user ("User CRUD").

        Raises:
            ConflictError: If *username* or *email* is already taken.
        """
        if await self._users.get_by_username(username) is not None:
            raise ConflictError(f"Username {username!r} is already taken.")
        if await self._users.get_by_email(email) is not None:
            raise ConflictError(f"Email {email!r} is already registered.")

        user = await self._users.create(
            User(
                username=username,
                email=email,
                display_name=display_name,
                first_name=first_name,
                middle_name=middle_name,
                last_name=last_name,
                phone_number=phone_number,
                timezone=timezone,
                language=language,
                locale=locale,
                status=status,
                organization_id=DEFAULT_ORGANIZATION_ID,
            )
        )
        await self._publish(
            UserCreatedEvent(
                source_service="user-management-service", payload={"user_id": str(user.id)}
            )
        )
        return user

    async def update(
        self,
        user: User,
        *,
        display_name: str | None,
        first_name: str | None,
        middle_name: str | None,
        last_name: str | None,
        phone_number: str | None,
        timezone: str,
        language: str,
        locale: str,
    ) -> User:
        """Full-replace *user*'s mutable fields ("User CRUD")."""
        user.display_name = display_name
        user.first_name = first_name
        user.middle_name = middle_name
        user.last_name = last_name
        user.phone_number = phone_number
        user.timezone = timezone
        user.language = language
        user.locale = locale
        await self._activity.record(user.id, activity_type=ActivityType.PROFILE_UPDATED)
        await self._publish(
            UserUpdatedEvent(
                source_service="user-management-service", payload={"user_id": str(user.id)}
            )
        )
        return user

    async def patch(self, user: User, **fields: object) -> User:
        """Partially update *user*, applying only the given fields ("User CRUD")."""
        target_status = fields.pop("status", None)
        for field, value in fields.items():
            if value is not None:
                setattr(user, field, value)
        if target_status is not None:
            await self.transition_status(user, target_status)  # type: ignore[arg-type]
        await self._activity.record(user.id, activity_type=ActivityType.PROFILE_UPDATED)
        await self._publish(
            UserUpdatedEvent(
                source_service="user-management-service", payload={"user_id": str(user.id)}
            )
        )
        return user

    async def transition_status(self, user: User, target: UserStatus) -> User:
        """Transition *user* to *target* status, validating the transition first.

        Raises:
            ConflictError: If the transition isn't legal.
        """
        # user.status round-trips through SQLAlchemy's String(32) column as a
        # plain str on a freshly-loaded row, not a real UserStatus instance
        # (unlike a value just assigned in this same process) -- StrEnum
        # equality/comparison still works either way, but .value does not,
        # so it's normalized explicitly here rather than assumed.
        previous = UserStatus(str(user.status))
        validate_transition(previous, target)
        user.status = target
        await self._activity.record(
            user.id,
            activity_type=ActivityType.STATUS_CHANGED,
            detail={"from": previous.value, "to": target.value},
        )
        if target == ACTIVE_STATUS and previous != ACTIVE_STATUS:
            await self._notifications.send_account_activated(str(user.id))
            await self._publish(
                UserActivatedEvent(
                    source_service="user-management-service", payload={"user_id": str(user.id)}
                )
            )
        elif previous == ACTIVE_STATUS and target != ACTIVE_STATUS:
            if target == UserStatus.SUSPENDED:
                await self._notifications.send_account_suspended(str(user.id))
            await self._publish(
                UserDeactivatedEvent(
                    source_service="user-management-service", payload={"user_id": str(user.id)}
                )
            )
        return user

    async def set_avatar(self, user: User, avatar_key: str | None) -> User:
        """Point *user* at its current avatar's storage key ("Avatar Upload"/"Delete")."""
        user.avatar = avatar_key
        await self._activity.record(user.id, activity_type=ActivityType.AVATAR_UPDATED)
        await self._publish(
            AvatarUpdatedEvent(
                source_service="user-management-service", payload={"user_id": str(user.id)}
            )
        )
        return user

    async def delete(self, user: User) -> None:
        """Soft-delete *user* ("User CRUD")."""
        await self._notifications.send_account_deleted(str(user.id))
        await self._users.delete(user.id)
        await self._activity.record(user.id, activity_type=ActivityType.STATUS_CHANGED)
        await self._publish(
            UserDeletedEvent(
                source_service="user-management-service", payload={"user_id": str(user.id)}
            )
        )

    async def search(
        self,
        *,
        query: str | None,
        filters: Sequence[Filter] | None,
        sort_fields: Sequence[SortField] | None,
        page: int | None,
        page_size: int | None,
    ) -> PaginatedResult[User]:
        """Search/filter/sort/paginate users ("User Search")."""
        return await self._users.search_and_paginate(
            query=query, filters=filters, sort_fields=sort_fields, page=page, page_size=page_size
        )

    async def get_by_id(self, user_id: UUID) -> User | None:
        """Return the user with *user_id*, or ``None``."""
        return await self._users.get_by_id(user_id)


__all__ = ["UserService"]
