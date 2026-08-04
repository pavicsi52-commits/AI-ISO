"""``incident_impacts``, ``incident_services``, ``incident_assets``.

What an incident is actually hurting. Kept as three tables because they
answer at different grains: :class:`IncidentImpact` is the assessed
severity of the incident as a whole (business impact, customer impact,
blast radius); :class:`IncidentServiceImpact` and
:class:`IncidentAssetImpact` are the individual services and assets
that make that assessment concrete and checkable rather than asserted.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from shared_core.database.base import BaseModel
from sqlalchemy import JSON, DateTime, Float, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.enums import ImpactLevel, RiskLevel


class IncidentImpact(BaseModel):
    """``incident_impacts`` -- the assessed severity of one incident.

    One row per assessment, not one mutable summary -- impact is
    re-assessed as an incident's scope becomes clearer, and the sequence
    of assessments is itself part of the record a review reads: an
    incident whose blast radius was underestimated for an hour is a
    different story than one correctly scoped from the start.
    """

    __tablename__ = "incident_impacts"
    __table_args__ = (
        Index("ix_incident_impact_incident", "organization_id", "incident_id", "assessed_at"),
    )

    incident_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("incidents.id", ondelete="CASCADE"), index=True
    )
    business_impact: Mapped[ImpactLevel] = mapped_column(String(32), default=ImpactLevel.NONE)
    customer_impact: Mapped[ImpactLevel] = mapped_column(String(32), default=ImpactLevel.NONE)
    topology_impact: Mapped[ImpactLevel] = mapped_column(String(32), default=ImpactLevel.NONE)
    risk_level: Mapped[RiskLevel] = mapped_column(String(32), default=RiskLevel.LOW, index=True)

    affected_users_estimate: Mapped[int | None] = mapped_column(Integer, default=None)
    revenue_impact_estimate: Mapped[float | None] = mapped_column(Float, default=None)
    blast_radius_summary: Mapped[str | None] = mapped_column(Text, default=None)

    assessed_by: Mapped[str | None] = mapped_column(String(255), default=None)
    assessed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    source_graph_snapshot: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    """The knowledge-graph traversal this assessment was derived from,
    when Prompt 049's dependency analysis produced it -- kept so an
    assessment nobody can currently reproduce can still be audited
    against what the topology looked like at the time."""


class IncidentServiceImpact(BaseModel):
    """``incident_services`` -- one platform service affected."""

    __tablename__ = "incident_services"
    __table_args__ = (Index("ix_incident_service_incident", "organization_id", "incident_id"),)

    incident_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("incidents.id", ondelete="CASCADE"), index=True
    )
    service_name: Mapped[str] = mapped_column(String(255))
    impact_level: Mapped[ImpactLevel] = mapped_column(String(32), default=ImpactLevel.MODERATE)
    is_root: Mapped[bool] = mapped_column(default=False)
    """Whether this service is where the problem originated, as opposed
    to one merely downstream of it. What separates "23 services affected"
    from "here is the one to actually go fix"."""

    detail: Mapped[str | None] = mapped_column(Text, default=None)


class IncidentAssetImpact(BaseModel):
    """``incident_assets`` -- one inventory asset affected."""

    __tablename__ = "incident_assets"
    __table_args__ = (Index("ix_incident_asset_incident", "organization_id", "incident_id"),)

    incident_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("incidents.id", ondelete="CASCADE"), index=True
    )
    asset_id: Mapped[str | None] = mapped_column(String(255), default=None, index=True)
    asset_name: Mapped[str] = mapped_column(String(255))
    asset_type: Mapped[str | None] = mapped_column(String(128), default=None)
    impact_level: Mapped[ImpactLevel] = mapped_column(String(32), default=ImpactLevel.MODERATE)
    detail: Mapped[str | None] = mapped_column(Text, default=None)


__all__ = ["IncidentAssetImpact", "IncidentImpact", "IncidentServiceImpact"]
