"""``/certificates``. Per docs/035 REST list."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter
from shared_core.logging.context import get_log_context

from app.api.deps import CertificateSvc, CurrentUserId
from app.models.certificate import Certificate
from app.schemas.certificate import CertificateImportRequest, CertificateResponse
from app.schemas.response import ResponseMeta, SuccessResponse

router = APIRouter(prefix="/certificates", tags=["Certificates"])


def _meta() -> ResponseMeta:
    return ResponseMeta(request_id=get_log_context().request_id or "unknown")


def _to_response(certificate: Certificate) -> CertificateResponse:
    return CertificateResponse(
        id=certificate.id,
        organization_id=certificate.organization_id,
        project_id=certificate.project_id,
        name=certificate.name,
        certificate_type=certificate.certificate_type,
        certificate_pem=certificate.certificate_pem,
        chain_pem=certificate.chain_pem,
        private_key_secret_id=certificate.private_key_secret_id,
        subject=certificate.subject,
        issuer=certificate.issuer,
        serial_number=certificate.serial_number,
        fingerprint=certificate.fingerprint,
        not_before=certificate.not_before,
        not_after=certificate.not_after,
        status=certificate.status,
        created_at=certificate.created_at,
        updated_at=certificate.updated_at,
    )


@router.get("", response_model=SuccessResponse[list[CertificateResponse]])
async def list_certificates(
    organization_id: UUID, certificates: CertificateSvc, _caller: CurrentUserId
) -> SuccessResponse[list[CertificateResponse]]:
    """List every certificate belonging to *organization_id*."""
    records = await certificates.list_for_org(organization_id)
    return SuccessResponse(
        message="Certificates retrieved.",
        data=[_to_response(c) for c in records],
        meta=_meta(),
    )


@router.post("", response_model=SuccessResponse[CertificateResponse], status_code=201)
async def import_certificate(
    body: CertificateImportRequest, certificates: CertificateSvc, _caller: CurrentUserId
) -> SuccessResponse[CertificateResponse]:
    """Import a certificate, optionally with its private key ("Import")."""
    certificate = await certificates.import_certificate(
        organization_id=body.organization_id,
        project_id=body.project_id,
        name=body.name,
        certificate_type=body.certificate_type,
        certificate_pem=body.certificate_pem,
        chain_pem=body.chain_pem,
        private_key=body.private_key,
        owner_id=body.owner_id,
    )
    return SuccessResponse(
        message="Certificate imported.", data=_to_response(certificate), meta=_meta()
    )


@router.delete("/{certificate_id}", response_model=SuccessResponse[dict[str, bool]])
async def delete_certificate(
    certificate_id: UUID, certificates: CertificateSvc, _caller: CurrentUserId
) -> SuccessResponse[dict[str, bool]]:
    """Delete a certificate ("Revocation")."""
    await certificates.delete(certificate_id)
    return SuccessResponse(message="Certificate deleted.", data={"success": True}, meta=_meta())


__all__ = ["router"]
