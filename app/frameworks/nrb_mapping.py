"""Suggested crosswalk from the NRB catalogues to the control library.

A topic match is not an assurance statement. It proposes the control that most
likely addresses a requirement so a reviewer starts from a shortlist instead
of a blank page. Every mapping it creates is therefore ``intersects`` (partial
overlap) and carries a note saying it was suggested, not assessed.

Requirements that already have any mapping are left alone, so re-seeding never
overwrites a reviewer's work.
"""
import re

from controls.models import Control, ControlFrameworkMapping

REVIEW_NOTE = (
    'Suggested by topic match (seed_nrb_frameworks); '
    'review before relying on it.'
)

# (control name/code pattern, requirement text pattern)
RULES = (
    (r'multi-factor|\bmfa\b|two-factor',
     r'multi-factor|two-factor|strong authentication|authentication'),
    (r'privileged',
     r'privileged|administrator|admin access|least privilege|segregation of duties'),
    (r'access control|identity',
     r'access control|access right|user access|account management|identity management'),
    (r'\blogging\b|\blog\b',
     r'\blog\b|logging|audit trail|record keeping|retention'),
    (r'awareness|training',
     r'training|awareness|competenc|skill'),
    (r'backup|recovery',
     r'backup|restore'),
    (r'continuity|disaster',
     r'continuity|disaster|business impact|recovery plan|recovery strateg'),
    (r'loss prevention|\bdlp\b',
     r'data loss|exfiltrat|leak|confidential|unauthori[sz]ed disclosure|personal data|personal information'),
    (r'encrypt|cryptograph',
     r'encrypt|cryptograph|key management'),
    (r'incident',
     r'incident|cyber attack|breach|report.{0,40}(nrb|regulator)'),
    (r'monitoring|\bsiem\b',
     r'security monitoring|monitor.{0,30}(security|threat|event|anomal)|detect|anomal|threat intelligence'),
    (r'network|firewall|segment',
     r'network|firewall|segment|perimeter|remote access'),
    (r'patch',
     r'patch|software update|security update'),
    (r'physical',
     r'physical|premises|data cent|facilit|site security'),
    (r'vendor|third.party|supplier',
     r'third.party|vendor|supplier|outsourc|service provider'),
    (r'vulnerabilit|scanning|penetration',
     r'vulnerabilit|penetration test|scan'),
)


def suggest_mappings(frameworks):
    """Create the suggested mappings for requirements that have none yet."""
    controls = list(Control.objects.all())
    if not controls:
        return 0

    control_index = [
        (control, f'{control.code} {control.name}'.lower())
        for control in controls
    ]

    created = 0
    for framework in frameworks:
        for requirement in framework.controls.all():
            if requirement.control_mappings.exists():
                continue
            text = f'{requirement.title} {requirement.description}'.lower()
            for control_pattern, requirement_pattern in RULES:
                if not re.search(requirement_pattern, text):
                    continue
                for control, control_text in control_index:
                    if not re.search(control_pattern, control_text):
                        continue
                    _mapping, was_created = ControlFrameworkMapping.objects.get_or_create(
                        control=control,
                        framework_control=requirement,
                        defaults={
                            'relationship': 'intersects',
                            'notes': REVIEW_NOTE,
                        },
                    )
                    created += was_created
    return created
