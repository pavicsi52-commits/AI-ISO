"""Direct service-layer tests for ``app/services/certificate.py``."""

from __future__ import annotations

import datetime
import uuid

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID
from shared_core.exceptions.conflict import ConflictError
from shared_core.exceptions.not_found import NotFoundError
from sqlalchemy.ext.asyncio import AsyncSession

from app.encryption.envelope import EnvelopeEncryption
from app.events.secret_events import CertificateImportedEvent
from app.models.enums import CertificateStatus, CertificateType
from app.repositories.certificate import CertificateRepository
from app.services.certificate import CertificateService
from tests.conftest import build_secret_service


def _make_self_signed_cert(*, common_name: str = "test.aiios.local") -> str:
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, common_name)])
    now = datetime.datetime.now(datetime.UTC)
    cert = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now)
        .not_valid_after(now + datetime.timedelta(days=365))
        .sign(key, hashes.SHA256())
    )
    return cert.public_bytes(serialization.Encoding.PEM).decode("ascii")


def _cert_service(
    db_session: AsyncSession, envelope: EnvelopeEncryption, **kwargs: object
) -> CertificateService:
    secrets = build_secret_service(db_session, envelope)
    return CertificateService(CertificateRepository(db_session), secrets, **kwargs)  # type: ignore[arg-type]


async def test_import_certificate_without_private_key(
    db_session: AsyncSession, envelope: EnvelopeEncryption
) -> None:
    service = _cert_service(db_session, envelope)
    pem = _make_self_signed_cert()
    org_id = uuid.uuid4()

    certificate = await service.import_certificate(
        organization_id=org_id,
        project_id=None,
        name="public-only",
        certificate_type=CertificateType.TLS,
        certificate_pem=pem,
        chain_pem=[],
        private_key=None,
        owner_id=None,
    )
    assert certificate.status == CertificateStatus.VALID
    assert certificate.private_key_secret_id is None
    assert certificate.subject == "CN=test.aiios.local"


async def test_import_certificate_with_private_key_creates_secret(
    db_session: AsyncSession, envelope: EnvelopeEncryption
) -> None:
    service = _cert_service(db_session, envelope)
    pem = _make_self_signed_cert(common_name="with-key.aiios.local")
    owner_id = uuid.uuid4()

    certificate = await service.import_certificate(
        organization_id=uuid.uuid4(),
        project_id=None,
        name="with-private-key",
        certificate_type=CertificateType.TLS,
        certificate_pem=pem,
        chain_pem=[],
        private_key="-----BEGIN PRIVATE KEY-----\nfake\n-----END PRIVATE KEY-----",
        owner_id=owner_id,
    )
    assert certificate.private_key_secret_id is not None

    secrets = build_secret_service(db_session, envelope)
    _secret, value = await secrets.get_decrypted(
        certificate.private_key_secret_id, actor_id=owner_id
    )
    assert value == "-----BEGIN PRIVATE KEY-----\nfake\n-----END PRIVATE KEY-----"


async def test_import_certificate_requires_owner_id_with_private_key(
    db_session: AsyncSession, envelope: EnvelopeEncryption
) -> None:
    service = _cert_service(db_session, envelope)
    pem = _make_self_signed_cert()
    with pytest.raises(ValueError, match="owner_id is required"):
        await service.import_certificate(
            organization_id=uuid.uuid4(),
            project_id=None,
            name="missing-owner",
            certificate_type=CertificateType.TLS,
            certificate_pem=pem,
            chain_pem=[],
            private_key="some-key",
            owner_id=None,
        )


async def test_import_duplicate_fingerprint_conflicts(
    db_session: AsyncSession, envelope: EnvelopeEncryption
) -> None:
    service = _cert_service(db_session, envelope)
    pem = _make_self_signed_cert(common_name="dup.aiios.local")
    org_id = uuid.uuid4()
    await service.import_certificate(
        organization_id=org_id,
        project_id=None,
        name="first",
        certificate_type=CertificateType.TLS,
        certificate_pem=pem,
        chain_pem=[],
        private_key=None,
        owner_id=None,
    )
    with pytest.raises(ConflictError):
        await service.import_certificate(
            organization_id=org_id,
            project_id=None,
            name="second",
            certificate_type=CertificateType.TLS,
            certificate_pem=pem,
            chain_pem=[],
            private_key=None,
            owner_id=None,
        )


async def test_import_certificate_publishes_event(
    db_session: AsyncSession, envelope: EnvelopeEncryption
) -> None:
    captured: list[object] = []

    async def _publish(event: object) -> None:
        captured.append(event)

    service = _cert_service(db_session, envelope, publish_event=_publish)
    pem = _make_self_signed_cert(common_name="event.aiios.local")
    await service.import_certificate(
        organization_id=uuid.uuid4(),
        project_id=None,
        name="event-cert",
        certificate_type=CertificateType.TLS,
        certificate_pem=pem,
        chain_pem=[],
        private_key=None,
        owner_id=None,
    )
    assert any(isinstance(event, CertificateImportedEvent) for event in captured)


async def test_list_for_org_scopes_correctly(
    db_session: AsyncSession, envelope: EnvelopeEncryption
) -> None:
    service = _cert_service(db_session, envelope)
    org_a = uuid.uuid4()
    await service.import_certificate(
        organization_id=org_a,
        project_id=None,
        name="org-a-cert",
        certificate_type=CertificateType.TLS,
        certificate_pem=_make_self_signed_cert(common_name="a.aiios.local"),
        chain_pem=[],
        private_key=None,
        owner_id=None,
    )
    await service.import_certificate(
        organization_id=uuid.uuid4(),
        project_id=None,
        name="org-b-cert",
        certificate_type=CertificateType.TLS,
        certificate_pem=_make_self_signed_cert(common_name="b.aiios.local"),
        chain_pem=[],
        private_key=None,
        owner_id=None,
    )
    results = await service.list_for_org(org_a)
    assert len(results) == 1
    assert results[0].name == "org-a-cert"


async def test_list_expiring_before_finds_valid_certs_only(
    db_session: AsyncSession, envelope: EnvelopeEncryption
) -> None:
    service = _cert_service(db_session, envelope)
    org_id = uuid.uuid4()
    certificate = await service.import_certificate(
        organization_id=org_id,
        project_id=None,
        name="expiring-cert",
        certificate_type=CertificateType.TLS,
        certificate_pem=_make_self_signed_cert(common_name="expiring.aiios.local"),
        chain_pem=[],
        private_key=None,
        owner_id=None,
    )
    cutoff = datetime.datetime.now(datetime.UTC) + datetime.timedelta(days=400)
    results = await service.list_expiring_before(cutoff)
    assert certificate.id in {c.id for c in results}


async def test_delete_removes_certificate(
    db_session: AsyncSession, envelope: EnvelopeEncryption
) -> None:
    service = _cert_service(db_session, envelope)
    certificate = await service.import_certificate(
        organization_id=uuid.uuid4(),
        project_id=None,
        name="deletable",
        certificate_type=CertificateType.TLS,
        certificate_pem=_make_self_signed_cert(common_name="deletable.aiios.local"),
        chain_pem=[],
        private_key=None,
        owner_id=None,
    )
    await service.delete(certificate.id)
    with pytest.raises(NotFoundError):
        await CertificateRepository(db_session).require_by_id(certificate.id)
