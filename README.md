<div align="center">

<img src="docs/branding/grc-nexus-logo.png" alt="GRC Nexus — from assets to assurance" width="420">

# GRC Nexus

### Governance · Risk · Compliance — unified in one correlated graph.

**Where is our risk concentrated, and what are we doing about it?**

[![Python](https://img.shields.io/badge/python-3.11-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![Django](https://img.shields.io/badge/django-5.2-092E20?logo=django&logoColor=white)](https://www.djangoproject.com/)
[![PostgreSQL](https://img.shields.io/badge/postgresql-16-4169E1?logo=postgresql&logoColor=white)](https://www.postgresql.org/)
[![Docker](https://img.shields.io/badge/docker-compose-2496ED?logo=docker&logoColor=white)](https://docs.docker.com/compose/)
[![Tests](https://img.shields.io/badge/tests-293%20passing-brightgreen)](#testing)
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
- **Sign-in throttling** — failed logins are counted per account **and** per client IP, and the
  next attempt is refused for an exponentially increasing cool-down (never a permanent
  lockout). Configurable via `LOGIN_*` settings, no extra dependencies.

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
- **Announcements** — HODs and superadmins can write a message and send it to every department,
  a chosen set of departments, their own department, or specific people. It arrives in the bell,
  the notifications page and the badge like any other alert, and can be copied to email in the
  same step. Announcements are never auto-cleared; they stay until a recipient dismisses them.
- **Email digests & escalations** — a scheduled scan finds overdue tickets, findings and actions,
  risks past their target date or beyond capacity, expiring risk exceptions, lapsing vendor
  contracts, red KRIs and SLA-breached vulnerabilities, **untriaged incidents past their
  severity SLA and GDPR breach-notification deadlines**. Each item is raised in-app for the
  owning department and emailed to the responsible person (owner, else the department HOD). An
  item is only emailed once while it stays unresolved, so the job is safe to run hourly. Users
  choose Off / Daily / Weekly digests and per-event email toggles in Settings (including a
  dedicated incident toggle), and can send themselves a test email to confirm delivery.
  **SMTP is configured in the UI** (Settings → Email delivery), stored in the database and
  encrypted with `SECRET_KEY`, so no `.env` edit or restart is needed. High-signal notifications
  (risk escalations, overdue items, incident SLA/GDPR deadlines, KRI and vulnerability breaches,
  expiring contracts, policy approvals) are also emailed immediately. With no SMTP configured,
  the console backend keeps everything observable via `docker compose logs -f web`. See
  [`docs/EMAIL.md`](docs/EMAIL.md) for an Ubuntu/Postfix walkthrough for `@everest.local` and a
  two-minute Mailpit option.
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
| Backend | Django 5.2 LTS · Python 3.11 |
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

Generate the three secrets before the first start. `POSTGRES_PASSWORD` belongs to the
bootstrap/break-glass superuser; `DB_APP_PASSWORD` belongs to the non-superuser runtime role
that the application uses, so PostgreSQL row-level security actually applies to it.

```bash
python -c "import secrets; print(secrets.token_urlsafe(64))"   # SECRET_KEY
python -c "import secrets; print(secrets.token_urlsafe(32))"   # POSTGRES_PASSWORD
python -c "import secrets; print(secrets.token_urlsafe(32))"   # DB_APP_PASSWORD
```

On the first `docker compose up`, `db/init/01-app-role.sh` creates `grc_app` and makes it the
database owner. The web container then migrates as `grc_app`, so every business table is owned
by the runtime role and the `FORCE ROW LEVEL SECURITY` policies apply. An existing PostgreSQL
volume from before this change needs the same role created once; the SQL in that script is the
reference.

> **Important:** secrets must **not** contain a `$` character; `docker compose`
> interpolates `$...` in `.env` files, which silently corrupts the value. The
> commands above use URL-safe characters only.

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

`seed_demo` no longer ships a fixed password. Set `DEMO_PASSWORD` in `.env` before seeding, or let the command generate a strong one and print it once. Every seeded account is forced to change it at first sign-in.

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

**Demo credentials:** set `DEMO_PASSWORD` before running `seed_demo`, or use the generated password
printed once by the command. Seeded accounts are flagged for mandatory rotation on first sign-in.
Use `createsuperuser` to make your own admin, or sign in as a seeded HOD to see department scoping
in action.

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
| `USE_TLS` | One switch for the HTTPS posture: redirect, secure cookies, HSTS and proxy-header trust. See [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md) |
| `SECURE_SSL_REDIRECT`, `SESSION_COOKIE_SECURE`, `CSRF_COOKIE_SECURE`, `SECURE_HSTS_SECONDS` | Individual TLS overrides (default to `USE_TLS`) |
| `TRUSTED_PROXY_HOPS` | Number of reverse proxies in front, so rate limits key on the real client address |
| `POSTGRES_DB`, `POSTGRES_HOST`, `POSTGRES_PORT` | Database name and address |
| `POSTGRES_USER`, `POSTGRES_PASSWORD` | Bootstrap/break-glass superuser used by the PostgreSQL container, not the application |
| `DB_APP_USER`, `DB_APP_PASSWORD` | Non-superuser runtime role the application uses; row-level security applies to it |
| `ABUSECH_AUTH_KEY`, `OTX_API_KEY` | Optional; enable ThreatFox / OTX IOC sync |
| `EMAIL_BACKEND` | Fallback backend used only while SMTP is disabled in the UI (console by default). Real SMTP is configured at Settings → Email delivery |
| `DEFAULT_FROM_EMAIL` | Fallback `From:` header used while SMTP is disabled in the UI |
| `SITE_BASE_URL` | Absolute base URL used to build the links inside emails (a cron job has no request) |
| `ESCALATION_FALLBACK_EMAILS` | Comma-separated catch-all for escalations that have no owner and no HOD. Empty drops them |
| `DIGEST_LOOKBACK_HOURS`, `ESCALATION_GRACE_DAYS`, `ESCALATION_WARN_DAYS` | Scheduling knobs: grace period before an item escalates, and how far ahead to warn about expiring exceptions/contracts |
| `TIME_ZONE` | IANA zone for business date maths (`localdate()`): overdue/renewal/SLA logic. Default `UTC`; the shipped `.env` uses `Asia/Kathmandu` |
| `LOGIN_MAX_FAILURES` / `LOGIN_FAILURE_WINDOW` / `LOGIN_BACKOFF_*` | Sign-in throttling: account failures allowed, the sliding window they count in (seconds), and the exponential cool-down (base / ceiling / multiplier). Defaults 5 / 900 / 30 / 900 / 2. `LOGIN_IP_*` configures the separate per-address counter |

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

Configure outbound mail first: sign in as a superuser, open **Settings → Email delivery** and
either enable SMTP or leave the console backend in place. The full walkthrough — including a
local Ubuntu/Postfix server for `@everest.local` and a two-minute Mailpit alternative — is in
[`docs/EMAIL.md`](docs/EMAIL.md). Use **Send a test message** on that page to confirm delivery
before scheduling anything.

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
docker compose exec web python manage.py check_links             # crawl the UI as admin, report dead links
docker compose exec web python manage.py check_links --user it_hod --max 500   # crawl as another role
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
# Ran 293 tests - OK
```

The suite also includes a dedicated security regression module
(`app/core/test_security.py`): CSP/nonce and browser headers, CSRF
enforcement, SQL-injection and XSS payloads, upload magic-byte checks,
rate limiting, MFA enrolment/login/backup codes, forced password
rotation, log redaction, SSRF blocking, webhook HMAC/replay checks,
CORS allowlisting, source-map absence and database-level row-level
security.

---

## Security

The hardening pass is deliberately layered. No single control is trusted on its own.

- **Authorization is centralised** in `app/core/mixins.py` (`scope_queryset`,
  `user_can_access`, ...). Views must never hand-roll department filtering. Cross-department
  detail pages return 404, and related links render as plain text when the target is not
  accessible.
- **PostgreSQL row-level security (RLS)** is the database backstop. The application connects
  as `DB_APP_USER` (`grc_app`), a non-superuser role, and every department-owned business
  table has `FORCE ROW LEVEL SECURITY` with a `grc_dept_isolation` policy. Per-user MFA
  secrets are scoped to their owner as well. `RLSMiddleware` sets
  `app.bypass_rls=off`, `app.department_id` and `app.user_id` per request; the connection
  starts with bypass on for migrations and management commands. The policy also honours
  explicit control sharing, django-guardian object grants, notification recipients and
  policy audiences. `python manage.py enable_rls` re-applies the policies.
- **CSP with per-response nonces.** Inline event handlers were removed and replaced with
  `static/js/ui.js`; `script-src-attr 'none'`, `object-src 'none'` and
  `frame-ancestors 'none'` are enforced. `/admin/` gets the narrow exceptions Django admin
  needs.
- **CSRF and browser hardening.** Django's CSRF middleware is enabled, logout is POST-only,
  HTMX sends the CSRF header, and failures render a friendly page. Responses also set
  `X-Frame-Options: DENY`, `X-Content-Type-Options: nosniff`, COOP/CORP, a restrictive
  `Permissions-Policy` and `Referrer-Policy: same-origin`.
- **Same-origin CORS by default.** No permissive wildcard is configured. An explicit
  allowlist middleware only emits `Access-Control-Allow-Origin` for configured origins and
  never enables credentials.
- **Session authentication, not JWT.** There is no JWT issuer or verifier to misconfigure,
  and no access/refresh token is stored in `localStorage`. The only client storage is the
  non-sensitive theme preference.
- **MFA is opt-in.** Users can enrol a standard TOTP authenticator, receive hashed one-time
  backup codes, regenerate them, or disable MFA after re-entering their password and a valid
  code. `MFA_REQUIRED_FOR_STAFF` can enforce it for staff.
- **Password policy and rotation.** PBKDF2-SHA256 is explicit, the minimum length is 12,
  common/numeric/similarity validators run, and `User.must_change_password` forces a change
  before the rest of the app is reachable. `flag_default_passwords` flags accounts still on a
  known seeded password. `seed_demo` no longer ships a fixed password: use `DEMO_PASSWORD` or
  let it generate one, then rotate on first sign-in.
- **Rate limiting and exponential backoff.** Sign-in, password-change and MFA endpoints get
  a strict per-IP bucket; failed sign-ins are counted per account **and** per IP with an
  exponentially increasing cool-down (never a permanent lockout). Public reads and
  authenticated reads/writes use looser buckets. All thresholds are settings/env values and
  `429` responses carry `Retry-After`.
- **Strict input validation.** A transport middleware rejects over-long paths, query strings,
  form bodies, parameter names, control characters, unsupported POST content types and
  oversized uploads before a view runs. Views that read raw `request.GET`/`request.POST`
  values use typed helpers (`choice`, `integer`, `boolean`, `positive_int`, `search_query`)
  that reject unexpected types and values instead of coercing them. Model-backed forms remain
  the domain schema.
- **Upload validation.** Evidence, policy documents and attachments are checked by
  extension, filename and magic bytes (PDF, images, Office/ZIP, PCAP), with empty files,
  renamed executables and text files containing executable signatures rejected. Uploads are
  stored in a private media volume outside the static tree and served only through the
  login- and department-scoped media view. Non-image files download as attachments with
  `nosniff`, a sandbox CSP and `Cache-Control: private, no-store`, so an upload can never
  execute as same-origin code.
- **Generic errors, full server-side logs.** Custom `400`/`403`/`404`/`429`/`500` pages never
  include stack traces, file paths or raw database errors. `ErrorLoggingMiddleware` logs the
  full exception with a request id; the id is also returned in `X-Request-ID` for support.
- **SSRF-resistant outbound HTTP.** Threat-intelligence and vulnerability enrichment calls go
  through `core/safe_http.py`: HTTPS/HTTP only, host allowlist, DNS resolution checks against
  private/loopback/link-local/metadata addresses, no redirects and a response-size cap.
- **Webhook signatures.** `core/webhooks.py` provides HMAC-SHA256 signing/verification with a
  timestamp replay window and constant-time comparison. The project has no inbound webhook
  endpoints, so the helper is covered by tests rather than wired to a route.
- **Sensitive data is redacted from logs.** A logging filter masks passwords, tokens,
  cookies, API keys and `Authorization` values before they reach the console handler.
- **No source maps ship.** `collectstatic` output and the source tree contain no `.map` files,
  and a regression test fails if one appears.
- **Dependencies are pinned and current.** Django 5.2 LTS replaces the EOL 4.2 line; Pillow,
  certifi, brotli and the image build tools are upgraded. `pip-audit` is used to check the
  resolved environment, and frontend packages were checked against OSV.
- **CSV/Excel formula injection** is neutralised on export. **No secrets are tracked in the
  current tree** — `.env`, `staticfiles/`, `media/` and the local backup file are git-ignored.
  Run `python scripts/scan_secrets.py` before pushing; it fails on private keys and
  high-confidence token formats. Rotate any credential that was ever committed in an earlier
  revision, even if it has since been deleted.

Report any vulnerability privately (see [Contributing](#contributing)) rather than opening a
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
   python scripts/scan_secrets.py
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
git tag -a v3.1.0 -m "GRC Nexus v3.1.0"
git push origin v3.1.0
gh release create v3.1.0 --title "GRC Nexus v3.1.0" --notes-file CHANGELOG.md
```

Existing tags: `v1.0.0`, `v2.0.0`, `v2.1.0`, `v2.2.0`, `v3.0.0`, `v3.1.0`.

See [CHANGELOG.md](CHANGELOG.md) for what changed in each release.

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
