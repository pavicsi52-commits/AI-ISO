"""``configuration_environments`` table. Per docs/039 "ENVIRONMENTS"
"Support": Development, Testing, QA, Staging, Production, Disaster
Recovery, Edge, Industrial, Custom Environments.
"""

from __future__ import annotations

from shared_core.database.base import BaseModel
from sqlalchemy import String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.enums import EnvironmentType


class ConfigurationEnvironment(BaseModel):
    """One environment definition an organization tracks profiles against."""

    __tablename__ = "configuration_environments"
    __table_args__ = (
        UniqueConstraint("organization_id", "name", name="uq_configuration_environment_name"),
    )

    name: Mapped[str] = mapped_column(String(128), index=True)
    environment_type: Mapped[EnvironmentType] = mapped_column(String(24), index=True)
    description: Mapped[str | None] = mapped_column(String(2048), default=None)


__all__ = ["ConfigurationEnvironment"]
