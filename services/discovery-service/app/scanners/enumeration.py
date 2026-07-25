"""The contract every *enumeration provider* implements.

Per docs/037 "CLOUD DISCOVERY"/"KUBERNETES DISCOVERY": unlike
:class:`~app.scanners.base.ProtocolScanner` (one probe against one
address, one :class:`~app.scanners.base.ScanOutcome` back), discovering
a cloud account or a Kubernetes cluster means enumerating an
arbitrarily long, heterogeneous list of sub-resources (instances,
subnets, security groups, load balancers, storage, managed databases,
namespaces, pods, deployments, ...). Modeling that as a single
"probe" would either lose most of the required data or force
:class:`~app.scanners.base.ScanOutcome` to carry an unbounded nested
payload no other scanner needs -- so cloud/Kubernetes discovery gets
its own, complementary contract instead:
:class:`EnumerationProvider`, keyed by
:class:`~app.models.enums.TargetType` (not
:class:`~app.models.enums.ProtocolType` -- a cloud account or cluster
is a *target kind*, not a wire protocol) and returning a list of
:class:`DiscoveredResource`, one per sub-resource found.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

from app.models.enums import TargetType
from app.scanners.base import ScanCredential


@dataclass(slots=True)
class DiscoveredResource:
    """One sub-resource found while enumerating a cloud account or cluster."""

    name: str
    resource_type: str
    identity: dict[str, Any] = field(default_factory=dict)


class EnumerationProvider(ABC):
    """Enumerates every sub-resource within one cloud account or cluster."""

    target_type: TargetType

    @abstractmethod
    async def enumerate(
        self, address: str, *, credential: ScanCredential | None, timeout_seconds: float
    ) -> list[DiscoveredResource]:
        """Enumerate every discoverable sub-resource of *address*.

        Raises:
            EnumerationError: If the account/cluster cannot be reached
                or authenticated against at all -- an empty result list
                (a real account/cluster with genuinely nothing in it)
                is a valid, distinct outcome from a failed connection.
        """


class EnumerationError(Exception):
    """Raised when an :class:`EnumerationProvider` cannot reach or
    authenticate against its target at all.
    """


__all__ = ["DiscoveredResource", "EnumerationError", "EnumerationProvider"]
