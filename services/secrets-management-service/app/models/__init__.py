"""SQLAlchemy models for the secrets management service.

Every model must be imported here so it registers with
:data:`shared_core.database.base.Base.metadata` -- both Alembic
autogenerate and any create_all() call rely on every table being
known before they run.
"""

from __future__ import annotations

from app.models.api_key import ApiKeyEntry
from app.models.certificate import Certificate
from app.models.credential_set import CredentialSet
from app.models.encryption_key import EncryptionKey
from app.models.key_rotation_history import KeyRotationHistoryEntry
from app.models.secret import Secret
from app.models.secret_access import SecretAccessGrant
from app.models.secret_audit import SecretAuditEntry
from app.models.secret_category import SecretCategory
from app.models.secret_lease import SecretLease
from app.models.secret_metadata import SecretMetadataEntry
from app.models.secret_provider import SecretProvider
from app.models.secret_rotation import SecretRotationEntry
from app.models.secret_tag import SecretTag
from app.models.secret_version import SecretVersion
from app.models.ssh_key import SSHKey
from app.models.token import TokenEntry

__all__ = [
    "ApiKeyEntry",
    "Certificate",
    "CredentialSet",
    "EncryptionKey",
    "KeyRotationHistoryEntry",
    "SSHKey",
    "Secret",
    "SecretAccessGrant",
    "SecretAuditEntry",
    "SecretCategory",
    "SecretLease",
    "SecretMetadataEntry",
    "SecretProvider",
    "SecretRotationEntry",
    "SecretTag",
    "SecretVersion",
    "TokenEntry",
]
