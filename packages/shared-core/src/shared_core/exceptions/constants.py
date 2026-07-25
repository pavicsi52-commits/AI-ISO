"""Exception framework constants: the error-code catalog and localization.

The single source of truth for every concrete :class:`AIIOSException`
subclass -- used to enforce "Codes must be unique" at import time, to
drive :mod:`shared_core.exceptions.factory`'s code-to-class lookup, and to
build the default (English) localization catalog from each class's
``default_user_message`` rather than duplicating those strings by hand.
"""

from __future__ import annotations

import re
from typing import Final

from shared_core.exceptions.ai import AIError
from shared_core.exceptions.authentication import AuthenticationError
from shared_core.exceptions.authorization import AuthorizationError
from shared_core.exceptions.automation import AutomationError
from shared_core.exceptions.base import AIIOSException
from shared_core.exceptions.business import BusinessRuleError
from shared_core.exceptions.cache import CacheError
from shared_core.exceptions.configuration import ConfigurationError
from shared_core.exceptions.conflict import ConflictError
from shared_core.exceptions.connector import ConnectorError
from shared_core.exceptions.database import DatabaseError
from shared_core.exceptions.dependency import DependencyError
from shared_core.exceptions.event import EventError
from shared_core.exceptions.inventory import InventoryError
from shared_core.exceptions.monitoring import MonitoringError
from shared_core.exceptions.network import NetworkError
from shared_core.exceptions.not_found import NotFoundError
from shared_core.exceptions.notification import NotificationError
from shared_core.exceptions.plugin import PluginError
from shared_core.exceptions.queue import QueueError
from shared_core.exceptions.rate_limit import RateLimitError
from shared_core.exceptions.scheduler import SchedulerError
from shared_core.exceptions.service import ExternalError, InternalError, UnknownError
from shared_core.exceptions.storage import StorageError
from shared_core.exceptions.telemetry import TelemetryError
from shared_core.exceptions.timeout import AIIOSTimeoutError
from shared_core.exceptions.validation import ValidationError
from shared_core.exceptions.workflow import WorkflowError


class ExceptionConstants:
    """Constants governing error-code shape and severity/HTTP mapping."""

    ERROR_CODE_PATTERN: Final[str] = r"^AIIOS-[A-Z]+-\d{4}$"
    SEVERITY_LEVELS: Final[tuple[str, ...]] = ("low", "medium", "high", "critical")
    DEFAULT_LOCALE: Final[str] = "en"


_ERROR_CODE_REGEX = re.compile(ExceptionConstants.ERROR_CODE_PATTERN)

ALL_EXCEPTION_CLASSES: Final[tuple[type[AIIOSException], ...]] = (
    AIError,
    AuthenticationError,
    AuthorizationError,
    AutomationError,
    BusinessRuleError,
    CacheError,
    ConfigurationError,
    ConflictError,
    ConnectorError,
    DatabaseError,
    DependencyError,
    EventError,
    ExternalError,
    InternalError,
    InventoryError,
    MonitoringError,
    NetworkError,
    NotFoundError,
    NotificationError,
    PluginError,
    QueueError,
    RateLimitError,
    SchedulerError,
    StorageError,
    TelemetryError,
    AIIOSTimeoutError,
    UnknownError,
    ValidationError,
    WorkflowError,
)


def _build_catalog(
    classes: tuple[type[AIIOSException], ...] = ALL_EXCEPTION_CLASSES,
) -> dict[str, type[AIIOSException]]:
    """Build the error-code -> exception-class catalog from *classes*.

    Raises:
        ValueError: If any class's ``error_code`` doesn't match
            :data:`ExceptionConstants.ERROR_CODE_PATTERN`, or two classes
            share the same code ("Codes must be unique").

    Takes *classes* as a parameter (rather than only ever reading the
    module-level :data:`ALL_EXCEPTION_CLASSES`) so this validation logic
    is unit-testable against a small deliberately-invalid set without
    mutating global state that other tests depend on.
    """
    catalog: dict[str, type[AIIOSException]] = {}
    for exception_cls in classes:
        code = exception_cls.error_code
        if not _ERROR_CODE_REGEX.match(code):
            raise ValueError(
                f"{exception_cls.__name__}.error_code {code!r} does not match "
                f"the required format {ExceptionConstants.ERROR_CODE_PATTERN!r}."
            )
        if code in catalog:
            raise ValueError(
                f"Duplicate error code {code!r}: used by both "
                f"{catalog[code].__name__} and {exception_cls.__name__}."
            )
        catalog[code] = exception_cls
    return catalog


ERROR_CODE_CATALOG: Final[dict[str, type[AIIOSException]]] = _build_catalog()

# Localization catalog: locale -> {error_code: translated user-facing message}.
# "en" is built automatically from each class's `default_user_message` -- one
# source of truth. Other locales are hand-authored and may cover only a
# subset of codes; `localize_message` falls back to English, then to
# whatever message the exception instance already carries.
MESSAGE_CATALOG: Final[dict[str, dict[str, str]]] = {
    "en": {cls.error_code: cls.default_user_message for cls in ALL_EXCEPTION_CLASSES},
    "es": {
        ValidationError.error_code: (
            "La solicitud no es válida. Verifique su información e intente de nuevo."
        ),
        AuthenticationError.error_code: "Error de autenticación. Inicie sesión nuevamente.",
        AuthorizationError.error_code: "No tiene permiso para realizar esta acción.",
        NotFoundError.error_code: "No se encontró el recurso solicitado.",
        ConflictError.error_code: (
            "Esta solicitud entra en conflicto con el estado actual del recurso."
        ),
        RateLimitError.error_code: (
            "Demasiadas solicitudes. Reduzca la velocidad e intente de nuevo."
        ),
        DatabaseError.error_code: "Ocurrió un error en la base de datos. Intente de nuevo.",
        DependencyError.error_code: "Un servicio requerido no está disponible temporalmente.",
        AIIOSTimeoutError.error_code: "La solicitud tardó demasiado. Intente de nuevo.",
        InternalError.error_code: "Ocurrió un error interno. Contacte con soporte.",
    },
}


def localize_message(error_code: str, locale: str, fallback: str) -> str:
    """Return the user-facing message for *error_code* in *locale*.

    Falls back to :data:`ExceptionConstants.DEFAULT_LOCALE` ("en"), then to
    *fallback* (typically the exception instance's own ``user_message``)
    if no translation exists anywhere.
    """
    locale_catalog = MESSAGE_CATALOG.get(locale, {})
    if error_code in locale_catalog:
        return locale_catalog[error_code]

    default_catalog = MESSAGE_CATALOG[ExceptionConstants.DEFAULT_LOCALE]
    return default_catalog.get(error_code, fallback)
