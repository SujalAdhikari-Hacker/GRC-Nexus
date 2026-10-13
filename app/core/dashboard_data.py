"""
Trend computation for the dashboard.
"""
import json
from datetime import timedelta
from django.db.models import Avg
from django.utils import timezone


def _month_bounds(today, months_back):
    """Return (start, end) for the month N months before today."""
    target = (today.replace(day=1) - timedelta(days=months_back * 30)).replace(day=1)
    next_month = (target + timedelta(days=32)).replace(day=1)
    return target, next_month


def compute_trends(risks, findings, actions, months=6):
    """Build N-month trend arrays for the dashboard charts."""
    today = timezone.now().date()

    labels = []
    inherent_trend = []
    residual_trend = []
    risks_created = []
    risks_closed = []
    findings_remediated = []
    actions_completed = []
    open_findings_cumulative = []
    open_actions_cumulative = []

    for i in range(months - 1, -1, -1):
        start, end = _month_bounds(today, i)
        labels.append(start.strftime('%b %Y'))

        snapshot = risks.filter(created_at__date__lt=end).exclude(status='closed')
        agg = snapshot.aggregate(i=Avg('inherent_score'), r=Avg('residual_score'))
        inherent_trend.append(round(agg['i'] or 0, 1))
        residual_trend.append(round(agg['r'] or 0, 1))

        risks_created.append(
            risks.filter(created_at__date__gte=start, created_at__date__lt=end).count()
        )
        risks_closed.append(
            risks.filter(closed_date__gte=start, closed_date__lt=end).count()
        )

        findings_remediated.append(
            findings.filter(remediated_date__gte=start, remediated_date__lt=end).count()
        )
        actions_completed.append(
            actions.filter(completed_date__gte=start, completed_date__lt=end).count()
        )

        open_findings_cumulative.append(
            findings.filter(created_at__date__lt=end)
            .exclude(status__in=['remediated', 'false_positive'])
            .count()
        )
        open_actions_cumulative.append(
            actions.filter(created_at__date__lt=end)
            .exclude(status__in=['completed', 'cancelled'])
            .count()
        )

    return {
        'trend_labels_json': json.dumps(labels),
        'risk_inherent_trend_json': json.dumps(inherent_trend),
        'risk_residual_trend_json': json.dumps(residual_trend),
        'risks_created_trend_json': json.dumps(risks_created),
        'risks_closed_trend_json': json.dumps(risks_closed),
        'findings_remediated_trend_json': json.dumps(findings_remediated),
        'actions_completed_trend_json': json.dumps(actions_completed),
        'open_findings_trend_json': json.dumps(open_findings_cumulative),
        'open_actions_trend_json': json.dumps(open_actions_cumulative),
    }