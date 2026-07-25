# AI Infrastructure Operating System (AI-IOS)

# Prompt 070

## Enterprise Administration Portal Service

Reference Documents

Prompt 000
Prompt 001
...
Prompt 069

---

# ROLE

You are the Principal Enterprise Platform Administration Architect.

Implement the Enterprise Administration Portal Service.

Use every previously implemented platform framework.

Do NOT redesign the platform.

Implement a production-ready enterprise administration platform.

---

# OBJECTIVE

Build a centralized Administration Portal responsible for global platform administration, tenant management, operational tooling, diagnostics, configuration, security administration, background operations, feature management, and platform governance.

The Administration Portal SHALL become the operational control plane for AI-IOS.

---

# SERVICE LOCATION

services/administration-portal-service/

---

# DIRECTORY STRUCTURE

administration-portal-service/

app/

api/

controllers/

services/

repositories/

models/

schemas/

organizations/

tenants/

users/

roles/

settings/

configuration/

feature_flags/

maintenance/

diagnostics/

jobs/

scheduler/

security/

audit/

licenses/

notifications/

api_management/

system/

health/

analytics/

reports/

events/

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

platform_settings

system_configuration

feature_flags

organizations

tenants

tenant_settings

tenant_limits

tenant_usage

tenant_health

tenant_provisioning

admin_sessions

admin_actions

system_jobs

job_history

maintenance_windows

platform_announcements

api_keys

api_usage

security_settings

security_events

diagnostics

health_checks

system_statistics

system_reports

system_audit

---

# GLOBAL ADMINISTRATION

Support

Platform Dashboard

Global Settings

Platform Branding

License Overview

Version Management

Environment Management

Platform Configuration

Maintenance Controls

Operational Console

---

# MULTI-TENANT MANAGEMENT

Support

Tenant Provisioning

Tenant Suspension

Tenant Activation

Tenant Deletion

Tenant Isolation

Tenant Migration

Tenant Backup

Tenant Restore

Tenant Usage

Tenant Health

Tenant Quotas

---

# ORGANIZATION MANAGEMENT

Integrate Prompt 033.

Support

Organization Creation

Organization Lifecycle

Business Units

Departments

Organization Policies

Organization Limits

Organization Reports

---

# USER ADMINISTRATION

Integrate Prompt 030.

Integrate Prompt 032.

Support

User Lifecycle

Password Reset

Account Lock

Unlock

Force Logout

Session Management

API Access

MFA Enforcement

Identity Federation

---

# ROLE ADMINISTRATION

Support

Global Roles

Tenant Roles

Permission Templates

Role Inheritance

Role Auditing

Permission Reports

---

# FEATURE FLAGS

Support

Global Flags

Tenant Flags

Organization Flags

Project Flags

Percentage Rollout

Scheduled Rollout

Kill Switch

Feature Dependencies

Version Constraints

---

# PLATFORM CONFIGURATION

Support

Global Variables

Environment Variables

Runtime Configuration

Configuration Validation

Configuration History

Configuration Rollback

Secret References

---

# SYSTEM DIAGNOSTICS

Support

Health Checks

Dependency Checks

Database Diagnostics

Cache Diagnostics

Queue Diagnostics

API Diagnostics

Storage Diagnostics

Cluster Diagnostics

AI Diagnostics

Connector Diagnostics

Plugin Diagnostics

---

# BACKGROUND JOB MANAGEMENT

Support

Job Scheduling

Job Queue

Job Retry

Pause Jobs

Resume Jobs

Cancel Jobs

Priority Management

Job History

Execution Logs

Dead Letter Queue

---

# API MANAGEMENT

Support

API Keys

API Tokens

API Rate Limits

API Quotas

API Analytics

API Revocation

API Rotation

API Usage Reports

---

# SECURITY ADMINISTRATION

Support

Security Policies

Password Policies

Session Policies

MFA Policies

IP Restrictions

Certificate Management

Secret Rotation

Threat Monitoring

Security Events

Security Reports

---

# MAINTENANCE

Support

Maintenance Windows

Read-only Mode

Emergency Maintenance

Rolling Maintenance

Maintenance Notifications

Approval Workflow

Scheduling

Audit Trail

---

# PLATFORM HEALTH

Support

Global Health Dashboard

Service Health

Database Health

Cache Health

Queue Health

Storage Health

Connector Health

Plugin Health

AI Health

Cluster Health

---

# ANNOUNCEMENTS

Support

Global Announcements

Tenant Announcements

Maintenance Notifications

Banner Messages

Scheduled Announcements

Announcement History

---

# PLATFORM INTEGRATIONS

Integrate

Authentication (030)

RBAC (032)

Organization Service (033)

Project Service (034)

Notification Center (055)

API Gateway (056)

License & Billing (069)

Cloud Management (068)

Edge Management (067)

Multi-Cluster Management (066)

Observability Platform (064)

Backup & Disaster Recovery (065)

AI Agent Platform (060)

---

# ANALYTICS

Collect

Tenant Count

User Count

API Usage

Platform Availability

Feature Usage

Background Job Metrics

Security Events

License Usage

Health Status

---

# REPORTING

Generate

Tenant Reports

Platform Reports

Security Reports

API Reports

Feature Reports

Health Reports

Operational Reports

Audit Reports

---

# EVENTS

Publish

TenantCreated

TenantUpdated

TenantDeleted

FeatureFlagUpdated

MaintenanceStarted

MaintenanceCompleted

AdminLogin

ConfigurationChanged

SecurityPolicyUpdated

PlatformHealthChanged

Integrate with Prompt 020.

---

# NOTIFICATIONS

Integrate Prompt 025.

Notify

Maintenance Scheduled

Tenant Provisioned

Platform Issue

Security Event

License Expiration

Feature Enabled

Configuration Changed

Health Degradation

---

# TELEMETRY

Integrate Prompt 024.

Trace

Administrative Actions

Configuration Updates

Feature Rollouts

Tenant Provisioning

API Operations

Background Jobs

Maintenance Operations

---

# AUDIT

Audit

Administrative Logins

Configuration Changes

Feature Flag Changes

Tenant Operations

Security Operations

API Management

Maintenance Operations

Platform Administration

---

# REST APIs

Implement

GET /admin/dashboard

GET /admin/settings

PUT /admin/settings

GET /admin/tenants

POST /admin/tenants

PUT /admin/tenants/{id}

DELETE /admin/tenants/{id}

GET /admin/feature-flags

POST /admin/feature-flags

PUT /admin/feature-flags/{id}

GET /admin/jobs

POST /admin/jobs

GET /admin/diagnostics

GET /admin/health

GET /admin/statistics

GET /admin/reports

---

# SECURITY

Integrate Prompt 017.

Integrate Prompt 032.

Integrate Prompt 035.

Integrate Prompt 050.

Enforce

Organization isolation

Tenant isolation

RBAC authorization

MFA for administrators

Just-in-Time administrative access

Approval workflow for critical operations

Immutable audit history

Protection against privilege escalation

Protection against configuration tampering

---

# PERFORMANCE

Support

100,000+ Organizations

1,000,000+ Users

10,000+ Tenants

Distributed Job Execution

Horizontal Scaling

Connection Pooling

Caching

High Availability

---

# TESTING

Unit Tests

Integration Tests

Tenant Management Tests

Feature Flag Tests

Diagnostics Tests

Security Tests

API Tests

Performance Tests

Coverage >=95%

---

# DOCUMENTATION

README

Administration Guide

Tenant Management Guide

Feature Flag Guide

Configuration Guide

Security Guide

Diagnostics Guide

REST API Reference

Developer Guide

Operations Guide

Architecture Notes

---

# ACCEPTANCE CRITERIA

✓ Global Administration

✓ Multi-tenant Management

✓ Organization Management

✓ User Administration

✓ Feature Flag Management

✓ Platform Configuration

✓ Diagnostics

✓ Background Job Management

✓ API Management

✓ Security Administration

✓ Maintenance Management

✓ Platform Health Dashboard

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

Identity Provider Software

Operating System Administration

Cloud Provider Administration

Third-party Monitoring Systems

Only implement the Enterprise Administration Portal Service.

---

# OUTPUT

Generate every required file.

Generate complete production-ready implementation.

Generate database migrations.

Generate OpenAPI documentation.

Generate tenant management engine.

Generate feature flag framework.

Generate diagnostics engine.

Generate platform administration services.

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

End Prompt 070.
