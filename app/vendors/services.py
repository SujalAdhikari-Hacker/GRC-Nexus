"""Supplier assurance scoring — NIS2 Art. 18 and Art. 21(2)(d).

Five components sum to 100 points. A vendor starts at 0 and earns points for
demonstrated assurance, so **higher is better** and ``band`` describes the
resulting supplier risk. The formula is published rather than hidden so an
auditor can reproduce any score by hand:

    certifications   max 25   ISO27001 12, SOC2 10, PCIDSS 6, ISO22301 6,
                              CSA-STAR 6, TISAX 6, ISO9001 3 (capped at 25)
    contract         max 30   security clauses 12, audit rights 10, SLA 5,
                              breach notification <= 24h 3; zeroed entirely
                              when the contract renewal date has passed
    assessment       max 20   within 12 months 20, 24 months 12, 36 months 5
    data exposure    max 15   inverted: no access 15 ... restricted 0
    jurisdiction     max 10   EU/EEA 10, third country 3, unconfirmed 0

The function reads plain attributes, so it scores saved rows and unsaved input
identically and can be tested without the database.
"""
from dataclasses import dataclass
from datetime import date

# key -> (label, points). One source of truth for the formula and the form.
CERTIFICATIONS = {
    'ISO27001': ('ISO/IEC 27001', 12),
    'SOC2': ('SOC 2', 10),
    'PCIDSS': ('PCI DSS', 6),
    'ISO22301': ('ISO 22301', 6),
    'CSA-STAR': ('CSA STAR', 6),
    'TISAX': ('TISAX', 6),
    'ISO9001': ('ISO 9001', 3),
}
CERTIFICATION_POINTS = {
    key: points for key, (_label, points) in CERTIFICATIONS.items()
}
CERTIFICATION_CHOICES = tuple(
    (key, label) for key, (label, _points) in CERTIFICATIONS.items()
)

MAX_CERTIFICATION_POINTS = 25
MAX_CONTRACT_POINTS = 30
MAX_AUDIT_POINTS = 20
MAX_DATA_ACCESS_POINTS = 15
MAX_GEOGRAPHY_POINTS = 10

# Vendor.data_sensitivity: 0 no access, 1 public, 2 internal, 3 confidential,
# 4 restricted. Inverted: the less the vendor can reach, the more points.
DATA_ACCESS_POINTS = {0: 15, 1: 13, 2: 9, 3: 4, 4: 0}
DATA_ACCESS_LABELS = {
    0: 'No access',
    1: 'Public',
    2: 'Internal',
    3: 'Confidential',
    4: 'Restricted',
}

# (max age in days, points) — first band that fits wins.
AUDIT_RECENCY_BANDS = ((365, 20), (730, 12), (1095, 5))

# Supplier-risk bands, highest threshold first.
BAND_THRESHOLDS = ((80, 'low'), (60, 'moderate'), (40, 'elevated'), (0, 'high'))
BAND_LABELS = {
    'low': 'Low risk',
    'moderate': 'Moderate risk',
    'elevated': 'Elevated risk',
    'high': 'High risk',
}
BAND_CSS = {
    'low': 'bg-success',
    'moderate': 'bg-info text-dark',
    'elevated': 'bg-warning text-dark',
    'high': 'bg-danger',
}

# Suppliers this critical are expected to clear a higher bar.
TIER_EXPECTED_SCORE = {1: 80, 2: 65, 3: 50}


@dataclass(frozen=True)
class ScoreComponent:
    key: str
    label: str
    max_points: int
    awarded: int
    rationale: str


@dataclass(frozen=True)
class VendorScore:
    score: int
    band: str
    components: tuple
    flags: tuple

    @property
    def band_label(self):
        return BAND_LABELS[self.band]

    @property
    def band_css(self):
        return BAND_CSS[self.band]


def band_for_score(score):
    for threshold, band in BAND_THRESHOLDS:
        if score >= threshold:
            return band
    return 'high'


def _score_certifications(certifications):
    held = sorted({
        c for c in (certifications or []) if c in CERTIFICATION_POINTS
    })
    awarded = min(
        sum(CERTIFICATION_POINTS[c] for c in held), MAX_CERTIFICATION_POINTS
    )
    if held:
        rationale = (
            f"{', '.join(held)} (capped at {MAX_CERTIFICATION_POINTS})"
        )
    else:
        rationale = 'No recognised certification on record'
    return ScoreComponent(
        'certifications', 'Certifications',
        MAX_CERTIFICATION_POINTS, awarded, rationale,
    )


def _score_contract(vendor, today):
    held = []
    awarded = 0
    if vendor.security_clauses:
        awarded += 12
        held.append('security clauses')
    if vendor.audit_rights:
        awarded += 10
        held.append('audit rights')
    if vendor.sla_defined:
        awarded += 5
        held.append('defined SLA')
    hours = vendor.breach_notification_hours
    if hours is not None and hours <= 24:
        awarded += 3
        held.append(f'{hours}h breach notification')

    renewal = vendor.contract_renewal_date
    if renewal and renewal < today:
        return ScoreComponent(
            'contract', 'Contractual controls', MAX_CONTRACT_POINTS, 0,
            'Contract expired — contractual controls are not enforceable',
        )
    return ScoreComponent(
        'contract', 'Contractual controls', MAX_CONTRACT_POINTS,
        min(awarded, MAX_CONTRACT_POINTS),
        ', '.join(held) or 'No security terms recorded in the contract',
    )


def _score_assessment_recency(last_assessed_on, today):
    if not last_assessed_on:
        return ScoreComponent(
            'assessment', 'Assessment recency', MAX_AUDIT_POINTS, 0,
            'Never assessed',
        )
    age_days = (today - last_assessed_on).days
    for max_age, points in AUDIT_RECENCY_BANDS:
        if age_days <= max_age:
            return ScoreComponent(
                'assessment', 'Assessment recency', MAX_AUDIT_POINTS, points,
                f'Last assessed {age_days} days ago',
            )
    return ScoreComponent(
        'assessment', 'Assessment recency', MAX_AUDIT_POINTS, 0,
        f'Last assessed {age_days} days ago — stale',
    )


def _score_data_access(level):
    points = DATA_ACCESS_POINTS.get(level, 0)
    label = DATA_ACCESS_LABELS.get(level, 'Unknown')
    return ScoreComponent(
        'data_access', 'Data exposure', MAX_DATA_ACCESS_POINTS, points,
        f'Vendor data access level: {label}',
    )


def _score_jurisdiction(jurisdiction):
    if jurisdiction == 'eu':
        return ScoreComponent(
            'jurisdiction', 'Jurisdiction', MAX_GEOGRAPHY_POINTS,
            MAX_GEOGRAPHY_POINTS, 'EU / EEA jurisdiction',
        )
    if jurisdiction == 'third':
        return ScoreComponent(
            'jurisdiction', 'Jurisdiction', MAX_GEOGRAPHY_POINTS, 3,
            'Third-country jurisdiction — transfer safeguards required',
        )
    return ScoreComponent(
        'jurisdiction', 'Jurisdiction', MAX_GEOGRAPHY_POINTS, 0,
        'Jurisdiction not confirmed',
    )


def score_vendor(vendor, today=None):
    """Score a vendor object (saved or unsaved) from 0 to 100."""
    today = today or date.today()
    components = (
        _score_certifications(vendor.certifications),
        _score_contract(vendor, today),
        _score_assessment_recency(vendor.last_assessment_date, today),
        _score_data_access(vendor.data_sensitivity),
        _score_jurisdiction(vendor.jurisdiction),
    )
    score = sum(c.awarded for c in components)
    flags = []

    expected = TIER_EXPECTED_SCORE.get(vendor.tier)
    if expected is not None and score < expected:
        flags.append(
            f'Score {score} is below the {expected}-point expectation '
            f'for a Tier {vendor.tier} supplier'
        )
    if vendor.contract_renewal_date and vendor.contract_renewal_date < today:
        flags.append('Contract has expired')
    if not vendor.audit_rights and vendor.tier in (1, 2):
        flags.append('Critical supplier without contractual audit rights')
    if vendor.data_sensitivity in (3, 4) and not vendor.security_clauses:
        flags.append(
            'Access to sensitive data without contractual security clauses'
        )
    if vendor.jurisdiction == 'third' and vendor.data_sensitivity != 0:
        flags.append(
            'Third-country supplier with data access — verify transfer mechanism'
        )
    if vendor.jurisdiction == 'unknown':
        flags.append('Jurisdiction not confirmed')

    return VendorScore(
        score=score,
        band=band_for_score(score),
        components=components,
        flags=tuple(flags),
    )
