"""Secret resolution and masking.

Resolution itself lives in :mod:`shared_core.config.secrets` (env var /
Docker secret / Kubernetes secret file); this module re-exports it under
the security namespace and adds masking for safe display/logging. Per
docs/017_Enterprise_Security_Framework.md.txt "SECRET MANAGEMENT":
HashiCorp Vault, AWS Secrets Manager, Azure Key Vault, and GCP Secret
Manager are explicitly future backends -- not implemented here.
"""

from __future__ import annotations

from shared_core.config.secrets import resolve_secret
from shared_core.helpers.string_helper import mask_string

__all__ = ["mask_secret", "resolve_secret"]


def mask_secret(value: str) -> str:
    """Mask a secret for safe display in logs or UIs."""
    return mask_string(value, visible_chars=4)
