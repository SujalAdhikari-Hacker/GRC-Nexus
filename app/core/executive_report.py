"""
Gathers all data + generates narratives for the executive report.
"""
from collections import Counter
from datetime import timedelta

from django.utils import timezone

from assets.models import Asset
from risks.models import Risk
from controls.models import Control
from frameworks.models import Framework
from vulnerabilities.models import Finding
from policies.models import Policy
from vendors.models import Vendor
from audits.models import AuditFinding, ActionItem
from core.correlation import get_framework_coverage
from . import report_charts as charts


def _get_scope(user):
    """Return whether user sees all data or just their department."""
    if user.is_superuser:
        return None
    return getattr(user, 'department', None)


def _filter(qs, dept, field='owner_dept'):
    if dept is None:
        return qs
    return qs.filter(**{field: dept})


def build_executive_report(user):
    """Return a dict with all data + charts + narratives."""
    dept = _get_scope(user)

    # ---------- Base querysets ----------
    risks      = _filter(Risk.objects.all(), dept)
    controls   = _filter(Control.objects.all(), dept)
    findings   = _filter(Finding.objects.all(), dept)
    actions    = _filter(ActionItem.objects.all(), dept)
    policies   = _filter(Policy.objects.all(), dept)
    assets     = _filter(Asset.objects.filter(is_active=True), dept)
    audit_find = _filter(AuditFinding.objects.all(), dept)
    vendors    = _filter(Vendor.objects.filter(status='active'), dept)

    # ---------- Counts ----------
    total_risks       = risks.count()
    breached_risks    = risks.filter(appetite_breached=True).count()
    open_risks        = risks.exclude(status='closed').count()
    critical_risks    = risks.filter(inherent_score__gte=20).count()
    high_risks        = risks.filter(inherent_score__gte=12, inherent_score__lt=20).count()

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
    avg_inherent = risks.aggregate_avg = (
        round(sum(r.inherent_score for r in risks) / total_risks, 1) if total_risks else 0
    )
    avg_residual = (
        round(sum(r.residual_score for r in risks) / total_risks, 1) if total_risks else 0
    )
    control_effectiveness_pct = round(effective / total_controls * 100) if total_controls else 0

    # ---------- Heatmap data ----------
    heatmap_cells = {}
    for r in risks:
        key = (r.likelihood, r.impact)
        heatmap_cells[key] = heatmap_cells.get(key, 0) + 1

    # ---------- Category distribution ----------
    category_counts = Counter(r.category.name for r in risks)
    cat_labels = list(category_counts.keys())
    cat_values = list(category_counts.values())

    # ---------- Trend data ----------
    today = timezone.now().date()
    trend_labels = []
    inherent_trend = []
    residual_trend = []
    for i in range(5, -1, -1):
        target = (today.replace(day=1) - timedelta(days=i * 30)).replace(day=1)
        next_month = (target + timedelta(days=32)).replace(day=1)
        month_risks = [r for r in risks
                       if r.created_at.date() < next_month and r.created_at.date() >= target]
        # For a proper snapshot we'd use historical records; approximate with current
        month_risks = list(risks.filter(created_at__date__lt=next_month).exclude(status='closed'))
        if month_risks:
            inherent_trend.append(round(sum(r.inherent_score for r in month_risks) / len(month_risks), 1))
            residual_trend.append(round(sum(r.residual_score for r in month_risks) / len(month_risks), 1))
        else:
            inherent_trend.append(0)
            residual_trend.append(0)
        trend_labels.append(target.strftime('%b'))

    # ---------- Top risks ----------
    top_risks = list(risks.order_by('-residual_score')[:10])

    # ---------- Top risky assets ----------
    asset_rows = []
    for asset in assets.select_related('owner_dept'):
        asset_risks = list(asset.risks.all())
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

    # ---------- NARRATIVES ----------
    org_label = dept.name if dept else 'the organization'

    # Executive summary paragraph
    risk_line = (
        f"{org_label.capitalize()} maintains <strong>{total_risks} active risk"
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

    # Recommendations — auto-generate based on worst signals
    recommendations = []
    if breached_risks:
        recommendations.append({
            'priority': 'high',
            'text': f'Escalate {breached_risks} appetite-breaching risk'
                    f'{"s" if breached_risks != 1 else ""} to the Risk Committee. '
                    f'Review treatment plans and confirm timelines.',
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
    if not recommendations:
        recommendations.append({
            'priority': 'low',
            'text': 'No critical issues detected. Continue monitoring risk and control health on the regular cadence.',
        })

    return {
        # meta
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
        'total_assets': total_assets,
        'critical_assets': critical_assets,
        'total_vendors': total_vendors,
        'tier1_vendors': tier1_vendors,
        'total_policies': total_policies,
        'approved_policies': approved_policies,
        'open_actions': open_actions,
        'overdue_actions': overdue_actions,

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
        'recommendations': recommendations,
    }
