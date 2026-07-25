# AI Infrastructure Operating System (AI-IOS)

# Prompt 063

## Enterprise Document Intelligence Service

Reference Documents

Prompt 000
Prompt 001
...
Prompt 062

---

# ROLE

You are the Principal Enterprise Document Intelligence Architect.

Implement the Enterprise Document Intelligence Service.

Use every previously implemented platform framework.

Do NOT redesign the platform.

Implement a production-ready Intelligent Document Processing (IDP) platform.

---

# OBJECTIVE

Build a centralized Document Intelligence Service responsible for document ingestion, OCR, layout analysis, document classification, entity extraction, table extraction, form processing, AI-powered understanding, validation, workflow integration, and knowledge extraction.

The service SHALL become the enterprise document understanding platform used by AI-IOS for automation, compliance, AI reasoning, and enterprise workflows.

---

# SERVICE LOCATION

services/document-intelligence-service/

---

# DIRECTORY STRUCTURE

document-intelligence-service/

app/

api/

controllers/

services/

repositories/

models/

schemas/

documents/

ocr/

layout/

classification/

entities/

tables/

forms/

key_value/

summarization/

translation/

validation/

review/

pipelines/

processors/

templates/

metadata/

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

documents

document_versions

document_pages

document_layouts

document_entities

document_tables

document_forms

document_key_values

document_classifications

document_summaries

document_translations

document_reviews

document_validation_results

document_processing_jobs

document_statistics

document_reports

document_audit

---

# DOCUMENT TYPES

Support

PDF

DOCX

TXT

Markdown

HTML

RTF

CSV

XLSX

JSON

XML

YAML

Images

TIFF

Scanned Documents

Multi-page Documents

ZIP Archives

---

# DOCUMENT LIFECYCLE

Support

Upload

Import

Validation

OCR

Parsing

Classification

Extraction

Summarization

Translation

Review

Approval

Archiving

Deletion

Restore

---

# OCR

Support

Printed Text

Handwritten Text

Multi-column Documents

Rotated Pages

Low-resolution Images

Multi-language OCR

Confidence Scores

Batch OCR

GPU Acceleration (Optional)

---

# LAYOUT ANALYSIS

Support

Page Detection

Header Detection

Footer Detection

Paragraph Detection

Table Detection

Image Detection

Section Detection

Reading Order

Page Regions

Bounding Boxes

---

# DOCUMENT CLASSIFICATION

Support

AI Classification

Rule-based Classification

Template Classification

Multi-label Classification

Confidence Scores

Custom Categories

Automatic Routing

---

# ENTITY EXTRACTION

Support

People

Organizations

Addresses

Emails

Phone Numbers

Dates

Currencies

Identifiers

Asset Names

Hostnames

IP Addresses

URLs

Serial Numbers

Custom Entities

---

# TABLE EXTRACTION

Support

Merged Cells

Nested Tables

Multi-page Tables

Header Detection

Footer Detection

Cell Confidence

CSV Export

JSON Export

Excel Export

---

# FORM EXTRACTION

Support

Key-Value Extraction

Checkbox Detection

Radio Button Detection

Signature Detection

Handwritten Fields

Validation Rules

Confidence Scores

Template Matching

---

# SUMMARIZATION

Support

Executive Summary

Technical Summary

Bullet Summary

Section Summary

AI Summary

Extractive Summary

Abstractive Summary

---

# TRANSLATION

Support

Multi-language Translation

Language Detection

Glossary Support

Terminology Preservation

Confidence Scores

---

# DOCUMENT VALIDATION

Support

Required Fields

Business Rules

Schema Validation

Completeness Validation

Duplicate Detection

Consistency Validation

Confidence Thresholds

---

# HUMAN REVIEW

Support

Review Queue

Assignment

Annotations

Corrections

Approval

Reprocessing

Version History

Audit Trail

---

# WORKFLOW INTEGRATION

Integrate

Workflow Runtime (042)

Automation (040)

AI Agent Platform (060)

Prompt Management (061)

RAG Service (062)

Knowledge Graph (049)

Scheduler (054)

Notification Center (055)

---

# ANALYTICS

Collect

Processed Documents

OCR Accuracy

Extraction Accuracy

Classification Accuracy

Review Time

Validation Failures

Average Processing Time

Language Distribution

---

# REPORTING

Generate

Processing Reports

OCR Reports

Extraction Reports

Classification Reports

Validation Reports

Review Reports

Audit Reports

---

# EVENTS

Publish

DocumentUploaded

OCRCompleted

ClassificationCompleted

ExtractionCompleted

ValidationCompleted

ReviewCompleted

DocumentArchived

Integrate with Prompt 020.

---

# NOTIFICATIONS

Integrate Prompt 025.

Notify

OCR Failed

Validation Failed

Review Assigned

Review Completed

Processing Completed

Translation Completed

---

# TELEMETRY

Integrate Prompt 024.

Trace

Upload

OCR

Layout Analysis

Classification

Entity Extraction

Table Extraction

Validation

Review

---

# AUDIT

Audit

Document Upload

Document Processing

OCR Results

Classification Changes

Validation Changes

Review Actions

Administrative Operations

---

# REST APIs

Implement

GET /documents

POST /documents

GET /documents/{id}

PUT /documents/{id}

DELETE /documents/{id}

POST /documents/{id}/ocr

POST /documents/{id}/classify

POST /documents/{id}/extract

POST /documents/{id}/summarize

POST /documents/{id}/translate

POST /documents/{id}/validate

POST /documents/{id}/review

GET /documents/statistics

GET /documents/reports

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

Encrypted document storage

Confidential document classification

Immutable audit history

Secure temporary file handling

Protection against malicious document uploads

---

# PERFORMANCE

Parallel Document Processing

Distributed Workers

Batch Processing

Incremental Processing

OCR Caching

Horizontal Scaling

Connection Pooling

High Availability

---

# TESTING

Unit Tests

Integration Tests

OCR Tests

Classification Tests

Entity Extraction Tests

Table Extraction Tests

Validation Tests

Performance Tests

Coverage >=95%

---

# DOCUMENTATION

README

Document Intelligence Guide

OCR Guide

Classification Guide

Entity Extraction Guide

Table Extraction Guide

Validation Guide

REST API Reference

Developer Guide

Operations Guide

Architecture Notes

---

# ACCEPTANCE CRITERIA

✓ Intelligent Document Processing

✓ OCR Engine

✓ Layout Analysis

✓ Document Classification

✓ Entity Extraction

✓ Table Extraction

✓ Form Extraction

✓ Summarization

✓ Translation

✓ Validation

✓ Human Review Workflow

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

Custom OCR Model Training

Business-specific Document Templates

Third-party SaaS OCR Dependencies

Only implement the Enterprise Document Intelligence Service.

---

# OUTPUT

Generate every required file.

Generate complete production-ready implementation.

Generate database migrations.

Generate OpenAPI documentation.

Generate OCR engine integration.

Generate layout analysis engine.

Generate entity extraction engine.

Generate document processing pipeline.

Generate validation framework.

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

End Prompt 063.
