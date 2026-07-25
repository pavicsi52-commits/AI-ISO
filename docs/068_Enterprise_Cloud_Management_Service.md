# AI Infrastructure Operating System (AI-IOS)

# Prompt 068

## Enterprise Cloud Management Service

Reference Documents

Prompt 000
Prompt 001
...
Prompt 067

---

# ROLE

You are the Principal Enterprise Cloud Platform Architect.

Implement the Enterprise Cloud Management Service.

Use every previously implemented platform framework.

Do NOT redesign the platform.

Implement a production-ready enterprise hybrid and multi-cloud management platform.

---

# OBJECTIVE

Build a centralized Cloud Management Service responsible for discovering, provisioning, governing, optimizing, monitoring, securing, and managing cloud infrastructure across multiple providers.

The platform SHALL provide a single enterprise control plane for hybrid cloud, private cloud, and public cloud infrastructure.

---

# SERVICE LOCATION

services/cloud-management-service/

---

# DIRECTORY STRUCTURE

cloud-management-service/

app/

api/

controllers/

services/

repositories/

models/

schemas/

providers/

aws/

azure/

gcp/

oci/

openstack/

vmware/

accounts/

subscriptions/

projects/

tenants/

resources/

compute/

networking/

storage/

database/

kubernetes/

iam/

governance/

policies/

finops/

cost/

budgets/

optimization/

capacity/

drift/

iac/

terraform/

opentofu/

pulumi/

catalog/

compliance/

security/

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

cloud_accounts

cloud_providers

cloud_regions

cloud_projects

cloud_resources

cloud_compute

cloud_storage

cloud_networks

cloud_databases

cloud_kubernetes

cloud_costs

cloud_budgets

cloud_policies

cloud_compliance

cloud_drift

cloud_iac

cloud_catalog

cloud_statistics

cloud_reports

cloud_audit

---

# CLOUD PROVIDERS

Support

Amazon Web Services

Microsoft Azure

Google Cloud Platform

Oracle Cloud Infrastructure

OpenStack

VMware Cloud

Alibaba Cloud

IBM Cloud

DigitalOcean

Private Cloud

Custom Cloud Providers

---

# RESOURCE TYPES

Support

Virtual Machines

Containers

Managed Kubernetes

Functions

Storage Buckets

Block Storage

File Storage

Virtual Networks

Load Balancers

Firewalls

DNS

VPN

Databases

Message Queues

Secrets

Identity Resources

AI Services

Custom Resources

---

# CLOUD ACCOUNT MANAGEMENT

Support

Organization Accounts

Projects

Subscriptions

Tenants

Multi-account Management

Credential Rotation

Account Validation

Account Health

---

# RESOURCE DISCOVERY

Support

Automatic Discovery

Scheduled Discovery

Incremental Discovery

Tag Discovery

Metadata Collection

Relationship Discovery

Resource Classification

Drift Detection

---

# RESOURCE LIFECYCLE

Support

Provision

Update

Scale

Suspend

Resume

Stop

Start

Delete

Archive

Clone

Import

Export

---

# NETWORK MANAGEMENT

Support

Virtual Networks

Subnets

Route Tables

Internet Gateways

NAT Gateways

VPN

Private Endpoints

DNS Zones

Load Balancers

Security Groups

Firewall Rules

Service Mesh Integration

---

# STORAGE MANAGEMENT

Support

Object Storage

Block Storage

File Storage

Snapshot Management

Lifecycle Policies

Replication

Encryption

Storage Classes

Tiering

---

# COMPUTE MANAGEMENT

Support

Virtual Machines

Auto Scaling

Placement Policies

Machine Images

Templates

GPU Instances

Spot Instances

Reserved Instances

Dedicated Hosts

---

# DATABASE MANAGEMENT

Support

Managed PostgreSQL

Managed MySQL

Managed SQL Server

Managed MongoDB

Managed Redis

Managed Kafka

Backup

Restore

Scaling

High Availability

---

# KUBERNETES MANAGEMENT

Support

Managed Kubernetes Discovery

Cluster Registration

Node Pools

Autoscaling

Upgrade Planning

Workload Inventory

Policy Synchronization

Integrate Prompt 066.

---

# IDENTITY MANAGEMENT

Support

IAM Roles

Policies

Groups

Users

Federation

OIDC

SAML

Service Accounts

Identity Synchronization

---

# GOVERNANCE

Integrate Prompt 050.

Support

Cloud Policies

Tag Policies

Naming Policies

Quota Policies

Budget Policies

Security Policies

Resource Restrictions

Approval Policies

---

# INFRASTRUCTURE AS CODE

Support

Terraform

OpenTofu

Pulumi

CloudFormation Import

ARM Import

Deployment Tracking

State Validation

Drift Detection

Version Management

---

# FINOPS

Support

Cost Allocation

Cost Breakdown

Budget Tracking

Forecasting

Chargeback

Showback

Rightsizing

Idle Resource Detection

Reserved Instance Analysis

Savings Recommendations

Carbon Footprint Metrics

---

# CAPACITY PLANNING

Support

CPU Forecasting

Memory Forecasting

Storage Forecasting

Network Forecasting

Growth Analysis

Scaling Recommendations

---

# SERVICE CATALOG

Support

Standardized Templates

Blueprints

Golden Images

Approved Services

Catalog Versioning

Approval Workflow

Self-service Provisioning

---

# COMPLIANCE

Integrate Prompt 051.

Support

CIS Benchmarks

NIST

ISO27001

SOC2

PCI DSS

HIPAA

IEC62443

O-PAS

Cloud Security Posture

Remediation Tracking

---

# PLATFORM INTEGRATIONS

Integrate

Discovery (037)

Inventory (036)

Automation (040)

Monitoring (044)

Knowledge Graph (049)

Policy Engine (050)

Compliance (051)

Scheduler (054)

Notification Center (055)

Backup & Disaster Recovery (065)

Multi-Cluster Management (066)

Edge Management (067)

---

# ANALYTICS

Collect

Cloud Resources

Account Count

Cost Trends

Budget Usage

Resource Utilization

Idle Resources

Drift Count

Compliance Status

Provisioning Time

---

# REPORTING

Generate

Cloud Inventory Reports

Cost Reports

Budget Reports

Compliance Reports

Optimization Reports

Capacity Reports

Audit Reports

---

# EVENTS

Publish

CloudAccountRegistered

CloudResourceDiscovered

CloudResourceProvisioned

CloudResourceUpdated

CloudResourceDeleted

BudgetThresholdExceeded

DriftDetected

OptimizationCompleted

Integrate with Prompt 020.

---

# NOTIFICATIONS

Integrate Prompt 025.

Notify

Budget Exceeded

Idle Resource Detected

Compliance Violation

Provisioning Failed

Credential Expiring

Cloud Drift Detected

Optimization Available

---

# TELEMETRY

Integrate Prompt 024.

Trace

Discovery

Provisioning

Scaling

IaC Operations

Cost Collection

Optimization

Compliance Scans

---

# AUDIT

Audit

Cloud Account Registration

Provisioning

Policy Changes

Cost Changes

IaC Deployments

Compliance Changes

Administrative Operations

---

# REST APIs

Implement

GET /cloud/providers

GET /cloud/accounts

POST /cloud/accounts

GET /cloud/resources

POST /cloud/resources/discover

POST /cloud/resources/provision

PUT /cloud/resources/{id}

DELETE /cloud/resources/{id}

GET /cloud/cost

GET /cloud/budgets

POST /cloud/budgets

GET /cloud/optimization

GET /cloud/compliance

GET /cloud/statistics

GET /cloud/reports

---

# SECURITY

Integrate Prompt 017.

Integrate Prompt 032.

Integrate Prompt 035.

Integrate Prompt 050.

Enforce

Organization isolation

Project isolation

RBAC authorization

Encrypted cloud credentials

Secure IAM federation

Certificate validation

Immutable audit history

Protection against credential leakage

Protection against unauthorized provisioning

---

# PERFORMANCE

Support

Management of 100,000+ cloud resources

Distributed discovery workers

Parallel provisioning

Incremental synchronization

Connection pooling

Caching

Horizontal scaling

High availability

---

# TESTING

Unit Tests

Integration Tests

Cloud Discovery Tests

Provisioning Tests

IaC Tests

Cost Analysis Tests

Compliance Tests

Performance Tests

Coverage >=95%

---

# DOCUMENTATION

README

Cloud Management Guide

Account Management Guide

Provisioning Guide

IaC Guide

FinOps Guide

Compliance Guide

REST API Reference

Developer Guide

Operations Guide

Architecture Notes

---

# ACCEPTANCE CRITERIA

✓ Multi-cloud Provider Support

✓ Cloud Account Management

✓ Resource Discovery

✓ Resource Lifecycle Management

✓ Network Management

✓ Storage Management

✓ Compute Management

✓ Database Management

✓ Managed Kubernetes Integration

✓ IAM Integration

✓ Infrastructure-as-Code Support

✓ FinOps

✓ Governance

✓ Compliance

✓ Service Catalog

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

Cloud Provider APIs

Cloud Hypervisors

Cloud Billing Engines

Provider-specific Internal Services

Only implement the Enterprise Cloud Management Service.

---

# OUTPUT

Generate every required file.

Generate complete production-ready implementation.

Generate database migrations.

Generate OpenAPI documentation.

Generate cloud discovery engine.

Generate provisioning engine.

Generate Infrastructure-as-Code integration.

Generate FinOps engine.

Generate governance framework.

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

End Prompt 068.
