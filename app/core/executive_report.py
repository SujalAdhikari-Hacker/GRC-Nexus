"""
Gathers all data + generates narratives for the executive report.
"""
from collections import Counter

from django.db.models import Q
from django.utils import timezone
from django.utils.html import escape

from assets.models import Asset
from risks.models import Risk
from controls.models import Control
from frameworks.models import Framework
from incidents.models import Incident
from vulnerabilities.models import Finding
from policies.models import Policy
from tickets.models import Ticket
from vendors.models import Vendor
from vendors.services import TIER_EXPECTED_SCORE
from audits.models import AuditFinding, ActionItem, EvidenceItem
from core.correlation import get_framework_coverage
from core.dashboard_data import iter_month_bounds
from core.mixins import scope_queryset
from . import report_charts as charts


def _fmt_money(val):
    """Format a currency amount with thousands separators and zero decimals."""
    return f'{(val or 0):,.0f}'


def _get_scope(user):
    """Return the department a report should be limited to, or None for org-wide.

    Only superusers get an org-wide report. A user with no department gets
    (correctly) an empty report rather than full visibility.
    """
    if user.is_superuser:
        return None
    return getattr(user, 'department', None)


def build_executive_report(user):
    """Return a dict with all data + charts + narratives."""
    dept = _get_scope(user)

    # ---------- Base querysets (respect object-level scoping, incl. sharing) ----------
    risks      = scope_queryset(Risk.objects.select_related('category', 'owner_dept', 'owner_user').prefetch_related('assets'), user)
    controls   = scope_queryset(Control.objects.all(), user)
    findings   = scope_queryset(Finding.objects.select_related('vulnerability', 'asset'), user)
    actions    = scope_queryset(ActionItem.objects.all(), user)
    policies   = scope_queryset(Policy.objects.all(), user)
    assets     = scope_queryset(Asset.objects.filter(is_active=True).select_related('owner_dept', 'bcp_policy', 'drp_policy').prefetch_related('risks'), user)
    audit_find = scope_queryset(AuditFinding.objects.all(), user)
    vendors    = scope_queryset(Vendor.objects.filter(status='active').select_related('owner_dept').prefetch_related('assessments'), user)
    incidents  = scope_queryset(Incident.objects.select_related('owner_dept', 'handler'), user)
    tickets    = scope_queryset(Ticket.objects.all(), user)
    evidence_items = scope_queryset(EvidenceItem.objects.all(), user)

    # ---------- Counts ----------
    # "Active" consistently means not closed — closed risks are not live
    # exposure and must not inflate any of the metrics below.
    active_risks      = risks.exclude(status='closed')
    total_risks       = active_risks.count()
    closed_risks      = risks.count() - total_risks
    breached_risks    = active_risks.filter(appetite_breached=True).count()
    open_risks        = total_risks
    critical_risks    = active_risks.filter(inherent_score__gte=20).count()
    high_risks        = active_risks.filter(inherent_score__gte=12, inherent_score__lt=20).count()

    total_controls    = controls.count()
    implemented       = controls.filter(status='implemented').count()
    effective         = controls.filter(effectiveness_rating='effective').count()
    ineffective       = controls.filter(effectiveness_rating='ineffective').count()
    not_tested        = controls.filter(effectiveness_rating='not_tested').count()
    partially         = controls.filter(effectiveness_rating='partially_effective').count()

    total_findings    = findings.count()
    open_findings     = findings.exclude(status__in=['remediated', 'accepted', 'false_positive']).count()
    overdue_findings  = sum(1 for f in findings if f.is_overdue)
    due_soon_findings = sum(1 for f in findings if f.is_due_soon)
    critical_findings = findings.filter(vulnerability__cvss_severity='critical').count()

    total_assets      = assets.count()
    critical_assets   = assets.filter(criticality=4).count()

    total_vendors     = vendors.count()
    tier1_vendors     = vendors.filter(tier=1).count()

    total_policies    = policies.count()
    approved_policies = policies.filter(status='approved').count()

    open_actions      = actions.exclude(status__in=['completed', 'cancelled']).count()
    overdue_actions   = sum(1 for a in actions if a.is_overdue)

    # ---------- Averages ----------
    avg_inherent = (
        round(sum(r.inherent_score for r in active_risks) / total_risks, 1) if total_risks else 0
    )
    avg_residual = (
        round(sum(r.residual_score for r in active_risks) / total_risks, 1) if total_risks else 0
    )
    control_effectiveness_pct = round(effective / total_controls * 100) if total_controls else 0

    # ---------- Heatmap data ----------
    heatmap_cells = {}
    for r in active_risks:
        key = (r.likelihood, r.impact)
        heatmap_cells[key] = heatmap_cells.get(key, 0) + 1

    # ---------- Category distribution ----------
    category_counts = Counter(r.category.name for r in active_risks)
    cat_labels = list(category_counts.keys())
    cat_values = list(category_counts.values())

    # ---------- Trend data ----------
    # Cohort averages per real calendar month (see core.dashboard_data for why
    # 30-day arithmetic and cumulative snapshots were wrong).
    today = timezone.localdate()
    trend_labels = []
    inherent_trend = []
    residual_trend = []
    for start, end in iter_month_bounds(today, 6):
        month_risks = list(
            risks.filter(created_at__date__gte=start, created_at__date__lt=end)
        )
        trend_labels.append(start.strftime('%b'))
        if month_risks:
            inherent_trend.append(
                round(sum(r.inherent_score for r in month_risks) / len(month_risks), 1)
            )
            residual_trend.append(
                round(sum(r.residual_score for r in month_risks) / len(month_risks), 1)
            )
        else:
            inherent_trend.append(0)
            residual_trend.append(0)

    # ---------- Top risks ----------
    top_risks = list(active_risks.order_by('-residual_score')[:10])

    # ---------- Top risky assets ----------
    asset_rows = []
    for asset in assets.select_related('owner_dept'):
        asset_risks = [r for r in asset.risks.all() if r.status != 'closed']
        if not asset_risks:
            continue
        max_residual = max((r.residual_score or 0) for r in asset_risks)
        exposure = max_residual * (asset.criticality or 1)
        asset_rows.append({
            'asset': asset,
            'risk_count': len(asset_risks),
            'max_residual': max_residual,
            'exposure': exposure,
            'breached': any(r.appetite_breached for r in asset_risks),
        })
    asset_rows.sort(key=lambda x: -x['exposure'])
    top_assets = asset_rows[:8]

    # ---------- Business Position metrics ----------
    from core.models import OrganisationProfile
    from decimal import Decimal

    org = OrganisationProfile.get()

    # Total asset base
    total_asset_value = sum((a.value or Decimal('0')) for a in assets)

    # Assets by criticality
    asset_by_crit = {
        'critical': sum(1 for a in assets if a.criticality == 4),
        'high':     sum(1 for a in assets if a.criticality == 3),
        'medium':   sum(1 for a in assets if a.criticality == 2),
        'low':      sum(1 for a in assets if a.criticality == 1),
    }

    # Assets by classification
    asset_by_class = {
        'restricted':   sum(1 for a in assets if a.classification == 'restricted'),
        'confidential': sum(1 for a in assets if a.classification == 'confidential'),
        'internal':     sum(1 for a in assets if a.classification == 'internal'),
        'public':       sum(1 for a in assets if a.classification == 'public'),
    }

    # Financial exposure is computed per asset (each asset counted once) using
    # the worst active risk on that asset. The previous per-risk sum counted an
    # asset once per linked risk, inflating exposure for shared assets.
    def _risk_exposure(r, residual=True):
        linked_assets = [
            a for a in r.assets.all()
            if a.owner_dept_id == r.owner_dept_id
        ]
        if not linked_assets:
            return Decimal('0')
        max_val = max((a.value or Decimal('0')) for a in linked_assets)
        score = r.residual_score if residual else r.inherent_score
        return max_val * Decimal(score) / Decimal('25')

    def _portfolio_exposure(residual=True):
        total = Decimal('0')
        for asset in assets:
            asset_risks = [
                r for r in asset.risks.all()
                if r.status != 'closed' and r.owner_dept_id == asset.owner_dept_id
            ]
            if not asset_risks:
                continue
            score = max(
                ((r.residual_score if residual else r.inherent_score) or 0)
                for r in asset_risks
            )
            total += (asset.value or Decimal('0')) * Decimal(score) / Decimal('25')
        return total

    total_inherent_exposure = _portfolio_exposure(residual=False)
    total_residual_exposure = _portfolio_exposure(residual=True)
    risk_reduction = total_inherent_exposure - total_residual_exposure
    risk_reduction_pct = (
        round(float(risk_reduction / total_inherent_exposure) * 100)
        if total_inherent_exposure > 0 else 0
    )

    # Top 3 risks in plain English
    top_business_risks = []
    for r in active_risks.order_by('-residual_score')[:3]:
        exp_val = _risk_exposure(r, residual=True)
        top_business_risks.append({
            'title': r.title,
            'exposure': exp_val,
            'exposure_fmt': _fmt_money(exp_val),
            'status': r.get_status_display(),
            'breached': r.appetite_breached,
        })

    # Ratios
    budget_pct_revenue = (
        round(float(org.annual_security_budget / org.annual_revenue) * 100, 1)
        if org.annual_revenue > 0 else 0
    )
    exposure_pct_revenue = (
        round(float(total_residual_exposure / org.annual_revenue) * 100, 2)
        if org.annual_revenue > 0 else 0
    )

    # ---------- Framework coverage ----------
    frameworks = list(Framework.objects.all().order_by('name'))
    fw_names = []
    fw_percents = []
    fw_rows = []
    for fw in frameworks:
        cov = get_framework_coverage(fw)
        fw_names.append(fw.name)
        fw_percents.append(cov['percent'])
        fw_rows.append({'framework': fw, 'cov': cov})

    overall_coverage = round(sum(fw_percents) / len(fw_percents)) if fw_percents else 0

    # ---------- Vulnerability severity counts ----------
    vuln_counts = Counter()
    for f in findings:
        vuln_counts[f.vulnerability.cvss_severity] += 1

    # ---------- SLA buckets ----------
    sla_within = sum(1 for f in findings
                     if not f.is_overdue and f.status not in ('remediated', 'accepted', 'false_positive'))
    sla_overdue = overdue_findings
    sla_closed = findings.filter(status__in=['remediated', 'accepted', 'false_positive']).count()

    # ---------- Generate charts ----------
    chart_heatmap   = charts.risk_heatmap_png(heatmap_cells)
    chart_category  = charts.risk_category_png(cat_labels, cat_values)
    chart_trend     = charts.risk_trend_png(trend_labels, inherent_trend, residual_trend)
    chart_control   = charts.control_effectiveness_png({
        'effective': effective,
        'partially_effective': partially,
        'ineffective': ineffective,
        'not_tested': not_tested,
    })
    chart_vuln_sev  = charts.vuln_severity_png(dict(vuln_counts))
    chart_sla       = charts.sla_donut_png(sla_within, sla_overdue, sla_closed)
    chart_frameworks = charts.framework_coverage_png(fw_names, fw_percents)

    # ---------- Incidents & NIS2 Article 23 ----------
    incident_list = list(incidents)
    total_incidents = len(incident_list)
    open_incidents = sum(1 for i in incident_list if i.status != 'closed')
    critical_incidents = sum(
        1 for i in incident_list if i.status != 'closed' and i.severity == 'critical'
    )
    nis2_significant_count = sum(1 for i in incident_list if i.nis2_significant)
    nis2_breached_count = sum(
        1 for i in incident_list if i.nis2_significant and i.nis2_status == 'breached'
    )
    nis2_due_soon_count = sum(
        1 for i in incident_list if i.nis2_significant and i.nis2_status == 'due_soon'
    )
    gdpr_pending_count = sum(1 for i in incident_list if i.breaching_event is not None)
    triage_sla_breached_count = sum(1 for i in incident_list if i.sla_breached)

    _nis2_rank = {'breached': 0, 'due_soon': 1, 'open': 2, 'complete': 3, None: 4}
    priority_incidents = [
        i for i in incident_list if i.nis2_significant or i.status != 'closed'
    ]
    priority_incidents.sort(
        key=lambda i: (
            _nis2_rank.get(i.nis2_status, 4),
            -(i.detected_at.timestamp() if i.detected_at else 0),
        )
    )
    incident_rows = []
    for inc in priority_incidents[:8]:
        clocks = (
            {c.phase: c for c in inc.nis2_clocks}
            if inc.nis2_significant and inc.detected_at
            else {}
        )
        incident_rows.append({
            'incident': inc,
            'nis2_status': inc.nis2_status,
            'clocks': clocks,
        })

    # ---------- Third-Party & Vendor Assurance (0-100 Scorecards) ----------
    vendor_list = list(vendors)
    vendor_band_counts = {'low': 0, 'moderate': 0, 'elevated': 0, 'high': 0}
    vendor_scored = []
    expired_contract_vendors = 0
    vendors_below_target = 0
    for v in vendor_list:
        sc = v.scorecard
        vendor_band_counts[sc.band] = vendor_band_counts.get(sc.band, 0) + 1
        tier_target = TIER_EXPECTED_SCORE.get(v.tier, 50)
        below_target = sc.score < tier_target
        if below_target:
            vendors_below_target += 1
        if v.is_contract_expired:
            expired_contract_vendors += 1
        vendor_scored.append({
            'vendor': v,
            'scorecard': sc,
            'components': {c.key: c for c in sc.components},
            'tier_target': tier_target,
            'below_target': below_target,
        })

    avg_vendor_score = (
        round(sum(item['scorecard'].score for item in vendor_scored) / len(vendor_scored))
        if vendor_scored else 0
    )
    high_risk_vendors = vendor_band_counts['high'] + vendor_band_counts['elevated']
    vendor_scored.sort(
        key=lambda item: (
            not item['vendor'].is_contract_expired,
            item['scorecard'].score,
            item['vendor'].tier,
            item['vendor'].name.lower(),
        )
    )
    top_risk_vendors = vendor_scored[:8]
    chart_vendor_scores = charts.vendor_risk_bands_png(vendor_band_counts)

    # ---------- Business Continuity & BIA Readiness ----------
    asset_list = list(assets)
    bia_complete_count = 0
    bia_gap_count = 0
    rto_exceeds_mtpd_count = 0
    missing_bcp_count = 0
    missing_drp_count = 0
    stale_continuity_test_count = 0
    critical_bia_gap_count = 0
    continuity_gap_rows = []
    for a in asset_list:
        gaps = a.continuity_gaps
        if not gaps:
            bia_complete_count += 1
        else:
            bia_gap_count += 1
            if a.criticality == 4:
                critical_bia_gap_count += 1
            if 'RTO exceeds MTPD' in gaps:
                rto_exceeds_mtpd_count += 1
            if 'No BCP linked' in gaps:
                missing_bcp_count += 1
            if 'No DRP linked' in gaps:
                missing_drp_count += 1
            if a.continuity_test_stale:
                stale_continuity_test_count += 1
            continuity_gap_rows.append({'asset': a, 'gaps': gaps})

    bia_readiness_pct = (
        round(bia_complete_count / len(asset_list) * 100) if asset_list else 0
    )
    continuity_gap_rows.sort(
        key=lambda item: (
            -(item['asset'].criticality or 0),
            -len(item['gaps']),
            item['asset'].asset_id or '',
        )
    )
    continuity_gap_assets = continuity_gap_rows[:8]
    chart_bia = charts.bia_readiness_png(bia_complete_count, bia_gap_count)

    # ---------- Audit Findings, Tickets, Evidence SHA-256 & Service Health ----------
    audit_find_list = list(audit_find)
    audit_findings_total = len(audit_find_list)
    audit_findings_open = sum(
        1 for af in audit_find_list if af.status not in ('resolved', 'accepted', 'closed')
    )
    audit_findings_overdue = sum(1 for af in audit_find_list if af.is_overdue)
    audit_findings_awaiting_verification = sum(
        1 for af in audit_find_list if af.awaiting_verification
    )

    ticket_list = list(tickets)
    open_tickets = sum(1 for t in ticket_list if t.is_open)
    overdue_tickets = sum(1 for t in ticket_list if t.is_overdue)
    critical_tickets = sum(1 for t in ticket_list if t.is_open and t.priority == 4)

    total_evidence = evidence_items.count()
    checksummed_evidence = (
        evidence_items.filter(versions__isnull=False)
        .exclude(versions__sha256='')
        .distinct()
        .count()
    )

    if user.is_superuser:
        from core.models import ServiceRun

        latest_by_service = {}
        for run in ServiceRun.objects.order_by('-started_at', '-id'):
            if run.service not in latest_by_service:
                latest_by_service[run.service] = run
        service_health_rows = [latest_by_service[name] for name in sorted(latest_by_service)]
        failed_services_count = sum(1 for r in service_health_rows if r.status == 'failed')
    else:
        service_health_rows = []
        failed_services_count = 0

    # ---------- NARRATIVES ----------
    # Executive summary paragraph. org_label is interpolated into HTML that the
    # template renders with |safe, so it must be escaped here. Capitalisation is
    # resolved before escaping so entities such as "&amp;" survive intact.
    org_label = escape(dept.name) if dept else 'The organization'

    # Executive summary paragraph
    risk_line = (
        f"{org_label} maintains <strong>{total_risks} active risk"
        f"{'s' if total_risks != 1 else ''}</strong> across {len(cat_labels)} "
        f"categor{'ies' if len(cat_labels) != 1 else 'y'}, with an average inherent score "
        f"of {avg_inherent}/25 and residual score of {avg_residual}/25."
    )
    if breached_risks:
        breach_line = (
            f"<strong>{breached_risks} risk{'s' if breached_risks != 1 else ''}</strong> currently "
            f"exceed the defined risk appetite and require escalation."
        )
    else:
        breach_line = "No risks currently exceed the defined appetite — the risk posture is within tolerance."

    control_line = (
        f"Of {total_controls} controls, <strong>{implemented} are implemented</strong> "
        f"({round(implemented / total_controls * 100) if total_controls else 0}%), with "
        f"{control_effectiveness_pct}% assessed as effective."
    )

    vuln_line = (
        f"The vulnerability register contains <strong>{total_findings} finding"
        f"{'s' if total_findings != 1 else ''}</strong>, of which {open_findings} remain open. "
    )
    if overdue_findings:
        vuln_line += f"<span style='color:#DC2626;'><strong>{overdue_findings} finding"
        vuln_line += f"{'s are' if overdue_findings != 1 else ' is'} overdue</strong></span> against the SLA clock. "
    vuln_line += f"{critical_findings} are critical severity."

    coverage_line = (
        f"Across {len(frameworks)} compliance frameworks, overall control coverage sits at "
        f"<strong>{overall_coverage}%</strong>."
    )

    resilience_line = (
        f"Operational resilience: <strong>{open_incidents} open incident"
        f"{'s' if open_incidents != 1 else ''}</strong>"
    )
    if nis2_breached_count:
        resilience_line += (
            f" (<span style='color:#DC2626;'><strong>{nis2_breached_count} NIS2 Art. 23 deadline"
            f"{'s' if nis2_breached_count != 1 else ''} breached</strong></span>)"
        )
    elif nis2_due_soon_count:
        resilience_line += (
            f" (<strong>{nis2_due_soon_count} NIS2 Art. 23 report"
            f"{'s' if nis2_due_soon_count != 1 else ''} due within 2 hours</strong>)"
        )
    resilience_line += (
        f", active vendor assurance averages <strong>{avg_vendor_score}/100</strong> "
        f"({expired_contract_vendors} expired contract{'s' if expired_contract_vendors != 1 else ''}), "
        f"and <strong>{bia_readiness_pct}%</strong> of active assets meet BIA continuity readiness."
    )

    # Recommendations — auto-generate based on worst signals
    recommendations = []
    if nis2_breached_count:
        recommendations.append({
            'priority': 'high',
            'text': f'File overdue NIS2 Article 23 regulatory report'
                    f'{"s" if nis2_breached_count != 1 else ""} for {nis2_breached_count} significant incident'
                    f'{"s" if nis2_breached_count != 1 else ""} and notify CSIRT immediately.',
        })
    if nis2_due_soon_count:
        recommendations.append({
            'priority': 'high',
            'text': f'{nis2_due_soon_count} NIS2 Article 23 deadline'
                    f'{"s are" if nis2_due_soon_count != 1 else " is"} within 2 hours of breach. '
                    f'Submit early warning or notification filing immediately.',
        })
    if breached_risks:
        recommendations.append({
            'priority': 'high',
            'text': f'Escalate {breached_risks} appetite-breaching risk'
                    f'{"s" if breached_risks != 1 else ""} to the Risk Committee. '
                    f'Review treatment plans and confirm timelines.',
        })
    if expired_contract_vendors:
        recommendations.append({
            'priority': 'high',
            'text': f'Renew or remediate {expired_contract_vendors} active vendor contract'
                    f'{"s" if expired_contract_vendors != 1 else ""} that ha'
                    f'{"ve" if expired_contract_vendors != 1 else "s"} expired (contract score zeroed under NIS2 Art. 21).',
        })
    if overdue_findings:
        recommendations.append({
            'priority': 'high',
            'text': f'Remediate {overdue_findings} SLA-overdue vulnerabilit'
                    f'{"ies" if overdue_findings != 1 else "y"}. '
                    f'Assign owners where missing and update target dates.',
        })
    if ineffective:
        recommendations.append({
            'priority': 'high',
            'text': f'Re-design {ineffective} ineffectiv'
                    f'{"e controls" if ineffective != 1 else "e control"}. '
                    f'Evaluate compensating controls in the interim.',
        })
    if vendors_below_target:
        recommendations.append({
            'priority': 'medium',
            'text': f'Address assurance gaps across {vendors_below_target} vendor'
                    f'{"s" if vendors_below_target != 1 else ""} scoring below their tier target '
                    f'(certifications, audit rights, or recency assessments).',
        })
    if critical_bia_gap_count or bia_gap_count:
        recommendations.append({
            'priority': 'medium',
            'text': f'Close BIA & continuity gaps on {bia_gap_count} active asset'
                    f'{"s" if bia_gap_count != 1 else ""} ({critical_bia_gap_count} critical) — '
                    f'confirm RTO/RPO/MTPD, link BCP/DRP policies, and record annual DR tests.',
        })
    if not_tested:
        recommendations.append({
            'priority': 'medium',
            'text': f'Test {not_tested} untested control{"s" if not_tested != 1 else ""}. '
                    f'Untested controls provide zero assurance.',
        })
    if due_soon_findings:
        recommendations.append({
            'priority': 'medium',
            'text': f'{due_soon_findings} vulnerabilit'
                    f'{"ies are" if due_soon_findings != 1 else "y is"} approaching SLA breach. '
                    f'Accelerate remediation or request an exception.',
        })
    if audit_findings_overdue or overdue_tickets:
        recommendations.append({
            'priority': 'medium',
            'text': f'Clear SLA-overdue remediation backlog: {audit_findings_overdue} audit finding'
                    f'{"s" if audit_findings_overdue != 1 else ""} and {overdue_tickets} ticket'
                    f'{"s" if overdue_tickets != 1 else ""} past due date.',
        })
    if overall_coverage < 60:
        recommendations.append({
            'priority': 'medium',
            'text': f'Compliance coverage is {overall_coverage}%. '
                    f'Prioritize mapping gaps in low-coverage frameworks.',
        })
    if overdue_actions:
        recommendations.append({
            'priority': 'medium',
            'text': f'{overdue_actions} remediation action{"s" if overdue_actions != 1 else ""} '
                    f'{"are" if overdue_actions != 1 else "is"} past due. '
                    f'Review with assigned teams.',
        })
    if failed_services_count:
        recommendations.append({
            'priority': 'medium',
            'text': f'Investigate {failed_services_count} failed scheduled background service'
                    f'{"s" if failed_services_count != 1 else ""} in the Service Run Log.',
        })
    if not recommendations:
        recommendations.append({
            'priority': 'low',
            'text': 'No critical issues detected. Continue monitoring risk and control health on the regular cadence.',
        })

    return {
        # meta
        'report_version': 'v3.3.0',
        'org_label': org_label if dept else 'Organization-wide',
        'report_scope': f'{dept.name} department' if dept else 'Organization-wide',
        'generated_at': timezone.now(),
        'generated_by': user,

        # counts
        'total_risks': total_risks,
        'breached_risks': breached_risks,
        'open_risks': open_risks,
        'critical_risks': critical_risks,
        'high_risks': high_risks,
        'total_controls': total_controls,
        'implemented_controls': implemented,
        'effective_controls': effective,
        'ineffective_controls': ineffective,
        'not_tested_controls': not_tested,
        'control_effectiveness_pct': control_effectiveness_pct,
        'total_findings': total_findings,
        'open_findings': open_findings,
        'overdue_findings': overdue_findings,
        'critical_findings': critical_findings,
        'sla_closed': sla_closed,
        'total_assets': total_assets,
        'critical_assets': critical_assets,
        'total_vendors': total_vendors,
        'tier1_vendors': tier1_vendors,
        'total_policies': total_policies,
        'approved_policies': approved_policies,
        'open_actions': open_actions,
        'overdue_actions': overdue_actions,

        # v3.3.0 modules
        'total_incidents': total_incidents,
        'open_incidents': open_incidents,
        'critical_incidents': critical_incidents,
        'nis2_significant_count': nis2_significant_count,
        'nis2_breached_count': nis2_breached_count,
        'nis2_due_soon_count': nis2_due_soon_count,
        'gdpr_pending_count': gdpr_pending_count,
        'triage_sla_breached_count': triage_sla_breached_count,
        'incident_rows': incident_rows,

        'avg_vendor_score': avg_vendor_score,
        'high_risk_vendors': high_risk_vendors,
        'expired_contract_vendors': expired_contract_vendors,
        'vendors_below_target': vendors_below_target,
        'vendor_band_counts': vendor_band_counts,
        'top_risk_vendors': top_risk_vendors,
        'chart_vendor_scores': chart_vendor_scores,

        'bia_complete_count': bia_complete_count,
        'bia_gap_count': bia_gap_count,
        'bia_readiness_pct': bia_readiness_pct,
        'rto_exceeds_mtpd_count': rto_exceeds_mtpd_count,
        'missing_bcp_count': missing_bcp_count,
        'missing_drp_count': missing_drp_count,
        'stale_continuity_test_count': stale_continuity_test_count,
        'continuity_gap_assets': continuity_gap_assets,
        'chart_bia': chart_bia,

        'audit_findings_total': audit_findings_total,
        'audit_findings_open': audit_findings_open,
        'audit_findings_overdue': audit_findings_overdue,
        'audit_findings_awaiting_verification': audit_findings_awaiting_verification,
        'open_tickets': open_tickets,
        'overdue_tickets': overdue_tickets,
        'critical_tickets': critical_tickets,
        'total_evidence': total_evidence,
        'checksummed_evidence': checksummed_evidence,
        'service_health_rows': service_health_rows,
        'failed_services_count': failed_services_count,

        # averages
        'avg_inherent': avg_inherent,
        'avg_residual': avg_residual,

        # charts
        'chart_heatmap': chart_heatmap,
        'chart_category': chart_category,
        'chart_trend': chart_trend,
        'chart_control': chart_control,
        'chart_vuln_sev': chart_vuln_sev,
        'chart_sla': chart_sla,
        'chart_frameworks': chart_frameworks,

        # tables
        'top_risks': top_risks,
        'top_assets': top_assets,
        'framework_rows': fw_rows,
        'overall_coverage': overall_coverage,

        # narratives
        'risk_line': risk_line,
        'breach_line': breach_line,
        'control_line': control_line,
        'vuln_line': vuln_line,
        'coverage_line': coverage_line,
        'resilience_line': resilience_line,
        'recommendations': recommendations,

        # Business Position
        'org_profile': org,
        'total_asset_value': total_asset_value,
        'total_asset_value_fmt': _fmt_money(total_asset_value),
        'asset_by_crit': asset_by_crit,
        'asset_by_class': asset_by_class,
        'total_inherent_exposure': total_inherent_exposure,
        'total_inherent_exposure_fmt': _fmt_money(total_inherent_exposure),
        'total_residual_exposure': total_residual_exposure,
        'total_residual_exposure_fmt': _fmt_money(total_residual_exposure),
        'risk_reduction': risk_reduction,
        'risk_reduction_fmt': _fmt_money(risk_reduction),
        'risk_reduction_pct': risk_reduction_pct,
        'top_business_risks': top_business_risks,
        'budget_pct_revenue': budget_pct_revenue,
        'exposure_pct_revenue': exposure_pct_revenue,
        'annual_security_budget_fmt': _fmt_money(org.annual_security_budget),
    }
