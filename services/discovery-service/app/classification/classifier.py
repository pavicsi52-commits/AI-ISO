"""Rule-based asset classification.

Per docs/037 "ASSET CLASSIFICATION": Infrastructure, Network, Compute,
Storage, Cloud, Industrial, Application, Database, Service, Custom.
Classification is deterministic, not heuristic/ML-based -- a lookup
table keyed by the protocol that discovered the asset (for
protocol-probed targets) or the cloud/Kubernetes resource type (for
enumeration-provider targets), both fixed closed sets, so a lookup
table is complete and predictable rather than a guess. A
:class:`~app.models.discovery_rule.DiscoveryRule` of
``rule_type=CLASSIFICATION`` (evaluated by
``app/services/discovery_rule.py``) can override this default for a
specific field/value match -- see that service's own docstring.
"""

from __future__ import annotations

from app.models.enums import AssetClassification, ProtocolType

_PROTOCOL_CLASSIFICATION: dict[ProtocolType, AssetClassification] = {
    ProtocolType.SSH: AssetClassification.COMPUTE,
    ProtocolType.WINRM: AssetClassification.COMPUTE,
    ProtocolType.WMI: AssetClassification.COMPUTE,
    ProtocolType.SNMP: AssetClassification.NETWORK,
    ProtocolType.REDFISH: AssetClassification.INFRASTRUCTURE,
    ProtocolType.IPMI: AssetClassification.INFRASTRUCTURE,
    ProtocolType.HTTP: AssetClassification.APPLICATION,
    ProtocolType.HTTPS: AssetClassification.APPLICATION,
    ProtocolType.REST: AssetClassification.APPLICATION,
    ProtocolType.GRAPHQL: AssetClassification.APPLICATION,
    ProtocolType.GRPC: AssetClassification.SERVICE,
    ProtocolType.LDAP: AssetClassification.SERVICE,
    ProtocolType.DNS: AssetClassification.SERVICE,
    ProtocolType.NTP: AssetClassification.SERVICE,
    ProtocolType.SMB: AssetClassification.STORAGE,
    ProtocolType.SFTP: AssetClassification.STORAGE,
    ProtocolType.FTP: AssetClassification.STORAGE,
    ProtocolType.OPC_UA: AssetClassification.INDUSTRIAL,
    ProtocolType.MODBUS: AssetClassification.INDUSTRIAL,
    ProtocolType.BACNET: AssetClassification.INDUSTRIAL,
    ProtocolType.MQTT: AssetClassification.INDUSTRIAL,
    ProtocolType.AMQP: AssetClassification.SERVICE,
    ProtocolType.JMX: AssetClassification.APPLICATION,
    ProtocolType.ICMP: AssetClassification.NETWORK,
    ProtocolType.TCP: AssetClassification.NETWORK,
    ProtocolType.UDP: AssetClassification.NETWORK,
    ProtocolType.PLUGIN: AssetClassification.CUSTOM,
}

_RESOURCE_TYPE_CLASSIFICATION: dict[str, AssetClassification] = {
    "instance": AssetClassification.COMPUTE,
    "region": AssetClassification.CLOUD,
    "availability_zone": AssetClassification.CLOUD,
    "virtual_network": AssetClassification.NETWORK,
    "subnet": AssetClassification.NETWORK,
    "security_group": AssetClassification.NETWORK,
    "load_balancer": AssetClassification.NETWORK,
    "storage": AssetClassification.STORAGE,
    "managed_database": AssetClassification.DATABASE,
    "kubernetes_service": AssetClassification.CLOUD,
    "resource_group": AssetClassification.CLOUD,
    "namespace": AssetClassification.CLOUD,
    "node": AssetClassification.COMPUTE,
    "pod": AssetClassification.APPLICATION,
    "deployment": AssetClassification.APPLICATION,
    "stateful_set": AssetClassification.APPLICATION,
    "daemon_set": AssetClassification.APPLICATION,
    "service": AssetClassification.SERVICE,
    "ingress": AssetClassification.NETWORK,
    "config_map": AssetClassification.SERVICE,
    "secret": AssetClassification.SERVICE,
    "persistent_volume": AssetClassification.STORAGE,
    "persistent_volume_claim": AssetClassification.STORAGE,
    "job": AssetClassification.APPLICATION,
    "cron_job": AssetClassification.APPLICATION,
}


def classify_by_protocol(protocol: ProtocolType) -> AssetClassification:
    """Classify a protocol-probed asset by which protocol discovered it."""
    return _PROTOCOL_CLASSIFICATION.get(protocol, AssetClassification.CUSTOM)


def classify_by_resource_type(resource_type: str) -> AssetClassification:
    """Classify a cloud/Kubernetes sub-resource by its
    :class:`~app.scanners.enumeration.DiscoveredResource.resource_type`.
    """
    return _RESOURCE_TYPE_CLASSIFICATION.get(resource_type, AssetClassification.CLOUD)


__all__ = ["classify_by_protocol", "classify_by_resource_type"]
