# AI Infrastructure Operating System (AI-IOS)

# Prompt 058

## Enterprise Integration Hub Service

Reference Documents

Prompt 000
Prompt 001
...
Prompt 057

---

# ROLE

You are the Principal Enterprise Integration Architect.

Implement the Enterprise Integration Hub Service.

Use every previously implemented platform framework.

Do NOT redesign the platform.

Implement a production-ready enterprise integration platform.

---

# OBJECTIVE

Build a centralized Integration Hub responsible for managing connectors, synchronization, credentials, transformations, event routing, integration monitoring, and connector lifecycle management.

The Integration Hub SHALL become the standard mechanism for integrating AI-IOS with enterprise applications, cloud providers, industrial protocols, DevOps platforms, monitoring systems, and customer environments.

---

# SERVICE LOCATION

services/integration-hub-service/

---

# DIRECTORY STRUCTURE

integration-hub-service/

app/

api/

controllers/

services/

repositories/

models/

schemas/

connectors/

catalog/

registry/

credentials/

authentication/

oauth/

sync/

jobs/

mapping/

transformations/

flows/

routing/

monitoring/

health/

discovery/

marketplace/

templates/

events/

notifications/

analytics/

reports/

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

connectors

connector_versions

connector_categories

connector_credentials

connector_connections

connector_sync_jobs

connector_transformations

connector_flows

connector_events

connector_health

connector_statistics

connector_reports

connector_marketplace

connector_audit

---

# CONNECTOR CATEGORIES

Cloud

Virtualization

Container Platforms

Monitoring

ITSM

DevOps

Identity

Networking

Storage

Databases

Industrial Protocols

Messaging

Security

Business Applications

Custom

---

# BUILT-IN CONNECTORS

## Cloud

AWS

Microsoft Azure

Google Cloud Platform

Oracle Cloud Infrastructure

OpenStack

VMware Cloud

---

## Virtualization

VMware vCenter

VMware ESXi

Proxmox VE

Microsoft Hyper-V

Nutanix AHV

KVM

---

## Container Platforms

Kubernetes

OpenShift

Rancher

Docker

Docker Swarm

---

## Identity

LDAP

Microsoft Active Directory

Keycloak

Azure Active Directory

Okta

---

## DevOps

GitHub

GitLab

Azure DevOps

Bitbucket

Jenkins

Argo CD

FluxCD

Harbor

---

## ITSM

ServiceNow

Jira

Freshservice

BMC Helix

ManageEngine ServiceDesk

---

## Monitoring

Prometheus

Grafana

Zabbix

Nagios

Datadog

New Relic

Elastic

Splunk

---

## Industrial

Redfish

IPMI

SNMP

OPC UA

MQTT

Modbus TCP

BACnet

EtherNet/IP

PROFINET

---

## Databases

PostgreSQL

MySQL

MariaDB

Microsoft SQL Server

Oracle Database

MongoDB

Neo4j

Redis

---

## Messaging

Kafka

RabbitMQ

NATS

ActiveMQ

MQTT Broker

---

## Storage

MinIO

Ceph

NetApp

Dell PowerStore

Pure Storage

---

## Custom

REST API

SOAP

GraphQL

Webhook

gRPC

Custom SDK Connector

---

# CONNECTOR LIFECYCLE

Support

Registration

Installation

Configuration

Credential Assignment

Validation

Testing

Enable

Disable

Upgrade

Rollback

Deprecation

Removal

---

# AUTHENTICATION

Support

OAuth2

OpenID Connect

API Keys

JWT

Basic Authentication

Bearer Tokens

Mutual TLS

Certificate Authentication

Username/Password

Custom Authentication

---

# CREDENTIAL MANAGEMENT

Integrate Prompt 035.

Support

Encrypted Secrets

Credential Rotation

Credential Validation

Credential Testing

Credential Expiration

Credential Ownership

Secret References

---

# DATA SYNCHRONIZATION

Support

One-way Sync

Two-way Sync

Incremental Sync

Full Sync

Scheduled Sync

Manual Sync

Event-driven Sync

Conflict Resolution

Checkpointing

Resume

---

# DATA TRANSFORMATION

Support

JSON Mapping

XML Mapping

CSV Mapping

YAML Mapping

Field Mapping

Schema Validation

Data Enrichment

Filtering

Aggregation

Normalization

Custom Transformation

---

# INTEGRATION FLOWS

Support

Visual Flow Definition

Conditional Logic

Branching

Loops

Retries

Error Handling

Compensation

Approval Steps

Scheduling

Parallel Execution

---

# EVENT ROUTING

Support

Internal Events

Webhook Events

Message Queue Events

REST Events

GraphQL Events

Streaming Events

Broadcast Events

Event Filtering

Event Enrichment

---

# HEALTH MANAGEMENT

Support

Connector Health

Endpoint Availability

Credential Status

Latency

Throughput

Failure Detection

Automatic Recovery

Heartbeat Monitoring

---

# MARKETPLACE

Support

Connector Catalog

Connector Metadata

Connector Versioning

Connector Dependencies

Connector Publishing

Connector Installation

Connector Updates

Connector Ratings

---

# PLATFORM INTEGRATIONS

Integrate

Connector SDK (027)

Secrets (035)

Inventory (036)

Discovery (037)

Automation (040)

Workflow Runtime (042)

Monitoring (044)

Knowledge Graph (049)

Scheduler (054)

Webhook Service (057)

---

# ANALYTICS

Collect

Connector Usage

Synchronization Success

Synchronization Failures

Latency

Throughput

Connector Health

Installation Count

Marketplace Usage

Transformation Usage

---

# REPORTING

Generate

Connector Reports

Synchronization Reports

Health Reports

Credential Reports

Marketplace Reports

Performance Reports

Audit Reports

---

# EVENTS

Publish

ConnectorRegistered

ConnectorInstalled

ConnectorEnabled

ConnectorDisabled

SynchronizationStarted

SynchronizationCompleted

SynchronizationFailed

ConnectorHealthChanged

MarketplaceUpdated

Integrate with Prompt 020.

---

# NOTIFICATIONS

Integrate Prompt 025.

Notify

Connector Failure

Credential Expiration

Synchronization Failure

Connector Update Available

Marketplace Publication

Health Degradation

---

# TELEMETRY

Integrate Prompt 024.

Trace

Connector Calls

Authentication

Synchronization

Transformation

Routing

Health Checks

Marketplace Operations

---

# AUDIT

Audit

Connector Registration

Configuration Changes

Credential Assignment

Synchronization

Marketplace Actions

Administrative Operations

---

# REST APIs

Implement

GET /integrations/connectors

GET /integrations/connectors/{id}

POST /integrations/connectors

PUT /integrations/connectors/{id}

DELETE /integrations/connectors/{id}

POST /integrations/connectors/{id}/test

POST /integrations/connectors/{id}/enable

POST /integrations/connectors/{id}/disable

POST /integrations/connectors/{id}/sync

GET /integrations/marketplace

POST /integrations/marketplace/publish

GET /integrations/health

GET /integrations/statistics

GET /integrations/reports

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

Encrypted connector credentials

Secure connector communication

Certificate validation

Immutable audit history

Protection against SSRF

Protection against malicious connector code

---

# PERFORMANCE

Distributed Connector Workers

Async Synchronization

Connection Pooling

Caching

Horizontal Scaling

Connector Isolation

Automatic Failover

High Availability

---

# TESTING

Unit Tests

Integration Tests

Connector Tests

Synchronization Tests

Transformation Tests

Authentication Tests

Marketplace Tests

Performance Tests

Coverage >=95%

---

# DOCUMENTATION

README

Integration Hub Guide

Connector Development Guide

Connector Administration Guide

Synchronization Guide

Transformation Guide

Marketplace Guide

REST API Reference

Developer Guide

Operations Guide

Architecture Notes

---

# ACCEPTANCE CRITERIA

✓ Connector Management

✓ Connector Catalog

✓ Built-in Enterprise Connectors

✓ Credential Management

✓ Synchronization Engine

✓ Transformation Engine

✓ Integration Flows

✓ Event Routing

✓ Health Monitoring

✓ Marketplace Integration

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

Commercial iPaaS Platforms

Low-code Business Automation Suites

Vendor-specific Licensing

Customer-specific Connectors

Only implement the Enterprise Integration Hub Service.

---

# OUTPUT

Generate every required file.

Generate complete production-ready implementation.

Generate database migrations.

Generate OpenAPI documentation.

Generate connector management engine.

Generate synchronization engine.

Generate transformation engine.

Generate marketplace integration.

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

End Prompt 058.
