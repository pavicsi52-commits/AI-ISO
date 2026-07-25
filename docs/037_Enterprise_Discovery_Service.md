# AI Infrastructure Operating System (AI-IOS)

# Prompt 037

## Enterprise Discovery Service

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

---

# ROLE

You are the Principal Infrastructure Discovery Architect.

Implement the Enterprise Discovery Service.

Use all previously implemented platform frameworks.

Do NOT redesign the platform.

Implement a production-ready enterprise discovery engine.

---

# OBJECTIVE

Build a centralized Discovery Service responsible for discovering infrastructure resources across on-premises, cloud, edge, Kubernetes, virtualization, and industrial environments.

The Discovery Service SHALL identify assets, collect metadata, detect relationships, classify resources, and synchronize discovered data into the Inventory Service while maintaining topology in Neo4j.

---

# SERVICE LOCATION

services/discovery-service/

---

# DIRECTORY STRUCTURE

discovery-service/

app/

api/

controllers/

services/

repositories/

models/

schemas/

discovery/

engines/

scanners/

collectors/

classifiers/

normalizers/

synchronization/

topology/

connectors/

schedules/

jobs/

profiles/

rules/

fingerprints/

network/

cloud/

kubernetes/

virtualization/

industrial/

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

discovery_jobs

discovery_profiles

discovery_targets

discovery_credentials

discovery_results

discovery_assets

discovery_relationships

discovery_schedules

discovery_history

discovery_failures

discovery_rules

discovery_filters

discovery_classification

discovery_statistics

discovery_audit

---

# DISCOVERY MODES

Manual

Scheduled

Continuous

Incremental

Full Scan

Agentless

Agent-Based

Hybrid

---

# SUPPORTED PROTOCOLS

SSH

WinRM

SNMP

Redfish

IPMI

HTTP

HTTPS

REST

GraphQL

gRPC

LDAP

DNS

NTP

SMB

SFTP

FTP

OPC UA

Modbus

BACnet

MQTT

AMQP

JMX

WMI

ICMP

TCP

UDP

Plugin-Based Protocols

Integrate with Prompt 027.

---

# DISCOVERY TARGETS

Physical Servers

Virtual Machines

Bare Metal

Hypervisors

VMware

Hyper-V

Proxmox

KVM

Docker

Containerd

Kubernetes

OpenShift

Cloud Providers

AWS

Azure

Google Cloud

Oracle Cloud

IBM Cloud

Edge Devices

Industrial Controllers

PLCs

RTUs

DCS

Switches

Routers

Firewalls

Load Balancers

Storage Arrays

Databases

Applications

Microservices

Custom Assets

---

# NETWORK DISCOVERY

Support

ICMP Sweep

ARP Scan

TCP Scan

UDP Scan

Subnet Discovery

CIDR Discovery

VLAN Discovery

DNS Resolution

Port Identification

Service Detection

OS Fingerprinting

Latency Measurement

---

# CLOUD DISCOVERY

Support

Cloud Accounts

Regions

Availability Zones

Instances

Virtual Networks

Subnets

Security Groups

Load Balancers

Storage

Managed Databases

Kubernetes Services

Cloud Metadata

---

# KUBERNETES DISCOVERY

Support

Clusters

Namespaces

Nodes

Pods

Deployments

StatefulSets

DaemonSets

Services

Ingress

ConfigMaps

Secrets Metadata

Persistent Volumes

Persistent Volume Claims

Jobs

CronJobs

Custom Resources

---

# INDUSTRIAL DISCOVERY

Support

OPC UA

Modbus TCP

BACnet

MQTT

PLC Discovery

RTU Discovery

DCS Discovery

Industrial Networks

Industrial Assets

---

# ASSET CLASSIFICATION

Automatically classify

Infrastructure

Network

Compute

Storage

Cloud

Industrial

Application

Database

Service

Custom

---

# FINGERPRINTING

Identify

Operating System

Vendor

Manufacturer

Model

Firmware

CPU

Memory

Storage

Network Interfaces

Installed Software

Running Services

Open Ports

---

# RELATIONSHIP DISCOVERY

Detect

Runs On

Connected To

Depends On

Hosted By

Contains

Communicates With

Managed By

Member Of

Part Of

Integrate with Inventory Service and Neo4j.

---

# INVENTORY SYNCHRONIZATION

Integrate with Prompt 036.

Support

Create Assets

Update Assets

Merge Assets

Conflict Detection

Duplicate Detection

Asset Reconciliation

Relationship Synchronization

Topology Updates

---

# DISCOVERY PROFILES

Support reusable profiles

Quick Scan

Deep Scan

Network Scan

Cloud Scan

Kubernetes Scan

Industrial Scan

Application Scan

Custom Profiles

---

# DISCOVERY RULES

Support

Include Rules

Exclude Rules

Filters

Asset Matching

Classification Rules

Relationship Rules

Tag Assignment

Owner Assignment

Project Assignment

---

# SCHEDULING

Integrate with Prompt 026.

Support

One-Time

Recurring

Cron

Interval

Maintenance Windows

Retry

Priority

Concurrency Limits

---

# EVENTS

Publish

DiscoveryStarted

DiscoveryCompleted

DiscoveryFailed

AssetDiscovered

AssetUpdated

RelationshipDiscovered

TopologyUpdated

DiscoveryCancelled

DiscoveryProfileCreated

DiscoveryScheduleTriggered

Integrate with Prompt 020.

---

# NOTIFICATIONS

Integrate Prompt 025

Notify

Discovery Started

Discovery Completed

Discovery Failed

Critical Asset Found

Duplicate Assets

Topology Changed

Scan Timeout

Credential Failure

---

# TELEMETRY

Integrate Prompt 024

Trace

Discovery Jobs

Protocol Execution

Classification

Synchronization

Topology Updates

Inventory Updates

Performance Metrics

---

# AUDIT

Audit

Discovery Creation

Execution

Cancellation

Profile Changes

Credential Usage

Inventory Synchronization

Administrative Operations

---

# REST APIs

Implement

GET /discovery/jobs

GET /discovery/jobs/{id}

POST /discovery/jobs

DELETE /discovery/jobs/{id}

GET /discovery/profiles

POST /discovery/profiles

PUT /discovery/profiles/{id}

DELETE /discovery/profiles/{id}

GET /discovery/schedules

POST /discovery/schedules

PUT /discovery/schedules/{id}

DELETE /discovery/schedules/{id}

POST /discovery/scan

POST /discovery/network-scan

POST /discovery/cloud-scan

POST /discovery/kubernetes-scan

POST /discovery/industrial-scan

GET /discovery/results

GET /discovery/statistics

---

# SECURITY

Integrate Prompt 017.

Integrate Prompt 032.

Integrate Prompt 035.

Credentials must be retrieved only from the Secrets Management Service.

Never persist plaintext credentials.

Enforce organization and project isolation.

Audit every discovery execution.

---

# PERFORMANCE

Async Discovery Workers

Parallel Discovery

Queue Integration

Incremental Synchronization

Batch Processing

Connection Pooling

Rate Limiting

Horizontal Scaling

Distributed Execution

---

# TESTING

Unit Tests

Integration Tests

Protocol Tests

Network Discovery Tests

Cloud Discovery Tests

Kubernetes Discovery Tests

Industrial Discovery Tests

Inventory Synchronization Tests

Topology Tests

Performance Tests

Coverage >=95%

---

# DOCUMENTATION

README

Discovery Guide

Discovery Profiles Guide

Protocol Guide

Topology Guide

Inventory Synchronization Guide

REST API Reference

Developer Guide

Operations Guide

Architecture Notes

---

# ACCEPTANCE CRITERIA

✓ Multi-Protocol Discovery

✓ Network Discovery

✓ Cloud Discovery

✓ Kubernetes Discovery

✓ Industrial Discovery

✓ Asset Classification

✓ Fingerprinting

✓ Relationship Discovery

✓ Inventory Synchronization

✓ Neo4j Topology Integration

✓ Scheduling

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

Automation Execution

Workflow Runtime

Validation Engine

Monitoring Engine

AI Assistant

Business-specific logic

Only implement the Enterprise Discovery Service.

---

# OUTPUT

Generate every required file.

Generate complete production-ready implementation.

Generate database migrations.

Generate OpenAPI documentation.

Generate complete REST APIs.

Generate unit and integration tests.

Generate protocol adapters.

Generate Inventory synchronization layer.

Generate Neo4j topology integration.

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

End Prompt 037.
