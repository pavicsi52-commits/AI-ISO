"""Repositories for the secrets management service, one per model."""

from __future__ import annotations

from app.repositories.api_key import ApiKeyRepository
from app.repositories.certificate import CertificateRepository
from app.repositories.credential_set import CredentialSetRepository
from app.repositories.encryption_key import EncryptionKeyRepository
from app.repositories.key_rotation_history import KeyRotationHistoryRepository
from app.repositories.secret import SecretRepository
from app.repositories.secret_access import SecretAccessRepository
from app.repositories.secret_audit import SecretAuditRepository
from app.repositories.secret_category import SecretCategoryRepository
from app.repositories.secret_lease import SecretLeaseRepository
from app.repositories.secret_metadata import SecretMetadataRepository
from app.repositories.secret_provider import SecretProviderRepository
from app.repositories.secret_rotation import SecretRotationRepository
from app.repositories.secret_tag import SecretTagRepository
from app.repositories.secret_version import SecretVersionRepository
from app.repositories.ssh_key import SSHKeyRepository
from app.repositories.token import TokenRepository

__all__ = [
    "ApiKeyRepository",
    "CertificateRepository",
    "CredentialSetRepository",
    "EncryptionKeyRepository",
    "KeyRotationHistoryRepository",
    "SSHKeyRepository",
    "SecretAccessRepository",
    "SecretAuditRepository",
    "SecretCategoryRepository",
    "SecretLeaseRepository",
    "SecretMetadataRepository",
    "SecretProviderRepository",
    "SecretRepository",
    "SecretRotationRepository",
    "SecretTagRepository",
    "SecretVersionRepository",
    "TokenRepository",
]
