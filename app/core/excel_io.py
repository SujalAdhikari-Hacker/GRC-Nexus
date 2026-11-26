"""Spreadsheet round-trip for the records people keep in Excel.

Download a workbook (or the empty template) of the rows you can see, edit it,
upload it back as .xlsx or .csv: rows with an ID are updated, rows without one
are created. Blank cells leave the stored value alone, so a partial sheet
cannot wipe a record.

One definition per entity keeps the export headers, the import parsers and the
instructions sheet in step. Adding another entity is one ``Entity`` entry.
"""
import csv
from collections import namedtuple
from datetime import date, datetime
from io import BytesIO, StringIO

from django.core.exceptions import ValidationError
from django.db import DatabaseError, transaction
from django.utils import timezone
from django.utils.dateparse import parse_date, parse_datetime

from assets.models import Asset, AssetCategory
from audits.models import Audit, AuditFinding
from controls.models import Control
from core.mixins import csv_safe, writable_queryset
from core.models import Department, User
from incidents.models import Incident
from policies.models import Policy, PolicyCategory
from risks.models import Risk, RiskCategory
from vendors.models import Vendor
from vulnerabilities.models import Vulnerability

ID_HEADER = 'ID'
MAX_UPLOAD_BYTES = 5 * 1024 * 1024

Column = namedtuple('Column', 'header attr parse hint')
Column.__new__.__defaults__ = ('',)


def _blank(value):
    return value is None or (isinstance(value, str) and not value.strip())


# ---------------------------------------------------------------- parsers

def _text(value):
    text = str(value).strip()
    # Undo the formula-injection escape the exporter adds.
    if len(text) > 1 and text[0] == "'" and text[1] in '=+-@':
        return text[1:]
    return text


def _int(value):
    try:
        return int(float(str(value).strip()))
    except (TypeError, ValueError):
        raise ValueError(f'"{value}" is not a whole number')


def _bool(value):
    text = str(value).strip().lower()
    if text in ('yes', 'true', '1', 'y'):
        return True
    if text in ('no', 'false', '0', 'n'):
        return False
    raise ValueError(f'"{value}" is not Yes or No')


def _date(value):
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    parsed = parse_date(str(value).strip())
    if parsed is None:
        raise ValueError(f'"{value}" is not a date (use YYYY-MM-DD)')
    return parsed


def _datetime(value):
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, date):
        parsed = datetime(value.year, value.month, value.day)
    else:
        text = str(value).strip()
        parsed = parse_datetime(text)
        if parsed is None:
            day = parse_date(text)
            if day is None:
                raise ValueError(f'"{value}" is not a date/time (use YYYY-MM-DD HH:MM)')
            parsed = datetime(day.year, day.month, day.day)
    if timezone.is_naive(parsed):
        parsed = timezone.make_aware(parsed)
    return parsed


def _lower(value):
    return str(value).strip().lower()


def _department(value):
    name = str(value).strip()
    department = Department.objects.filter(name__iexact=name).first()
    if department is None:
        raise ValueError(f'unknown department "{name}"')
    return department


def _user(value):
    username = str(value).strip()
    user = User.objects.filter(username__iexact=username).first()
    if user is None:
        raise ValueError(f'unknown user "{username}"')
    return user


def _risk_category(value):
    name = str(value).strip()
    category = RiskCategory.objects.filter(name__iexact=name).first()
    if category is None:
        raise ValueError(f'unknown risk category "{name}"')
    return category


def _control_ref(value):
    code = str(value).strip()
    control = Control.objects.filter(code__iexact=code).first()
    if control is None:
        raise ValueError(f'unknown control code "{code}"')
    return control


def _audit_ref(value):
    name = str(value).strip()
    audit = Audit.objects.filter(name__iexact=name).first()
    if audit is None:
        raise ValueError(f'unknown audit "{name}"')
    return audit


def _vendor_ref(value):
    name = str(value).strip()
    vendor = Vendor.objects.filter(name__iexact=name).first()
    if vendor is None:
        raise ValueError(f'unknown vendor "{name}"')
    return vendor


def _asset_category(value):
    name = str(value).strip()
    category = AssetCategory.objects.filter(name__iexact=name).first()
    if category is None:
        raise ValueError(f'unknown asset category "{name}"')
    return category


def _policy_category(value):
    name = str(value).strip()
    category = PolicyCategory.objects.filter(name__iexact=name).first()
    if category is None:
        raise ValueError(f'unknown policy category "{name}"')
    return category


# ---------------------------------------------------------------- entities

class Entity:
    def __init__(self, key, label, model, columns, note, scope_field='owner_dept'):
        self.key = key
        self.label = label
        self.model = model
        self.columns = columns
        self.note = note
        self.scope_field = scope_field

    @property
    def required_headers(self):
        return [column.header for column in self.columns[:1]]


DEPARTMENT = Column('Department', 'owner_dept', _department, 'exact department name')
OWNER = Column('Owner', 'owner_user', _user, 'username')

RISKS = Entity(
    'risks', 'Risks', Risk, [
        Column('Title', 'title', _text),
        Column('Description', 'description', _text),
        Column('Threat', 'threat', _text),
        Column('Vulnerability', 'vulnerability', _text),
        Column('Impact Description', 'impact_description', _text),
        Column('Category', 'category', _risk_category, 'risk category name'),
        DEPARTMENT,
        OWNER,
        Column('Likelihood (1-5)', 'likelihood', _int),
        Column('Impact (1-5)', 'impact', _int),
        Column('Treatment Strategy', 'treatment_strategy', _lower),
        Column('Status', 'status', _lower),
        Column('Identified Date', 'identified_date', _date),
        Column('Target Close Date', 'target_close_date', _date),
        Column('Next Review Date', 'next_review_date', _date),
        Column('Closure Notes', 'closure_notes', _text),
    ],
    note='Scores are derived from likelihood and impact, so they are not imported.',
)

VENDORS = Entity(
    'vendors', 'Vendors', Vendor, [
        Column('Name', 'name', _text),
        Column('Description', 'description', _text),
        Column('Service', 'service', _text),
        Column('Tier (1-3)', 'tier', _int),
        Column('Data Sensitivity (0-4)', 'data_sensitivity', _int),
        Column('Status', 'status', _lower),
        DEPARTMENT,
        OWNER,
        Column('Jurisdiction', 'jurisdiction', _text),
        Column('Security Clauses', 'security_clauses', _bool, 'Yes or No'),
        Column('Audit Rights', 'audit_rights', _bool, 'Yes or No'),
        Column('SLA Defined', 'sla_defined', _bool, 'Yes or No'),
        Column('Breach Notification Hours', 'breach_notification_hours', _int),
        Column('Contact Name', 'contact_name', _text),
        Column('Contact Email', 'contact_email', _text),
        Column('Contact Phone', 'contact_phone', _text),
        Column('Contract Start', 'contract_start', _date),
        Column('Contract Renewal Date', 'contract_renewal_date', _date),
        Column('Notes', 'notes', _text),
    ],
    note='Certifications and linked assets are maintained on the vendor page.',
)

CONTROLS = Entity(
    'controls', 'Controls', Control, [
        Column('Code', 'code', _text, 'unique control ID, e.g. CTL-AC-001'),
        Column('Name', 'name', _text),
        Column('Description', 'description', _text),
        Column('Type', 'control_type', _lower),
        Column('Category', 'category', _lower),
        Column('Status', 'status', _lower),
        Column('Frequency', 'frequency', _lower),
        DEPARTMENT,
        OWNER,
        Column('Implementation Notes', 'implementation_notes', _text),
    ],
    note='Effectiveness ratings need a test date, so they are set on the control page.',
)

AUDITS = Entity(
    'audits', 'Audits', Audit, [
        Column('Name', 'name', _text),
        Column('Type', 'audit_type', _lower),
        Column('Status', 'status', _lower),
        DEPARTMENT,
        Column('Lead', 'auditor_lead', _user, 'username'),
        Column('Start Date', 'start_date', _date),
        Column('End Date', 'end_date', _date),
        Column('Scope', 'scope', _text),
        Column('Notes', 'notes', _text),
    ],
    note='Framework links are maintained on the audit page.',
)

FINDINGS = Entity(
    'findings', 'Audit Findings', AuditFinding, [
        Column('Title', 'title', _text),
        Column('Severity', 'severity', _lower),
        Column('Status', 'status', _lower),
        Column('Audit', 'audit', _audit_ref, 'audit name'),
        Column('Related Control', 'related_control', _control_ref, 'control code'),
        DEPARTMENT,
        OWNER,
        Column('Due Date', 'due_date', _date),
        Column('Description', 'description', _text),
        Column('Recommendation', 'recommendation', _text),
    ],
    note='Findings cannot be closed until remediation is verified on the finding page.',
)

ASSETS = Entity(
    'assets', 'Assets', Asset, [
        Column('Name', 'name', _text),
        Column('Hostname', 'hostname', _text),
        Column('IP Address', 'ip_address', _text),
        Column('FQDN', 'fqdn', _text),
        Column('Type', 'asset_type', _lower),
        Column('Hosting', 'hosting', _lower),
        Column('Cloud Provider', 'cloud_provider', _lower),
        Column('Cloud Region', 'cloud_region', _text),
        Column('Location', 'location', _text),
        Column('OS Family', 'os_family', _lower),
        Column('OS Version', 'os_version', _text),
        Column('Vendor', 'vendor', _vendor_ref, 'vendor name'),
        Column('Classification', 'classification', _lower),
        DEPARTMENT,
        OWNER,
        Column('Environment', 'environment', _lower),
        Column('Asset Category', 'category', _asset_category, 'asset category name'),
        Column('Criticality (1-4)', 'criticality', _int),
        Column('Confidentiality (1-3)', 'confidentiality', _int),
        Column('Integrity (1-3)', 'integrity', _int),
        Column('Availability (1-3)', 'availability', _int),
        Column('Value', 'value', _text),
        Column('Is Active', 'is_active', _bool, 'Yes or No'),
        Column('Description', 'description', _text),
    ],
    note='Linked policies and dependencies are maintained on the asset page.',
)

POLICIES = Entity(
    'policies', 'Policies', Policy, [
        Column('Title', 'title', _text),
        Column('Code', 'code', _text, 'unique policy code'),
        Column('Category', 'category', _policy_category, 'policy category name'),
        Column('Version', 'version', _text),
        Column('Status', 'status', _lower),
        DEPARTMENT,
        Column('Approved By', 'approved_by', _user, 'username'),
        Column('Approval Date', 'approval_date', _date),
        Column('Next Review Date', 'next_review_date', _date),
        Column('Description', 'description', _text),
        Column('Content', 'content', _text),
    ],
    note='The policy document file is uploaded on the policy page.',
)

INCIDENTS = Entity(
    'incidents', 'Incidents', Incident, [
        Column('Title', 'title', _text),
        Column('Description', 'description', _text),
        Column('Type', 'incident_type', _lower),
        Column('Source', 'source', _lower),
        Column('Severity', 'severity', _lower),
        Column('Status', 'status', _lower),
        DEPARTMENT,
        Column('Handler', 'handler', _user, 'username'),
        Column('Detected At', 'detected_at', _datetime, 'YYYY-MM-DD HH:MM'),
        Column('Data Subjects Affected', 'data_subjects_affected', _int),
        Column('Regulatory Notification Required', 'regulatory_notification_required', _bool, 'Yes or No'),
        Column('NIS2 Significant', 'nis2_significant', _bool, 'Yes or No'),
        Column('Root Cause', 'root_cause', _text),
        Column('Lessons Learned', 'lessons_learned', _text),
    ],
    note='The reference and lifecycle timestamps are assigned by the app.',
)

VULNERABILITIES = Entity(
    'vulnerabilities', 'Vulnerabilities', Vulnerability, [
        Column('CVE ID', 'cve_id', _text),
        Column('Title', 'title', _text),
        Column('Description', 'description', _text),
        Column('CVSS Score', 'cvss_score', _text),
        Column('CVSS Vector', 'cvss_vector', _text),
        Column('CVSS Severity', 'cvss_severity', _lower),
        Column('EPSS Score', 'epss_score', _text),
        Column('EPSS Percentile', 'epss_percentile', _text),
        Column('KEV Listed', 'kev_status', _bool, 'Yes or No'),
        Column('KEV Due Date', 'kev_due_date', _date),
        Column('Published Date', 'published_date', _date),
        Column('References', 'references', _text),
        Column('Source', 'source', _lower),
    ],
    note='EPSS, KEV and NVD enrichment is refreshed by threat intel. These are shared records.',
    scope_field=None,
)

ENTITIES = {
    entity.key: entity
    for entity in (
        ASSETS, RISKS, VENDORS, POLICIES, CONTROLS, AUDITS, FINDINGS,
        INCIDENTS, VULNERABILITIES,
    )
}


# ---------------------------------------------------------------- export

def _export_value(instance, attr):
    value = getattr(instance, attr, None)
    if value is None:
        return ''
    if isinstance(value, bool):
        return 'Yes' if value else 'No'
    if isinstance(value, (date, datetime)):
        return value
    if instance._meta.get_field(attr).is_relation:
        for name in ('code', 'username', 'name'):
            if hasattr(value, name):
                return csv_safe(getattr(value, name))
        return csv_safe(value)
    return csv_safe(value)


def export_workbook(entity, queryset, include_rows=True):
    """Return an .xlsx response of ``queryset`` that can be edited and re-uploaded.

    ``include_rows=False`` produces the blank template (headers + guide only).
    """
    from django.http import HttpResponse
    from django.utils import timezone
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font, PatternFill
    from openpyxl.utils import get_column_letter

    workbook = Workbook()
    sheet = workbook.active
    sheet.title = 'Data'

    headers = [ID_HEADER] + [column.header for column in entity.columns]
    sheet.append(headers)
    for cell in sheet[1]:
        cell.font = Font(bold=True, color='FFFFFF')
        cell.fill = PatternFill('solid', start_color='0B1220', end_color='0B1220')
        cell.alignment = Alignment(vertical='center')

    if include_rows:
        for instance in queryset:
            sheet.append(
                [instance.pk]
                + [_export_value(instance, column.attr) for column in entity.columns]
            )

    for index, header in enumerate(headers, start=1):
        width = max(len(str(header)) + 2, 14)
        sheet.column_dimensions[get_column_letter(index)].width = min(width, 40)
    sheet.freeze_panes = 'A2'

    guide = workbook.create_sheet('How to use')
    lines = [
        f'{entity.label} - bulk import',
        '',
        entity.note,
        '',
        'Rows with an ID update that record. Leave the ID blank to create a new one.',
        'Blank cells leave the existing value unchanged.',
        'Save as .xlsx or .csv and upload the file from the Import / Export page.',
        '',
        'Allowed values:',
    ]
    field_names = {field.name for field in entity.model._meta.fields}
    for column in entity.columns:
        if column.hint:
            lines.append(f'  {column.header}: {column.hint}')
        if column.attr in field_names:
            field = entity.model._meta.get_field(column.attr)
            if getattr(field, 'choices', None):
                values = ', '.join(str(value) for value, _label in field.choices)
                lines.append(f'  {column.header}: {values}')
    for offset, line in enumerate(lines, start=1):
        guide.cell(row=offset, column=1, value=line)
    guide.column_dimensions['A'].width = 110

    output = BytesIO()
    workbook.save(output)
    output.seek(0)

    response = HttpResponse(
        output.getvalue(),
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    )
    suffix = '' if include_rows else '_template'
    response['Content-Disposition'] = (
        f'attachment; filename="{entity.key}{suffix}_{timezone.localdate():%Y%m%d}.xlsx"'
    )
    return response


def export_csv(entity, queryset):
    """Return the same columns as a .csv download that can be re-uploaded."""
    from django.http import HttpResponse
    from django.utils import timezone

    response = HttpResponse(content_type='text/csv; charset=utf-8')
    response['Content-Disposition'] = (
        f'attachment; filename="{entity.key}_{timezone.localdate():%Y%m%d}.csv"'
    )
    response.write('\ufeff')  # Excel needs the BOM to read UTF-8 CSV
    writer = csv.writer(response)
    writer.writerow([ID_HEADER] + [column.header for column in entity.columns])
    for instance in queryset:
        writer.writerow(
            [instance.pk]
            + [_export_value(instance, column.attr) for column in entity.columns]
        )
    return response


def table_rows(entity, queryset):
    """Header and string rows for the PDF renderer."""
    headers = [column.header for column in entity.columns]
    rows = [
        [str(_export_value(instance, column.attr)) for column in entity.columns]
        for instance in queryset
    ]
    return headers, rows


# ---------------------------------------------------------------- import

def _flatten_errors(exc):
    if hasattr(exc, 'message_dict'):
        return '; '.join(
            f'{field}: {"; ".join(messages)}'
            for field, messages in exc.message_dict.items()
        )
    return '; '.join(exc.messages)


def _resolve(entity, row, id_index, user):
    value = row[id_index] if id_index is not None and id_index < len(row) else None
    if _blank(value):
        return entity.model(), True

    try:
        pk = int(float(str(value).strip()))
    except (TypeError, ValueError):
        raise ValueError(f'ID "{value}" is not a number')

    if entity.scope_field is None:
        queryset = entity.model.objects.all()
    else:
        queryset = writable_queryset(
            entity.model.objects.all(), user, field=entity.scope_field,
        )
    instance = queryset.filter(pk=pk).first()
    if instance is None:
        raise ValueError(
            f'{entity.label.rstrip("s").lower()} {pk} does not exist '
            f'or is not yours to edit'
        )
    return instance, False


def _apply_ownership(instance, user, is_new):
    if hasattr(instance, 'owner_dept_id'):
        if not instance.owner_dept_id and user.department_id:
            instance.owner_dept = user.department
        if not user.is_superuser and instance.owner_dept_id != user.department_id:
            raise ValueError('you can only import records for your own department')
    if is_new and hasattr(instance, 'created_by_id'):
        instance.created_by = user
    if hasattr(instance, 'updated_by_id'):
        instance.updated_by = user
    # Incidents number themselves; full_clean would reject the blank reference.
    if is_new and hasattr(instance, 'next_reference') and not instance.reference:
        instance.reference = instance.next_reference()


def import_rows(entity, workbook, user):
    """Create/update rows from the ``Data`` sheet; one bad row does not stop the rest."""
    sheet = workbook['Data'] if 'Data' in workbook.sheetnames else workbook.active
    return _import_rows(entity, sheet.iter_rows(values_only=True), user)


def import_csv(entity, stream, user):
    """Same rules as the workbook, from a UTF-8 (or Windows-1252) CSV file."""
    raw = stream.read()
    for encoding in ('utf-8-sig', 'cp1252'):
        try:
            text = raw.decode(encoding)
            break
        except UnicodeDecodeError:
            continue
    else:
        raise ValueError('the file is not valid UTF-8 or Windows-1252 text')
    return _import_rows(entity, csv.reader(StringIO(text)), user)


def _import_rows(entity, rows, user):
    header = next(rows, None)
    if not header:
        raise ValueError('the first sheet is empty')

    index = {
        str(value).strip().lower(): position
        for position, value in enumerate(header)
        if not _blank(value)
    }
    missing = [
        name for name in entity.required_headers
        if name.lower() not in index
    ]
    if missing:
        raise ValueError(f'missing column(s): {", ".join(missing)}')

    columns = [column for column in entity.columns if column.header.lower() in index]
    id_index = index.get(ID_HEADER.lower())

    created = updated = 0
    errors = []
    for row_number, row in enumerate(rows, start=2):
        if not row or all(_blank(cell) for cell in row):
            continue
        try:
            with transaction.atomic():
                instance, is_new = _resolve(entity, row, id_index, user)
                for column in columns:
                    value = row[index[column.header.lower()]]
                    if _blank(value):
                        continue
                    setattr(instance, column.attr, column.parse(value))
                _apply_ownership(instance, user, is_new)
                instance.full_clean()
                instance.save()
        except (ValidationError, ValueError) as exc:
            errors.append((row_number, _flatten_errors(exc) if isinstance(
                exc, ValidationError) else str(exc)))
        except DatabaseError as exc:
            errors.append((row_number, f'database error: {exc}'))
        else:
            created += is_new
            updated += not is_new

    return {'created': created, 'updated': updated, 'errors': errors}
