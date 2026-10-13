"""
Notification signal hooks.

Every time certain models are created, we file a notification for the
department (and the assignee if any). Auto-clearing is handled lazily
by notification_registry.
"""
from django.db.models.signals import post_save
from django.dispatch import receiver

from .notifications import create_notification


# ------------------------------------------------------------------
# ASSETS
# ------------------------------------------------------------------
@receiver(post_save, sender='assets.Asset')
def asset_notifications(sender, instance, created, **kwargs):
    if not created:
        return
    dept = instance.owner_dept
    prefix = instance.asset_id or f'AST-{instance.pk:04d}'

    create_notification(
        'asset_needs_vendor',
        f'{prefix} — "{instance.name[:40]}" needs a vendor linked',
        f'/assets/{instance.pk}/edit/',
        dept, instance,
    )
    create_notification(
        'asset_needs_owner',
        f'{prefix} — assign an owner user',
        f'/assets/{instance.pk}/edit/',
        dept, instance,
    )
    create_notification(
        'asset_needs_policies',
        f'{prefix} — link applicable policies',
        f'/assets/{instance.pk}/edit/',
        dept, instance,
    )


# ------------------------------------------------------------------
# RISKS
# ------------------------------------------------------------------
@receiver(post_save, sender='risks.Risk')
def risk_notifications(sender, instance, created, **kwargs):
    if not created:
        return
    dept = instance.owner_dept
    prefix = f'RSK-{instance.pk:04d}'

    create_notification(
        'risk_needs_assessment',
        f'{prefix} — assess "{instance.title[:40]}"',
        f'/risks/{instance.pk}/edit/',
        dept, instance,
    )
    create_notification(
        'risk_needs_controls',
        f'{prefix} — attach mitigating controls',
        f'/risks/{instance.pk}/edit/',
        dept, instance,
    )


# ------------------------------------------------------------------
# VENDORS
# ------------------------------------------------------------------
@receiver(post_save, sender='vendors.Vendor')
def vendor_notifications(sender, instance, created, **kwargs):
    if not created:
        return
    dept = instance.owner_dept
    prefix = instance.vendor_id or f'VEN-{instance.pk:04d}'

    create_notification(
        'vendor_needs_assessment',
        f'{prefix} — "{instance.name[:40]}" needs an assessment',
        f'/vendors/{instance.pk}/',
        dept, instance,
    )


# ------------------------------------------------------------------
# POLICIES
# ------------------------------------------------------------------
@receiver(post_save, sender='policies.Policy')
def policy_notifications(sender, instance, created, **kwargs):
    if not created:
        return
    if instance.status != 'draft':
        return
    dept = instance.owner_dept
    create_notification(
        'policy_needs_approval',
        f'{instance.code} — "{instance.title[:40]}" awaiting approval',
        f'/policies/{instance.pk}/',
        dept, instance,
    )


# ------------------------------------------------------------------
# CONTROLS
# ------------------------------------------------------------------
@receiver(post_save, sender='controls.Control')
def control_notifications(sender, instance, created, **kwargs):
    if not created:
        return
    dept = instance.owner_dept

    if instance.effectiveness_rating == 'not_tested' and instance.status == 'implemented':
        create_notification(
            'control_needs_testing',
            f'{instance.code} — control is implemented but never tested',
            f'/controls/{instance.pk}/',
            dept, instance,
        )
    if not instance.framework_controls.exists():
        create_notification(
            'control_needs_mapping',
            f'{instance.code} — link to a framework requirement',
            f'/controls/{instance.pk}/edit/',
            dept, instance,
        )


# ------------------------------------------------------------------
# KRIs
# ------------------------------------------------------------------
@receiver(post_save, sender='kris.KRI')
def kri_notifications(sender, instance, created, **kwargs):
    if not created:
        return
    create_notification(
        'kri_needs_reading',
        f'"{instance.name[:50]}" — record the first reading',
        f'/kris/{instance.pk}/',
        instance.owner_dept, instance,
    )


# ------------------------------------------------------------------
# AUDITS
# ------------------------------------------------------------------
@receiver(post_save, sender='audits.Audit')
def audit_notifications(sender, instance, created, **kwargs):
    if not created:
        return
    create_notification(
        'audit_needs_lead',
        f'Audit "{instance.name[:40]}" needs an auditor lead',
        f'/audits/{instance.pk}/edit/',
        instance.owner_dept, instance,
    )


@receiver(post_save, sender='audits.AuditFinding')
def finding_notifications(sender, instance, created, **kwargs):
    if not created:
        return
    dept = instance.owner_dept
    create_notification(
        'finding_needs_owner',
        f'Finding "{instance.title[:40]}" — assign an owner',
        f'/audits/findings/{instance.pk}/edit/',
        dept, instance,
    )
    create_notification(
        'finding_needs_actions',
        f'Finding "{instance.title[:40]}" — create remediation actions',
        f'/audits/findings/{instance.pk}/',
        dept, instance,
    )


# ------------------------------------------------------------------
# ACTION ITEMS
# ------------------------------------------------------------------
@receiver(post_save, sender='audits.ActionItem')
def action_notifications(sender, instance, created, **kwargs):
    if not created:
        return
    create_notification(
        'action_needs_owner',
        f'{instance.action_id} — assign an owner',
        f'/audits/actions/{instance.pk}/edit/',
        instance.owner_dept, instance,
    )


# ------------------------------------------------------------------
# TICKETS
# ------------------------------------------------------------------
@receiver(post_save, sender='tickets.Ticket')
def ticket_notifications(sender, instance, created, **kwargs):
    if not created:
        return
    if instance.assigned_to_id is not None:
        return
    create_notification(
        'ticket_unassigned',
        f'{instance.ticket_id} — "{instance.title[:40]}" needs an assignee',
        f'/tickets/{instance.pk}/',
        instance.owner_dept, instance,
    )
