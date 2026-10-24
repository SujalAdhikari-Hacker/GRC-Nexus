"""
Pending actions engine.

Each function returns {'count': N, 'label': 'description'}.
Callers pass (dept, is_super) for department scoping.

Scoping rule (shared): superusers see everything; a user with a department
sees that department; a user with no department sees *nothing* — never the
whole organisation.
"""
from datetime import timedelta

from django.utils import timezone


def _scoped(qs, dept, is_super, field='owner_dept'):
    if is_super:
        return qs
    if not dept:
        return qs.none()
    return qs.filter(**{field: dept})


def pending_assets(dept=None, is_super=False):
    from assets.models import Asset
    qs = _scoped(
        Asset.objects.filter(
            is_active=True,
            owner_user__isnull=True,
            criticality__gte=3,
        ),
        dept, is_super,
    )
    return {
        'count': qs.count(),
        'label': 'high-criticality assets without an assigned owner',
    }


def pending_vendors(dept=None, is_super=False):
    from vendors.models import Vendor, VendorAssessment
    twelve_months_ago = timezone.localdate() - timedelta(days=365)
    recent_ids = VendorAssessment.objects.filter(
        assessment_date__gte=twelve_months_ago
    ).values_list('vendor_id', flat=True)
    qs = _scoped(Vendor.objects.filter(status='active'), dept, is_super)
    qs = qs.exclude(pk__in=recent_ids)
    return {
        'count': qs.count(),
        'label': 'active vendors with no assessment in the last 12 months',
    }


def pending_policies(dept=None, is_super=False):
    from policies.models import Policy
    today = timezone.localdate()
    threshold = today + timedelta(days=30)
    qs = _scoped(
        Policy.objects.filter(
            status='approved',
            next_review_date__isnull=False,
            next_review_date__lte=threshold,
        ),
        dept, is_super,
    )
    return {
        'count': qs.count(),
        'label': 'approved policies due for review within 30 days',
    }


def pending_controls(dept=None, is_super=False):
    from controls.models import Control
    qs = _scoped(
        Control.objects.filter(
            status='implemented',
            effectiveness_rating='not_tested',
        ),
        dept, is_super,
    )
    return {
        'count': qs.count(),
        'label': 'implemented controls never tested',
    }


def pending_risks(dept=None, is_super=False):
    from risks.models import Risk
    qs = _scoped(Risk.objects.filter(status='identified'), dept, is_super)
    return {
        'count': qs.count(),
        'label': 'risks awaiting assessment',
    }


def pending_kris(dept=None, is_super=False):
    from kris.models import KRI, KRIReading
    thirty_days_ago = timezone.localdate() - timedelta(days=30)
    recent_ids = KRIReading.objects.filter(
        reading_date__gte=thirty_days_ago
    ).values_list('kri_id', flat=True)
    qs = _scoped(KRI.objects.all(), dept, is_super).exclude(pk__in=recent_ids)
    return {
        'count': qs.count(),
        'label': 'KRIs with no reading in the last 30 days',
    }


def pending_audits(dept=None, is_super=False):
    from audits.models import AuditFinding
    qs = _scoped(
        AuditFinding.objects.exclude(
            status__in=['resolved', 'closed', 'accepted']
        ).filter(owner_user__isnull=True),
        dept, is_super,
    )
    return {
        'count': qs.count(),
        'label': 'open findings with no assigned owner',
    }


def all_pending(dept=None, is_super=False):
    """Return a dict of every pending category."""
    return {
        'assets':   pending_assets(dept, is_super),
        'vendors':  pending_vendors(dept, is_super),
        'policies': pending_policies(dept, is_super),
        'controls': pending_controls(dept, is_super),
        'risks':    pending_risks(dept, is_super),
        'kris':     pending_kris(dept, is_super),
        'audits':   pending_audits(dept, is_super),
    }
