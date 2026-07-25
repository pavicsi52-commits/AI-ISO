# AI Infrastructure Operating System (AI-IOS)

# Prompt 033

## Enterprise Organization Service

Reference Documents

Prompt 000
Prompt 001
Prompt 002
Prompt 003
Prompt 004
Prompt 005
Prompt 006
Prompt 007
Prompt 008
Prompt 009
Prompt 010
Prompt 011
Prompt 012
Prompt 013
Prompt 014
Prompt 015
Prompt 016
Prompt 017
Prompt 018
Prompt 019
Prompt 020
Prompt 021
Prompt 022
Prompt 023
Prompt 024
Prompt 025
Prompt 026
Prompt 027
Prompt 028
Prompt 029
Prompt 030
Prompt 031
Prompt 032

---

# ROLE

You are the Principal Multi-Tenant Platform Architect.

Implement the Enterprise Organization Service.

Use all previously implemented platform frameworks.

Do NOT redesign the architecture.

Implement a production-ready multi-tenant organization management service.

---

# OBJECTIVE

Create a centralized Organization Service responsible for tenant isolation and enterprise management.

Every resource inside AI-IOS SHALL belong to an Organization.

The service shall support

Organization Management

Departments

Business Units

Teams

Organization Branding

Organization Settings

Organization Preferences

Licensing

Subscription Plans

Quotas

Resource Limits

Organization Invitations

Organization Audit

Organization Analytics

Organization Metadata

Organization Lifecycle

---

# SERVICE LOCATION

services/organization-service/

---

# DIRECTORY STRUCTURE

organization-service/

app/

api/

controllers/

services/

repositories/

models/

schemas/

organizations/

departments/

business_units/

teams/

branding/

settings/

preferences/

subscriptions/

licenses/

quotas/

limits/

analytics/

metadata/

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

organizations

organization_settings

organization_preferences

organization_metadata

organization_domains

organization_branding

organization_subscriptions

organization_licenses

organization_limits

organization_quotas

organization_departments

organization_business_units

organization_teams

organization_invitations

organization_members

organization_activity

organization_audit

organization_statistics

organization_tags

---

# ORGANIZATION MODEL

Every organization shall contain

Organization ID

Organization Name

Display Name

Short Name

Description

Status

Primary Domain

Primary Contact

Logo

Website

Industry

Timezone

Language

Country

Currency

Subscription

License

Created At

Updated At

Metadata

---

# ORGANIZATION STATUS

Pending

Trial

Active

Suspended

Maintenance

Expired

Disabled

Archived

Deleted

---

# ORGANIZATION SETTINGS

Manage

Branding

Security Policies

Password Policies

MFA Enforcement

Allowed Domains

Default Language

Default Timezone

Session Policies

Retention Policies

Storage Policies

Notification Policies

---

# BRANDING

Support

Logo

Dark Logo

Favicon

Primary Color

Secondary Color

Theme

Email Templates

Login Screen Branding

Dashboard Branding

---

# DEPARTMENTS

Support

CRUD

Hierarchy

Department Manager

Department Members

Department Metadata

Department Tags

---

# BUSINESS UNITS

Support

CRUD

Hierarchy

Business Unit Owner

Departments

Teams

Metadata

---

# TEAMS

Support

CRUD

Members

Team Leads

Projects

Tags

Metadata

---

# SUBSCRIPTIONS

Support

Trial

Community

Professional

Enterprise

Custom

Track

Renewal

Expiration

Billing Reference

Status

---

# LICENSE MANAGEMENT

Track

License Type

License Key

Seat Count

Consumed Seats

Expiration

Grace Period

Activation

Validation

---

# QUOTAS

Support

Maximum Users

Maximum Projects

Maximum Assets

Maximum Storage

Maximum Workflows

Maximum Automation Jobs

Maximum Connectors

Maximum API Calls

Maximum AI Requests

Maximum Plugins

Configurable per organization.

---

# RESOURCE LIMITS

CPU

Memory

Storage

Queue Usage

Concurrent Workflows

Concurrent Jobs

Concurrent AI Tasks

Concurrent Users

Bandwidth

---

# ORGANIZATION INVITATIONS

Support

Invite Member

Accept

Reject

Resend

Expire

Audit

Bulk Invitations

---

# ORGANIZATION ANALYTICS

Collect

User Count

Project Count

Asset Count

Workflow Count

Automation Count

Validation Count

Storage Usage

API Usage

AI Usage

License Utilization

---

# EVENTS

Publish

OrganizationCreated

OrganizationUpdated

OrganizationDeleted

OrganizationActivated

OrganizationSuspended

DepartmentCreated

DepartmentDeleted

TeamCreated

SubscriptionChanged

QuotaExceeded

LicenseExpired

Integrate with Prompt 020.

---

# NOTIFICATIONS

Integrate Prompt 025

Notify

Organization Created

Invitation

Subscription Expiring

License Expiring

Quota Warning

Quota Exceeded

Organization Suspended

---

# TELEMETRY

Integrate Prompt 024

Trace

Organization CRUD

Department Operations

Quota Checks

License Validation

Analytics

---

# AUDIT

Audit

Organization Creation

Updates

Deletion

Settings Changes

Branding Changes

License Changes

Quota Changes

Member Invitations

Administrative Actions

---

# REST APIs

Implement

GET /organizations

GET /organizations/{id}

POST /organizations

PUT /organizations/{id}

DELETE /organizations/{id}

GET /organizations/{id}/settings

PUT /organizations/{id}/settings

GET /organizations/{id}/branding

PUT /organizations/{id}/branding

GET /organizations/{id}/departments

POST /organizations/{id}/departments

PUT /departments/{id}

DELETE /departments/{id}

GET /organizations/{id}/teams

POST /organizations/{id}/teams

PUT /teams/{id}

DELETE /teams/{id}

GET /organizations/{id}/licenses

PUT /organizations/{id}/licenses

GET /organizations/{id}/quotas

PUT /organizations/{id}/quotas

POST /organizations/{id}/invite

GET /organizations/{id}/analytics

---

# SECURITY

Integrate Prompt 017

Integrate Prompt 032

Strict tenant isolation.

Validate organization ownership.

Prevent cross-tenant access.

Enforce quotas.

Audit privileged operations.

---

# PERFORMANCE

Async APIs

Caching

Background Analytics

Queue Integration

Efficient Pagination

Horizontal Scaling

---

# TESTING

Unit Tests

Integration Tests

Quota Tests

License Tests

Department Tests

Team Tests

Organization Tests

Performance Tests

Coverage >=95%

---

# DOCUMENTATION

README

Organization Guide

Department Guide

Team Guide

Subscription Guide

License Guide

Quota Guide

API Reference

Developer Guide

Operations Guide

---

# ACCEPTANCE CRITERIA

✓ Organization CRUD

✓ Department Management

✓ Team Management

✓ Branding

✓ Settings

✓ Licensing

✓ Subscription Management

✓ Quotas

✓ Resource Limits

✓ Analytics

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

Project Management

Inventory

Automation

Workflow Engine

Discovery

Validation

Business Logic outside organization scope.

Only the Enterprise Organization Service.

---

# OUTPUT

Generate every required file.

Generate complete production-ready implementation.

Generate database migrations.

Generate OpenAPI documentation.

Generate REST APIs.

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

End Prompt 033.
