"""Enumerations for the secrets management service's persisted domain.

Per docs/035 "SECRET TYPES"/"SECRET STATUS"/etc.
"""

from __future__ import annotations

from enum import StrEnum


class SecretType(StrEnum):
    """Per docs/035 "SECRET TYPES" (18 values, verbatim)."""

    PASSWORD = "password"
    SSH_KEY = "ssh_key"
    PRIVATE_KEY = "private_key"
    PUBLIC_KEY = "public_key"
    API_KEY = "api_key"
    OAUTH_TOKEN = "oauth_token"
    JWT_SIGNING_KEY = "jwt_signing_key"
    CERTIFICATE = "certificate"
    TLS_CERTIFICATE = "tls_certificate"
    DATABASE_CREDENTIAL = "database_credential"
    CLOUD_CREDENTIAL = "cloud_credential"
    SERVICE_ACCOUNT_KEY = "service_account_key"
    WEBHOOK_SECRET = "webhook_secret"
    APPLICATION_SECRET = "application_secret"
    LICENSE_KEY = "license_key"
    ENCRYPTION_KEY = "encryption_key"
    AI_PROVIDER_KEY = "ai_provider_key"
    CUSTOM = "custom"


class SecretStatus(StrEnum):
    """Per docs/035 "SECRET STATUS" (7 values, verbatim)."""

    ACTIVE = "active"
    DISABLED = "disabled"
    EXPIRED = "expired"
    PENDING_ROTATION = "pending_rotation"
    REVOKED = "revoked"
    ARCHIVED = "archived"
    DELETED = "deleted"


class EncryptionKeyStatus(StrEnum):
    """A Data Encryption Key's own lifecycle state, distinct from any
    secret it protects.
    """

    ACTIVE = "active"
    ROTATED = "rotated"
    REVOKED = "revoked"


class RotationOutcome(StrEnum):
    """Whether a rotation attempt succeeded, per docs/035 "SECRET
    ROTATION": "Failure Recovery"."""

    SUCCESS = "success"
    FAILED = "failed"


class RotationTrigger(StrEnum):
    """Per docs/035 "SECRET ROTATION": Manual, Scheduled, Automatic."""

    MANUAL = "manual"
    SCHEDULED = "scheduled"
    AUTOMATIC = "automatic"


class LeaseStatus(StrEnum):
    """Per docs/035 "SECRET LEASING"."""

    ACTIVE = "active"
    EXPIRED = "expired"
    REVOKED = "revoked"


class CertificateType(StrEnum):
    """Per docs/035 "CERTIFICATE MANAGEMENT": TLS, Client, CA."""

    TLS = "tls"
    CLIENT = "client"
    CA = "ca"


class CertificateStatus(StrEnum):
    VALID = "valid"
    EXPIRED = "expired"
    REVOKED = "revoked"


class SSHKeyType(StrEnum):
    """Per docs/035 "SSH KEY MANAGEMENT": RSA, ECDSA, Ed25519."""

    RSA = "rsa"
    ECDSA = "ecdsa"
    ED25519 = "ed25519"


class SSHKeyStatus(StrEnum):
    ACTIVE = "active"
    REVOKED = "revoked"
    EXPIRED = "expired"


class ApiKeyStatus(StrEnum):
    ACTIVE = "active"
    REVOKED = "revoked"
    EXPIRED = "expired"


class TokenType(StrEnum):
    """Per docs/035 "TOKEN MANAGEMENT": OAuth, Access, Refresh, Webhook,
    Cloud, AI."""

    OAUTH = "oauth"
    ACCESS = "access"
    REFRESH = "refresh"
    WEBHOOK = "webhook"
    CLOUD = "cloud"
    AI = "ai"


class TokenStatus(StrEnum):
    ACTIVE = "active"
    REVOKED = "revoked"
    EXPIRED = "expired"


class ProviderType(StrEnum):
    """Per docs/035 "SECRET PROVIDERS" (7 values, verbatim)."""

    INTERNAL_VAULT = "internal_vault"
    HASHICORP_VAULT = "hashicorp_vault"
    AWS_SECRETS_MANAGER = "aws_secrets_manager"
    AZURE_KEY_VAULT = "azure_key_vault"
    GOOGLE_SECRET_MANAGER = "google_secret_manager"
    CYBERARK = "cyberark"
    PLUGIN = "plugin"


class SecretAccessAction(StrEnum):
    """Per docs/035 "SECRET ACCESS" (8 values, verbatim) -- the
    permission vocabulary ``secret_access`` grants carry.
    """

    READ = "read"
    WRITE = "write"
    ROTATE = "rotate"
    DELETE = "delete"
    EXPORT = "export"
    SHARE = "share"
    LEASE = "lease"
    RESTORE = "restore"


class AuditOutcome(StrEnum):
    """Whether an audited action succeeded or failed."""

    SUCCESS = "success"
    FAILURE = "failure"


__all__ = [
    "ApiKeyStatus",
    "AuditOutcome",
    "CertificateStatus",
    "CertificateType",
    "EncryptionKeyStatus",
    "LeaseStatus",
    "ProviderType",
    "RotationOutcome",
    "RotationTrigger",
    "SSHKeyStatus",
    "SSHKeyType",
    "SecretAccessAction",
    "SecretStatus",
    "SecretType",
    "TokenStatus",
    "TokenType",
]
