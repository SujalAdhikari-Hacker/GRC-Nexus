# Changelog

All notable changes to GRC Nexus are recorded here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses
[Semantic Versioning](https://semver.org/).

## [Unreleased]

### Added

- **SLA clocks on findings and tickets** (`core/sla.py`). One ladder — 7, 14,
  30, 60 and 90 days — applies to audit findings and vulnerability findings by
  severity, and to tickets by priority (critical/high/medium/low). A blank due
  date is filled from the record's creation date on save; an explicit date is
  left alone. A finding or ticket is **breached** when its due date is before
  today and it is still open. Existing rows are backfilled by data migration,
  and lists and detail pages show the due date with a breached badge.
- **BIA and continuity gaps** (`assets`). Assets now carry RTO, RPO and MTPD in
  hours, links to the BCP and DRP policies, and the date continuity was last
  tested. A gap report checks every active High/Critical asset for a missing BIA
  value, an unlinked BCP or DRP, RTO longer than MTPD, or no test in the last 12
  months, and shows the gaps on the asset page. The asset register import and
  export now carries those fields too.
- **Hardened outbound-URL validator** (`core/safe_http.py`). Every outbound
  fetch must be http(s) with no embedded credentials, come from an allowlisted
  host, and resolve only to globally routable addresses. IPv4-mapped IPv6 is
  judged as IPv4, and CGNAT, documentation and benchmarking ranges are refused
  alongside loopback, private, link-local and multicast addresses. Invalid
  ports and unresolvable hosts are rejected before any request is made.

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
