# Security operations

This document is the operator-facing companion to the security controls in the
codebase. It covers the knobs you are expected to tune, the checks to run before
a release, and the limits of each control.

## 1. Configuration and secrets

- **Never commit `.env`.** The runtime reads secrets from environment variables
  (`SECRET_KEY`, `POSTGRES_PASSWORD`, `DB_APP_PASSWORD`, optional threat-intel
  and SMTP keys). `.env.example` documents every supported key with safe
  placeholders.
- **Two database roles.** `POSTGRES_USER` is the bootstrap/break-glass
  superuser. The application connects as `DB_APP_USER` (`grc_app`), a
  non-superuser that owns the schema so `FORCE ROW LEVEL SECURITY` applies.
- **Rotate anything that was ever committed.** Deleting a key in a later commit
  does not remove it from git history. Generate a new value, update `.env`,
  restart the stack, and invalidate the old value at the provider.
- **Scan before pushing:**

  ```bash
  python scripts/scan_secrets.py
  ```

  The scanner checks git-tracked files for private keys and high-confidence
  token formats (AWS, GitHub, Slack, Google, Stripe, SendGrid) plus
  random-looking `key = "value"` assignments. It prints masked values only and
  exits non-zero on a finding. Use `--all` to scan the working tree, including
  files that are not tracked yet.

## 2. Authentication and rate limiting

Sign-in failures are counted per account **and** per client IP. Once a counter
passes its threshold the next attempt is refused for an exponentially
increasing cool-down, capped by `LOGIN_BACKOFF_MAX_SECONDS` /
`LOGIN_IP_BACKOFF_MAX_SECONDS`. There is no permanent lockout. A successful
sign-in clears the account counter only; the IP counter decays with
`LOGIN_FAILURE_WINDOW` so one valid account cannot reset credential-stuffing
protection for an address.

| Setting | Default | Purpose |
|---|---|---|
| `LOGIN_MAX_FAILURES` | 5 | Account failures before backoff |
| `LOGIN_FAILURE_WINDOW` | 900 | Counter lifetime (seconds) |
| `LOGIN_BACKOFF_BASE_SECONDS` | 30 | First cool-down |
| `LOGIN_BACKOFF_MAX_SECONDS` | 900 | Cool-down ceiling |
| `LOGIN_BACKOFF_MULTIPLIER` | 2 | Growth per extra failure |
| `LOGIN_IP_MAX_FAILURES` | 20 | IP failures before backoff |
| `LOGIN_IP_BACKOFF_BASE_SECONDS` | 60 | First IP cool-down |
| `LOGIN_IP_BACKOFF_MAX_SECONDS` | 3600 | IP cool-down ceiling |

Request buckets are configured with `RATE_LIMIT_*` (see `.env.example`).
Authentication routes use `RATE_LIMIT_AUTH` and exponential backoff; anonymous
traffic uses `RATE_LIMIT_PUBLIC`; signed-in reads/writes use
`RATE_LIMIT_READ`/`RATE_LIMIT_WRITE`. Buckets are keyed per user when signed in
and per IP otherwise. `429` responses include `Retry-After`.

> The default cache is per process. For a multi-worker or multi-node
> deployment, point `CACHES` at Redis so every worker shares the counters.

MFA is opt-in. Set `MFA_REQUIRED_FOR_STAFF=true` to force staff and superusers
to enrol. MFA codes use the same exponential model (`MFA_*` settings) and the
disable/regenerate endpoints require both the password and a valid code.

## 3. Input validation

Two layers apply:

1. **Transport** — `RequestValidationMiddleware` rejects over-long paths, query
   strings, form bodies, parameter names, control characters, unsupported POST
   content types and oversized uploads with a generic `400`.
2. **Domain** — Django forms validate model-backed input. Views that read raw
   `request.GET`/`request.POST` values use the typed helpers in
   `core/input_validation.py` (`choice`, `integer`, `boolean`, `positive_int`,
   `id_list`, `search_query`, `identifier`). These reject unexpected types and
   values instead of coercing them.

Limits are configurable with `INPUT_*` settings. They are deliberately generous
enough for normal use and small enough to stop memory/CPU probes.

## 4. Uploads

Allowed evidence extensions and magic-byte signatures live in
`core/validators.py`. Uploads are validated by the form, the model validator and
again when served.

- `MAX_EVIDENCE_UPLOAD_SIZE` (default 10 MB) and
  `MAX_EVIDENCE_FILENAME_LENGTH` (default 255) bound size and name length.
- Empty files, path traversal (`..`), NUL/control characters and executable
  signatures in text files are rejected.
- Files are stored in the private media volume, **not** under `static/`.
  `/media/` is served by `core.media.download_media`, which checks that the
  requesting user can see a record referencing the file.
- Images and PDFs may render inline. Everything else is forced to download as
  `application/octet-stream` with `X-Content-Type-Options: nosniff`, a
  `default-src 'none'; sandbox` CSP and `Cache-Control: private, no-store`.

Do not map `/media/` straight to a directory in a reverse proxy. That bypasses
the authorization check.

## 5. Errors and logging

Users see generic `400`, `403`, `404`, `429` and `500` pages. Stack traces,
internal paths and raw database errors are never rendered. `ErrorLoggingMiddleware`
logs the full exception with a request id, and `X-Request-ID` is returned to the
client. `SensitiveDataFilter` redacts passwords, tokens, cookies, API keys and
`Authorization` headers before log records reach the console handler.

## 6. Database row-level security

All department-owned business tables use `FORCE ROW LEVEL SECURITY` with a
`grc_dept_isolation` policy. `RLSMiddleware` sets `app.bypass_rls=off`,
`app.department_id` and `app.user_id` for every ordinary request, including
anonymous requests. The connection starts with bypass on for migrations and
management commands. Re-apply policies after a schema change with:

```bash
docker compose exec web python manage.py enable_rls
```

## 7. Dependency and release checks

```bash
docker compose exec -T web python manage.py check
docker compose exec -T web python manage.py makemigrations --check --dry-run
docker compose exec -T web python manage.py test
docker compose exec -T web pip-audit -r requirements.txt
docker compose exec -T web pip check
python scripts/scan_secrets.py
```

Frontend libraries are pinned with Subresource Integrity where they are loaded
from a CDN. Run an OSV or equivalent check when bumping them.

## 8. Reporting

Report vulnerabilities privately to the maintainers rather than opening a
public issue. Include the affected route, a minimal reproduction, and the
impact you believe it has.
