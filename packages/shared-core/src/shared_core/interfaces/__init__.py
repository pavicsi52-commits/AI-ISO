"""Structural interfaces (``typing.Protocol``) implemented by concrete
framework components. Depending on an interface here, rather than a
concrete class, keeps services swappable per the Dependency Inversion
Principle (docs/005_Coding_Standards_Master.md.txt).
"""

from shared_core.interfaces.event import EventConsumerProtocol, EventPublisherProtocol
from shared_core.interfaces.queue import QueueProtocol
from shared_core.interfaces.repository import RepositoryProtocol
from shared_core.interfaces.service import ServiceProtocol
from shared_core.interfaces.storage import StorageProtocol
from shared_core.interfaces.validator import ValidatorProtocol

__all__ = [
    "EventConsumerProtocol",
    "EventPublisherProtocol",
    "QueueProtocol",
    "RepositoryProtocol",
    "ServiceProtocol",
    "StorageProtocol",
    "ValidatorProtocol",
]
