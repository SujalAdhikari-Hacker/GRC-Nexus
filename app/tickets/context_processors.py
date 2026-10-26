"""
Context processors for the tickets app.

Injects ticket counters into every template's context so the sidebar
can show badges like "Tickets (3)" without modifying every view.
"""


def ticket_counters(request):
    """Add open-ticket counts to the template context for authenticated users."""
    user = getattr(request, 'user', None)
    if user is None or not user.is_authenticated:
        return {}

    from .models import Ticket

    # Base queryset — scoped by department for non-superusers
    base = Ticket.objects.all()
    if not user.is_superuser:
        if not user.department_id:
            return {'open_tickets_count': 0, 'my_tickets_count': 0, 'available_tickets_count': 0}
        base = base.filter(owner_dept=user.department)

    open_statuses = ['open', 'assigned', 'in_progress', 'blocked']

    open_count = base.filter(status__in=open_statuses).count()
    my_count = base.filter(
        status__in=open_statuses,
        assigned_to=user,
    ).count()
    available_count = base.filter(
        status='open',
        assigned_to__isnull=True,
    ).count()

    return {
        'open_tickets_count': open_count,
        'my_tickets_count': my_count,
        'available_tickets_count': available_count,
    }