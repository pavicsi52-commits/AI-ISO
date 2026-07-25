"""Protocol scanner and enumeration provider registries.

One process-wide instance of every scanner/provider in this package,
keyed by the enum value it implements -- ``app/services/discovery_execution
.py`` (the job runner) looks up the right one for a given target rather
than branching on protocol/target-type itself.
"""

from __future__ import annotations

from app.models.enums import ProtocolType
from app.scanners.amqp_scanner import AmqpScanner
from app.scanners.bacnet_scanner import BacnetScanner
from app.scanners.base import ProtocolScanner
from app.scanners.cloud.aws_provider import AwsProvider
from app.scanners.cloud.azure_provider import AzureProvider
from app.scanners.cloud.gcp_provider import GcpProvider
from app.scanners.cloud.ibm_provider import IbmProvider
from app.scanners.cloud.oracle_provider import OracleProvider
from app.scanners.dns_scanner import DnsScanner
from app.scanners.enumeration import EnumerationProvider
from app.scanners.ftp_scanner import FtpScanner
from app.scanners.graphql_scanner import GraphQLScanner
from app.scanners.grpc_scanner import GrpcScanner
from app.scanners.http_scanner import HttpScanner
from app.scanners.ipmi_scanner import IpmiScanner
from app.scanners.jmx_scanner import JmxScanner
from app.scanners.kubernetes_provider import KubernetesProvider
from app.scanners.ldap_scanner import LdapScanner
from app.scanners.modbus_scanner import ModbusScanner
from app.scanners.mqtt_scanner import MqttScanner
from app.scanners.network import IcmpScanner, TcpScanner, UdpScanner
from app.scanners.ntp_scanner import NtpScanner
from app.scanners.opcua_scanner import OpcUaScanner
from app.scanners.redfish_scanner import RedfishScanner
from app.scanners.sftp_scanner import SftpScanner
from app.scanners.smb_scanner import SmbScanner
from app.scanners.snmp_scanner import SnmpScanner
from app.scanners.ssh_scanner import SshScanner
from app.scanners.winrm_scanner import WinRmScanner
from app.scanners.wmi_scanner import WmiScanner

PROTOCOL_SCANNERS: dict[ProtocolType, ProtocolScanner] = {
    ProtocolType.SSH: SshScanner(),
    ProtocolType.WINRM: WinRmScanner(),
    ProtocolType.SNMP: SnmpScanner(),
    ProtocolType.REDFISH: RedfishScanner(),
    ProtocolType.IPMI: IpmiScanner(),
    ProtocolType.HTTP: HttpScanner(ProtocolType.HTTP, use_tls=False),
    ProtocolType.HTTPS: HttpScanner(ProtocolType.HTTPS, use_tls=True),
    ProtocolType.REST: HttpScanner(ProtocolType.REST, use_tls=False),
    ProtocolType.GRAPHQL: GraphQLScanner(),
    ProtocolType.GRPC: GrpcScanner(),
    ProtocolType.LDAP: LdapScanner(),
    ProtocolType.DNS: DnsScanner(),
    ProtocolType.NTP: NtpScanner(),
    ProtocolType.SMB: SmbScanner(),
    ProtocolType.SFTP: SftpScanner(),
    ProtocolType.FTP: FtpScanner(),
    ProtocolType.OPC_UA: OpcUaScanner(),
    ProtocolType.MODBUS: ModbusScanner(),
    ProtocolType.BACNET: BacnetScanner(),
    ProtocolType.MQTT: MqttScanner(),
    ProtocolType.AMQP: AmqpScanner(),
    ProtocolType.JMX: JmxScanner(),
    ProtocolType.WMI: WmiScanner(),
    ProtocolType.ICMP: IcmpScanner(),
    ProtocolType.TCP: TcpScanner(),
    ProtocolType.UDP: UdpScanner(),
}
"""Every :class:`~app.models.enums.ProtocolType` except ``PLUGIN`` (the
"Plugin-Based Protocols" catch-all docs/037 names has no fixed
implementation by definition -- a future plugin loader, out of scope
for this prompt) maps to a real scanner instance.
"""


CLOUD_PROVIDERS: dict[str, EnumerationProvider] = {
    "aws": AwsProvider(),
    "azure": AzureProvider(),
    "gcp": GcpProvider(),
    "oracle": OracleProvider(),
    "ibm": IbmProvider(),
}
"""Keyed by a caller-supplied vendor name (not
:class:`~app.models.enums.TargetType`, since every cloud provider
shares the single ``CLOUD_ACCOUNT`` target type -- the vendor itself is
what selects the provider, carried in
:class:`~app.models.discovery_target.DiscoveryTarget`'s own
``metadata`` as ``{"cloud_vendor": "aws"}``).
"""

KUBERNETES_PROVIDER: EnumerationProvider = KubernetesProvider()
"""The one enumeration provider keyed directly by
:class:`~app.models.enums.TargetType`, since
``TargetType.KUBERNETES_CLUSTER`` has exactly one implementation.
"""


def get_scanner(protocol: ProtocolType) -> ProtocolScanner:
    """Return the registered scanner for *protocol*.

    Raises:
        KeyError: If no scanner is registered for *protocol* (only
            ``ProtocolType.PLUGIN`` currently has none).
    """
    return PROTOCOL_SCANNERS[protocol]


def get_cloud_provider(vendor: str) -> EnumerationProvider:
    """Return the registered cloud enumeration provider for *vendor*
    (``"aws"``, ``"azure"``, ``"gcp"``, ``"oracle"``, or ``"ibm"``).

    Raises:
        KeyError: If *vendor* names no registered provider.
    """
    return CLOUD_PROVIDERS[vendor]


__all__ = [
    "CLOUD_PROVIDERS",
    "KUBERNETES_PROVIDER",
    "PROTOCOL_SCANNERS",
    "get_cloud_provider",
    "get_scanner",
]
