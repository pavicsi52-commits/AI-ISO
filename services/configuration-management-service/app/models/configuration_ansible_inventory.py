"""``configuration_ansible_inventories`` table. Per docs/039 "ANSIBLE
INTEGRATION" "Support": Inventories, Host Variables, Group Variables,
Playbooks, Roles, Collections, Vault References, Execution Metadata.

Per docs/039's own SECURITY section, :attr:`vault_ref` stores only a
``services/secrets-management-service`` reference id, never a raw
Ansible Vault password.
"""

from __future__ import annotations

import uuid
from typing import Any

from shared_core.database.base import BaseModel
from sqlalchemy import JSON, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column


class ConfigurationAnsibleInventory(BaseModel):
    """One Ansible inventory bundle backing a configuration profile."""

    __tablename__ = "configuration_ansible_inventories"

    profile_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("configuration_profiles.id", ondelete="SET NULL"), default=None, index=True
    )
    name: Mapped[str] = mapped_column(String(255), index=True)
    inventory_content: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    host_vars: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    group_vars: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    playbooks: Mapped[list[str]] = mapped_column(JSON, default=list)
    roles: Mapped[list[str]] = mapped_column(JSON, default=list)
    collections: Mapped[list[str]] = mapped_column(JSON, default=list)
    vault_ref: Mapped[str | None] = mapped_column(String(255), default=None)


__all__ = ["ConfigurationAnsibleInventory"]
