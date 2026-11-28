# Changelog

All notable changes to GRC Nexus are recorded here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses
[Semantic Versioning](https://semver.org/).

## [Unreleased]

## [3.3.0] - 2026-11-28

Security hardening, RBAC/RLS completion, scanner & executive reporting automation, and 1-click governance workflows.

### Changed

- **UI/UX refresh.** Simplified layout density and introduced subtle, accessibility-aware micro-interactions (`brand.css`) with `prefers-reduced-motion` support across dashboards, tables, forms, and cards.
- **Repository hygiene cleanup.** Removed stray root-level app stubs (`assets/`, `frameworks/`, `policies/`), unused `app/vendors/cls` and seal leftovers, duplicate `DB relationship Diagram.png`, and tracked generated `docs/previews/*.pdf` artifacts.
- **Role-driven dashboard hub & control clarity.** Added **My Tasks Today** (pending policy attestations and assigned tickets) for every user, **Approvals & Attention Queue** for HODs/Superadmins, and `operational` / `effective` control counts on the Dashboard card (`core/views.py`, `dashboard.html`).
- **HOD/Staff group alignment & seed hygiene.** Stripped stray `admin` logentry permissions from `Department Staff` (aligned with `Department HODs` at 172 perms), aligned all HOD users (`sunita.magar`) to `Department HODs`, deduplicated seeded Operations `Employee Laptops`, removed leftover QA test incident, fixed `Critical patch SLA (7 days)` KRI direction + auto-cancelled its false ticket, aligned `CTL-BCP-001` status/lifecycle, and corrected seed typos (`AWS S3 Backup Bucket`, `SIEM alert tuning gaps`) (`core.0019`, `core.0022`).

### Fixed

- **Strict superuser-only Django Admin & RBAC UI alignment.** Restricted Django Admin (`/admin/`) to active superusers, removed `is_staff` from non-superuser forms/accounts (`core.0016`), hid admin links from non-superusers, aligned detail `Edit`/`Delete` buttons (`can_change` / `can_delete`) with backend permissions, and scoped non-superuser user dropdowns by department.
- **Forced password-rotation hardening.** Blocked reusing the current password on `/password-change/` (`NoReusePasswordChangeForm`) and added clear rotation instructions.
- **Incidents create/close validation & table layout.** Allowed department-less superusers to pick `owner_dept` on `POST /incidents/new/` (eliminating HTTP 500), enforced a mandatory `root_cause` whenever `status == 'closed'`, and added `text-nowrap` / horizontal table sizing on `/incidents/`.
- **Vendor assessment scale & overdue days.** Standardized all five `VendorAssessment` dimensions to `0–20` (summing to `100`) and added `Vendor.days_overdue` so non-overdue renewal dates never display negative overdue counts.
- **SoA KPIs, partial badges & all-N/A readiness.** Fixed `partially_covered` and `no_internal_control` summary counts on `/frameworks/soa/`, fixed the `</hh1>` tag in `soa_report.html`, added `Partial` badges on framework detail controls, and returned `None` (`N/A`) when all compliance assessment items are marked N/A.
- **Deletion cascade cleanup & baseline safety.** Auto-cancelled open alert tickets when linked records are deleted, deleted unassessed `'identified'` risks when their source `Finding` is deleted, and stopped finding-to-risk cascades from closing `"Unassessed risk"` baseline records.
- **Audit result choices & open finding consistency.** Trimmed `ControlTest.RESULT_CHOICES` to `pass`/`partial`/`fail` (`audits.0013`) and aligned `/audits/findings/` open count with `/audits/`.
- **`AnonymousUser` exclusion.** Added `core.models.real_users()` and form/view guards so `django-guardian`'s `AnonymousUser` sentinel is hidden from `/admin-ui/users/`, department counts, sharing UI/endpoints, and user dropdowns.
- **Search gaps, missing UI deletes & Settings/Policy polish.** Added `RSK-XXXX` code lookup in `/risks/` and `⌘K`, added scoped `AuditFinding` results in `⌘K`, fixed `userdate` Django format rendering and version labels, fixed Policy body help text, corrected `0–20` dimension bars on vendor assessment detail, and added HOD/superuser delete views/buttons for Vendors, Vendor Assessments, KRIs, and Vulnerability Findings.

### Added

- **Read-only org-wide oversight for Internal Audit & Compliance.** Added `Department.has_org_read_oversight` (`core.0017`, `core.0018`) enforced in both Python (`scope_queryset`) and PostgreSQL RLS (`grc_org_oversight_read`, while preserving per-user isolation on `core_usermfa` and `core_notification`).
- **CSV & JSON scanner output import** (`/vulnerabilities/import/`). Pure-Python ingestion supporting Nessus/OpenVAS/Qualys/generic CSV, flat/wrapped JSON arrays, Trivy JSON, and SARIF 2.1.0, strictly scoped to writable department assets (`vulnerabilities/scanner_import.py`).
- **Scheduled monthly executive PDF board-report pack** (`send_board_report`). Generates the WeasyPrint executive report headless (`render_pdf_bytes`), emails it with PDF attachment (`BOARD_REPORT_RECIPIENTS` / `OrganisationProfile`), logs a `ServiceRun`, and adds a superadmin `"Send now"` control in Settings (`core.0020`).
- **Sign-out-all-devices & admin session revocation.** Added `User.session_nonce` (`core.0021`), `User.revoke_sessions()`, `/settings/sign-out-all/`, and superadmin `/admin-ui/users/<pk>/revoke-sessions/`.
- **Role-based idle & 8-hour absolute session timeouts.** `SessionTimeoutMiddleware` enforces **30 min idle / 8 h absolute** for normal users and **15 min idle / 8 h absolute** for superadmins, with clear expiry notices and HTMX redirect support.
- **1-click lifecycle workflows & guided empty states.** Added 1-click workflow buttons across Policies (`/policies/<pk>/transition/`), Incidents progress stepper + `/incidents/<pk>/advance/` + root-cause Close modal, and Risks inline control linking + HOD approve/close (`/risks/<pk>/link-control/`, `/approve-close/`), plus curated MITRE ATT&CK baseline seeding (`sync_attack_data --seed-baseline`) and superadmin UI sync.
- **Formula transparency & score breakdowns.** Added inline `?` formula tooltips and expandable component breakdowns for Vulnerability composite scores, Residual Risk (`residual_score_breakdown`), Weighted Framework Coverage, and Vendor NIS2 Assurance.
- **SLA clocks on findings and tickets** (`core/sla.py`). One ladder — 7, 14, 30, 60 and 90 days — applies to audit findings and vulnerability findings by severity, and to tickets by priority, with breach tracking and migration backfill.
- **BIA and continuity gaps** (`assets`). Tracks RTO, RPO, MTPD, BCP/DRP links, and continuity tests, flagging missing/contradictory plans across High/Critical assets and supporting import/export.
- **Hardened outbound-URL validator** (`core/safe_http.py`). Enforces HTTPS-only, no credentials, host allowlist, and DNS resolution checks rejecting private, loopback, link-local, CGNAT, and IPv4-mapped IPv6 addresses.

## [3.2.0] - 2026-11-26

Feature release. Completes the first four items on the assurance roadmap and
makes every register importable.

### Added

- **Supplier assurance score** (`vendors/services.py`). Every vendor carries a
  0–100 score derived from five weighted inputs — certifications (25), contract
  clauses (30), last assessment (20), data access (15) and jurisdiction (10). An
  expired contract zeroes the contract component. The score is computed on read,
  so it cannot go stale, and the breakdown is shown on the vendor page and in
  admin.
- **NIS2 Article 23 clock** (`incidents/nis2.py`). Significant incidents show the
  three statutory deadlines — early warning (24 h), notification (72 h) and final
  report (30 days) — anchored on `detected_at`, with `pending`, `due_soon` (two
  hours out), `breached` and `submitted` states. A scheduled sweep raises one
  alert per phase, deduplicated.
- **Evidence checksums** (`audits.EvidenceVersion`). Every saved evidence file
  records its SHA-256 digest and size; any version can be downloaded, and the
  response carries `X-Checksum-SHA256` so a recipient can verify the bytes.
- **Service-run log** (`core.ServiceRun`, `core/service_runs.py`). Every scheduled
  management command records what ran, when, whether it succeeded and the counts
  it reported. Runs older than 90 days are pruned; dry runs are not recorded.
- **Import / Export** (`/data-exchange/`, "Import / Export" in the sidebar). One
  page covers twelve registers — assets, risks, risk treatments, vendors,
  policies, controls, audits, audit findings, tickets, incidents, vulnerabilities
  and vulnerability findings. Each offers a blank template plus Excel, CSV and
  PDF downloads and accepts `.xlsx` or `.csv` uploads. A row with an ID updates
  in place, a blank ID creates a record, blank cells leave stored values alone,
  and a bad row is reported by row number without blocking the rest. The page is
  HOD/superuser-only, and downloads and writes stay department-scoped.
- **NRB and Nepal digital/electronic act requirements** (`frameworks`). Adds the
  NRB Artificial Intelligence Guidelines, NRB Cyber Resilience Guidelines, NRB IT
  & Cyber Security Directives and the Nepal digital/electronic acts as selectable
  frameworks.
- **Cross-framework equivalent mappings** (`frameworks`). Mapping a control to
  one framework proposes its best equivalent in every other framework as an
  `intersects` mapping marked **Auto**, with a backfill command for existing data.

### Changed

- CSV exports include a UTF-8 BOM and CSV imports accept UTF-8 (with or without
  BOM) and Windows-1252, so a plain "Save as CSV" from Excel round-trips.
- Risk treatments and vulnerability findings are imported through the linked risk
  or asset, and a record can only be linked to a related record in the importer's
  own department.

## [3.1.1] - 2026-10-28

Patch release. Fixes a stacking-order defect in the layout.

### Fixed

- **Sticky cards painted over the top bar menus.** `.topbar` sat at
  `z-index: 5`, below Bootstrap's `.sticky-top` (`1020`), so the bell menu and
  the user menu were clipped by the sticky side card on form pages. The top bar
  now sits at `1030` — above sticky content, below the mobile drawer (`1050`),
  its backdrop (`1040`) and modals (`1055`).
- **Sticky side cards started underneath the top bar.** `.top-1rem` used a flat
  `top: 1rem`, which put the top of a sticky card behind the 56px top bar. It now
  offsets by `calc(var(--topbar-h) + 1rem)` so the card clears it.

## [3.1.0] - 2026-10-28

Feature release. Adds configurable email delivery and in-app announcements.

### Added

- **Email delivery configured in the UI** (`core.EmailSettings`,
  `core/email_config.py`). A superadmin sets host, port, encryption, credentials,
  timeout and the `From:` identity at **Settings → Email delivery**; the SMTP
  password is encrypted with `SECRET_KEY`. Changes take effect immediately — no
  `.env` edit and no container restart. A test button sends one message and
  reports how many the relay accepted.
- **Announcements** (`core/announcements.py`). HODs and superadmins write a
  message and send it to every department, a chosen set of departments, their own
  department, or specific people. One notification row is written per department,
  or one row addressed to a single recipient. The composer scopes the department
  and user lists by role and re-checks the audience before writing, so a HOD
  cannot reach another department by crafting a POST.
- **Optional email copy per announcement.** One message goes to everyone who can
  see the announcement, honouring each user's master email preference; it is
  skipped when SMTP is disabled and the in-app notification is still delivered.
- **Help page** now documents sending announcements and configuring email
  delivery, including troubleshooting.
- **`docs/EMAIL.md`**: Ubuntu/Postfix + Dovecot + Roundcube walkthrough for
  `@everest.local`, plus a two-minute Mailpit alternative.

### Changed

- `Notification.owner_dept` is nullable. A direct message has no owning
  department, so it is visible to the named recipient only and never to their
  whole department.
- `Notification` gained `body` and `sent_by`, both shown in the notifications
  list and the bell.
- A department-less user is no longer hidden from notifications addressed to them
  directly.
- Announcements are exempt from the auto-clear sweep (`MANUAL_KINDS`): they
  describe no record, so they stay until a recipient dismisses them.

## [3.0.0] - 2026-10-26

Security-focused major release. The application behaviour and UI are unchanged;
the deployment model, authentication hardening and input handling are not
backwards compatible, hence the major version bump.

### Added

- **Configurable rate limiting** (`core/rate_limit.py`): per-IP and per-user
  buckets for auth, public, search, media, read and write traffic, with
  `Retry-After` on `429`.
- **Exponential backoff for failed authentication.** Sign-in failures are
  counted per account and per client IP; MFA verification has its own counter.
  There is no permanent lockout.
- **Strict input validation.** `RequestValidationMiddleware` rejects over-long
  paths, query strings and form bodies, invalid parameter names, control
  characters, unsupported content types and oversized uploads with a generic
  `400` before a view runs. `core/input_validation.py` provides typed helpers
  used by every view that reads raw `request.GET`/`request.POST`.
- **Upload hardening.** Model-level validators on audit evidence, control
  evidence and policy documents: extension allowlist, filename limits, magic
  bytes, executable-content detection, empty-file rejection.
- **Authorised media serving.** `/media/` is served by `core.media`, which
  checks that the signed-in user can see a record referencing the file. Files
  are served with `nosniff`, a sandbox CSP and `Cache-Control: private, no-store`.
- **Request IDs and generic error pages** (`400`, `403`, `404`, `429`, `500`)
  with full exception detail logged server-side only.
- **PostgreSQL row-level security.** Split roles (`POSTGRES_USER` for
  bootstrap, `DB_APP_USER`/`grc_app` at runtime), `FORCE ROW LEVEL SECURITY` on
  department-owned tables, and an `enable_rls` management command.
- **MFA (TOTP)** with hashed backup codes, opt-in per user, optional enforcement
  for staff.
- **Secret scanner** (`scripts/scan_secrets.py`) with a `--history` mode for
  pre-publication checks, plus a CI workflow that runs it on every push.
- **Hardened `.gitignore`** covering `.env` variants, TLS keys, database dumps,
  backups, logs and caches.
- **Deployment guide** (`docs/DEPLOYMENT.md`) and example Caddy/nginx configs
  under `deploy/`.
- **`USE_TLS` switch** for the HTTPS posture, plus `TRUSTED_PROXY_HOPS` so rate
  limits key on the real client behind a proxy.

### Changed

- `manage.py check --deploy` is clean with `USE_TLS=true`; the local HTTP stack
  intentionally reports the four transport warnings.
- Media is always served through the scoped view; the unused `SERVE_MEDIA`
  setting was removed.
- `SECURE_HSTS_PRELOAD` follows `USE_TLS` (the header is harmless on its own;
  submitting to the preload list remains a separate, deliberate step).
- Vulnerability enrichment failures return a generic message and log the
  exception instead of echoing it to the user.
- Test suite grew from 262 to 293 tests.

### Fixed

- Integer-valued list filters (vendor tier, IOC confidence, action-item
  priority) rejected every valid value because they were compared against
  string choice sets.
- 400/500 pages no longer fail when a bad `Host` header is rejected before
  `AuthenticationMiddleware` runs.
- `U+FFFD` replacement characters in `brand.css` and the policy detail template.

### Security

- CSP with per-response nonces, no inline event handlers; a looser policy only
  for `/admin/`.
- CSRF protection on every state-changing route, including sign-out.
- SSRF-safe outbound HTTP (`core.safe_http`) with private-address blocking.
- HMAC-SHA256 webhook helpers with replay protection (no inbound routes).
- Log redaction for passwords, tokens, cookies and `Authorization` headers.
- CSV/Excel formula-injection neutralisation on export.

## [2.2.0]

- Object-level permissions via `django-guardian` and a per-record sharing panel.
- Audit finding verification loop; bulk actions; saved list views.
- Incident register, policy attestation, asset dependencies, change log,
  statement of applicability.
- Sign-in throttling, accessibility pass, design-system cleanup.

## [2.1.0]

- Correlation engine, cascade scoring, risk appetite and treatment workflows.

## [2.0.0]

- Department-scoped RBAC, PostgreSQL backend, Docker Compose stack.

## [1.0.0]

- Initial public release: assets, risks, controls, policies, vendors,
  frameworks, audits, vulnerabilities, KRIs.
