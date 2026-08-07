"""``connector_credentials`` and ``connector_connections``."""

from __future__ import annotations

import uuid
from datetime import datetime

from shared_core.connectors.credentials import CredentialType
from shared_core.database.base import BaseModel
from sqlalchemy import JSON, DateTime, Float, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.enums import ConnectionStatus, CredentialStatus


class ConnectorCredential(BaseModel):
    """``connector_credentials`` -- one connector's own assigned credential.

    Holds either a *reference* to a secrets-management-service-owned
    secret (``secret_ref``, resolved live at connection time -- the
    established precedent for a third-party credential this service
    does not itself mint, matching automation-service/discovery-service/
    configuration-management-service's own ``CredentialResolver``) or an
    *encrypted value this service manages itself* (``encrypted_value``,
    AES-256-GCM via ``shared_core.security.encryption`` -- used for
    OAuth2 access/refresh tokens this service's own token-exchange flow
    obtains, which have no secrets-management-service secret id to
    reference). Exactly one of the two is ever set.
    """

    __tablename__ = "connector_credentials"
    __table_args__ = (Index("ix_connector_credential_connector", "connector_id"),)

    connector_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("connectors.id", ondelete="CASCADE"), index=True
    )
    credential_type: Mapped[CredentialType] = mapped_column(String(24))
    status: Mapped[CredentialStatus] = mapped_column(
        String(24), default=CredentialStatus.PENDING_VALIDATION, index=True
    )
    secret_ref: Mapped[str | None] = mapped_column(String(255), default=None)
    encrypted_value: Mapped[str | None] = mapped_column(Text, default=None)
    encrypted_refresh_value: Mapped[str | None] = mapped_column(Text, default=None)
    """The OAuth2 refresh token, encrypted separately from the access
    token (``encrypted_value``) -- refreshing rotates the access token
    far more often than the refresh token itself."""
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    last_validated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), default=None
    )
    last_rotated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    owner_id: Mapped[str | None] = mapped_column(String(128), default=None)


class ConnectorConnection(BaseModel):
    """``connector_connections`` -- one discrete test/validate/connect attempt."""

    __tablename__ = "connector_connections"
    __table_args__ = (Index("ix_connector_connection_connector", "connector_id"),)

    connector_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("connectors.id", ondelete="CASCADE"), index=True
    )
    credential_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("connector_credentials.id", ondelete="SET NULL"), default=None
    )
    status: Mapped[ConnectionStatus] = mapped_column(String(16), default=ConnectionStatus.TESTING)
    tested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    latency_ms: Mapped[float | None] = mapped_column(Float, default=None)
    error: Mapped[str | None] = mapped_column(Text, default=None)
    response_metadata: Mapped[dict[str, object]] = mapped_column(JSON, default=dict)
    attempt_number: Mapped[int] = mapped_column(Integer, default=1)


__all__ = ["ConnectorConnection", "ConnectorCredential"]
