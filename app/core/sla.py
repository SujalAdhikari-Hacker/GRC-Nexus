"""One SLA ladder for findings and tickets.

Critical work gets seven days, then 14, 30, 60 and 90 as severity drops. Audit
findings and vulnerability findings use severity; tickets use priority, which
maps onto the same ladder. Keeping the numbers in one place stops the clocks
from drifting apart.
"""
from datetime import timedelta

SLA_DAYS = {
    'critical': 7,
    'high':     14,
    'medium':   30,
    'low':      60,
    'none':     90,
}

PRIORITY_TO_SEVERITY = {
    4: 'critical',
    3: 'high',
    2: 'medium',
    1: 'low',
}


def sla_due_date(start, severity):
    """Return the SLA due date for a record opened on ``start``."""
    days = SLA_DAYS.get(str(severity or '').lower(), SLA_DAYS['none'])
    return start + timedelta(days=days)
