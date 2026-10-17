"""Signals for the vulnerability → risk cascade.

Every finding save refreshes the risk it maps to (see services.cascade_finding_to_risk).
"""
from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver

from .models import Finding, Vulnerability


@receiver(post_save, sender=Finding)
def finding_cascade_to_risk(sender, instance, **kwargs):
    """CASCADE: a finding creates/updates (or closes) its linked risk."""
    from .services import sync_finding_cascade
    sync_finding_cascade(instance)


@receiver(post_save, sender=Vulnerability)
def vulnerability_enrich_cascade(sender, instance, **kwargs):
    """Re-score the risks of every finding when the CVE's intel changes.

    Keeps the register honest when a CVE is later added to KEV or its EPSS
    score moves. Delegates to ``sync_finding_cascade`` so a finding that is
    already remediated (or that never met the escalation rule) is *not*
    re-cascaded into a fresh open risk.
    """
    from .services import sync_finding_cascade
    for finding in instance.findings.all():
        sync_finding_cascade(finding)
