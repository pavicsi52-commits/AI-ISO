"""AWS discovery, via ``boto3``.

Per docs/037 "CLOUD DISCOVERY". Live-verified against ``moto``'s real
in-process AWS API emulator (``tests/test_scanner_aws.py``) -- a
genuine ``boto3`` client talking to a server that implements the real
AWS API request/response contract, not a hand-rolled fake.
"""

from __future__ import annotations

import asyncio

import boto3
from botocore.exceptions import BotoCoreError, ClientError

from app.models.enums import TargetType
from app.scanners.base import ScanCredential
from app.scanners.enumeration import DiscoveredResource, EnumerationError, EnumerationProvider

_DEFAULT_REGION = "us-east-1"


class AwsProvider(EnumerationProvider):
    """Enumerates an AWS account's regions, EC2/VPC/networking, storage,
    managed databases, load balancers, and EKS clusters.
    """

    target_type = TargetType.CLOUD_ACCOUNT

    async def enumerate(
        self, address: str, *, credential: ScanCredential | None, timeout_seconds: float
    ) -> list[DiscoveredResource]:
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, self._enumerate, credential)

    def _enumerate(self, credential: ScanCredential | None) -> list[DiscoveredResource]:
        region = (credential.extra.get("region") if credential else None) or _DEFAULT_REGION
        session = boto3.Session(
            aws_access_key_id=credential.username if credential else None,
            aws_secret_access_key=credential.password if credential else None,
            aws_session_token=credential.token if credential else None,
            region_name=region,
        )
        try:
            resources: list[DiscoveredResource] = []
            resources += self._list_regions(session)
            resources += self._list_instances(session, region)
            resources += self._list_vpcs(session, region)
            resources += self._list_subnets(session, region)
            resources += self._list_security_groups(session, region)
            resources += self._list_load_balancers(session, region)
            resources += self._list_buckets(session)
            resources += self._list_db_instances(session, region)
            resources += self._list_eks_clusters(session, region)
            return resources
        except ClientError as exc:
            error_code = exc.response.get("Error", {}).get("Code", "")
            if error_code in ("AuthFailure", "UnauthorizedOperation", "InvalidClientTokenId"):
                raise EnumerationError(f"AWS authentication failed: {exc}") from exc
            raise EnumerationError(f"AWS API error: {exc}") from exc
        except BotoCoreError as exc:
            raise EnumerationError(f"AWS unreachable: {exc}") from exc

    @staticmethod
    def _list_regions(session: boto3.Session) -> list[DiscoveredResource]:
        ec2 = session.client("ec2")
        return [
            DiscoveredResource(name=region["RegionName"], resource_type="region")
            for region in ec2.describe_regions()["Regions"]
        ]

    @staticmethod
    def _list_instances(session: boto3.Session, region: str) -> list[DiscoveredResource]:
        ec2 = session.client("ec2", region_name=region)
        resources = []
        for reservation in ec2.describe_instances()["Reservations"]:
            for instance in reservation["Instances"]:
                name = instance["InstanceId"]
                for tag in instance.get("Tags", []):
                    if tag["Key"] == "Name":
                        name = tag["Value"]
                resources.append(
                    DiscoveredResource(
                        name=name,
                        resource_type="instance",
                        identity={
                            "instance_id": instance["InstanceId"],
                            "instance_type": instance.get("InstanceType"),
                            "state": instance.get("State", {}).get("Name"),
                            "availability_zone": instance.get("Placement", {}).get(
                                "AvailabilityZone"
                            ),
                        },
                    )
                )
        return resources

    @staticmethod
    def _list_vpcs(session: boto3.Session, region: str) -> list[DiscoveredResource]:
        ec2 = session.client("ec2", region_name=region)
        return [
            DiscoveredResource(
                name=vpc["VpcId"],
                resource_type="virtual_network",
                identity={"cidr": vpc["CidrBlock"]},
            )
            for vpc in ec2.describe_vpcs()["Vpcs"]
        ]

    @staticmethod
    def _list_subnets(session: boto3.Session, region: str) -> list[DiscoveredResource]:
        ec2 = session.client("ec2", region_name=region)
        return [
            DiscoveredResource(
                name=subnet["SubnetId"],
                resource_type="subnet",
                identity={"cidr": subnet["CidrBlock"], "vpc_id": subnet["VpcId"]},
            )
            for subnet in ec2.describe_subnets()["Subnets"]
        ]

    @staticmethod
    def _list_security_groups(session: boto3.Session, region: str) -> list[DiscoveredResource]:
        ec2 = session.client("ec2", region_name=region)
        return [
            DiscoveredResource(
                name=group["GroupName"],
                resource_type="security_group",
                identity={"group_id": group["GroupId"], "vpc_id": group.get("VpcId")},
            )
            for group in ec2.describe_security_groups()["SecurityGroups"]
        ]

    @staticmethod
    def _list_load_balancers(session: boto3.Session, region: str) -> list[DiscoveredResource]:
        elbv2 = session.client("elbv2", region_name=region)
        try:
            balancers = elbv2.describe_load_balancers()["LoadBalancers"]
        except ClientError:
            return []
        return [
            DiscoveredResource(
                name=lb["LoadBalancerName"],
                resource_type="load_balancer",
                identity={"dns_name": lb.get("DNSName"), "scheme": lb.get("Scheme")},
            )
            for lb in balancers
        ]

    @staticmethod
    def _list_buckets(session: boto3.Session) -> list[DiscoveredResource]:
        s3 = session.client("s3")
        return [
            DiscoveredResource(name=bucket["Name"], resource_type="storage")
            for bucket in s3.list_buckets()["Buckets"]
        ]

    @staticmethod
    def _list_db_instances(session: boto3.Session, region: str) -> list[DiscoveredResource]:
        rds = session.client("rds", region_name=region)
        try:
            instances = rds.describe_db_instances()["DBInstances"]
        except ClientError:
            return []
        return [
            DiscoveredResource(
                name=db["DBInstanceIdentifier"],
                resource_type="managed_database",
                identity={"engine": db.get("Engine"), "status": db.get("DBInstanceStatus")},
            )
            for db in instances
        ]

    @staticmethod
    def _list_eks_clusters(session: boto3.Session, region: str) -> list[DiscoveredResource]:
        eks = session.client("eks", region_name=region)
        try:
            cluster_names = eks.list_clusters()["clusters"]
        except ClientError:
            return []
        return [
            DiscoveredResource(name=name, resource_type="kubernetes_service")
            for name in cluster_names
        ]


__all__ = ["AwsProvider"]
