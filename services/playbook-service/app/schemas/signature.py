"""Request/response schemas for playbook digital signatures."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel

from app.models.enums import SignatureAlgorithm


class PlaybookSignatureCreateRequest(BaseModel):
    """Body of ``POST /playbooks/{id}/versions/{version_id}/sign``."""

    signer_id: UUID | None = None


class PlaybookSignatureResponse(BaseModel):
    """One digital signature over a playbook version's own content checksum."""

    id: UUID
    playbook_id: UUID
    version_id: UUID
    signer_id: UUID | None
    algorithm: SignatureAlgorithm
    public_key_fingerprint: str
    signature: str
    checksum: str
    verified: bool
    signed_at: datetime


__all__ = ["PlaybookSignatureCreateRequest", "PlaybookSignatureResponse"]
