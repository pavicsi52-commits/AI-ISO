"""Enterprise Security Framework.

Everything security-related lives inside this package
(docs/017_Enterprise_Security_Framework.md.txt "OBJECTIVE"). Every
microservice uses this framework; no service implements custom security.
"""

from shared_core.decorators.security import (
    requires_organization,
    requires_permission,
    requires_project,
    requires_role,
)
from shared_core.security.apikey import (
    ApiKeyRecord,
    check_api_key_ip_allowed,
    check_api_key_scope,
    create_api_key,
    generate_api_key,
    generate_random_token,
    hash_api_key,
    is_api_key_expired,
    is_api_key_usable,
    record_api_key_usage,
    revoke_api_key,
    rotate_api_key,
)
from shared_core.security.audit import SecurityAuditEventType, audit_security_event
from shared_core.security.authentication import (
    AuthenticationResult,
    authenticate_with_api_key,
    authenticate_with_jwt,
)
from shared_core.security.authorization import AuthorizationResult, authorize
from shared_core.security.certificates import (
    days_until_expiration,
    get_certificate_fingerprint,
    is_certificate_expired,
    is_certificate_not_yet_valid,
    is_certificate_valid_now,
    is_self_signed,
    parse_certificate,
)
from shared_core.security.constants import SecurityFrameworkConstants
from shared_core.security.context import (
    SecurityContext,
    bind_security_context,
    get_security_context,
    reset_security_context,
)
from shared_core.security.cors import (
    CorsConfig,
    development_cors_config,
    is_origin_allowed,
    production_cors_config,
)
from shared_core.security.csrf import generate_csrf_token, validate_double_submit_token
from shared_core.security.decorators import requires_api_key, requires_auth, requires_mfa
from shared_core.security.encryption import (
    decrypt,
    encrypt,
    generate_encryption_key,
    generate_rsa_keypair,
    rotate_key,
    rsa_decrypt,
    rsa_encrypt,
)
from shared_core.security.exceptions import (
    CertificateExpiredError,
    CsrfValidationError,
    InvalidMfaCodeError,
    MfaRequiredError,
    SessionExpiredError,
    SessionRevokedError,
    TokenRevokedError,
)
from shared_core.security.hashing import sign, verify_signature
from shared_core.security.headers import (
    SecurityHeadersConfig,
    build_security_headers,
    development_headers,
    production_headers,
)
from shared_core.security.jwt import (
    CLOCK_SKEW_LEEWAY_SECONDS,
    SUPPORTED_ALGORITHMS,
    KeyRing,
    decode_token,
    encode_token,
    get_key_id,
)
from shared_core.security.mfa import (
    generate_email_otp,
    generate_recovery_codes,
    generate_totp_code,
    generate_totp_secret,
    generate_trusted_device_token,
    verify_recovery_code,
    verify_totp_code,
)
from shared_core.security.password import (
    PasswordPolicyResult,
    check_dictionary,
    check_password_expired,
    check_password_history,
    hash_password,
    hibp_lookup_key,
    is_breached,
    needs_rehash,
    verify_password,
)
from shared_core.security.permissions import can_access_resource, effective_permissions
from shared_core.security.policies import Policy, PolicyContext, PolicyEngine, PolicyPredicate
from shared_core.security.providers import AuthenticationProvider
from shared_core.security.ratelimit import DistributedRateLimiter, rate_limit_key
from shared_core.security.rbac import (
    ROLE_PERMISSIONS,
    PermissionScope,
    has_all_permissions,
    has_any_permission,
    has_permission,
    has_scoped_permission,
)
from shared_core.security.refresh import TokenPair, issue_token_pair, rotate_token_pair
from shared_core.security.roles import CustomRole, resolve_custom_role_permissions
from shared_core.security.secrets import mask_secret, resolve_secret
from shared_core.security.sessions import Session, SessionManager
from shared_core.security.validators import (
    validate_certificate_not_expired,
    validate_certificate_pem,
    validate_required_security_headers,
)

__all__ = [
    "CLOCK_SKEW_LEEWAY_SECONDS",
    "ROLE_PERMISSIONS",
    "SUPPORTED_ALGORITHMS",
    "ApiKeyRecord",
    "AuthenticationProvider",
    "AuthenticationResult",
    "AuthorizationResult",
    "CertificateExpiredError",
    "CorsConfig",
    "CsrfValidationError",
    "CustomRole",
    "DistributedRateLimiter",
    "InvalidMfaCodeError",
    "KeyRing",
    "MfaRequiredError",
    "PasswordPolicyResult",
    "PermissionScope",
    "Policy",
    "PolicyContext",
    "PolicyEngine",
    "PolicyPredicate",
    "SecurityAuditEventType",
    "SecurityContext",
    "SecurityFrameworkConstants",
    "SecurityHeadersConfig",
    "Session",
    "SessionExpiredError",
    "SessionManager",
    "SessionRevokedError",
    "TokenPair",
    "TokenRevokedError",
    "audit_security_event",
    "authenticate_with_api_key",
    "authenticate_with_jwt",
    "authorize",
    "bind_security_context",
    "build_security_headers",
    "can_access_resource",
    "check_api_key_ip_allowed",
    "check_api_key_scope",
    "check_dictionary",
    "check_password_expired",
    "check_password_history",
    "create_api_key",
    "days_until_expiration",
    "decode_token",
    "decrypt",
    "development_cors_config",
    "development_headers",
    "effective_permissions",
    "encode_token",
    "encrypt",
    "generate_api_key",
    "generate_csrf_token",
    "generate_email_otp",
    "generate_encryption_key",
    "generate_random_token",
    "generate_recovery_codes",
    "generate_rsa_keypair",
    "generate_totp_code",
    "generate_totp_secret",
    "generate_trusted_device_token",
    "get_certificate_fingerprint",
    "get_key_id",
    "get_security_context",
    "has_all_permissions",
    "has_any_permission",
    "has_permission",
    "has_scoped_permission",
    "hash_api_key",
    "hash_password",
    "hibp_lookup_key",
    "is_api_key_expired",
    "is_api_key_usable",
    "is_breached",
    "is_certificate_expired",
    "is_certificate_not_yet_valid",
    "is_certificate_valid_now",
    "is_origin_allowed",
    "is_self_signed",
    "issue_token_pair",
    "mask_secret",
    "needs_rehash",
    "parse_certificate",
    "production_cors_config",
    "production_headers",
    "rate_limit_key",
    "record_api_key_usage",
    "requires_api_key",
    "requires_auth",
    "requires_mfa",
    "requires_organization",
    "requires_permission",
    "requires_project",
    "requires_role",
    "reset_security_context",
    "resolve_custom_role_permissions",
    "resolve_secret",
    "revoke_api_key",
    "rotate_api_key",
    "rotate_key",
    "rotate_token_pair",
    "rsa_decrypt",
    "rsa_encrypt",
    "sign",
    "validate_certificate_not_expired",
    "validate_certificate_pem",
    "validate_double_submit_token",
    "validate_required_security_headers",
    "verify_password",
    "verify_recovery_code",
    "verify_signature",
    "verify_totp_code",
]
