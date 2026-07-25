"""Configuration-specific exceptions.

Every exception here subclasses
:class:`shared_core.exceptions.configuration.ConfigurationError`, so
existing ``except ConfigurationError`` handlers keep working, while callers
that need to distinguish the specific failure mode
(docs/013_Configuration_Framework.md.txt "ERROR HANDLING") can catch the
concrete subclass.
"""

from __future__ import annotations

from typing import Any

from shared_core.exceptions.configuration import ConfigurationError


class InvalidConfigurationError(ConfigurationError):
    """A configuration section failed to load or validate."""

    error_code = "AIIOS-CONFIG-0002"

    def __init__(self, section: str, reason: str) -> None:
        super().__init__(
            f"Invalid configuration in section '{section}': {reason}",
            details=[reason],
            metadata={"section": section},
        )


class MissingVariableError(ConfigurationError):
    """A required configuration variable was not set."""

    error_code = "AIIOS-CONFIG-0003"

    def __init__(self, variable: str) -> None:
        super().__init__(
            f"Configuration variable '{variable}' is required but was not set.",
            metadata={"variable": variable},
        )


class InvalidTypeError(ConfigurationError):
    """A configuration value could not be interpreted as the requested type."""

    error_code = "AIIOS-CONFIG-0004"

    def __init__(self, variable: str, expected_type: str, value: Any) -> None:
        super().__init__(
            f"Configuration variable '{variable}' could not be interpreted as "
            f"{expected_type} (got {value!r}).",
            metadata={"variable": variable, "expected_type": expected_type},
        )


class MissingSecretError(ConfigurationError):
    """A required production secret is missing."""

    error_code = "AIIOS-CONFIG-0005"
    severity = "critical"

    def __init__(self, missing: list[str]) -> None:
        super().__init__(
            "Missing required production secrets.",
            details=missing,
        )


class UnknownEnvironmentError(ConfigurationError):
    """An unrecognized deployment environment name was supplied."""

    error_code = "AIIOS-CONFIG-0006"

    def __init__(self, value: str) -> None:
        super().__init__(
            f"Unknown environment '{value}'.",
            metadata={"value": value},
        )


class CircularConfigurationError(ConfigurationError):
    """A configuration value references itself, directly or indirectly."""

    error_code = "AIIOS-CONFIG-0007"

    def __init__(self, variable: str) -> None:
        super().__init__(
            f"Circular configuration reference detected for '{variable}'.",
            metadata={"variable": variable},
        )
