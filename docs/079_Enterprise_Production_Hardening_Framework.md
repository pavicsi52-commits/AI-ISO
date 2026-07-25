# AI Infrastructure Operating System (AI-IOS)

# Prompt 079

## Enterprise Production Hardening Framework

Reference Documents

Prompt 000
Prompt 001
...
Prompt 078

---

# ROLE

You are the Principal Enterprise Security & Production Readiness Architect.

Implement the Enterprise Production Hardening Framework.

Use every previously implemented platform framework.

Do NOT redesign the platform.

Implement a production-ready enterprise hardening and certification framework.

---

# OBJECTIVE

Build a centralized Production Hardening Framework responsible for validating, securing, certifying, and enforcing production readiness across every AI-IOS component before release.

The framework SHALL provide automated security hardening, operational validation, compliance verification, and production certification.

---

# SERVICE LOCATION

services/production-hardening-framework/

---

# DIRECTORY STRUCTURE

production-hardening-framework/

app/

api/

controllers/

services/

repositories/

models/

schemas/

hardening/

security/

compliance/

certification/

runtime/

containers/

kubernetes/

linux/

database/

network/

tls/

certificates/

secrets/

supply_chain/

sbom/

signing/

verification/

vulnerability/

policy/

zero_trust/

runtime_protection/

disaster_recovery/

operational_readiness/

analytics/

reports/

events/

notifications/

middleware/

validators/

workers/

config/

tests/

migrations/

README.md

---

# DATABASE TABLES

Create

hardening_profiles

hardening_runs

hardening_results

security_findings

vulnerability_scans

sbom_catalog

signed_artifacts

runtime_protection

compliance_results

production_certifications

operational_readiness

disaster_recovery_checks

certificate_inventory

hardening_statistics

hardening_reports

hardening_audit

---

# SECURITY HARDENING

Support

Operating System Hardening

Container Hardening

Kubernetes Hardening

API Hardening

Database Hardening

Network Hardening

TLS Hardening

Identity Hardening

Secrets Hardening

Logging Hardening

---

# CIS BENCHMARKS

Support

Linux CIS

Docker CIS

Kubernetes CIS

PostgreSQL CIS

Redis CIS

RabbitMQ CIS

NGINX CIS

Custom Enterprise Benchmarks

---

# ZERO TRUST

Support

Identity Verification

Continuous Authentication

Least Privilege

Micro-segmentation

Policy Enforcement

Device Trust

Session Validation

Risk-based Access

---

# SUPPLY CHAIN SECURITY

Support

SBOM Generation

SBOM Validation

Artifact Signing

Signature Verification

Dependency Validation

Package Integrity

Provenance Tracking

Trusted Build Validation

---

# VULNERABILITY MANAGEMENT

Support

Dependency Scanning

Container Scanning

OS Package Scanning

Secrets Detection

License Validation

CVE Monitoring

Risk Prioritization

Remediation Tracking

---

# RUNTIME PROTECTION

Support

Runtime Threat Detection

Container Protection

Process Monitoring

Privilege Escalation Detection

File Integrity Monitoring

Anomaly Detection

Policy Enforcement

Incident Recording

---

# CERTIFICATES

Support

TLS Validation

Certificate Inventory

Certificate Rotation

Certificate Expiration Monitoring

Mutual TLS Validation

PKI Integration

Certificate Compliance

---

# SECRETS

Integrate Prompt 035.

Support

Secrets Rotation

Secrets Validation

Encryption Verification

Vault Integration

Access Validation

Secret Usage Analytics

---

# COMPLIANCE

Integrate Prompt 051.

Support

ISO27001

SOC2

PCI DSS

NIST

IEC62443

O-PAS

Internal Policies

Production Readiness Checklist

---

# DISASTER RECOVERY

Integrate Prompt 065.

Support

Backup Validation

Restore Validation

Recovery Time Validation

Recovery Point Validation

Failover Validation

Disaster Recovery Drills

Business Continuity Validation

---

# OPERATIONAL READINESS

Support

Runbook Validation

Monitoring Validation

Alert Validation

Logging Validation

Telemetry Validation

Scaling Validation

Capacity Validation

Support Readiness

SLA Validation

---

# PRODUCTION CERTIFICATION

Support

Certification Profiles

Approval Workflow

Risk Assessment

Certification Reports

Expiration Policies

Re-certification

Certification History

Executive Sign-off

---

# PLATFORM INTEGRATIONS

Integrate

Security Framework (017)

Policy Engine (050)

Compliance Service (051)

Monitoring (044)

Observability Platform (064)

Backup & Disaster Recovery (065)

Testing Framework (077)

Performance Framework (078)

Administration Portal (070)

Upgrade Framework (076)

---

# ANALYTICS

Collect

Security Score

Compliance Score

Hardening Score

Risk Score

Vulnerability Trends

Certification Status

Operational Readiness

Production Readiness

---

# REPORTING

Generate

Hardening Reports

Security Reports

Compliance Reports

Vulnerability Reports

SBOM Reports

Certification Reports

Operational Readiness Reports

Executive Reports

Audit Reports

---

# EVENTS

Publish

HardeningStarted

HardeningCompleted

SecurityIssueDetected

VulnerabilityDetected

CertificationGranted

CertificationRevoked

ComplianceValidated

ProductionReady

Integrate with Prompt 020.

---

# NOTIFICATIONS

Integrate Prompt 025.

Notify

Critical Vulnerability

Certificate Expiring

Hardening Failed

Certification Granted

Certification Expired

Compliance Failure

Operational Risk

---

# TELEMETRY

Integrate Prompt 024.

Trace

Hardening Execution

Security Scans

SBOM Generation

Runtime Monitoring

Certification

Compliance Validation

---

# AUDIT

Audit

Hardening Runs

Security Changes

Certification Decisions

Compliance Validation

Administrative Operations

---

# REST APIs

Implement

GET /hardening

POST /hardening/run

GET /hardening/results

GET /security/findings

GET /vulnerabilities

GET /certifications

POST /certifications

GET /compliance

GET /production-readiness

GET /reports

GET /statistics

---

# SECURITY

Integrate Prompt 017.

Integrate Prompt 032.

Integrate Prompt 035.

Integrate Prompt 050.

Enforce

RBAC Authorization

Immutable Audit History

Signed Release Artifacts

Verified Supply Chain

Encrypted Secrets

Trusted Runtime

Zero Trust Policies

Protection Against Configuration Drift

---

# PERFORMANCE

Support

100,000+ Production Assets

Parallel Hardening

Distributed Security Scanning

Incremental Validation

Horizontal Scaling

Caching

High Availability

---

# TESTING

Unit Tests

Integration Tests

Security Tests

Compliance Tests

Hardening Tests

Runtime Protection Tests

Certification Tests

Coverage >=95%

---

# DOCUMENTATION

README

Production Hardening Guide

Security Guide

Compliance Guide

SBOM Guide

Runtime Protection Guide

Certification Guide

Operations Guide

REST API Reference

Architecture Notes

---

# ACCEPTANCE CRITERIA

✓ Security Hardening

✓ CIS Benchmark Enforcement

✓ Zero Trust

✓ Supply Chain Security

✓ SBOM Generation

✓ Artifact Signing

✓ Vulnerability Management

✓ Runtime Protection

✓ Compliance Validation

✓ Disaster Recovery Validation

✓ Operational Readiness

✓ Production Certification

✓ Analytics

✓ Reports

✓ Events

✓ Notifications

✓ Audit

✓ REST APIs

✓ Database Migrations

✓ OpenAPI Documentation

✓ Tests Passing

✓ Documentation Complete

---

# DO NOT IMPLEMENT

Operating System Security Products

Commercial Vulnerability Scanners

Hardware TPM Firmware

Cloud Provider Security Services

Only implement the Enterprise Production Hardening Framework.

---

# OUTPUT

Generate every required file.

Generate complete production-ready implementation.

Generate database migrations.

Generate OpenAPI documentation.

Generate production hardening engine.

Generate security certification engine.

Generate SBOM generation framework.

Generate vulnerability management engine.

Generate runtime protection integration.

Generate unit and integration tests.

No placeholders.

No TODO comments.

No demo code.

Implementation must compile successfully.

Implementation must pass

- Ruff
- Black
- MyPy
- Pytest

Do not summarize.

End Prompt 079.
