<div align="center">

<img src="docs/branding/grc-nexus-logo.png" alt="GRC Nexus — from assets to assurance" width="420">

# GRC Nexus

### Governance · Risk · Compliance — unified in one correlated graph.

**Where is our risk concentrated, and what are we doing about it?**

[![Python](https://img.shields.io/badge/python-3.11-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![Django](https://img.shields.io/badge/django-4.2-092E20?logo=django&logoColor=white)](https://www.djangoproject.com/)
[![PostgreSQL](https://img.shields.io/badge/postgresql-16-4169E1?logo=postgresql&logoColor=white)](https://www.postgresql.org/)
[![Docker](https://img.shields.io/badge/docker-compose-2496ED?logo=docker&logoColor=white)](https://docs.docker.com/compose/)
[![Tests](https://img.shields.io/badge/tests-219%20passing-brightgreen)](#testing)
[![License](https://img.shields.io/badge/license-MIT-blue)](LICENSE)

</div>

---

## Overview

**GRC Nexus** is a full-stack Governance, Risk and Compliance platform built around
**department-level ownership**. Every Head of Department owns their own risks, controls and
policies; the executive layer sees the org-wide picture. It is a single, correlated graph of
assets, vendors, risks, controls, policies, frameworks, audits and vulnerabilities — not a set
of disconnected registers.

It is designed for mid-size organisations and for security/GRC practitioners who want a
realistic, self-hostable platform rather than a spreadsheet sprawl.

---

## Why it's different

- **Correlation engine** — objects know their relationships. Creating an asset automatically
  raises a baseline risk, links applicable policies, and ties into vendor and control views.
- **Cascade scoring** — change a control's effectiveness and every risk it mitigates has its
  residual score recomputed against department-specific appetite thresholds. A vulnerability
  finding cascades into the risk register automatically.
- **Defence-in-depth risk maths** — residual risk is reduced multiplicatively by weighted,
  evidence-gated controls (never additively), so a stack of "perfect" controls can never drive a
  risk to zero. See [Architecture](#architecture).
- **Department-scoped RBAC** — enforced at the *queryset* level (`core/mixins.py`), not just in
  the UI. A user with no department sees nothing rather than everything.
- **Cross-framework mapping** — one control satisfies many framework requirements
  (ISO 27001 + NIST + CIS) with relationship types and weighted coverage.
- **Model history & merged change log** — `django-simple-history` tracks who changed what, and
  when, on the core domain models, and the **Change Log** page (`/history/`, HODs and superusers)
  merges the newest rows across every tracked register into one filterable, paginated list —
  the "show me everything that changed this quarter" page auditors ask for.
- **Sign-in throttling** — repeated failed logins from the same IP+username are locked out
  (5 failures / 15 min window) before the password is ever checked; configurable via
  `LOGIN_MAX_FAILURES`, `LOGIN_FAILURE_WINDOW` and `LOGIN_LOCKOUT_SECONDS`, no extra
  dependencies.

---

## Feature highlights

### Governance & inventory
- **Asset inventory** — `AST-XXXX` IDs, hostname, IP, FQDN, OS, cloud provider/region,
  location, classification, CIA ratings and business context.
- **Asset dependencies** — an upstream/downstream dependency graph (`depends_on`) with its own
  form section: every asset page shows what it needs *and* which systems it can take down,
  i.e. the outage blast radius auditors and ops both care about.
- **Relationship Explorer** — interactive force-directed graph of
  asset ↔ vendor ↔ risk ↔ control ↔ policy ↔ framework connections.
- **Classification & owner views** — grouped by Public/Internal/Confidential/Restricted, and by
  department or individual.
- **Vendor register** — `VEN-XXXX` IDs, service type, tier and compliance attestations.
  Contract expiry is derived from the renewal date, so a vendor left "active" whose contract has
  lapsed is surfaced as **contract expired** (with days overdue) in the list and detail views.
- **Vendor risk assessment** — 5-dimension scoring (Security, Compliance, Financial,
  Reputation, Operational) with an auto-computed overall rating.
- **Policy library** — versioning, an approval workflow (Draft → Review → Approved, named
  approver required), applies-to departments, and PDF attachment.

### Risk & controls
- **Risk register** — inherent/residual scoring, appetite-breach flagging, treatment plans.
- **Risk appetite** — appetite level (Averse → Hungry), statements, board approval and
  thresholds; registration beyond capacity is blocked. Breach detection is **residual-governed**:
  an untreated risk is also checked against the inherent ceiling, then re-evaluated purely on
  residual once effective controls are in place — so linking real mitigation clears the breach,
  and "no appetite configured" is shown distinctly from "within appetite".
- **Risk matrix** — side-by-side inherent vs residual 5×5 grids, clickable cells, quick-add.
- **Workflow state machine** - risks move through legal transitions only; closing a risk that
  breaches appetite requires a named approver. **A risk closes when every treatment plan is
  resolved and at least one completed** — and it reopens automatically if a treatment returns to
  active. Completing a treatment promotes its controls onto the risk (so the residual score
  actually moves).
- **Risk exceptions** — formal risk acceptance with approver, expiry and auto-expiration. The
  named approver is notified and is the **only** person who can accept the risk (superuser can
  break-glass) — the approver is never silently overwritten.
- **Controls** — lifecycle, effectiveness rating (evidence-gated: no test date, no rating),
  frequency and primary framework.
- **Framework matrix** — Control × Framework grid with relationship types and coverage %.
- **Control lifecycle board** — kanban: Proposed → Designed → Implemented → Operational →
  Monitored → Reviewed → Retired.
- **Key Risk Indicators** — RAG status, trends, linked risks/appetites, 6-month trend chart.
- **Vulnerabilities** — CVE catalogue with live NVD/EPSS/KEV enrichment and a composite risk
  score. Findings cascade into the risk register; remediation auto-closes the derived risk.

### Compliance
- **Framework coverage** calculated with relationship weights.
- **Compliance status** dashboard across all frameworks.
- **Compliance assessments** — readiness checklists with auto-populated items per framework.
- **Statement of Applicability** — a derived, always-current SoA report per framework
  (`/frameworks/soa/`): one row per requirement with the verdict from your control mappings and
  the newest assessment (covered / partially covered / gap / excluded), with CSV export for
  auditors.
- Ships with a seeder for **ISO/IEC 27001, NIST CSF, SOC 2, PCI DSS, GDPR and CIS Controls**
  (500+ framework requirements).

### Incident management
- **Security incident register** — `INC-YYYY-NNNN` references, incident types, detection source,
  severity and a forward-only lifecycle (Detected → Triaged → Contained → Mitigated → Closed)
  with automatic timeline stamps (triage, containment, resolution, closure).
- **Severity-driven triage SLAs** — critical 1h, high 4h, medium 24h, low 72h; an untriaged
  incident past its SLA escalates (in-app notification + email to the handler or HOD).
- **Personal-data breach tracking (GDPR Art. 33)** — affected-person counting, a live 72-hour
  notification clock with days/hours remaining, overdue escalation, and a cabinet-level warning
  on the close page when the notification is still outstanding.
- **Closure discipline** — an incident cannot be closed without a recorded root cause; lessons
  learned are captured on the record.
- **Risk linkage** — one click raises a risk-register entry from an investigated incident
  (pre-filled, pre-linked, refuses duplicates) — incidents may also be linked to existing risks.

### Audit & assurance
- **Audit schedule** — types (External / Internal / Self-Assessment) and a status workflow,
  plus a kanban timeline.
- **Evidence library** — screenshots, exports, configs and logs linked to controls.
- **Evidence scoring** — 5-dimension evaluation (Relevance, Completeness, Timeliness,
  Reliability, Sufficiency) → 0–100 score with rating bands.
- **Control testing** — 8 result types (Pass, Partial, Fail, Self Audit, Continuous Monitoring…),
  with the tester recorded from the user list.
- **Audit findings** — severity, source, owner, due date, recommendation, overdue tracking.
- **Verification loop** — a finding moves Resolved → Verified → Closed; it cannot be closed
  until a HOD or superuser verifies the fix (rejection sends it back for remediation).
- **Action plans** — sub-tasks under findings with `ACT-XXXX` IDs, priority and progress.
- **Per-audit PDF report** — full engagement report with findings, tests, evidence and sign-off.

### Policy attestation
- **Attestation workflow** — approved policies show an *"I have read and accept this policy"*
  control; attestations are recorded per **policy version**, so a re-approved policy (bumped
  version) makes prior acknowledgements stale and asks the same people again. The policy detail
  page lists who has acknowledged the current version with timestamps; org-wide policies can be
  attested by anyone, department-scoped ones by their audience.

### Threat intelligence
- **MITRE ATT&CK matrix** — tactics × techniques, highlighting techniques with matching IOCs.
- **Threat actors** — APT groups with attributed techniques.
- **IOC feed** — live indicators (ThreatCluster / ThreatFox / OTX) with enrichment
  (first_seen, last_seen, malware_family, confidence).

### Reporting
- **Executive report** — multi-page narrative PDF with embedded charts, cover, TOC and
  auto-generated recommendations.
- **Asset inventory**, **risk register** and **vulnerability findings** — PDF + Excel.
- **Per-audit report** — full engagement PDF.
- All generated PDFs carry a confidentiality watermark (one seal per page).

### Platform
- **Login & RBAC** — department-scoped, enforced at the queryset level, plus **object-level
  permissions** via `django-guardian`: a HOD can share a single record with a user or group
  from the sharing panel on its detail page, without widening their whole department view.
- **Command palette** (Ctrl/⌘ + K) — search across assets, risks, controls, policies, vendors,
  findings, audits, frameworks, KRIs, tickets and threat actors.
- **Notifications** — a department-scoped work queue (unread is real unread).
- **Email digests & escalations** — a scheduled scan finds overdue tickets, findings and actions,
  risks past their target date or beyond capacity, expiring risk exceptions, lapsing vendor
  contracts, red KRIs and SLA-breached vulnerabilities, **untriaged incidents past their
  severity SLA and GDPR breach-notification deadlines**. Each item is raised in-app for the
  owning department and emailed to the responsible person (owner, else the department HOD). An
  item is only emailed once while it stays unresolved, so the job is safe to run hourly. Users
  choose Off / Daily / Weekly digests and per-event email toggles in Settings (including a
  dedicated incident toggle), and can send themselves a test email to confirm delivery. Ships
  with the console email backend, so it is observable out of the box via `docker compose logs
  -f web` — point `EMAIL_BACKEND` at SMTP for real mail.
- **Dark mode** with persistence; native `type="date"` calendar pickers everywhere.
- **CSV / Excel / PDF export** on the list views that support it.
- **Bulk actions** — select rows on a register and apply a server-approved change (e.g. set
  severity, set classification) in one step, scoped to what you can see.
- **Saved views** — name the filters you use most and recall them from a dropdown on the list.
- **Tickets** — a work item can be linked to a specific asset, risk, control or policy (pick at
  most one), so tickets can be raised *for* a given record.
- **Delete actions** — HOD/superuser-only and department-scoped, with a confirmation page that
  warns about linked records before anything is removed.
- **Custom error pages** — 403 and 404 pages explain cross-department access denials and offer a
  route back, instead of a bare framework error.
- **Authorised media downloads** — evidence and policy documents are served through a login- and
  department-scoped view (`core/media.py`), never raw `/media/`.
- **Accessibility & responsive** — skip link, live regions, visible focus states, print
  stylesheet, reduced-motion support and an off-canvas mobile sidebar.

---

## Tech stack

| Layer | Technology |
|---|---|
| Backend | Django 4.2 LTS · Python 3.11 |
| Database | PostgreSQL 16 |
| Frontend | Django Templates · Bootstrap 5.3 · HTMX · Chart.js · vis-network |
| Reporting | WeasyPrint (PDF) · matplotlib (charts) · openpyxl (Excel) |
| External data | NIST NVD · FIRST EPSS · CISA KEV · MITRE ATT&CK (STIX) · ThreatCluster · abuse.ch ThreatFox · AlienVault OTX |
| Auth | Django auth + department-scoped queryset RBAC (`django-guardian` available) |
| History | `django-simple-history` |
| Server | gunicorn + WhiteNoise |
| Config | `python-decouple` (12-factor) |
| Infra | Docker · Docker Compose |

---

## Architecture

GRC Nexus is a modular Django project. Business logic lives in a service layer
(`*/services.py`), authorization lives in one place (`core/mixins.py`), and mutations ripple
through signals. Views stay thin.

```
grc-nexus/
├── app/
│   ├── config/            # settings (base/dev/prod), urls, wsgi
│   ├── core/              # users, departments, dashboard, search, notifications, email, escalations, media, mixins
│   ├── frameworks/        # frameworks, requirements, coverage, assessments
│   ├── assets/            # asset inventory + relationship explorer
│   ├── vendors/           # vendor register + risk assessments
│   ├── policies/          # policy library + lifecycle workflow
│   ├── controls/          # control library, effectiveness, evidence
│   ├── risks/             # register, appetite, treatments, exceptions, cascade engine
│   ├── vulnerabilities/   # CVE catalogue, findings, NVD/EPSS/KEV enrichment, cascade
│   ├── kris/              # key risk indicators + readings
│   ├── audits/            # audits, evidence, scoring, testing, findings, actions
│   ├── threatintel/       # ATT&CK matrix, actors, IOC feeds
│   ├── tickets/           # remediation tickets + alerting
│   ├── templates/         # shared + per-app templates
│   └── static/            # CSS design tokens, JS, brand assets
├── docs/                  # audit record and PDF previews
├── docker-compose.yml
├── .env.example
└── README.md
```

**The cascade, in one line:** `Asset → baseline risk → controls → residual score → appetite
breach → escalation`, and `Vulnerability finding → risk → treatment → remediation → auto-close`.

**Residual scoring model** (`risks/services.py`):

```
reduction_i = min(MAX_SINGLE_CONTROL_REDUCTION, effectiveness_ratio_i × type_weight_i) × CONTROL_CONFIDENCE
remaining   = Π (1 − reduction_i)
residual    = inherent × remaining          # clamped to 1–25 when inherent > 0
```

Control-type weights: preventive `1.0`, corrective `0.8`, detective `0.7`. Effectively-tested
controls reduce more; untested/ineffective controls reduce nothing. The residual never reaches
zero while a risk has any inherent score.

The entity relationships are in the bundled ER diagram:

![Entity-relationship diagram](er-diagram.drawio.png)

---

## Quick start

### Prerequisites
- **Docker Desktop** (with WSL 2 on Windows) — the only hard requirement
- **Git**

### 1. Clone

```bash
git clone https://github.com/SujalAdhikari-Hacker/GRC-Nexus.git
cd GRC-Nexus
```

### 2. Configure the environment

```bash
cp .env.example .env
```

The defaults work out of the box. Edit `.env` only if you want a custom `SECRET_KEY` or
different database credentials.

> **Important:** `SECRET_KEY` must **not** contain a `$` character — `docker compose`
> interpolates `$…` in `.env` files, which silently corrupts the key. Generate one with:
> `python -c "import secrets; print(secrets.token_urlsafe(64))"`

### 3. Build and start

```bash
docker compose up --build
```

The first build takes a few minutes. The `web` container waits for PostgreSQL, applies
migrations automatically, collects static files, then starts **gunicorn** (production settings)
on port `8000`.

### 4. Load demo data (optional but recommended)

In a second terminal:

```bash
docker compose exec web python manage.py seed_demo
docker compose exec web python manage.py createsuperuser
```

### 5. Open the app

| | |
|---|---|
| App | <http://localhost:8000> |
| Admin | <http://localhost:8000/admin> |

Seeded demo users all use the password **`demo1234`** (for example `it_hod`, `fin_hod`).

---

## Demo data

`seed_demo` is idempotent and creates a realistic starting point: departments, HOD/demo users,
asset categories and assets, vendors with assessments, policy categories and policies, controls,
risk categories, appetites and risks, plus the compliance frameworks and their requirements.

```bash
# Core demo dataset (departments, users, assets, vendors, policies, controls, risks, frameworks)
docker compose exec web python manage.py seed_demo

# Optional extras
docker compose exec web python manage.py seed_frameworks_extra   # additional frameworks
docker compose exec web python manage.py seed_kris               # key risk indicators + readings
docker compose exec web python manage.py seed_vulnerabilities    # sample CVE catalogue
docker compose exec web python manage.py populate_assessment_items

# Remove seeded/test data
docker compose exec web python manage.py clean_test_data
```

**Demo credentials:** every seeded user's password is `demo1234`. Use `createsuperuser` to make
your own admin, or sign in as a seeded HOD to see department scoping in action.

---

## Configuration

### Environment variables (`.env`)

| Variable | Purpose |
|---|---|
| `DJANGO_SETTINGS_MODULE` | `config.settings.prod` (container) or `config.settings.dev` (local) |
| `DEBUG` | `False` by default; set `True` only for local debugging |
| `SECRET_KEY` | Long random string, **no `$`** |
| `ALLOWED_HOSTS` | Comma-separated hostnames |
| `CSRF_TRUSTED_ORIGINS` | Comma-separated origins allowed to POST |
| `SECURE_SSL_REDIRECT`, `SESSION_COOKIE_SECURE`, `CSRF_COOKIE_SECURE`, `SECURE_HSTS_SECONDS` | TLS switches — relaxed for local HTTP, enable behind a TLS proxy |
| `SERVE_MEDIA` | Legacy flag; media is served through the scoped view regardless |
| `POSTGRES_DB`, `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_HOST`, `POSTGRES_PORT` | Database connection |
| `ABUSECH_AUTH_KEY`, `OTX_API_KEY` | Optional; enable ThreatFox / OTX IOC sync |
| `EMAIL_BACKEND`, `EMAIL_HOST`, `EMAIL_PORT`, `EMAIL_HOST_USER`, `EMAIL_HOST_PASSWORD`, `EMAIL_USE_TLS`, `EMAIL_USE_SSL` | Outbound mail. Defaults to the **console** backend (messages land in the app log); switch to the SMTP backend for real delivery |
| `DEFAULT_FROM_EMAIL` | `From:` header on every message |
| `SITE_BASE_URL` | Absolute base URL used to build the links inside emails (a cron job has no request) |
| `ESCALATION_FALLBACK_EMAILS` | Comma-separated catch-all for escalations that have no owner and no HOD. Empty drops them |
| `DIGEST_LOOKBACK_HOURS`, `ESCALATION_GRACE_DAYS`, `ESCALATION_WARN_DAYS` | Scheduling knobs: grace period before an item escalates, and how far ahead to warn about expiring exceptions/contracts |
| `TIME_ZONE` | IANA zone for business date maths (`localdate()`): overdue/renewal/SLA logic. Default `UTC`; the shipped `.env` uses `Asia/Kathmandu` |
| `LOGIN_MAX_FAILURES` / `LOGIN_FAILURE_WINDOW` / `LOGIN_LOCKOUT_SECONDS` | Sign-in throttling: failures allowed, the sliding window they count in (seconds) and the lockout duration (seconds). Defaults 5 / 900 / 900 |

See [`.env.example`](.env.example) for the annotated list.

### Settings layout

Configuration lives in `app/config/settings/`:

| Module | Purpose |
|---|---|
| `base.py` | Environment-neutral settings; values read via `python-decouple` |
| `dev.py` | Permissive local development (`DEBUG=True`, relaxed security) |
| `prod.py` | Hardened defaults (HTTPS, HSTS, secure cookies) as shipped in the container |

Select the module with `DJANGO_SETTINGS_MODULE`.

### Scheduled jobs (digests & escalations)

Two idempotent management commands do the outbound mail. Neither needs a request, so they are safe
to run from cron, a scheduler or a sidecar:

```bash
# Alert on overdue / expiring / breaching items (in-app + email). Run hourly or daily.
docker compose exec -T web python manage.py send_escalations
docker compose exec -T web python manage.py send_escalations --dry-run   # see what would fire

# Email each opted-in user a digest of what is outstanding for them.
docker compose exec -T web python manage.py send_email_digest
docker compose exec -T web python manage.py send_email_digest --force --user admin   # test one
```

`send_escalations` covers overdue tickets, findings and remediation actions; risks past their target
close date or beyond appetite capacity; expiring/expired risk exceptions; lapsed and soon-to-renew
vendor contracts; KRIs that have breached tolerance; vulnerabilities past their remediation SLA;
untriaged incidents past their severity triage SLA; and personal-data breaches whose GDPR 72-hour
notification window is closing (or has passed). Hour-based SLAs map onto the day-granularity scan,
so a critical incident raises roughly a day after its hour SLA is missed rather than at the exact
hour.
Each item is raised once in-app for the owning department and, when it is *newly* raised, email is
sent to the responsible user (owner, else the department HOD, else `ESCALATION_FALLBACK_EMAILS`).
Every alert carries a matching auto-clear rule, so it disappears the moment the underlying condition
is fixed — and will alert again if the problem comes back.

A sample crontab (inside the host, where the compose project lives):

```cron
15 * * * *  cd /srv/grc-nexus && docker compose exec -T web python manage.py send_escalations
0 7 * * *   cd /srv/grc-nexus && docker compose exec -T web python manage.py send_email_digest
```

---

## Common commands

```bash
docker compose logs -f web                                  # follow app logs
docker compose restart web                                  # after editing code (gunicorn does not hot-reload)
docker compose exec web python manage.py migrate
docker compose exec web python manage.py collectstatic --noinput
docker compose exec web python manage.py recompute_risk_scores   # re-derive residual scores
docker compose exec web python manage.py scan_for_alerts         # generate remediation tickets
docker compose exec web python manage.py sync_attack_data        # MITRE ATT&CK data
docker compose exec web python manage.py sync_recent_cves        # latest CVEs from NVD
docker compose exec web python manage.py send_escalations         # overdue/expiring items → notify + email
docker compose exec web python manage.py send_email_digest        # daily/weekly digest to opted-in users
docker compose exec web python manage.py test                    # run the test suite
docker compose down                                              # stop
docker compose down -v                                           # stop and wipe the database
```

> Editing code? The project is bind-mounted (`./app:/app`), so changes are picked up on
> `docker compose restart web` — gunicorn does not auto-reload.

---

## Testing

The suite covers the invariants the product depends on: risk-scoring maths and the non-zero
residual floor, residual-governed appetite breach detection, the treatment→risk sync, severity
banding, the risk/policy state machines, control evidence gating, the vulnerability→risk cascade,
vendor contract expiry derivation, object-level sharing (django-guardian) and department scoping,
the finding verification loop, approver-gated risk-exception approval, ticket linking, delete
authorization, the custom 403/404 pages, bulk actions and saved views, the authenticated media
view, CSV-injection guarding, export fidelity, the PDF watermark, and the email layer:
preference gating, digest scheduling windows, escalation detection/grace periods, notification
idempotency and the escalation auto-clear rules.

```bash
docker compose exec web python manage.py test
# Ran 120 tests — OK
```

---

## Security

- **Authorization is centralised** in `app/core/mixins.py` (`scope_queryset`, `user_can_access`,
  …). Views must never hand-roll department filtering.
- **Uploaded files are not public.** Evidence and policy documents are served through
  `core/media.py`, which requires a login and only serves a file when the user can see a record
  that references it. The raw `/media/` mount is removed. Path-traversal and symlink escapes are
  rejected.
- **CSV/Excel formula injection** is neutralised on export.
- **No secrets in the repo** — `.env`, `staticfiles/` and `media/` are git-ignored.
- Report any vulnerability privately (see [Contributing](#contributing)) rather than opening a
  public issue.

---

## Contributing

Contributions are welcome — bug reports, features, docs and tests.

1. **Fork** the repo and create a branch:
   ```bash
   git checkout -b feat/short-description
   ```
2. **Make your change.** Keep the existing patterns:
   - business logic in `*/services.py`, not in views or templates;
   - all authorization via `core/mixins.py`;
   - add a regression test under the relevant app's `tests.py`.
3. **Run the checks** before committing:
   ```bash
   docker compose exec web python manage.py check
   docker compose exec web python manage.py makemigrations --check --dry-run
   docker compose exec web python manage.py test
   ```
4. **Commit** with a clear message (imperative mood, e.g.
   `fix: cap residual risk at a non-zero floor`).
5. **Open a pull request** describing the change and how you verified it.

Attribution and a fuller contribution guide live in [CONTRIBUTORS.md](CONTRIBUTORS.md).

---

## Releases & versioning

GRC Nexus follows [Semantic Versioning](https://semver.org/). Releases are cut as annotated,
signed-off tags on `main`.

```bash
git tag -a v2.3.0 -m "GRC Nexus v2.3.0"
git push origin v2.3.0
gh release create v2.3.0 --title "GRC Nexus v2.3.0" --notes "See CHANGELOG"
```

Existing tags: `v1.0.0`, `v2.0.0`, `v2.1.0`, `v2.2.0`.

---

## Roadmap

The platform is under active development.

**Recently shipped**

- [x] Object-level permissions via `django-guardian`, with a per-record sharing panel
- [x] Audit finding → verification loop (a finding cannot be closed until it is verified)
- [x] Bulk actions on registers and per-user saved list views
- [x] Design-system cleanup — recurring inline styles moved to tokens/utility classes
- [x] Residual-governed appetite breach detection; treatment completes → risk closes
- [x] Vendor contract-expiry derivation; ticket linking; approver-gated risk exceptions
- [x] Custom 403/404 pages; delete actions; stray duplicate tree removed
- [x] Email digests and escalation notifications (scheduled `send_escalations` / `send_email_digest`)

**Planned**

- [ ] SSO / OIDC and MFA for enterprise deployments

---

## License

Released under the [MIT License](LICENSE).

---

## Acknowledgements

- **Sujal Adhikari** — Creator, architect and lead developer · [@SujalAdhikari-Hacker](https://github.com/SujalAdhikari-Hacker)
- Built with [Django](https://www.djangoproject.com/), [Bootstrap](https://getbootstrap.com/),
  [HTMX](https://htmx.org/), [Chart.js](https://www.chartjs.org/), [vis-network](https://visjs.github.io/vis-network/docs/network/),
  [WeasyPrint](https://weasyprint.org/) and [openpyxl](https://openpyxl.readthedocs.io/).
- Threat data from [NIST NVD](https://nvd.nist.gov/), [FIRST EPSS](https://www.first.org/epss/),
  [CISA KEV](https://www.cisa.gov/known-exploited-vulnerabilities-catalog) and
  [MITRE ATT&CK](https://attack.mitre.org/).

<div align="center"><sub>Built for people who take governance, risk and compliance seriously.</sub></div>
