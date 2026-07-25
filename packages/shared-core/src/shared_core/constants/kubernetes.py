"""Kubernetes-related constants."""

from typing import Final


class KubernetesConstants:
    """Kubernetes deployment constants."""

    DEFAULT_NAMESPACE: Final[str] = "ai-ios"
    LIVENESS_PATH: Final[str] = "/liveness"
    READINESS_PATH: Final[str] = "/readiness"
    METRICS_PATH: Final[str] = "/metrics"
    HEALTH_PATH: Final[str] = "/health"
