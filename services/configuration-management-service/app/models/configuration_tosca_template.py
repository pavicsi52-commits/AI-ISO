"""``configuration_tosca_templates`` table. Per docs/039 "TOSCA
INTEGRATION" "Integrate": TOSCA Templates, CSAR Packages, Node
Templates, Relationship Templates, Policies, Substitution Mappings,
Artifacts, Service Templates.
"""

from __future__ import annotations

import uuid
from typing import Any

from shared_core.database.base import BaseModel
from sqlalchemy import JSON, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.enums import ToscaComponentType


class ConfigurationToscaTemplate(BaseModel):
    """One TOSCA template component (CSAR/node/relationship/policy/
    substitution-mapping/artifact/service template).
    """

    __tablename__ = "configuration_tosca_templates"

    profile_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("configuration_profiles.id", ondelete="SET NULL"), default=None, index=True
    )
    component_type: Mapped[ToscaComponentType] = mapped_column(String(32), index=True)
    name: Mapped[str] = mapped_column(String(255), index=True)
    content: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    csar_url: Mapped[str | None] = mapped_column(String(1024), default=None)


__all__ = ["ConfigurationToscaTemplate"]
