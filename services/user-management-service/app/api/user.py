"""GET/POST/PUT/PATCH/DELETE /users, POST /users/search."""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Query
from shared_core.database.filtering import Filter, FilterOperator
from shared_core.database.sorting import parse_sort_expression
from shared_core.exceptions.not_found import NotFoundError
from shared_core.logging.context import get_log_context

from app.api.deps import CacheSvc, CurrentUserId, UserSvc
from app.models.user import User
from app.schemas.response import ResponseMeta, SuccessResponse
from app.schemas.user import (
    UserCreateRequest,
    UserDetail,
    UserPatchRequest,
    UserSearchRequest,
    UserSummary,
    UserUpdateRequest,
)
from app.services.user import UserService

router = APIRouter(prefix="/users", tags=["Users"])


def _meta() -> ResponseMeta:
    return ResponseMeta(request_id=get_log_context().request_id or "unknown")


def _to_detail(user: User) -> UserDetail:
    return UserDetail(
        id=user.id,
        username=user.username,
        email=user.email,
        display_name=user.display_name,
        first_name=user.first_name,
        middle_name=user.middle_name,
        last_name=user.last_name,
        phone_number=user.phone_number,
        avatar=user.avatar,
        timezone=user.timezone,
        language=user.language,
        locale=user.locale,
        status=user.status,
        last_login=user.last_login,
        metadata=user.metadata_,
        created_at=user.created_at,
        updated_at=user.updated_at,
    )


def _to_summary(user: User) -> UserSummary:
    return UserSummary(
        id=user.id,
        username=user.username,
        email=user.email,
        display_name=user.display_name,
        avatar=user.avatar,
        status=user.status,
        created_at=user.created_at,
    )


async def _require_user(users: UserService, user_id: UUID) -> User:
    user = await users.get_by_id(user_id)
    if user is None:
        raise NotFoundError(f"User '{user_id}' was not found.")
    return user


@router.post("", response_model=SuccessResponse[UserDetail], status_code=201)
async def create_user(
    body: UserCreateRequest, users: UserSvc, _caller: CurrentUserId
) -> SuccessResponse[UserDetail]:
    """Create a new user ("User CRUD")."""
    user = await users.create(
        username=body.username,
        email=body.email,
        display_name=body.display_name,
        first_name=body.first_name,
        middle_name=body.middle_name,
        last_name=body.last_name,
        phone_number=body.phone_number,
        timezone=body.timezone,
        language=body.language,
        locale=body.locale,
    )
    return SuccessResponse(message="User created.", data=_to_detail(user), meta=_meta())


@router.get("", response_model=SuccessResponse[list[UserSummary]])
async def list_users(
    users: UserSvc,
    _caller: CurrentUserId,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=200)] = 20,
) -> SuccessResponse[list[UserSummary]]:
    """List users, paginated ("User CRUD")."""
    result = await users.search(
        query=None, filters=None, sort_fields=None, page=page, page_size=page_size
    )
    return SuccessResponse(
        message="Users retrieved.", data=[_to_summary(u) for u in result.items], meta=_meta()
    )


@router.post("/search", response_model=SuccessResponse[list[UserSummary]])
async def search_users(
    body: UserSearchRequest, users: UserSvc, _caller: CurrentUserId
) -> SuccessResponse[list[UserSummary]]:
    """Search/filter/sort/paginate users ("User Search")."""
    filters: list[Filter] = []
    if body.status is not None:
        filters.append(Filter("status", FilterOperator.EQUAL, body.status.value))
    sort_fields = parse_sort_expression(body.sort) if body.sort else None
    result = await users.search(
        query=body.query,
        filters=filters or None,
        sort_fields=sort_fields,
        page=body.page,
        page_size=body.page_size,
    )
    return SuccessResponse(
        message="Search results retrieved.",
        data=[_to_summary(u) for u in result.items],
        meta=_meta(),
    )


@router.get("/{user_id}", response_model=SuccessResponse[UserDetail])
async def get_user(
    user_id: UUID, users: UserSvc, cache: CacheSvc, _caller: CurrentUserId
) -> SuccessResponse[UserDetail]:
    """Return one user by id ("User CRUD"), served from cache when available."""
    cached = await cache.get(user_id)
    if cached is not None:
        return SuccessResponse(message="User retrieved.", data=UserDetail(**cached), meta=_meta())
    user = await _require_user(users, user_id)
    detail = _to_detail(user)
    await cache.set(user_id, detail.model_dump(mode="json"))
    return SuccessResponse(message="User retrieved.", data=detail, meta=_meta())


@router.put("/{user_id}", response_model=SuccessResponse[UserDetail])
async def replace_user(
    user_id: UUID, body: UserUpdateRequest, users: UserSvc, cache: CacheSvc, _caller: CurrentUserId
) -> SuccessResponse[UserDetail]:
    """Full-replace a user's mutable fields ("User CRUD")."""
    user = await _require_user(users, user_id)
    user = await users.update(
        user,
        display_name=body.display_name,
        first_name=body.first_name,
        middle_name=body.middle_name,
        last_name=body.last_name,
        phone_number=body.phone_number,
        timezone=body.timezone,
        language=body.language,
        locale=body.locale,
    )
    await cache.invalidate(user_id)
    return SuccessResponse(message="User updated.", data=_to_detail(user), meta=_meta())


@router.patch("/{user_id}", response_model=SuccessResponse[UserDetail])
async def patch_user(
    user_id: UUID, body: UserPatchRequest, users: UserSvc, cache: CacheSvc, _caller: CurrentUserId
) -> SuccessResponse[UserDetail]:
    """Partially update a user ("User CRUD")."""
    user = await _require_user(users, user_id)
    fields = body.model_dump(exclude_unset=True)
    user = await users.patch(user, **fields)
    await cache.invalidate(user_id)
    return SuccessResponse(message="User updated.", data=_to_detail(user), meta=_meta())


@router.delete("/{user_id}", response_model=SuccessResponse[dict[str, bool]])
async def delete_user(
    user_id: UUID, users: UserSvc, cache: CacheSvc, _caller: CurrentUserId
) -> SuccessResponse[dict[str, bool]]:
    """Soft-delete a user ("User CRUD")."""
    user = await _require_user(users, user_id)
    await users.delete(user)
    await cache.invalidate(user_id)
    return SuccessResponse(message="User deleted.", data={"success": True}, meta=_meta())


__all__ = ["router"]
