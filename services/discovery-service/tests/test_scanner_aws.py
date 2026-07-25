"""Tests for :class:`app.scanners.cloud.aws_provider.AwsProvider` against
``moto``'s real, in-process AWS API emulator (see the provider's own
module docstring) -- a genuine ``boto3`` client/server exchange, not a
hand-rolled fake. The two exception-mapping branches (an authentication
failure, an unreachable endpoint) are exercised by patching
``boto3.Session.client`` directly, since moto's own emulator doesn't
model network-level AWS outages.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import boto3
import pytest
from botocore.exceptions import BotoCoreError, ClientError
from moto import mock_aws

from app.scanners.base import ScanCredential
from app.scanners.cloud.aws_provider import AwsProvider
from app.scanners.enumeration import DiscoveredResource, EnumerationError

_TIMEOUT_SECONDS = 30.0
_REGION = "us-east-1"


def _credential() -> ScanCredential:
    return ScanCredential(username="testing", password="testing", extra={"region": _REGION})


def _seed_resources() -> dict[str, str]:
    """Populate the *currently-active* ``mock_aws()`` context -- must be
    called from inside a test already inside its own ``with mock_aws():``
    block (a second, nested one would establish and tear down its own
    independent mock state boundary, making anything seeded here
    invisible once it exits).
    """
    ec2 = boto3.client("ec2", region_name=_REGION)
    instance = ec2.run_instances(ImageId="ami-12345678", MinCount=1, MaxCount=1)["Instances"][0]
    ec2.create_tags(Resources=[instance["InstanceId"]], Tags=[{"Key": "Name", "Value": "web-01"}])
    vpc = ec2.create_vpc(CidrBlock="10.0.0.0/16")["Vpc"]
    subnet = ec2.create_subnet(VpcId=vpc["VpcId"], CidrBlock="10.0.1.0/24")["Subnet"]
    security_group = ec2.create_security_group(
        GroupName="test-sg", Description="test", VpcId=vpc["VpcId"]
    )

    s3 = boto3.client("s3", region_name=_REGION)
    s3.create_bucket(Bucket="aiios-test-bucket")

    return {
        "instance_id": instance["InstanceId"],
        "vpc_id": vpc["VpcId"],
        "subnet_id": subnet["SubnetId"],
        "security_group_id": security_group["GroupId"],
    }


async def test_enumerate_lists_real_resources_via_moto() -> None:
    # `@mock_aws` as a decorator on an `async def` test confuses
    # pytest-asyncio's own auto-detection of async tests (it reports
    # "async def functions are not natively supported" as if no plugin
    # were installed at all) -- used as a plain context manager instead.
    with mock_aws():
        seeded = _seed_resources()

        resources = await AwsProvider().enumerate(
            "123456789012", credential=_credential(), timeout_seconds=_TIMEOUT_SECONDS
        )
        by_type: dict[str, list[DiscoveredResource]] = {}
        for resource in resources:
            by_type.setdefault(resource.resource_type, []).append(resource)

        assert "region" in by_type
        assert any(r.name == "web-01" for r in by_type["instance"])
        instance = next(r for r in by_type["instance"] if r.name == "web-01")
        assert instance.identity["instance_id"] == seeded["instance_id"]
        assert any(r.name == seeded["vpc_id"] for r in by_type["virtual_network"])
        assert any(r.name == seeded["subnet_id"] for r in by_type["subnet"])
        assert any(r.name == "test-sg" for r in by_type["security_group"])
        assert any(r.name == "aiios-test-bucket" for r in by_type["storage"])


async def test_enumerate_with_no_resources_returns_infrastructure_only() -> None:
    with mock_aws():
        resources = await AwsProvider().enumerate(
            "123456789012", credential=None, timeout_seconds=_TIMEOUT_SECONDS
        )
    by_type = {resource.resource_type for resource in resources}
    assert "region" in by_type
    assert "instance" not in by_type


async def test_enumerate_auth_failure_raises_enumeration_error() -> None:
    error = ClientError({"Error": {"Code": "AuthFailure", "Message": "denied"}}, "DescribeRegions")
    fake_client = MagicMock()
    fake_client.describe_regions.side_effect = error
    with (
        patch.object(boto3.Session, "client", return_value=fake_client),
        pytest.raises(EnumerationError, match="authentication failed"),
    ):
        await AwsProvider().enumerate(
            "123456789012", credential=_credential(), timeout_seconds=_TIMEOUT_SECONDS
        )


async def test_enumerate_unreachable_raises_enumeration_error() -> None:
    with (
        patch.object(boto3.Session, "client", side_effect=BotoCoreError()),
        pytest.raises(EnumerationError, match="unreachable"),
    ):
        await AwsProvider().enumerate(
            "123456789012", credential=_credential(), timeout_seconds=_TIMEOUT_SECONDS
        )
