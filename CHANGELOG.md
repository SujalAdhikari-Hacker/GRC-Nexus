# Changelog

All notable changes to GRC Nexus are recorded here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses
[Semantic Versioning](https://semver.org/).

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
