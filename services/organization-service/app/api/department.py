"""``/organizations/{id}/departments`` and ``/departments/{id}``. Per docs/033 REST list.

Two router prefixes in one file since they're the same domain but
different URL shapes. ``/departments/{id}`` has no ``organization_id``
in its path, so its admin check loads the department first to discover
which organization it belongs to, then calls
:func:`app.api.deps.require_role_in_org` directly rather than via
``Depends()`` (which needs the path parameter to exist up front).
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends
from shared_core.logging.context import get_log_context

from app.api.deps import (
    CurrentUserId,
    DepartmentSvc,
    MemberSvc,
    require_admin,
    require_member,
    require_role_in_org,
)
from app.models.department import Department
from app.models.enums import MemberRole
from app.schemas.department import (
    DepartmentCreateRequest,
    DepartmentResponse,
    DepartmentUpdateRequest,
)
from app.schemas.response import ResponseMeta, SuccessResponse

org_router = APIRouter(prefix="/organizations/{organization_id}/departments", tags=["Departments"])
router = APIRouter(prefix="/departments", tags=["Departments"])


def _meta() -> ResponseMeta:
    return ResponseMeta(request_id=get_log_context().request_id or "unknown")


def _to_response(department: Department) -> DepartmentResponse:
    return DepartmentResponse(
        id=department.id,
        organization_id=department.organization_id,
        name=department.name,
        code=department.code,
        description=department.description,
        parent_department_id=department.parent_department_id,
        manager_id=department.manager_id,
        metadata=department.metadata_,
        created_at=department.created_at,
        updated_at=department.updated_at,
    )


@org_router.get(
    "",
    response_model=SuccessResponse[list[DepartmentResponse]],
    dependencies=[Depends(require_member)],
)
async def list_departments(
    organization_id: UUID, departments: DepartmentSvc, _caller: CurrentUserId
) -> SuccessResponse[list[DepartmentResponse]]:
    """List every department in an organization ("Department Management")."""
    records = await departments.list_for_org(organization_id)
    return SuccessResponse(
        message="Departments retrieved.", data=[_to_response(d) for d in records], meta=_meta()
    )


@org_router.post(
    "",
    response_model=SuccessResponse[DepartmentResponse],
    status_code=201,
    dependencies=[Depends(require_admin)],
)
async def create_department(
    organization_id: UUID, body: DepartmentCreateRequest, departments: DepartmentSvc
) -> SuccessResponse[DepartmentResponse]:
    """Create a new department ("Create")."""
    department = await departments.create(
        organization_id,
        name=body.name,
        code=body.code,
        description=body.description,
        parent_department_id=body.parent_department_id,
        manager_id=body.manager_id,
        metadata=body.metadata,
    )
    return SuccessResponse(
        message="Department created.", data=_to_response(department), meta=_meta()
    )


@router.put("/{department_id}", response_model=SuccessResponse[DepartmentResponse])
async def update_department(
    department_id: UUID,
    body: DepartmentUpdateRequest,
    departments: DepartmentSvc,
    caller: CurrentUserId,
    members: MemberSvc,
) -> SuccessResponse[DepartmentResponse]:
    """Update a department's mutable fields ("Update")."""
    existing = await departments.get_by_id(department_id)
    await require_role_in_org(existing.organization_id, caller, members, MemberRole.ADMIN)
    department = await departments.update(
        department_id,
        name=body.name,
        description=body.description,
        parent_department_id=body.parent_department_id,
        manager_id=body.manager_id,
        metadata=body.metadata,
    )
    return SuccessResponse(
        message="Department updated.", data=_to_response(department), meta=_meta()
    )


@router.delete("/{department_id}", response_model=SuccessResponse[dict[str, bool]])
async def delete_department(
    department_id: UUID, departments: DepartmentSvc, caller: CurrentUserId, members: MemberSvc
) -> SuccessResponse[dict[str, bool]]:
    """Delete a department ("Delete")."""
    existing = await departments.get_by_id(department_id)
    await require_role_in_org(existing.organization_id, caller, members, MemberRole.ADMIN)
    await departments.delete(department_id)
    return SuccessResponse(message="Department deleted.", data={"success": True}, meta=_meta())


__all__ = ["org_router", "router"]
