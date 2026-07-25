# AI Infrastructure Operating System (AI-IOS)

# Prompt 038

## Enterprise Asset Management Service

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
Prompt 033
Prompt 034
Prompt 035
Prompt 036
Prompt 037

---

# ROLE

You are the Principal Enterprise Asset Management Architect.

Implement the Enterprise Asset Management Service.

Use all previously implemented platform frameworks.

Do NOT redesign the platform.

Implement a production-ready Enterprise Asset Management (EAM) solution.

---

# OBJECTIVE

Build a centralized Asset Management Service responsible for the complete operational lifecycle, governance, ownership, compliance, financial tracking, maintenance, and operational health of enterprise assets.

The service SHALL integrate with the Inventory Service while adding enterprise asset governance capabilities.

Inventory identifies assets.

Asset Management manages assets.

---

# SERVICE LOCATION

services/asset-management-service/

---

# DIRECTORY STRUCTURE

asset-management-service/

app/

api/

controllers/

services/

repositories/

models/

schemas/

assets/

ownership/

assignments/

maintenance/

contracts/

warranty/

compliance/

risk/

costs/

lifecycle/

firmware/

software/

health/

dependencies/

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

managed_assets

asset_assignments

asset_owners

asset_contacts

asset_warranty

asset_contracts

asset_vendors

asset_procurement

asset_depreciation

asset_costs

asset_budget

asset_maintenance

asset_maintenance_windows

asset_maintenance_history

asset_firmware

asset_software

asset_patch_history

asset_compliance

asset_risk

asset_health_rollups

asset_dependency_analysis

asset_change_history

asset_retirement

asset_reports

asset_statistics

asset_audit

---

# MANAGED ASSET MODEL

Every managed asset shall contain

Managed Asset ID

Inventory Asset ID

Organization ID

Project ID

Business Name

Business Owner

Technical Owner

Support Team

Vendor

Status

Lifecycle State

Criticality

Warranty Status

Compliance Status

Risk Score

Operational Health

Acquisition Date

Retirement Date

Metadata

Tags

Labels

---

# ASSET STATUS

Planned

Ordered

Provisioning

Operational

Maintenance

Standby

Suspended

Retired

Disposed

Archived

Deleted

---

# CRITICALITY

Critical

High

Medium

Low

Informational

---

# OWNERSHIP

Support

Business Owner

Technical Owner

Application Owner

Infrastructure Owner

Department

Support Team

Vendor Contact

Escalation Contact

Ownership History

Transfer Ownership

---

# ASSIGNMENTS

Support

Assign Asset

Reassign Asset

Bulk Assignment

Assignment History

Assignment Approval

Temporary Assignment

---

# WARRANTY

Track

Warranty Provider

Warranty Number

Coverage

Start Date

End Date

Expiration Alerts

Renewal Status

Warranty Claims

---

# CONTRACT MANAGEMENT

Support

Support Contracts

Maintenance Contracts

License Contracts

Vendor Contracts

Contract Expiration

Renewal Tracking

Documents

Attachments

---

# PROCUREMENT

Track

Purchase Order

Invoice

Cost Center

Supplier

Acquisition Cost

Purchase Date

Expected Lifetime

Financial Metadata

---

# DEPRECIATION

Support

Straight Line

Declining Balance

Units of Production

Custom Policies

Book Value

Residual Value

Depreciation Reports

---

# COST MANAGEMENT

Track

Acquisition Cost

Operational Cost

Maintenance Cost

Support Cost

Energy Cost

Cloud Cost

Subscription Cost

Repair Cost

Replacement Cost

Total Cost of Ownership (TCO)

---

# MAINTENANCE

Support

Scheduled Maintenance

Emergency Maintenance

Preventive Maintenance

Corrective Maintenance

Maintenance History

Maintenance Calendar

Approval Workflow

---

# MAINTENANCE WINDOWS

Support

Recurring Windows

One-Time Windows

Downtime Tracking

Approval

Notifications

Execution History

---

# FIRMWARE MANAGEMENT

Track

Firmware Version

Available Updates

Upgrade History

Rollback History

Firmware Compliance

Vendor Recommendations

---

# SOFTWARE MANAGEMENT

Track

Installed Software

Versions

Licenses

Patches

Security Updates

End-of-Life Status

Software Inventory

---

# COMPLIANCE

Support

Security Compliance

Configuration Compliance

License Compliance

Patch Compliance

Industry Compliance

Internal Policies

Compliance Reports

Exceptions

---

# RISK MANAGEMENT

Evaluate

Operational Risk

Security Risk

Business Risk

Vendor Risk

Compliance Risk

Risk Scoring

Mitigation Plans

Risk History

---

# HEALTH MANAGEMENT

Aggregate

Monitoring Status

Validation Status

Discovery Status

Automation Status

Incident Count

Performance Indicators

Availability

Health Score

Health Trends

---

# DEPENDENCY ANALYSIS

Integrate with Neo4j.

Support

Impact Analysis

Dependency Graph

Service Dependency

Application Dependency

Infrastructure Dependency

Blast Radius Analysis

Root Cause Relationships

---

# LIFECYCLE MANAGEMENT

Support

Provision

Operate

Maintain

Upgrade

Reassign

Retire

Archive

Dispose

Lifecycle Audit

---

# REPORTING

Generate

Asset Reports

Cost Reports

Compliance Reports

Warranty Reports

Maintenance Reports

Risk Reports

Lifecycle Reports

Executive Dashboards

---

# ANALYTICS

Collect

Asset Growth

Operational Health

Maintenance Trends

Compliance Trends

Risk Trends

Cost Trends

Vendor Performance

Lifecycle Distribution

---

# EVENTS

Publish

ManagedAssetCreated

AssetAssigned

OwnershipTransferred

MaintenanceScheduled

MaintenanceCompleted

WarrantyExpired

ContractExpired

ComplianceFailed

RiskScoreChanged

AssetRetired

LifecycleChanged

Integrate with Prompt 020.

---

# NOTIFICATIONS

Integrate Prompt 025

Notify

Warranty Expiring

Contract Expiring

Maintenance Due

Maintenance Completed

Risk Increased

Compliance Failure

Asset Retirement

Ownership Changed

---

# TELEMETRY

Integrate Prompt 024

Trace

Asset Operations

Maintenance

Compliance

Risk Analysis

Cost Analysis

Dependency Queries

Health Aggregation

---

# AUDIT

Audit

Ownership Changes

Assignments

Maintenance

Compliance Changes

Risk Updates

Lifecycle Events

Financial Updates

Administrative Operations

---

# REST APIs

Implement

GET /assets

GET /assets/{id}

POST /assets

PUT /assets/{id}

PATCH /assets/{id}

DELETE /assets/{id}

POST /assets/{id}/assign

POST /assets/{id}/transfer

GET /assets/{id}/maintenance

POST /assets/{id}/maintenance

GET /assets/{id}/contracts

POST /assets/{id}/contracts

GET /assets/{id}/warranty

PUT /assets/{id}/warranty

GET /assets/{id}/compliance

GET /assets/{id}/risk

GET /assets/{id}/costs

GET /assets/{id}/health

GET /assets/{id}/dependencies

GET /assets/analytics

GET /assets/reports

---

# SECURITY

Integrate Prompt 017.

Integrate Prompt 032.

Integrate Prompt 033.

Integrate Prompt 034.

Enforce

Organization isolation

Project isolation

Role-based authorization

Audit all asset operations

Validate ownership before updates

---

# PERFORMANCE

Async APIs

Caching

Background Analytics

Queue Integration

Neo4j Query Optimization

Bulk Updates

Horizontal Scaling

---

# TESTING

Unit Tests

Integration Tests

Maintenance Tests

Compliance Tests

Risk Tests

Warranty Tests

Dependency Analysis Tests

Analytics Tests

Performance Tests

Coverage >=95%

---

# DOCUMENTATION

README

Asset Management Guide

Maintenance Guide

Warranty Guide

Contract Guide

Compliance Guide

Risk Guide

REST API Reference

Developer Guide

Operations Guide

Architecture Notes

---

# ACCEPTANCE CRITERIA

✓ Asset Lifecycle Management

✓ Ownership & Assignment

✓ Warranty Tracking

✓ Contract Management

✓ Maintenance Scheduling

✓ Firmware Management

✓ Software Management

✓ Compliance Management

✓ Risk Assessment

✓ Cost Tracking

✓ Health Rollups

✓ Dependency Analysis

✓ Reporting

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

Discovery Engine

Inventory Engine

Automation Engine

Workflow Runtime

Monitoring Engine

Incident Management

AI Assistant

Business-specific logic

Only implement the Enterprise Asset Management Service.

---

# OUTPUT

Generate every required file.

Generate complete production-ready implementation.

Generate database migrations.

Generate OpenAPI documentation.

Generate complete REST APIs.

Generate Neo4j dependency integration.

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

End Prompt 038.
