# AI Infrastructure Operating System (AI-IOS)

# Prompt 036

## Enterprise Inventory Service

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

---

# ROLE

You are the Principal Enterprise Infrastructure Architect.

Implement the Enterprise Inventory Service.

Use all previously implemented platform frameworks.

Do NOT redesign the platform.

Implement a production-ready enterprise inventory and CMDB service.

---

# OBJECTIVE

Build a centralized Inventory Service that acts as the authoritative source of infrastructure assets across AI-IOS.

The inventory SHALL support hybrid, cloud, edge, industrial, and Kubernetes environments.

Every discovered asset SHALL be represented in this service.

The Inventory Service SHALL integrate with Neo4j to maintain asset relationships and topology.

---

# SERVICE LOCATION

services/inventory-service/

---

# DIRECTORY STRUCTURE

inventory-service/

app/

api/

controllers/

services/

repositories/

models/

schemas/

assets/

relationships/

topology/

groups/

labels/

tags/

ownership/

classification/

health/

lifecycle/

locations/

synchronization/

imports/

exports/

analytics/

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

inventory_assets

asset_types

asset_categories

asset_classes

asset_relationships

asset_groups

asset_labels

asset_tags

asset_locations

asset_owners

asset_contacts

asset_metadata

asset_attributes

asset_custom_fields

asset_status

asset_health

asset_lifecycle

asset_versions

asset_history

asset_import_jobs

asset_export_jobs

asset_discovery_links

asset_topology_cache

inventory_statistics

inventory_audit

---

# SUPPORTED ASSET TYPES

Physical Servers

Virtual Machines

Bare Metal

Hypervisors

Containers

Container Images

Kubernetes Clusters

Namespaces

Pods

Deployments

StatefulSets

DaemonSets

Services

Ingress

Persistent Volumes

Storage Systems

SAN

NAS

Object Storage

Switches

Routers

Firewalls

Load Balancers

Wireless Controllers

Industrial Controllers

PLCs

RTUs

DCS Controllers

OPC UA Servers

OPC UA Devices

IoT Devices

Cloud Accounts

Cloud Regions

Cloud Resources

Applications

Microservices

Databases

Middleware

Message Brokers

Web Servers

API Gateways

Monitoring Agents

Automation Agents

Validation Agents

Custom Assets

---

# ASSET MODEL

Every asset shall contain

Asset ID

Organization ID

Project ID

Asset Name

Display Name

Hostname

FQDN

IP Address

MAC Address

Serial Number

Vendor

Manufacturer

Model

Firmware Version

Operating System

Architecture

Environment

Location

Owner

Status

Health

Lifecycle State

Criticality

Tags

Labels

Metadata

Created At

Updated At

---

# ASSET STATUS

Discovered

Registered

Managed

Unmanaged

Provisioning

Maintenance

Retired

Archived

Deleted

---

# HEALTH STATUS

Healthy

Warning

Critical

Unknown

Offline

Unreachable

---

# LIFECYCLE

Planned

Provisioning

Operational

Maintenance

Retired

Disposed

Archived

---

# RELATIONSHIP MODEL

Support

Runs On

Hosted By

Connected To

Depends On

Consumes

Provides

Owns

Managed By

Protected By

Replicated To

Backed Up By

Contains

Part Of

Member Of

Communicates With

Custom Relationships

---

# TOPOLOGY

Integrate with Neo4j.

Maintain

Dependency Graph

Network Graph

Application Graph

Infrastructure Graph

Industrial Topology

Cloud Topology

Kubernetes Topology

Relationship Traversal

Impact Analysis

---

# GROUPS

Support

Static Groups

Dynamic Groups

Rule-Based Groups

Location Groups

Application Groups

Environment Groups

Custom Groups

---

# TAGS

Support

Multiple Tags

Bulk Assignment

Filtering

Search

Inheritance

---

# LABELS

Support

Key/Value Labels

Namespaces

Selectors

Kubernetes Compatible Labels

---

# LOCATIONS

Support

Country

Region

Site

Building

Floor

Rack

Rack Unit

Room

GPS Coordinates

Custom Locations

---

# OWNERSHIP

Track

Business Owner

Technical Owner

Support Team

Vendor

Department

Organization

Project

---

# CUSTOM ATTRIBUTES

Support

Dynamic Fields

Custom Metadata

Schemas

Validation

Typed Values

---

# INVENTORY SYNCHRONIZATION

Support

Discovery Updates

Manual Updates

Bulk Sync

Conflict Detection

Merge Policies

Duplicate Detection

Asset Reconciliation

---

# IMPORT

Support

CSV

Excel

JSON

YAML

ZIP

Bulk Import

Validation

Preview

Rollback

---

# EXPORT

Support

CSV

Excel

JSON

YAML

PDF

ZIP

Background Processing

Audit

---

# SEARCH

Support

Hostname

IP Address

MAC Address

Serial Number

Vendor

Model

OS

Tags

Labels

Metadata

Owner

Project

Organization

Full Text Search

Pagination

Sorting

Filtering

---

# ANALYTICS

Collect

Asset Count

Asset Types

Health Distribution

Lifecycle Distribution

OS Distribution

Vendor Distribution

Location Distribution

Relationship Count

Discovery Statistics

Growth Trends

---

# EVENTS

Publish

AssetCreated

AssetUpdated

AssetDeleted

AssetImported

AssetExported

AssetHealthChanged

AssetMoved

AssetOwnerChanged

RelationshipCreated

RelationshipDeleted

InventorySynchronized

Integrate with Prompt 020.

---

# NOTIFICATIONS

Integrate Prompt 025

Notify

Asset Offline

Health Changed

Duplicate Detected

Import Completed

Import Failed

Topology Changed

Critical Asset Updated

---

# TELEMETRY

Integrate Prompt 024

Trace

Inventory CRUD

Topology Updates

Relationship Queries

Imports

Exports

Synchronization

Search Operations

---

# AUDIT

Audit

Asset Creation

Updates

Deletion

Imports

Exports

Relationship Changes

Ownership Changes

Status Changes

Metadata Changes

Administrative Actions

---

# REST APIs

Implement

GET /inventory/assets

GET /inventory/assets/{id}

POST /inventory/assets

PUT /inventory/assets/{id}

PATCH /inventory/assets/{id}

DELETE /inventory/assets/{id}

POST /inventory/import

POST /inventory/export

GET /inventory/search

GET /inventory/groups

POST /inventory/groups

GET /inventory/topology

GET /inventory/relationships

POST /inventory/relationships

DELETE /inventory/relationships/{id}

GET /inventory/statistics

GET /inventory/analytics

---

# SECURITY

Integrate Prompt 017.

Integrate Prompt 032.

Integrate Prompt 033.

Integrate Prompt 034.

Enforce

Organization isolation

Project isolation

RBAC authorization

Audit all inventory changes

Validate asset ownership

Prevent duplicate identifiers

---

# PERFORMANCE

Async APIs

Bulk Operations

Background Imports

Background Exports

Caching

Queue Integration

Neo4j Batch Updates

Optimized Search

Horizontal Scaling

---

# TESTING

Unit Tests

Integration Tests

Relationship Tests

Topology Tests

Import Tests

Export Tests

Synchronization Tests

Performance Tests

Coverage >=95%

---

# DOCUMENTATION

README

Inventory Guide

Asset Model Guide

Relationship Guide

Topology Guide

Import Guide

Export Guide

REST API Reference

Developer Guide

Operations Guide

Architecture Notes

---

# ACCEPTANCE CRITERIA

✓ Inventory CRUD

✓ Asset Classification

✓ Relationship Management

✓ Neo4j Topology Integration

✓ Asset Groups

✓ Labels

✓ Tags

✓ Ownership

✓ Synchronization

✓ Import

✓ Export

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

Automation Engine

Workflow Runtime

Validation Engine

Monitoring Engine

Connector Execution

AI Assistant

Business-specific logic

Only implement the Enterprise Inventory Service.

---

# OUTPUT

Generate every required file.

Generate complete production-ready implementation.

Generate database migrations.

Generate OpenAPI documentation.

Generate complete REST APIs.

Generate unit and integration tests.

Generate Neo4j integration layer.

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

End Prompt 036.
