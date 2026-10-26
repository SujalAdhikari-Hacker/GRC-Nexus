"""
Live enrichment from public APIs + cascade to risk register.

APIs used (all free, no auth):
  - NVD:  https://services.nvd.nist.gov/rest/json/cves/2.0?cveId=CVE-XXXX-XXXX
  - EPSS: https://api.first.org/data/v1/epss?cve=CVE-XXXX-XXXX
  - KEV:  https://www.cisa.gov/sites/default/files/feeds/known_exploited_vulnerabilities.json

NVD rate limit: 5 requests per 30 seconds without API key.
"""
import logging
from datetime import datetime

from django.utils import timezone
from core.safe_http import safe_get
from django.db import transaction

from .models import Vulnerability, Finding, compute_composite_score

logger = logging.getLogger(__name__)


NVD_URL = 'https://services.nvd.nist.gov/rest/json/cves/2.0'
EPSS_URL = 'https://api.first.org/data/v1/epss'
KEV_URL = 'https://www.cisa.gov/sites/default/files/feeds/known_exploited_vulnerabilities.json'

HTTP_TIMEOUT = 15


def _severity_from_score(score):
    if score >= 9.0:
        return 'critical'
    if score >= 7.0:
        return 'high'
    if score >= 4.0:
        return 'medium'
    if score > 0:
        return 'low'
    return 'none'


def enrich_from_nvd(vuln):
    """Fetch CVSS score + vector from NIST NVD API."""
    if not vuln.cve_id:
        return {'ok': False, 'error': 'No CVE ID set'}

    try:
        r = safe_get(NVD_URL, params={'cveId': vuln.cve_id}, timeout=HTTP_TIMEOUT)
        r.raise_for_status()
        data = r.json()
    except Exception:
        logger.exception('NVD enrichment failed for vulnerability %s', vuln.pk)
        return {
            'ok': False,
            'error': 'NVD lookup failed. Try again later.',
        }

    items = data.get('vulnerabilities', [])
    if not items:
        return {'ok': False, 'error': f'CVE {vuln.cve_id} not found in NVD'}

    cve = items[0]['cve']
    metrics = cve.get('metrics', {})

    score = None
    vector = ''
    for key in ('cvssMetricV31', 'cvssMetricV30', 'cvssMetricV2'):
        if key in metrics and metrics[key]:
            m = metrics[key][0]['cvssData']
            score = m.get('baseScore')
            vector = m.get('vectorString', '')
            break

    if score is None:
        return {'ok': False, 'error': 'No CVSS score available in NVD'}

    desc = ''
    for d in cve.get('descriptions', []):
        if d.get('lang') == 'en':
            desc = d.get('value', '')
            break

    pub = cve.get('published', '')
    pub_date = None
    if pub:
        try:
            pub_date = datetime.fromisoformat(pub.replace('Z', '+00:00')).date()
        except Exception:
            pass

    refs = '\n'.join(ref.get('url', '') for ref in cve.get('references', []))

    vuln.cvss_score = score
    vuln.cvss_vector = vector
    vuln.cvss_severity = _severity_from_score(float(score))
    if desc:
        vuln.description = desc
    if pub_date:
        vuln.published_date = pub_date
    if refs:
        vuln.references = refs
    vuln.last_enriched = timezone.now()
    vuln.save()

    return {'ok': True, 'message': f'CVSS {score} ({vuln.cvss_severity})'}


def enrich_from_epss(vuln):
    """Fetch EPSS probability from FIRST.org."""
    if not vuln.cve_id:
        return {'ok': False, 'error': 'No CVE ID set'}

    try:
        r = safe_get(EPSS_URL, params={'cve': vuln.cve_id}, timeout=HTTP_TIMEOUT)
        r.raise_for_status()
        data = r.json()
    except Exception:
        logger.exception('EPSS enrichment failed for vulnerability %s', vuln.pk)
        return {
            'ok': False,
            'error': 'EPSS lookup failed. Try again later.',
        }

    items = data.get('data', [])
    if not items:
        return {'ok': False, 'error': f'No EPSS data for {vuln.cve_id}'}

    row = items[0]
    vuln.epss_score = float(row.get('epss', 0))
    vuln.epss_percentile = float(row.get('percentile', 0))
    vuln.last_enriched = timezone.now()
    vuln.save()

    return {'ok': True, 'message': f'EPSS {vuln.epss_score:.4f}'}


def check_cisa_kev(vuln):
    """Check if this CVE is in the CISA Known Exploited Vulnerabilities catalog."""
    if not vuln.cve_id:
        return {'ok': False, 'error': 'No CVE ID set'}

    try:
        r = safe_get(KEV_URL, timeout=HTTP_TIMEOUT)
        r.raise_for_status()
        data = r.json()
    except Exception:
        logger.exception('KEV enrichment failed for vulnerability %s', vuln.pk)
        return {
            'ok': False,
            'error': 'KEV lookup failed. Try again later.',
        }

    for item in data.get('vulnerabilities', []):
        if item.get('cveID', '').upper() == vuln.cve_id.upper():
            vuln.kev_status = True
            due = item.get('dueDate', '')
            if due:
                try:
                    vuln.kev_due_date = datetime.fromisoformat(due).date()
                except Exception:
                    pass
            vuln.last_enriched = timezone.now()
            vuln.save()
            return {'ok': True, 'message': f'In KEV — due {vuln.kev_due_date or "N/A"}'}

    vuln.kev_status = False
    vuln.save()
    return {'ok': True, 'message': 'Not in KEV catalog'}


def enrich_vulnerability(vuln):
    """Run all three enrichments. Return combined result."""
    results = {
        'nvd':  enrich_from_nvd(vuln),
        'epss': enrich_from_epss(vuln),
        'kev':  check_cisa_kev(vuln),
    }
    recalc_findings_for_vuln(vuln)
    return results


def recalc_findings_for_vuln(vuln):
    """Recompute composite score for every finding linked to this vulnerability."""
    for finding in vuln.findings.all():
        finding.composite_score = compute_composite_score(finding)
        finding.save(update_fields=['composite_score'])


# ============================================================
# CASCADE TO RISK REGISTER
# ============================================================

def should_cascade(finding):
    vuln = finding.vulnerability
    asset = finding.asset
    cvss = float(vuln.cvss_score or 0)

    if vuln.kev_status and asset.criticality >= 2:
        return True
    if cvss >= 9.0 and asset.criticality >= 3:
        return True
    return False


def _risk_scoring(finding):
    """Derive (likelihood, impact) for the risk from CVSS / EPSS / KEV."""
    vuln = finding.vulnerability
    cvss = float(vuln.cvss_score or 5.0)
    impact = min(5, max(1, round(cvss / 2)))
    likelihood = 2
    if vuln.kev_status:
        likelihood = 4
    elif vuln.epss_score and float(vuln.epss_score) >= 0.5:
        likelihood = 3
    return likelihood, impact


@transaction.atomic
def cascade_finding_to_risk(finding):
    """Create or refresh the Risk linked to the finding's asset.

    Returns ``(risk, created)`` — the contract used by the manual cascade view.
    Idempotent: re-running refreshes the same risk rather than duplicating it,
    and links it back via ``Risk.source_finding`` for traceability.
    """
    from risks.models import Risk, RiskCategory

    vuln = finding.vulnerability
    asset = finding.asset
    likelihood, impact = _risk_scoring(finding)

    risk = Risk.objects.filter(source_finding=finding).first()
    if risk is None:
        # Back-compat: risks created before the source_finding link existed.
        risk = Risk.objects.filter(
            title__startswith=f"[{vuln.cve_id}]",
            owner_dept=finding.owner_dept,
        ).first()
        if risk is not None and risk.source_finding_id is None:
            risk.source_finding = finding

    created = False
    if risk is None:
        category, _ = RiskCategory.objects.get_or_create(
            name='Information Security',
            defaults={'description': 'Auto-created from vulnerability findings'},
        )
        risk = Risk(
            title=f"[{vuln.cve_id or 'VULN'}] {vuln.title[:150]}",
            category=category,
            owner_dept=finding.owner_dept,
            status='identified',
            treatment_strategy='mitigate',
            identified_date=finding.discovered_date,
            source_finding=finding,
        )
        created = True

    risk.likelihood = likelihood
    risk.impact = impact
    risk.description = (
        f"Auto-generated from finding on asset '{asset.name}'.\n"
        f"CVSS {vuln.cvss_score} · EPSS {vuln.epss_score or 'N/A'} · "
        f"KEV {'yes' if vuln.kev_status else 'no'}\n"
        f"Composite score: {finding.composite_score}\n\n"
        f"Evidence: {(finding.evidence or '')[:500]}"
    )
    risk.save()

    if not risk.assets.filter(pk=asset.pk).exists():
        risk.assets.add(asset)

    return risk, created


def close_risks_for_finding(finding):
    """Close any live risks derived from a finding that is now closed."""
    from risks.models import Risk

    closed = 0
    for risk in Risk.objects.filter(source_finding=finding).exclude(status='closed'):
        risk.status = 'closed'
        note = f"Auto-closed: finding {finding.vulnerability} marked {finding.get_status_display()}."
        risk.closure_notes = f"{risk.closure_notes} {note}".strip() if risk.closure_notes else note
        risk.save(update_fields=['status', 'closed_date', 'closure_notes'])
        closed += 1
    return closed


def sync_finding_cascade(finding):
    """Signal entry point: cascade or close depending on the finding's status.

    Only *open* findings that meet the escalation rule (``should_cascade``)
    raise a risk. A remediated/false-positive finding closes any risk it
    previously raised, and later enrichment of the CVE can no longer
    resurrect a risk for a finding that is already closed.
    """
    from risks.models import Risk

    if finding.status in ('remediated', 'false_positive'):
        return close_risks_for_finding(finding)

    already_raised = Risk.objects.filter(source_finding=finding).exists()
    if should_cascade(finding) or already_raised:
        # Score when the finding qualifies, and keep an already-raised risk in
        # sync if the intel later drifts out of the escalation band (we do not
        # silently drop a risk that someone may be treating).
        return cascade_finding_to_risk(finding)
    return None
