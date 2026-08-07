"""Plugin package build, download, and signature verification
(docs/059 "PACKAGING" / "SECURITY", extension surface).
"""

from __future__ import annotations

import base64
from uuid import UUID

from fastapi import APIRouter
from shared_core.exceptions.not_found import NotFoundError
from shared_core.logging.context import get_log_context

from app.api.deps import PackageSvc
from app.schemas.marketplace import (
    PluginPackageBuildRequest,
    PluginPackageResponse,
    PluginPackageVerifyRequest,
)
from app.schemas.response import ResponseMeta, SuccessResponse

router = APIRouter(prefix="/plugins/{plugin_id}/versions/{version_id}/package", tags=["Packages"])


def _meta() -> ResponseMeta:
    return ResponseMeta(request_id=get_log_context().request_id or "unknown")


@router.get(
    "", response_model=SuccessResponse[PluginPackageResponse], summary="Get a version's own package"
)
async def get_package(
    version_id: UUID, packages: PackageSvc
) -> SuccessResponse[PluginPackageResponse]:
    """The stored package artifact for one plugin version."""
    found = await packages.get_for_version(version_id)
    if found is None:
        raise NotFoundError(f"No package has been built for version {version_id}.")
    return SuccessResponse(
        message="Package found.", data=PluginPackageResponse.model_validate(found), meta=_meta()
    )


@router.post(
    "",
    response_model=SuccessResponse[PluginPackageResponse],
    status_code=201,
    summary="Build and store a version's own package",
)
async def build_package(
    organization_id: UUID,
    plugin_id: UUID,
    version_id: UUID,
    body: PluginPackageBuildRequest,
    packages: PackageSvc,
) -> SuccessResponse[PluginPackageResponse]:
    """Build a real archive from the given files, upload it, and optionally sign its checksum."""
    files = {path: base64.b64decode(content) for path, content in body.files.items()}
    created = await packages.build_and_store(
        organization_id,
        plugin_id,
        version_id,
        files=files,
        package_format=body.package_format,
        signer_id=body.signer_id,
        signing_private_key_pem=body.signing_private_key_pem,
        signer_key_fingerprint=body.signer_key_fingerprint,
    )
    return SuccessResponse(
        message="Package built.", data=PluginPackageResponse.model_validate(created), meta=_meta()
    )


@router.post(
    "/verify",
    response_model=SuccessResponse[PluginPackageResponse],
    summary="Verify a version's own package signature",
)
async def verify_package(
    version_id: UUID, body: PluginPackageVerifyRequest, packages: PackageSvc
) -> SuccessResponse[PluginPackageResponse]:
    """Verify a package's own signature against a publisher's public key.

    Raises:
        NotFoundError: If no package has been built for this version.
    """
    found = await packages.get_for_version(version_id)
    if found is None:
        raise NotFoundError(f"No package has been built for version {version_id}.")
    verified = await packages.verify(found, public_key_pem=body.public_key_pem)
    return SuccessResponse(
        message="Package verified.",
        data=PluginPackageResponse.model_validate(verified),
        meta=_meta(),
    )


__all__ = ["router"]
