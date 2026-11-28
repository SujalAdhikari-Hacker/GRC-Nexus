"""Import vulnerability findings from CSV and JSON scanner outputs.

Supports pure-Python parsing of:
  - Generic / Nessus / OpenVAS / Qualys / Trivy CSV exports
  - Flat or wrapped JSON finding lists (``list``, or dict with
    ``findings`` / ``vulnerabilities`` / ``results``)
  - Trivy JSON reports (``Results[].Vulnerabilities[]``)
  - SARIF 2.1.0 JSON reports (``runs[].results[]``)

Every created or updated Finding is strictly scoped to assets the importing
user has write access to via ``writable_queryset``.
"""
import csv
import json
import re
from decimal import Decimal, InvalidOperation
from io import StringIO

from django.db import transaction
from django.utils import timezone
from django.utils.dateparse import parse_date, parse_datetime

from assets.models import Asset
from core.mixins import writable_queryset

from .models import Finding, Vulnerability

MAX_SCAN_UPLOAD_BYTES = 5 * 1024 * 1024
MAX_SCAN_ROWS = 5000

_CVE_RE = re.compile(r'CVE-\d{4}-\d{4,}', re.IGNORECASE)

_SEVERITY_MAP = {
    'critical': 'critical',
    'crit': 'critical',
    'high': 'high',
    'medium': 'medium',
    'med': 'medium',
    'moderate': 'medium',
    'low': 'low',
    'none': 'none',
    'info': 'none',
    'informational': 'none',
    'note': 'none',
}

_DEFAULT_CVSS = {
    'critical': Decimal('9.5'),
    'high': Decimal('7.5'),
    'medium': Decimal('5.0'),
    'low': Decimal('2.5'),
    'none': Decimal('0.0'),
}

_VALID_FINDING_STATUSES = {key for key, _ in Finding.STATUS_CHOICES}

_ALIASES = {
    'cve': ('cve', 'cve_id', 'cveid', 'vulnerability_id', 'vulnerabilityid'),
    'title': ('title', 'name', 'plugin_name', 'nvt_name', 'summary', 'vulnerability', 'pkgname', 'pkg_name'),
    'asset': ('asset', 'asset_id', 'host', 'hostname', 'ip', 'ip_address', 'target', 'fqdn', 'asset_name'),
    'port': ('port', 'service_port'),
    'severity': ('severity', 'risk', 'risk_factor', 'cvss_severity', 'threat', 'level'),
    'cvss': ('cvss', 'cvss_score', 'cvss3_base_score', 'cvss_v3_base_score', 'cvss_base_score', 'score'),
    'description': ('description', 'synopsis', 'details'),
    'solution': ('solution', 'remediation', 'fix', 'fixed_version', 'fixedversion'),
    'evidence': ('evidence', 'plugin_output', 'output', 'proof', 'result', 'message'),
    'discovered_date': ('discovered_date', 'first_found', 'detected_at', 'date'),
    'status': ('status',),
}


def _norm_key(key):
    return re.sub(r'[\s.\-]+', '_', str(key or '').strip().lower()).strip('_')


def _pick(norm_dict, field_group):
    for key in _ALIASES[field_group]:
        val = norm_dict.get(key)
        if val is not None and str(val).strip() != '':
            return val
    return None


def _normalize_cve(raw):
    if not raw:
        return None
    if isinstance(raw, (list, tuple)):
        for item in raw:
            found = _normalize_cve(item)
            if found:
                return found
        return None
    match = _CVE_RE.search(str(raw))
    return match.group(0).upper() if match else None


def _normalize_severity(raw, cvss=None):
    if raw is not None:
        key = str(raw).strip().lower()
        if key in _SEVERITY_MAP:
            return _SEVERITY_MAP[key]
    if cvss is not None:
        try:
            score = float(cvss)
            if score >= 9.0:
                return 'critical'
            if score >= 7.0:
                return 'high'
            if score >= 4.0:
                return 'medium'
            if score > 0:
                return 'low'
            return 'none'
        except (TypeError, ValueError):
            pass
    return 'medium'


def _normalize_cvss(raw, severity):
    if raw is not None and str(raw).strip() != '':
        try:
            val = Decimal(str(raw).strip())
            if val < 0:
                val = Decimal('0.0')
            elif val > 10:
                val = Decimal('10.0')
            return val.quantize(Decimal('0.1'))
        except (InvalidOperation, ValueError):
            pass
    return _DEFAULT_CVSS.get(severity, Decimal('5.0'))


def _normalize_date(raw):
    if raw is None or str(raw).strip() == '':
        return timezone.localdate()
    text = str(raw).strip()
    dt = parse_datetime(text)
    if dt is not None:
        return dt.date()
    day = parse_date(text)
    if day is not None:
        return day
    return timezone.localdate()


def _normalize_port(raw):
    if raw is None:
        return ''
    text = str(raw).strip()
    if text.lower() in ('', '0', 'none', 'general/tcp', 'general/udp'):
        return ''
    return text[:20]


def _normalize_mapping(item):
    if not isinstance(item, dict):
        raise ValueError('Each finding record must be an object/mapping.')
    norm = {_norm_key(k): v for k, v in item.items()}
    raw_cvss = _pick(norm, 'cvss')
    severity = _normalize_severity(_pick(norm, 'severity'), cvss=raw_cvss)
    cvss = _normalize_cvss(raw_cvss, severity)
    if _pick(norm, 'severity') is None and raw_cvss is not None:
        severity = _normalize_severity(None, cvss=cvss)

    cve_id = _normalize_cve(_pick(norm, 'cve'))
    title_raw = _pick(norm, 'title')
    if not cve_id and title_raw:
        cve_id = _normalize_cve(title_raw)
    title = str(title_raw or cve_id or '').strip()[:500]

    raw_status = str(_pick(norm, 'status') or 'new').strip().lower()
    status = raw_status if raw_status in _VALID_FINDING_STATUSES else 'new'

    return {
        'cve_id': cve_id,
        'title': title,
        'asset': str(_pick(norm, 'asset') or '').strip(),
        'port': _normalize_port(_pick(norm, 'port')),
        'severity': severity,
        'cvss_score': cvss,
        'description': str(_pick(norm, 'description') or '').strip(),
        'solution': str(_pick(norm, 'solution') or '').strip(),
        'evidence': str(_pick(norm, 'evidence') or '').strip(),
        'discovered_date': _normalize_date(_pick(norm, 'discovered_date')),
        'status': status,
    }


def parse_scanner_csv(text):
    """Parse scanner CSV text into normalized finding dictionaries."""
    if not text or not text.strip():
        return []
    reader = csv.DictReader(StringIO(text))
    if not reader.fieldnames:
        raise ValueError('CSV file has no header row.')
    rows = []
    for raw_row in reader:
        if len(rows) >= MAX_SCAN_ROWS:
            raise ValueError(f'Scan exceeds the maximum of {MAX_SCAN_ROWS} rows.')
        if not any(str(v or '').strip() for v in raw_row.values()):
            continue
        rows.append(_normalize_mapping(raw_row))
    return rows


def _extract_trivy_cvss(vuln):
    cvss_map = vuln.get('CVSS') or {}
    if isinstance(cvss_map, dict):
        scores = []
        for entry in cvss_map.values():
            if isinstance(entry, dict):
                for key in ('V3Score', 'V2Score'):
                    if entry.get(key) is not None:
                        scores.append(entry[key])
        if scores:
            return max(scores, key=lambda v: float(v))
    return vuln.get('CvssScore')


def _parse_trivy_json(data):
    rows = []
    for result in data.get('Results') or []:
        if not isinstance(result, dict):
            continue
        target = str(result.get('Target') or data.get('ArtifactName') or '').strip()
        for vuln in result.get('Vulnerabilities') or []:
            if len(rows) >= MAX_SCAN_ROWS:
                raise ValueError(f'Scan exceeds the maximum of {MAX_SCAN_ROWS} rows.')
            if not isinstance(vuln, dict):
                continue
            pkg = vuln.get('PkgName') or ''
            installed = vuln.get('InstalledVersion') or ''
            fixed = vuln.get('FixedVersion') or ''
            solution = f'Upgrade {pkg} to {fixed}'.strip() if fixed and pkg else fixed
            evidence = f'Package: {pkg} {installed}'.strip() if pkg else ''
            rows.append(_normalize_mapping({
                'cve_id': vuln.get('VulnerabilityID'),
                'title': vuln.get('Title') or (f'{vuln.get("VulnerabilityID")} in {pkg}'.strip() if pkg else ''),
                'asset': target,
                'severity': vuln.get('Severity'),
                'cvss': _extract_trivy_cvss(vuln),
                'description': vuln.get('Description') or '',
                'solution': solution,
                'evidence': evidence,
            }))
    return rows


def _parse_sarif_json(data):
    _sarif_level_map = {'error': 'high', 'warning': 'medium', 'note': 'low', 'none': 'none'}
    rows = []
    for run in data.get('runs') or []:
        if not isinstance(run, dict):
            continue
        driver = ((run.get('tool') or {}).get('driver') or {})
        rules = {}
        for rule in driver.get('rules') or []:
            if isinstance(rule, dict) and rule.get('id'):
                rules[rule['id']] = rule

        for res in run.get('results') or []:
            if len(rows) >= MAX_SCAN_ROWS:
                raise ValueError(f'Scan exceeds the maximum of {MAX_SCAN_ROWS} rows.')
            if not isinstance(res, dict):
                continue
            rule_id = res.get('ruleId') or ''
            rule_meta = rules.get(rule_id) or {}
            props = {**(rule_meta.get('properties') or {}), **(res.get('properties') or {})}
            msg = ((res.get('message') or {}).get('text') or '').strip()
            short_desc = ((rule_meta.get('shortDescription') or {}).get('text') or '').strip()
            full_desc = ((rule_meta.get('fullDescription') or {}).get('text') or '').strip()

            artifact_uri = ''
            locations = res.get('locations') or []
            if locations and isinstance(locations[0], dict):
                phys = locations[0].get('physicalLocation') or {}
                artifact_uri = ((phys.get('artifactLocation') or {}).get('uri') or '').strip()

            cve_id = _normalize_cve([rule_id, msg, short_desc, props.get('tags')])
            raw_sev = props.get('severity') or _sarif_level_map.get(str(res.get('level') or '').lower())
            raw_cvss = props.get('security-severity') or props.get('cvss')

            rows.append(_normalize_mapping({
                'cve_id': cve_id,
                'title': short_desc or rule_meta.get('name') or rule_id or msg[:120],
                'asset': artifact_uri,
                'severity': raw_sev,
                'cvss': raw_cvss,
                'description': full_desc or short_desc,
                'evidence': msg,
            }))
    return rows


def parse_scanner_json(text):
    """Parse JSON scanner output (flat list, wrapped list, Trivy, or SARIF 2.1.0)."""
    data = json.loads(text)
    if isinstance(data, dict):
        if 'runs' in data and isinstance(data.get('runs'), list):
            return _parse_sarif_json(data)
        if 'Results' in data and isinstance(data.get('Results'), list):
            return _parse_trivy_json(data)
        for key in ('findings', 'vulnerabilities', 'results'):
            if key in data and isinstance(data[key], list):
                if len(data[key]) > MAX_SCAN_ROWS:
                    raise ValueError(f'Scan exceeds the maximum of {MAX_SCAN_ROWS} rows.')
                return [_normalize_mapping(item) for item in data[key]]
        raise ValueError(
            'Unrecognized JSON structure. Expected a list of findings, '
            'Trivy JSON ("Results"), or SARIF 2.1.0 ("runs").'
        )
    if isinstance(data, list):
        if len(data) > MAX_SCAN_ROWS:
            raise ValueError(f'Scan exceeds the maximum of {MAX_SCAN_ROWS} rows.')
        return [_normalize_mapping(item) for item in data]
    raise ValueError('JSON root must be an array of findings or a recognized report object.')


def _build_asset_index(user):
    """Build case-insensitive lookup table restricted to assets the user can edit."""
    writable = writable_queryset(Asset.objects.filter(is_active=True), user).select_related('owner_dept')
    index = {}
    allowed_pks = set()
    for asset in writable:
        allowed_pks.add(asset.pk)
        for candidate in (asset.asset_id, asset.ip_address, asset.hostname, asset.fqdn, asset.name):
            key = str(candidate or '').strip().lower()
            if key and key not in index:
                index[key] = asset
    return index, allowed_pks


def _resolve_asset(target, index, allowed_pks, default_asset):
    key = (target or '').strip().lower()
    if key:
        return index.get(key)
    if default_asset is not None and default_asset.pk in allowed_pks:
        return default_asset
    return None


def _get_or_create_vulnerability(row, user):
    cve_id = row['cve_id']
    if cve_id:
        existing = Vulnerability.objects.filter(cve_id__iexact=cve_id).first()
        if existing is not None:
            return existing
        return Vulnerability.objects.create(
            cve_id=cve_id,
            title=(row['title'] or cve_id)[:500],
            description=row['description'],
            cvss_score=row['cvss_score'],
            cvss_severity=row['severity'],
            source='scanner',
            created_by=user,
            updated_by=user,
        )

    title = (row['title'] or '')[:500]
    existing = Vulnerability.objects.filter(
        cve_id__isnull=True, title__iexact=title, source='scanner',
    ).first()
    if existing is not None:
        return existing
    return Vulnerability.objects.create(
        cve_id=None,
        title=title,
        description=row['description'],
        cvss_score=row['cvss_score'],
        cvss_severity=row['severity'],
        source='scanner',
        created_by=user,
        updated_by=user,
    )


def import_scanner_upload(uploaded_file, user, *, default_asset=None, scanner_label=''):
    """Validate, parse, and import an uploaded CSV or JSON scanner report."""
    if uploaded_file is None:
        return {'error': 'Choose a .csv or .json scanner file first.'}

    filename = (getattr(uploaded_file, 'name', '') or '').lower()
    if uploaded_file.size > MAX_SCAN_UPLOAD_BYTES:
        return {'error': 'File exceeds the 5 MB limit.'}

    if filename.endswith('.csv'):
        fmt = 'csv'
    elif filename.endswith('.json'):
        fmt = 'json'
    else:
        return {'error': 'Only .csv or .json scanner exports are supported.'}

    try:
        raw_bytes = uploaded_file.read()
        if len(raw_bytes) > MAX_SCAN_UPLOAD_BYTES:
            return {'error': 'File exceeds the 5 MB limit.'}
        text = raw_bytes.decode('utf-8-sig')
    except UnicodeDecodeError as exc:
        return {'error': f'File must be UTF-8 encoded: {exc}'}

    try:
        rows = parse_scanner_csv(text) if fmt == 'csv' else parse_scanner_json(text)
    except (ValueError, csv.Error, json.JSONDecodeError) as exc:
        return {'error': f'Could not parse {fmt.upper()} scan output: {exc}'}

    asset_index, allowed_pks = _build_asset_index(user)
    if default_asset is not None and default_asset.pk not in allowed_pks:
        default_asset = None

    label = (scanner_label or '').strip()
    created = 0
    updated = 0
    skipped = 0
    errors = []

    for idx, row in enumerate(rows, start=1):
        if not row['cve_id'] and not row['title']:
            skipped += 1
            errors.append(f'Row {idx}: missing both CVE ID and vulnerability title.')
            continue

        asset = _resolve_asset(row['asset'], asset_index, allowed_pks, default_asset)
        if asset is None:
            skipped += 1
            target_label = row['asset'] or '(blank)'
            errors.append(f'Row {idx}: no writable asset matched "{target_label}".')
            continue

        evidence = row['evidence']
        if label:
            prefix = f'[Scanner: {label}]'
            if evidence and not evidence.startswith(prefix):
                evidence = f'{prefix} {evidence}'
            elif not evidence:
                evidence = prefix

        try:
            with transaction.atomic():
                vuln = _get_or_create_vulnerability(row, user)
                existing = Finding.objects.filter(
                    vulnerability=vuln, asset=asset, port=row['port'],
                ).first()
                if existing is None:
                    Finding.objects.create(
                        vulnerability=vuln,
                        asset=asset,
                        owner_dept=asset.owner_dept,
                        port=row['port'],
                        evidence=evidence,
                        solution=row['solution'],
                        discovered_date=row['discovered_date'],
                        status=row['status'],
                        created_by=user,
                        updated_by=user,
                    )
                    created += 1
                else:
                    changed = False
                    if evidence and evidence != existing.evidence:
                        existing.evidence = evidence
                        changed = True
                    if row['solution'] and row['solution'] != existing.solution:
                        existing.solution = row['solution']
                        changed = True
                    existing.updated_by = user
                    existing.save()
                    if changed or True:
                        updated += 1
        except Exception as exc:
            skipped += 1
            errors.append(f'Row {idx}: {exc}')

    return {
        'format': fmt.upper(),
        'total_rows': len(rows),
        'created': created,
        'updated': updated,
        'skipped': skipped,
        'errors': errors[:50],
        'error_count': len(errors),
    }
