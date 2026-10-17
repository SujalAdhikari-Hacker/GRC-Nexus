"""Trend computation for the dashboard and reports.

All month bucketing uses real calendar months (never 30-day approximations,
which skip or duplicate months around month ends).
"""
from datetime import datetime

from django.db.models import Avg, Count
from django.db.models.functions import TruncMonth
from django.utils import timezone


def _add_months(day, delta):
    """Return the first day of the month ``delta`` months from ``day``."""
    month_index = day.month - 1 + delta
    year = day.year + month_index // 12
    month = month_index % 12 + 1
    return day.replace(year=year, month=month, day=1)


def month_bounds(today, months_back):
    """Return ``(start, end)`` covering the calendar month ``months_back`` ago."""
    start = _add_months(today.replace(day=1), -months_back)
    end = _add_months(start, 1)
    return start, end


def iter_month_bounds(today, months):
    """Yield ``(start, end)`` oldest-first for the last ``months`` calendar months."""
    for i in range(months - 1, -1, -1):
        yield month_bounds(today, i)


def _month_bucket(value):
    """Normalise a ``TruncMonth`` result to the first day of its month (date)."""
    if value is None:
        return None
    if isinstance(value, datetime):
        value = value.date()
    return value.replace(day=1)


def _per_month(queryset, date_field, **aggregates):
    """Return ``{month_start_date: {agg: value}}`` in a single GROUP BY query."""
    rows = (
        queryset
        .annotate(_bucket=TruncMonth(date_field))
        .values('_bucket')
        .annotate(**aggregates)
    )
    result = {}
    for row in rows:
        key = _month_bucket(row['_bucket'])
        if key is not None:
            result[key] = row
    return result


def compute_trends(risks, findings, actions, months=6):
    """Build N-month trend arrays for the dashboard charts.

    The inherent/residual trend is the average score of the *cohort* of risks
    created in each month. This is a stable, non-misleading metric — unlike a
    cumulative snapshot, it does not silently change as today's data changes.

    Five GROUP BY queries in total (one per metric), rather than five queries
    per month: the previous implementation issued ~30 queries per page load.
    """
    today = timezone.now().date()

    created = _per_month(
        risks, 'created_at',
        n=Count('id'), i=Avg('inherent_score'), r=Avg('residual_score'),
    )
    closed = _per_month(risks, 'closed_date', n=Count('id'))
    remediated = _per_month(findings, 'remediated_date', n=Count('id'))
    completed = _per_month(actions, 'completed_date', n=Count('id'))

    labels = []
    inherent_trend = []
    residual_trend = []
    risks_created = []
    risks_closed = []
    findings_remediated = []
    actions_completed = []

    for start, _end in iter_month_bounds(today, months):
        labels.append(start.strftime('%b %Y'))
        row = created.get(start, {})
        inherent_trend.append(round(row.get('i') or 0, 1))
        residual_trend.append(round(row.get('r') or 0, 1))
        risks_created.append(row.get('n', 0))
        risks_closed.append(closed.get(start, {}).get('n', 0))
        findings_remediated.append(remediated.get(start, {}).get('n', 0))
        actions_completed.append(completed.get(start, {}).get('n', 0))

    return {
        'trend_labels': labels,
        'risk_inherent_trend': inherent_trend,
        'risk_residual_trend': residual_trend,
        'risks_created_trend': risks_created,
        'risks_closed_trend': risks_closed,
        'findings_remediated_trend': findings_remediated,
        'actions_completed_trend': actions_completed,
    }
