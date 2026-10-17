# Aegis — Governance, Risk & Compliance Platform

> **Governance. Risk. Compliance. Unified.**

Aegis is a modern GRC platform that connects assets, vendors, risks, controls, policies, frameworks, audits, and vulnerabilities into a single correlated graph — with automatic cascading, department-scoped RBAC, and model history.

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
- **Model history** — django-simple-history tracks who changed what, when, on the core domain models.

---

## Feature highlights

### Inventory & Library
- **Asset inventory** with AST-XXXX IDs, hostname, IP, FQDN, OS, cloud provider/region, location, classification, CIA ratings, and business context
- **Relationship Explorer** — interactive force-directed graph showing asset ↔ vendor ↔ risk ↔ control ↔ policy ↔ framework connections
- **Asset Classification** view — grouped by Public / Internal / Confidential / Restricted
- **Asset Owners** view — grouped by department or individual
- **Vendor register** with VEN-XXXX IDs, service type, tier, compliance attestations
- **Vendor Risk Assessment** — 5-dimension scoring (Security, Compliance, Financial, Reputation, Operational) with auto-computed overall rating
- **Policy Library** — versioning, approval workflow (Draft → Review → Approved, named approver required), applies-to departments, PDF attachment

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
- **Login & RBAC** — department-scoped RBAC enforced at the queryset level (`core/mixins.py`); django-guardian is installed and available for future object-level permissions
- **Command palette** (Ctrl+K / ⌘K) — search across assets, risks, controls, policies, vendors, findings, audits, frameworks, KRIs, tickets and threat actors
- **Dark mode** with persistence
- **CSV + Excel + PDF export** on the list views that support it
- **Model history** (django-simple-history) on the core domain models
- **Authorised media downloads** — evidence and policy documents are served through a login- and department-scoped view, not raw `/media/`
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
| Auth | Django auth + department-scoped queryset RBAC (django-guardian available) |
| Audit | django-simple-history |
| Infra | Docker · Docker Compose |

---

## Contributors

**Sujal Adhikari** — Creator & Lead Developer
- GitHub: [@SujalAdhikari-Hacker](https://github.com/SujalAdhikari-Hacker)
- Role: Architecture, backend, business logic, security, UI/UX

See [CONTRIBUTORS.md](CONTRIBUTORS.md) for full attribution and contribution guidelines.

---

## Quick start

### Prerequisites
- Docker Desktop (with WSL 2 on Windows)
- Git

### 1. Clone the repository
```bash
git clone https://github.com/SujalAdhikari-Hacker/aegis-grc.git
cd aegis-grc
```

### 2. Configure environment

```bash
cp .env.example .env
```

Edit `.env` if you want a custom `SECRET_KEY` or different database credentials.

### 3. Build and start

```bash
docker compose up --build
```

The first build takes a few minutes. The web container waits for PostgreSQL, applies migrations automatically, collects static files, then starts **gunicorn** (production settings) on port 8000.

Because the container runs the production settings module, a few TLS-only switches are relaxed for local HTTP. See `.env.example` — importantly, make sure `SECRET_KEY` contains **no `$` character**, as `docker compose` interpolates `$…` in `.env` files.

### 4. Load demo data (optional)

In a second terminal:

```bash
docker compose exec web python manage.py seed_demo
docker compose exec web python manage.py createsuperuser
```

### 5. Open the app

- App: <http://localhost:8000>
- Admin: <http://localhost:8000/admin>

Seeded demo users all use the password `demo1234` (e.g. `it_hod`, `fin_hod`).

### Useful commands

```bash
docker compose logs -f web          # follow app logs
docker compose exec web python manage.py migrate
docker compose exec web python manage.py collectstatic --noinput
docker compose exec web python manage.py recompute_risk_scores   # re-derive residual scores
docker compose restart web          # after editing code (gunicorn does not auto-reload)
docker compose down                 # stop
docker compose down -v              # stop and wipe the database
```

### Settings layout

Configuration lives in `app/config/settings/`:

| Module | Purpose |
|---|---|
| `base.py` | Everything environment-neutral; reads values via `python-decouple` |
| `dev.py` | Permissive local development (`DEBUG=True`, relaxed security) |
| `prod.py` | Hardened defaults (HTTPS, HSTS, secure cookies) as shipped in the container |

Select the module with `DJANGO_SETTINGS_MODULE` (set in `.env` for the containers).

## Notes

- The database is not published on the host by default. Add `ports: ["5432:5432"]` to the `db` service in `docker-compose.yml` if you need to connect from a host tool.
- For production: set `DEBUG=False`, use a strong `SECRET_KEY` (no `$`), set a real `ALLOWED_HOSTS`, and terminate TLS at a reverse proxy. Static files are served by WhiteNoise. Uploaded media (evidence, policy documents) is served only through the login- and department-scoped view in `app/core/media.py` — the raw `/media/` mount is removed so it cannot be bypassed.
- Authorization is centralised in `app/core/mixins.py` (`scope_queryset`, `user_can_access`, …). Views must not hand-roll department filtering; a user with no department sees nothing rather than everything.