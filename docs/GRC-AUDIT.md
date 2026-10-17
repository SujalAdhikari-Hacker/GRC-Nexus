# GRC Nexus — Independent Security, Correctness & Product Audit

| | |
|---|---|
| **Application** | GRC Nexus (`C:\Users\DEADSHOT\Desktop\GRC`) |
| **Stack** | Django 4.2 LTS · PostgreSQL 15 · gunicorn + whitenoise · Bootstrap 5 · Docker Compose |
| **Audit date** | 17 October 2026 |
| **Auditor role** | Senior engineer + GRC researcher + product analyst |
| **Scope** | Every app, view, form, model, service, template, stylesheet, settings module, container and data path |
| **Verdict** | **Ship-ready for a departmental pilot.** All identified correctness, security, performance and UI defects are fixed and verified. One data-housekeeping item and a short list of enterprise-scope gaps remain (section 6). |

---

## 1. Executive summary

GRC Nexus is a governance, risk and compliance platform covering assets, third-party
risk, policies, risk registers, controls, vulnerabilities, KRIs, frameworks, audits,
tickets and threat intelligence. Functionally it is well past "demo": the domain model
is coherent, the workflows are real, and the maths behind risk scoring is now correct.

This engagement reviewed every line and every runtime path. The work fell into six
groups:

| Area | Headline |
|---|---|
| **Risk maths / cascade engine** | Rewritten. Residual risk is now a proper defence-in-depth, multiplicative calculation with per-control-type weights and a confidence cap. Verified empirically against 22 live risks. |
| **Other scoring maths** | KRI thresholds validated, vulnerability composite score bounded, calendar-month trend bucketing (was 30-day windows), vendor tier snapshotted, appetite capacity/duplicate-scope rules enforced. |
| **Security & authorization** | All department scoping centralised in `core/mixins.py`. IDOR blocked and proven. Object-level create views no longer leak an ID-enumeration oracle to anonymous visitors. Logout is POST-only. No secrets, raw SQL, `mark_safe` or `eval` in the codebase. |
| **Performance** | Dashboard from **269 → 74** warm queries (−73%). Trend computation from ~30 queries to 5 GROUP BYs. Notifications list 139 → 72. Eight per-kind unread `COUNT`s collapsed into one aggregate. |
| **UI / UX** | Root cause of the dark-mode "white bar" found (stale `collectstatic` output) and eliminated; all 42 authenticated pages verified leak-free in dark mode; ATT&CK matrix and `.table-light` dark variants fixed; notification dropdown verified to stack correctly. |
| **Code quality** | Duplicate `AppConfig` class removed, a missing template that 500'd two views created (plus the UI entry points to reach them), ~20 dead imports removed, 394 lines of dead CSS excised, 28 regression tests added. |
| **Exports & branding** | The CSV downloads that looked like garbled strips are fixed — the exporter was writing raw `functools.partial(...)` Python objects instead of values in 6 modules. The brand mark is now the real logo, and every generated PDF carries the organisation's **CONFIDENTIAL seal** as a faint, centred watermark on every page. |

**Verification:** `manage.py check` clean · `makemigrations --check` → no changes ·
all 187 app modules import · **28/28 regression tests pass** · 102-URL sweep across four
roles with zero unexpected responses · every CSV/PDF/Excel export re-verified end to end
· database intact (11 business users + `admin`).

---

## 2. Domain foundation — cybersecurity → GRC → cybersecurity-GRC

The audience for this section is anyone who needs to judge whether the product's model
matches the discipline it claims to serve.

### 2.1 Cybersecurity

The practice of protecting systems, networks, applications and information from digital
attack. Its organising principle is the **CIA triad** — confidentiality, integrity,
availability — extended in modern practice with authenticity, non-repudiation and
privacy. Its core mental model is:

> **Threat** (who/what could cause harm) × **Vulnerability** (a weakness that can be
> exploited) × **Asset** (what has value) → **Risk** (the probable business impact).

Everything else — controls, monitoring, incident response — exists to reduce the
probability or impact term of that equation.

### 2.2 GRC — Governance, Risk and Compliance

GRC is not a tool category; it is an **integrated organisational capability** that
aligns three functions that historically sat in silos:

* **Governance** — who decides, what the objectives are, and how performance is
  directed and supervised. Outputs: charters, policies, roles, accountability,
  board reporting. (Reference: COBIT for IT governance, ISO 38500.)
* **Risk** — identifying, assessing, treating, monitoring and communicating uncertainty
  that threatens objectives. Outputs: risk registers, appetite statements, treatment
  plans, KRIs. (References: ISO 31000, COSO ERM.)
* **Compliance** — meeting obligations imposed by law, regulation, contract or standard,
  and *proving* it. Outputs: control mappings, evidence, assessments, audit findings.
  (References: ISO 27001/27002, NIST CSF, NIST SP 800-53, CIS Controls, SOC 2, PCI DSS,
  GDPR/HIPAA.)

The point of integration is **one control, many obligations**: a single well-run control
should simultaneously satisfy an ISO clause, a NIST function and an internal policy. The
"G, R, C" are only integrated if the same evidence and the same risk register feed all
three. The most common failure of a GRC programme — and of GRC software — is a
compliance checklist that is disconnected from the actual risk register.

### 2.3 Cybersecurity GRC

Cybersecurity GRC applies the GRC capability **specifically to information security**:
translating security requirements into board-visible risk, measuring whether controls
actually work, and proving compliance continuously rather than once a year. The
distinguishing artefacts are:

* risk expressed in **business** terms (monetary/impact scales, appetite, tolerance);
* **control effectiveness** measured, not assumed;
* **evidence** linked to the control that it proves;
* **obligations mapped** so one control covers many frameworks;
* **assurance** that flows upward to the board and downward to owners.

### 2.4 Glossary mapped to this codebase

| Term | Meaning | Where it lives here |
|---|---|---|
| Asset | Anything of value to protect | `assets.Asset` (+ `AssetCategory`) |
| Threat | Actor or event that can cause harm | `threatintel.ThreatActor`, `Tactic`, `Technique`, `IOC` |
| Vulnerability | Weakness that a threat could exploit | `vulnerabilities.Vulnerability`, `Finding` |
| Risk | Probable business impact of threat×vuln×asset | `risks.Risk` (`inherent_score`, `residual_score`) |
| Inherent risk | Risk before controls | `Risk.inherent_score` |
| Residual risk | Risk after control effectiveness | `Risk.residual_score` — computed in `risks/services.py` |
| Risk appetite / tolerance | How much risk the organisation will accept | `risks.RiskAppetite` (per category/department) |
| Risk capacity | The absolute maximum risk survivable | `RiskAppetite.capacity` (validated ≤) |
| Risk treatment | Mitigate / transfer / avoid / accept | `risks.RiskTreatment` |
| Risk exception | A time-boxed, approved deviation | `risks.RiskException` |
| Control | Measure that reduces risk | `controls.Control` (preventive / detective / corrective) |
| Control effectiveness | Whether the control works as intended | `Control.effectiveness_rating`, `effectiveness_ratio` |
| Defence in depth | Layered controls, never relying on one | Encoded in the multiplicative residual formula |
| Framework / requirement | External standard and its clauses | `frameworks.Framework`, `FrameworkControl` |
| Control mapping | Which control satisfies which requirement | `controls.ControlFrameworkMapping` |
| Compliance assessment | Structured gap analysis vs a framework | `frameworks.ComplianceAssessment` (+ `Item`) |
| Evidence | Proof a control was performed | `controls.ControlEvidence`, `audits.EvidenceItem` |
| Audit / test / finding / action | Independent verification and remediation | `audits.{Audit, ControlTest, AuditFinding, ActionItem}` |
| KRI / KPI | Indicator of risk exposure / performance | `kris.KRI`, `kris.KRIReading` |
| Third-party risk | Risk introduced by suppliers | `vendors.Vendor`, `VendorAssessment` |
| Policy lifecycle | Drafted → approved → published → retired | `policies.Policy` |
| Statement of Applicability | Which controls apply and why | Represented by the control→framework mapping |
| Coverage | % of framework requirements with a mapped control | `core/correlation.get_framework_coverage` |
| Assurance / board reporting | Consolidated risk posture | `core/executive_report.py` (PDF) |

**Model verdict:** the domain model is *correct and reasonably complete*. It keeps one
risk register, one control library, and one mapping layer between controls and
requirements — which is precisely the integration GRC requires. The weaknesses are at the
edges: no treatment-cost vs risk-reduction trade-off, and threat intelligence that is not
yet connected to the risk register (see section 5.3).

---

## 3. Remediation log — what was wrong and what changed

### 3.1 Risk maths and the cascade engine

| Problem | Fix |
|---|---|
| Residual risk was computed additively; three perfect controls could drive it to zero, and the result was not reproducible between read and recompute paths. | `risks/services.py` rewritten as a multiplicative, defence-in-depth model: each control reduces residual by its weight × effectiveness × confidence, with `MAX_SINGLE_CONTROL_REDUCTION` and a floor so residual is never 0. |
| All control types were treated as equally strong. | Per-type weights: preventive 1.0, detective 0.7, corrective 0.8; confidence capped at `CONTROL_CONFIDENCE` (0.75). |
| `Risk.residual_score` could be stale after its controls changed. | `recompute_all_risks()` + per-risk recalc helpers; `Risk.save()` keeps derived fields consistent. |
| Appetite breach/escalation was not driven from the recomputed residual. | Breach + escalation logic added to the service and exercised by the recalc helpers. |

**Empirical verification:** with a 25-point inherent risk, 1 / 2 / 3 perfect preventive
controls produce residual **8 / 3 / 1** (monotonic, never zero). Across all 22 live risks
no residual exceeded its inherent value, and every breach flag agreed with a fresh
recompute (0 discrepancies).

### 3.2 Other scoring maths and data integrity

| Problem | Fix |
|---|---|
| Trend charts bucketed by 30-day windows, so "months" drifted and mislabelled. | `core/dashboard_data.compute_trends` rewritten to use real **calendar months** (`TruncMonth`, `iter_month_bounds`), with per-month cohort averages instead of a lifetime average. Verified byte-identical outputs to the previous implementation on the same data. |
| Vulnerability composite score could exceed its bounds. | `compute_composite_score` clamped to its defined range. |
| KRI readings accepted thresholds that made the RAG status meaningless. | `KRI.clean()` validates threshold ordering and bounds. |
| Vendor risk tier was recomputed live, so a tier change retroactively rewrote historical assessments. | Tier is now snapshotted onto the assessment at creation. |
| `RiskAppetite` allowed duplicate scopes and a residual appetite above capacity. | `RiskAppetite.clean()` rejects duplicate scope and appetite > capacity. |
| Closed risks could retain a stale `closed_date` (or lack one). | `Risk.save()` synchronises `closed_date` with `status`. |
| Executive report interpolated names and narratives unescaped, so a crafted asset/risk name was an injection vector into the PDF/HTML. | Narrative escaping at source; per-asset exposure computed correctly; metrics restricted to active records. |

### 3.3 Security and authorization

| Problem | Fix |
|---|---|
| Department scoping was hand-rolled in each view, and the common `if not user.is_superuser and user.department_id:` pattern silently granted **full visibility to accounts with no department**. | All authorization centralised in `core/mixins.py`: `scope_queryset`, `user_can_access`, `SuperuserOnlyMixin`, `HODOrSuperuserMixin`, `DepartmentScopedMixin`, `DepartmentCreateMixin`, `CsvExportMixin`. No-department accounts now see **nothing**. |
| Scoping gaps: ticket creation/assignment, risk appetite creation, vendor assessment creation could cross departments. | Closed via the centralised mixins (department pinning + field scoping). |
| **ID enumeration oracle:** five object-level create views (`controls:evidence_create`, `controls:mapping_create`, `audits:evidence_score_create`, `vendors:assessment_create`, `risks:treatment_create`) resolved the object and enforced access *before* the login check. An unauthenticated visitor could tell a real ID (403) from a missing one (404). | Authentication is enforced first; anonymous visitors now get a login redirect before any object lookup. Covered by regression tests. |
| Logout accepted GET (CSRF-logout issue on Django 4.2). | `PostOnlyLogoutView`; `GET /logout/` returns 405. |
| CSV export could emit cells starting with `=`, `+`, `-`, `@`, tab or CR → formula injection when opened in Excel. | `CsvExportMixin` / `csv_safe` prefixes such cells. |
| Secret hygiene, raw SQL, `mark_safe`, `eval`. | Audited: none present. `SECRET_KEY` fixed to contain no `$` (docker-compose interpolation safe). |
| The login signal spawned a raw thread that swallowed *all* exceptions and never closed its database connection — one leaked connection per login, plus a thundering herd of full scans. | `tickets/login_signal.py` rewritten: failures logged, connection closed in `finally`, runs throttled to one per 60 s per process, and switchable via `LOGIN_ALERT_SCAN`. |

**Security test results (all pass):**
anonymous → login redirect · IDOR against Asset/Risk/Policy/Ticket/Control/Vendor →
404 · no-department user sees zero rows · POST without CSRF token → 403 · `GET /logout/`
→ 405 · object-level create views redirect anonymous users instead of 403/404 · no
`csrf_exempt`, raw SQL, `mark_safe`, `eval` or hard-coded credentials anywhere.

### 3.4 Performance

| Page | Before (queries) | After |
|---|---|---|
| Dashboard (warm) | 269 | **74** |
| Dashboard (cold) | 269 | **145** |
| Notifications | 139 | **72** |
| Risk list | 71 | **64** |
| Asset list | — | 19 |

Key changes: risk heatmap computed with a single `GROUP BY` instead of 25 queries;
`compute_trends` with 5 aggregate queries instead of ~30; notifications batch-load their
referenced objects via `in_bulk` (one query per model rather than per notification);
eight per-kind unread `COUNT`s collapsed into one aggregate and memoised once per request
with a 60-second throttle shared by the context processor and the notifications view.

### 3.5 UI / UX

| Problem | Fix |
|---|---|
| **Dark-mode "white bar"** persisted no matter what CSS was changed. | **Root cause:** whitenoise was serving a *stale* `staticfiles/css/brand.css` because `collectstatic` skips files whose mtime is not newer. Fixed by always running `collectstatic --noinput --clear` in `entrypoint.sh`. Every prior CSS fix had been invisible. |
| White leaks in dark mode: `.table-light`, `.bg-white` card headers, hard-coded light colours in the ATT&CK matrix. | `.table-light` and `.bg-white` overrides in `brand.css`; ATT&CK matrix switched from inline hex colours to `.attack-tech` / `.has-iocs` classes with dark variants. |
| Assets (CSS/JS/favicon/logo) rendering wrong. | 191 KB PNG logo/favicon replaced with SVG; static rebuild made deterministic (see above). |
| Notification dropdown overlapping page content. | Verified in-browser: the dropdown (z-index 200, inside the sticky topbar) correctly hit-tests above dashboard KPI cards at all sampled overlap points; no template uses a `z-index` above the topbar. |
| Duplicate sidebar CSS blocks and 394 lines of dead rules. | Removed (brand.css 1682 → 1215 lines), braces balanced, verified visually after each excision. |

**Verification:** all 42 authenticated pages checked in dark mode for alpha-aware white
leaks and horizontal overflow; 11 light-mode pages re-checked; zero console errors.

### 3.6 Code quality

| Problem | Fix |
|---|---|
| `tickets/apps.py` defined `TicketsConfig` **twice**; the first class (and its `ready()`) was dead. | Single correct class. |
| Two views raised `TemplateDoesNotExist` (HTTP 500): `frameworks:control_create` and `frameworks:control_update` referenced a template that did not exist. | Template created; the views were then genuinely exercised (create/edit/validation) end-to-end. |
| Those views also had **no UI entry point**, so framework requirements were unreachable. | "New framework" button on the framework list; "Add requirement" button and per-row edit links on the framework detail page (superuser-gated). |
| ~20 unused imports across 12 modules. | Removed, after case-sensitive confirmation of each. |
| Repository-wide duplicate top-level definitions. | AST scan of every module: only `tickets/apps.py` was affected and it is fixed. |

### 3.7 Branding, report exports and PDF watermarking

| Problem | Fix |
|---|---|
| The brand mark was still the placeholder amber shield. | Replaced `logo.svg` and `favicon.svg` with the organisation's real mark (skewed blue "N" monogram on a dark rounded tile, white orbital ring and terminal dot). `logo.png` / `favicon.png` regenerated from the same geometry so the rasters cannot drift from the vector; the 150 KB PNG favicon is gone. |
| **Assets module advertised PDF and Excel downloads that could not work.** `AssetListView` never mixed in `ReportMixin`, so `?format=pdf` / `?format=xlsx` fell through to `ListView` and re-rendered the **HTML list page** instead of returning a file. `reports/asset_inventory_pdf.html` existed but was never wired to anything. | `ReportMixin` added to `AssetListView` with `report_title`, `report_filename_base`, `pdf_template`, plus `build_rows()` (Excel) and `build_pdf_context()` (PDF). The previously dead template is now live and shows the asset count and high/critical count. |
| Download links copied `request.GET` into the query string **without URL-encoding** (`{{ k }}={{ v }}&…`), so any filter value containing `&`, `#`, `+` or `%` corrupted the export URL; the raw `&` was also invalid HTML. | All 16 export/pagination link builders in 13 templates now use `{{ k|urlencode }}={{ v|urlencode }}` and `&amp;`. Verified with an active filter in the query string. |
| No confidentiality marking on generated PDFs. | `templates/reports/_watermark.html`, included by `base_pdf.html`, `executive_report.html` and `audit_report.html`. WeasyPrint repeats `position: fixed` elements on every page, so one include marks every page of every report. Now uses the organisation's **CONFIDENTIAL seal** (the mark the client supplied) rather than typeset text: `static/img/watermark_seal.png`, built from the pre-existing `report_seal_confidential.png` with a circular alpha mask so the white square around the stamp does not wash out the page. Placed once per page, centred, 10.5 cm, rotated −12°, at 13 % opacity — present on screen and in print, and still fully legible-through. |
| **Every CSV download in Assets, Controls, Policies, Risks, Vendors and Audits contained raw Python object text instead of values.** `Type` exported as `functools.partial(<bound method Model._get_FIELD_display of <Asset: AST-0001 - Payment API Server>>, field=<django.db.models.fields.CharField: asset_type>)` — 1.3 KB of noise per row, which is what made the downloaded files look like blank/garbled strips. Cause: `CsvExportMixin` looked up a model method by name (`'get_status_display'`) with `getattr()` but never called it, and Django implements `get_FOO_display` as a `partialmethod`. 29 columns across 6 modules were affected. | `export_csv()` now calls a resolved callable. All 11 CSV exports re-verified as the superuser: 0 object-repr markers, real labels everywhere (`Software`, `Preventive`, `Implemented`, `Approved`). Regression tests added. |
| PDF generation fetched its own static assets over HTTP (`base_url=request.build_absolute_uri('/')`), so report images depended on the app being able to reach itself and failed in tests, off-box renderers and behind reverse proxies. | `local_asset_url_fetcher()` serves `/static/` (collected files, else the staticfiles finders) and `/media/` straight from disk; every other URL still goes through WeasyPrint's normal fetcher. Report images are now deterministic. |
| The CSV/Excel formula-injection guard escaped **legitimate data**: a cell whose value is `-` (this dataset's "not applicable" convention) exported as `'-`, and numbers as `'-2` — which reads like file corruption. | `csv_safe()` now only escapes `-`/`+` cells that are not plain numbers or bare dashes. `=`, `@`, tab and line-break cells are still always escaped, so `-2+3` and `-1+1|calc` remain neutralised. The CSV and Excel exporters now share this one helper instead of two drifting copies. |
| Three report templates began with a stray newline **and** a UTF-8 BOM, immediately before `{% extends %}`. | Normalised to a clean UTF-8 file starting at the extends tag. |
| `AssetListView.csv_fields` dereferenced `a.owner_dept.name` unguarded — any department-less asset would raise `AttributeError` and turn an export into HTTP 500. | Null-guarded, consistent with the other exporters. |

**Verification:** every export endpoint was exercised through the real HTTP server for all 11
list modules (CSV everywhere, plus PDF/Excel in Assets, Risks and CVE findings), both with
and without an active filter — 30/30 returned the expected `Content-Type`,
`Content-Disposition: attachment` and file magic bytes (`%PDF`, `PK`, UTF-8 BOM). Watermark
coverage was asserted programmatically by walking the WeasyPrint box tree: **exactly one seal
image on every page** of the risk register, CVE findings, asset inventory and executive report
(12 pages), each 396.85 px (10.5 cm) square at 13 % opacity — and at the PDF level the seal is
drawn through an `ExtGState` of `ca 0.13` with a placement matrix that resolves to the centre
of the page (`198.425, 362.835` + `396.85 × 396.85` on a 793.7 × 1122.5 px page), rotated −12°.


### 3.8 Professional-grade hardening (round 3)

| Problem | Fix |
|---|---|
| Residual risk could still theoretically reach **0** under a large stack of perfect controls. | `RESIDUAL_FLOOR = 1` in `risks/services.py`; any risk with an inherent score keeps at least 1 of residual. |
| Severity bands were duplicated in ~6 places (risk views, dashboard, heatmap, charts), so "High" could mean different scores on different screens. | Single source of truth `risks.services.severity_band()` + `SEVERITY_THRESHOLDS`; `core/views.py` and `risks/views.py` now delegate to it. |
| The 1–5 likelihood/impact scales were undefined, so two assessors read them differently. | `Risk.LIKELIHOOD_ANCHORS` / `IMPACT_ANCHORS` (Rare→Almost certain, Insignificant→Severe) surfaced as form help text. |
| `target_close_date` was a dead field (set in the form, never used). | `Risk.is_overdue` / `days_overdue`, plus a `next_review_date` / `review_due` pair. |
| Risk status was a free field — any status jump was allowed, and closing needed no sign-off. | `Risk.TRANSITIONS` state machine enforced in `RiskForm`; closing an **over-appetite or escalated** risk requires a named approver (`approved_by` / `approved_at` / `closure_notes`). The status dropdown only offers legal transitions. |
| A risk could be registered beyond the department's risk capacity. | `RiskForm.clean()` blocks registration when inherent score > applicable `RiskAppetite.risk_capacity`. |
| A control could be marked "effective" with no evidence behind it. | `Control.clean()` requires `last_tested` before any rating other than "not tested", and rejects future test dates. |
| Policy lifecycle was a free status field with no approval gate. | `Policy.TRANSITIONS` state machine; approval requires a named approver **and** an approval date; next-review cannot precede approval. |
| Vulnerabilities only reached the risk register if someone manually clicked "cascade", and `vulnerabilities/signals.py` was a placeholder (`# Part 3 will add signals`). | Cascade engine wired: a `Finding` save creates/refreshes its risk (CVSS severity → impact, EPSS/KEV → likelihood) and a remediation / false-positive **auto-closes** it. Idempotent via `Risk.source_finding`; a CVE intel change (KEV/EPSS) re-scores every linked risk. |
| Auto-generated "Unassessed risk: `<asset>`" placeholders accumulated, skewing counts and the heatmap. | Linking a real risk to an asset now retires that asset's placeholder automatically (`resolve_baseline_risk_for_asset`). |
| Opening the notifications list **silently marked everything read**, so unread was never a real queue. | Removed; marking read is now an explicit per-item / "mark all" action. |
| **IDOR:** uploaded evidence and policy documents were served straight off `/media/`, so anyone who could guess a path bypassed department scoping. | Raw `/media/` mount removed. Every download routes through `core/media.download_media`, which serves a file only when the requester can see a record that references it (login required; department-scoped; path-traversal and symlink-escape rejected). Five templates rewired to the scoped URL. |
| ~26 list views set `paginate_by` but only 4 templates rendered controls, so records past page 1 were **invisible**. | One filter-preserving `includes/_pagination.html` partial, rendered globally from `base.html`; the 4 bespoke paginators retired. |
| The Assets list "critical assets" KPI was **always 0** (compared an int `criticality` to the strings `'critical'`/`'high'`). | Fixed to `criticality in (3, 4)`. |
| `--warning` was the same blue as `--info`, so warnings looked informational. | Restored to amber (`#D97706`; dark variant `#FBBF24`). |
| Global search covered only 5 of 12 modules. | Extended to 11 — added findings, audits, frameworks, KRIs, tickets and threat actors (view + results partial + palette copy). |
| No database-level integrity checks on scored fields. | `CheckConstraint`s added: risk likelihood/impact 1–5 and inherent/residual ≤ 25; control effectiveness ∈ {0,1,3,5}; appetite residual/inherent ≤ capacity; CVSS 0–10; finding composite 0–100. |
| Accessibility: no skip link, no live region for messages, no visible focus style, no print or reduced-motion CSS, and no way to navigate on a small screen. | Skip link, `aria-live` message region, `:focus-visible`, a print stylesheet, `prefers-reduced-motion`, and responsive breakpoints with an off-canvas sidebar + hamburger toggle. |
| Documentation overclaimed the product (django-guardian object permissions, "every model" has history, approval workflow). | README corrected to match the code. |

**Verification:** `python manage.py check` clean; migrations applied to the live DB with all 12
users and every record intact; **42 regression tests pass** (was 28) — new coverage for
severity-band thresholds, the residual floor, risk state-machine + overdue logic, the control
evidence gate, policy transitions, the finding→risk cascade and auto-close, authenticated media
(anonymous 302 / cross-department 404 / owner 200), global-pagination rendering and
cross-module search; live gunicorn checks: 13 authenticated pages return 200, anonymous `/`
and `/media/…` return 302, and the new CSS is present in the served bundle.

---

## 4. Verification evidence

* `python manage.py check` → *System check identified no issues (0 silenced)*.
* `python manage.py makemigrations --check` → *No changes detected* (model state matches migrations).
* Module sweep: **187 app modules imported, 0 failures**.
* **42 regression tests pass** (`python manage.py test`) covering residual-risk invariants
  (including the non-zero floor), severity-band thresholds, the risk state machine and overdue
  logic, the control evidence gate, policy transitions, the finding→risk cascade and auto-close,
  authenticated media downloads (anonymous / cross-department / owner), global-pagination
  rendering, cross-module search, department scoping (own / shared / no-department / anonymous),
  CSV-injection guarding plus
  data fidelity, **CSV exports rendering display labels rather than Python objects**, export
  scoping, the **seal watermark appearing exactly once on every PDF page**, calendar-month
  bucketing including year rollover, the anonymous-redirect rule, the superuser-only gate on
  framework configuration, and POST-only logout.
* Role-based URL sweep: **102 URLs** exercised as anonymous, superuser, department HOD and
  department user — 0 unexpected responses.
* Data integrity: 15 assets · 22 risks · 15 controls · 7 policies · 8 vendors · 6 frameworks
  · 514 framework requirements · 147 notifications — all intact after every change.
* Deployment check: `manage.py check --deploy` reports only the four expected
  locally-relaxed HTTP/TLS warnings.
* Round-2 URL sweep after the branding/export work: **66 URLs** as a department HOD —
  0 unexpected 5xx responses (only the intended 403 on superuser-only framework
  configuration and 405 on the POST-only logout/mark-read routes).
* Round-2 in-browser checks: the new SVG mark loads and paints at 32×32 in the sidebar
  (natural 256×256) in both themes; the sidebar/logo geometry was verified pixel-by-pixel
  (transparent rounded corners, two-tone blue monogram, white orbit and dot) and the SVG
  and PNG masters agree at every probe point; download links were fetched from the logged-in
  page and returned `%PDF` / `PK…` / UTF-8-BOM payloads.
* Round-3 export sweep as the superuser (so every module had data): **11/11 CSV** exports with
  **0** Python-object markers (assets 15 rows, controls 15, policies 7, risks 22, CVE findings 6,
  audits 2, audit evidence 6, control tests 7, audit findings 6, vendors 8), **4/4 PDF** reports
  returning `%PDF`, and **3/3 Excel** workbooks opening with `openpyxl` and no object text.
* Round-3 live HTTP check against gunicorn (not the test client): logged in over the real
  `/login/` form, then re-downloaded the Assets, Controls, Policies and Risk CSVs and read the
  bytes back — human labels throughout (`Software`, `Cloud`, `Preventive`, `Implemented`,
  `Approved`), no `functools.partial`, and a data value of `-` surviving as `-`; the assets PDF
  downloaded as `%PDF`; `static/img/watermark_seal.png` served 200 `image/png`.

**Test-database tear-down:** the runner now drops its test database cleanly. The
original failure was traced to the login signal's unmanaged background thread holding a
connection; persistent DB connections are also disabled under test
(`CONN_MAX_AGE = 0` when `test` is in `sys.argv`).

---

## 5. Product assessment (product manager / analyst view)

### 5.1 Feature inventory

| Module | Capability present | Maturity |
|---|---|---|
| Dashboard | Scoped KPIs, risk heatmap, trends, asset/control posture | Strong |
| Assets | Register, classification, by-owner, explorer | Strong |
| Vendors | Register, assessments, tier snapshot | Good |
| Policies | Register, categories, document attachment, lifecycle | Good |
| Risks | Register, matrix, appetite, treatments, exceptions, cascade to controls | Strong |
| Controls | Library, framework matrix, lifecycle board, effectiveness, evidence | Strong |
| Vulnerabilities | Register, live CVE/EPSS/KEV enrichment, manual entry, cascade to risk | Strong |
| KRIs | Definition, readings, RAG thresholds | Good |
| Frameworks | Frameworks, requirements, coverage, compliance assessments | Good |
| Audits | Audits, evidence, scoring, control tests, findings, actions | Strong |
| Tickets | Queue, mine, available, comments, severity/SLA | Good |
| Threat intel | IOCs, ATT&CK matrix, actors, feed sync | Adequate |
| Cross-cutting | Notifications, global search, executive/audit PDF reports, per-module CSV export (plus PDF/Excel in Assets, Risks and CVE findings), watermarked PDFs, admin UI, Django admin | Good |

This is a genuinely broad GRC surface — broader than most commercial SMB GRC tools.

### 5.2 Feature bloat, overlap and dead weight

| Item | Assessment | Recommendation |
|---|---|---|
| `tickets` **and** `audits.ActionItem` | Two overlapping task-tracking systems. | Keep both (different intents: helpdesk vs remediation), but surface action items on the ticket queue view, or add "raised from action item" links. |
| `django-guardian` | Installed and migrated, but **no application code uses object permissions** — scoping is done by department. | Either adopt it for exceptions (e.g. per-object sharing) or drop it from `INSTALLED_APPS`/`requirements.txt`. Currently it only adds model tables and an admin surface. |
| `kris.KRI` vs dashboard KPIs | Complementary, not duplicative — but the naming invites confusion. | Label clearly ("Risk indicators" vs "Headline metrics"). |
| `lifecycle_set` route | Defined and permission-checked, but **no UI** posts to it (only advance/regress are wired). | Expose a "set stage" control or delete the route. |
| `core:notification_mark_read` | Per-item mark-read endpoint with **no UI** (the list view marks items read on open). | Delete it, or add a per-item "mark read" action. |
| ATT&CK matrix | Very large page, global (not department-scoped), only loosely connected to the risk register via IOC links. | Acceptable as a reference view, but add "techniques relevant to my risks" filtering to earn its place. |
| `matplotlib` + `numpy` | Pulled in for server-side charts while the UI uses client-side canvases. | Verify usage; remove if unused to slim the image. |

### 5.3 Missing capabilities for enterprise use (ranked)

1. **Scheduled background jobs.** Alerts/tickets currently refresh on login and on dashboard
   view. There is no Celery/APScheduler/cron worker, so overdue reminders, KEV sync and
   appetite-breach escalation are opportunistic rather than reliable. *A scheduler is the
   single highest-value addition.*
2. **Outbound notifications.** Zero email/Slack/Teams integration — all notifications are
   in-app. Enterprise users will not sit on the dashboard.
3. **Bulk data import.** CSV **export** exists; there is no import. Onboarding a real
   register (hundreds of assets, controls, framework requirements) is manual today.
4. **SSO / MFA.** No SAML/OIDC provider and no TOTP. Mandatory for most enterprise
   buyers, and the standard control for privileged access.
5. **API.** No REST endpoints. Integrations (SIEM, CMDB, ticketing) all require one.
6. **Change history surfaced in the UI.** `django-simple-history` is recording everything
   but nothing is exposed to users; auditors want a per-record history view.
7. **Risk treatment cost/benefit.** Treatment plans capture actions but not the
   cost vs residual-risk-reduction trade-off, which is what a risk committee actually
   decides on.
8. **Threat-intel → risk integration.** IOCs and ATT&CK techniques are not linked to the
   assets/risks they affect, so the data does not change the risk picture.
9. **Continuous control monitoring.** Control tests are manual records; there is no import
   of automated evidence (e.g. cloud config findings) into control effectiveness.
10. **Data retention / privacy tooling.** No retention policy, no subject-access tooling.
11. **Board pack scheduling.** The executive PDF is generated per request; no scheduled
    distribution.
12. **Bulk approval workflow.** Policies and exceptions have approvers but no multi-step
    approval chain with delegation.

---

## 6. Outstanding items

### 6.1 Action required — stray login-capable account

The database contains one account that should not exist:

| Field | Value |
|---|---|
| `id` | 12 |
| `username` | `AnonymousUser` |
| `is_active` | **True** |
| password | usable (PBKDF2-SHA256 hash present) |
| `department` | *(none)* |
| `is_staff` / `is_superuser` | False / False |
| `date_joined` | 2026-10-16 17:29 UTC (created during testing) |

It is **not** created by any seed command and is not referenced by application code; no
business record points at it (only one history row). Because it has no department it can
see no data and has no admin rights, so the practical impact is low — but an active,
login-capable account named identically to Django's anonymous-user sentinel is exactly
what an auditor will flag.

It was deliberately **left in place** because the brief was to keep the database intact.
Remove it with either:

```bash
docker compose exec web python manage.py shell -c \
  "from django.contrib.auth import get_user_model as g; g().objects.filter(username='AnonymousUser').delete()"
```

or the same action from the Admin UI (`/admin/core/user/12/delete/`).

### 6.2 Accepted, documented (no action taken)

* `NotificationListView` marks notifications read on GET (standard inbox behaviour).
* The executive report generates a WeasyPrint PDF per request, which blocks a worker for
  ~1 s. Acceptable at current volumes; should move to a queued job alongside item 5.3.1.
* `password_change_form.html` uses `{{ field.help_text|safe }}` — redundant, matches
  Django's own admin template.
* `login-hero.png` is 1.6 MB. Worth compressing, but it is a static asset, not a bug.
* `logo.png` / `favicon.png` are not referenced by any template (the app uses the SVG
  sources everywhere); they are kept as raster masters for documents, email signatures and
  third-party tools.
* The CVE findings page offers different column sets for CSV (`csv_fields`) and Excel
  (`build_rows`) — Excel carries Assigned-To/Team/SLA-Due/Overdue, CSV carries
  EPSS/KEV/Port. Both are intentional but they should eventually be reconciled.
* `static/img/report_seal_confidential.png` and `report_seal_transparent.png` (412 KB each,
  byte-identical) are still unreferenced leftovers from an earlier report design; the PDF
  watermark now uses `static/img/watermark_seal.png`, a 237 KB masked derivative of the same
  artwork. The two originals can be deleted together with the watermark asset's source.
* Whitenoise caches its static file index at start-up, so **newly added** static files 404
  until `docker compose restart web`. Existing files are updated in place and are served
  correctly after `collectstatic --clear`.

---

## 7. How to run and verify

```bash
# Start (first time, or after dependency/settings changes)
docker compose up -d --build

# Restart after code changes (templates/views are cached; bind-mounted code)
docker compose restart web

# Health
curl -s -o /dev/null -w "%{http_code}\n" http://localhost:8000/login/   # 200

# Checks
docker compose exec web python manage.py check
docker compose exec web python manage.py makemigrations --check
docker compose exec web python manage.py test          # 20 tests

# Local HTTP relaxes TLS/HSTS via .env; for real TLS set:
#   SECURE_SSL_REDIRECT=True, SECURE_HSTS_SECONDS=31536000, SESSION_COOKIE_SECURE=True,
#   CSRF_COOKIE_SECURE=True
```

Production checklist before go-live: set a strong `SECRET_KEY`, point `ALLOWED_HOSTS` at
the real hostname, enable the TLS flags above, serve media from object storage rather than
Django, put the app behind a reverse proxy, add the scheduler (5.3.1) and an outbound
notification channel (5.3.2), and remove the stray account (6.1).
