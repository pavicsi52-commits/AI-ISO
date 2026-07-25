"""Automation-related constants."""

from typing import Final


class AutomationConstants:
    """Playbook and execution engine constants."""

    DEFAULT_EXECUTION_TIMEOUT_SECONDS: Final[int] = 3_600
    MAX_CONCURRENT_EXECUTIONS: Final[int] = 50
    DEFAULT_RETRY_ATTEMPTS: Final[int] = 3
