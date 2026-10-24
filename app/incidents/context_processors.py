"""
Context processor for the incidents app.

Injects open-incident counters into every template so the sidebar shows a
badge on *Incidents* the same way tickets do.
"""


def incident_counters(request):
    """Add open-incident counts to the template context for authenticated users."""
    if not request.user.is_authenticated:
        return {}

    from .models import Incident

    user = request.user
    base = Incident.objects.all()
    if not user.is_superuser:
        if not user.department_id:
            return {'open_incidents_count': 0, 'open_incidents_critical': False}
        base = base.filter(owner_dept=user.department)

    open_count = base.exclude(status='closed').count()
    critical_open = base.exclude(status='closed').filter(
        severity='critical'
    ).exists()

    return {
        'open_incidents_count': open_count,
        'open_incidents_critical': critical_open,
    }
