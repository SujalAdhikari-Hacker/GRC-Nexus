# Aegis — Governance, Risk & Compliance Platform

> **Governance. Risk. Compliance. Unified.**

Aegis is a modern GRC platform that connects assets, vendors, risks, controls, policies, frameworks, audits, and vulnerabilities into a single correlated graph — with automatic cascading, per-department RBAC, and full audit trails.

![Status](https://img.shields.io/badge/status-active%20development-blue)
![Python](https://img.shields.io/badge/python-3.11-blue)
![Django](https://img.shields.io/badge/django-4.2-green)
![PostgreSQL](https://img.shields.io/badge/postgresql-16-blue)
![License](https://img.shields.io/badge/license-MIT-lightgrey)

---

## Overview

Aegis is a full-stack Governance, Risk, and Compliance platform designed for mid-size organizations. Unlike centralized security tools, Aegis is built around department-level workflows where each Head of Department owns their own risk, controls, and policies — while the executive layer sees the org-wide picture.

It answers the executive question: *"Where is our risk concentrated, and what are we doing about it?"*

### What makes Aegis different

- **Correlation engine** — every object knows its relationships. Add an asset → baseline risk is created, policies auto-link, vendors update.
- **Cascade scoring** — change a control's effectiveness → every risk it mitigates has its residual score recalculated against department-specific appetite thresholds.
- **Cross-framework mapping** — one control satisfies multiple framework requirements (ISO 27001 + NIST + CIS) with relationship weights (Equal, Subset, Superset, Intersects, Functional Partial).
- **Department-scoped RBAC** — HODs see only their own data. Superadmins see everything. Enforced at queryset level, not just UI.
- **Full audit trail** — every model has a History button. Who changed what, when, and the before/after values.

---

## Feature highlights

### Inventory & Library
- **Asset inventory** with AST-XXXX IDs, hostname, IP, FQDN, OS, cloud provider/region, location, classification, CIA ratings, and business context
- **Relationship Explorer** — interactive force-directed graph showing asset ↔ vendor ↔ risk ↔ control ↔ policy ↔ framework connections
- **Asset Classification** view — grouped by Public / Internal / Confidential / Restricted
- **Asset Owners** view — grouped by department or individual
- **Vendor register** with VEN-XXXX IDs, service type, tier, compliance attestations
- **Vendor Risk Assessment** — 5-dimension scoring (Security, Compliance, Financial, Reputation, Operational) with auto-computed overall rating
- **Policy Library** — versioning, approval workflow, applies-to departments, PDF attachment

### Risk & Controls
- **Risk Register** with inherent/residual scoring, appetite breach flagging, treatment plans
- **Risk Appetite** — appetite level (Averse → Hungry), statements, board approval, thresholds
- **Risk Matrix** — side-by-side inherent vs residual 5×5 grids, clickable cells, quick-add from cell
- **Risk Exceptions** — formal risk acceptance with approver, expiry, and auto-expiration
- **Controls** with lifecycle, effectiveness rating, frequency, primary framework
- **Framework Matrix** — Control × Framework grid with relationship types and coverage %
- **Control Lifecycle Board** — kanban: Proposed → Designed → Implemented → Operational → Monitored → Reviewed → Retired
- **Key Risk Indicators** — RAG status, trends, linked risks and appetites, 6-month trend chart
- **Vulnerabilities** — CVE catalog with live NVD/EPSS/KEV enrichment + composite risk score
- **Live CVE Feed** — synced from NIST NVD
- **Manual vulnerability entry** with 7-stage workflow, SLA, assignment, and solution tracking

### Compliance
- **9 pre-configured frameworks** — ISO 27001, NIST CSF, SOC 2, PCI DSS, GDPR, CIS Controls, CMMC, COBIT, ISO 42001
- **Framework coverage** calculated with relationship weights
- **Compliance Status** dashboard — all frameworks side-by-side
- **Compliance Assessments** — readiness checklists with auto-populated items per framework

### Audit & Compliance
- **Audit Schedule** with types (External / Internal / Self-Assessment) and status workflow
- **Audit Timeline** — kanban by status
- **Evidence Library** — screenshots, exports, configs, logs linked to controls
- **Evidence Scoring** — 5-dimension evaluation (Relevance, Completeness, Timeliness, Reliability, Sufficiency) → 0-100 score with rating bands
- **Control Testing** — 8 result types (Pass, Partial, Fail, Self Audit, Continuous Monitoring, etc.)
- **Audit Findings** — severity, source, owner, due date, recommendation, overdue tracking
- **Action Plans (Remediation)** — sub-tasks under findings with ACT-XXXX IDs, priority, progress tracking
- **Per-audit PDF reports** — full engagement report with findings, tests, evidence, and sign-off

### Threat Intelligence
- **MITRE ATT&CK Matrix** — 14 tactics × 600+ techniques, highlights techniques with IOCs
- **Threat Actors** — 150+ APT groups with attributed techniques
- **IOC Feed** — live indicators from ThreatCluster
- **IOC enrichment** — first_seen, last_seen, malware_family, confidence levels

### Reports
- **Executive Report** — 10-page narrative PDF with 7 embedded charts, cover, TOC, auto-generated recommendations
- **Asset Inventory** — PDF + Excel
- **Risk Register** — PDF + Excel
- **Vulnerability Findings** — PDF + Excel
- **Per-Audit Report** — full engagement PDF

### Platform
- **Login & RBAC** — Groups + object-level permissions via django-guardian
- **Command palette** (Ctrl+K / ⌘K) — search across assets, risks, controls, policies, vendors
- **Dark mode** with persistence
- **CSV export** on every list view
- **Audit trail** (django-simple-history) on every model
- **Native calendar pickers** on all date fields

---

## Tech stack

| Layer | Technology |
|---|---|
| Backend | Django 4.2 LTS · Python 3.11 |
| Database | PostgreSQL 16 |
| Frontend | Django Templates · Bootstrap 5.3 · HTMX 1.9 · Chart.js 4.4 · vis-network |
| Reporting | WeasyPrint (PDF) · matplotlib (charts) · openpyxl (Excel) |
| External APIs | NIST NVD · FIRST EPSS · CISA KEV · MITRE ATT&CK STIX · ThreatCluster |
| Auth | Django auth + django-guardian (object-level permissions) |
| Audit | django-simple-history |
| Infra | Docker · Docker Compose |

---

## Quick start

### Prerequisites
- Docker Desktop (with WSL 2 on Windows)
- Git

### 1. Clone the repository
```bash
git clone https://github.com/SujalAdhikari-Hacker/aegis-grc.git
cd aegis-grc