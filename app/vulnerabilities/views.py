from datetime import timedelta

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import Q
from django.http import HttpResponse
from django.shortcuts import render, redirect, get_object_or_404
from django.utils import timezone
from django.views.decorators.http import require_POST
from django.views.generic import ListView, DetailView
from core.reports import ReportMixin
from core.mixins import DepartmentScopedMixin, CsvExportMixin
from .models import Vulnerability, Finding
from .services import enrich_vulnerability, cascade_finding_to_risk


# ============================================================
# FINDINGS
# ============================================================

class FindingListView(ReportMixin, DepartmentScopedMixin, CsvExportMixin, ListView):
    model = Finding
    template_name = 'vulnerabilities/finding_list.html'
    context_object_name = 'findings'
    paginate_by = 25
    department_field = 'owner_dept'

    report_title = 'Vulnerability Findings'
    report_filename_base = 'vulnerability_findings'
    pdf_template = 'reports/findings_pdf.html'

    csv_filename = 'findings.csv'
    csv_fields = [
        ('CVE', lambda f: f.vulnerability.cve_id or ''),
        ('Title', lambda f: f.vulnerability.title),
        ('CVSS', lambda f: float(f.vulnerability.cvss_score)),
        ('Severity', lambda f: f.vulnerability.get_cvss_severity_display()),
        ('EPSS', lambda f: float(f.vulnerability.epss_score) if f.vulnerability.epss_score else ''),
        ('KEV', lambda f: 'Yes' if f.vulnerability.kev_status else 'No'),
        ('Asset', lambda f: f.asset.name),
        ('Department', lambda f: f.owner_dept.name),
        ('Status', lambda f: f.get_status_display()),
        ('Composite', lambda f: float(f.composite_score)),
        ('Discovered', lambda f: f.discovered_date),
        ('Port', lambda f: f.port),
    ]

    def get_queryset(self):
        qs = super().get_queryset().select_related('vulnerability', 'asset', 'owner_dept')
        q = self.request.GET.get('q', '').strip()
        if q:
            qs = qs.filter(
                Q(vulnerability__cve_id__icontains=q) |
                Q(vulnerability__title__icontains=q) |
                Q(asset__name__icontains=q)
            )
        status = self.request.GET.get('status')
        if status:
            qs = qs.filter(status=status)
        severity = self.request.GET.get('severity')
        if severity:
            qs = qs.filter(vulnerability__cvss_severity=severity)
        kev = self.request.GET.get('kev')
        if kev == '1':
            qs = qs.filter(vulnerability__kev_status=True)
        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['statuses'] = Finding.STATUS_CHOICES
        ctx['severities'] = Vulnerability.SEVERITY_CHOICES
        ctx['search_query'] = self.request.GET.get('q', '')
        ctx['selected_status'] = self.request.GET.get('status', '')
        ctx['selected_severity'] = self.request.GET.get('severity', '')
        ctx['kev_filter'] = self.request.GET.get('kev', '')

        base = super().get_queryset()
        user = self.request.user
        if not user.is_superuser and user.department_id:
            base = base.filter(owner_dept=user.department)
        ctx['total_count'] = base.count()
        ctx['open_count'] = base.exclude(status__in=Finding.CLOSED_STATUSES).count()
        ctx['critical_count'] = base.filter(vulnerability__cvss_severity='critical').count()
        ctx['kev_count'] = base.filter(vulnerability__kev_status=True).count()
        return ctx


    def build_rows(self):
        headers = ['CVE', 'Title', 'Severity', 'CVSS', 'Asset', 'Status',
                   'Assigned To', 'Team', 'Discovered', 'SLA Due', 'Overdue']
        rows = []
        for f in self.get_queryset():
            rows.append([
                f.vulnerability.cve_id or 'Manual',
                f.vulnerability.title[:200],
                f.vulnerability.get_cvss_severity_display(),
                float(f.vulnerability.cvss_score),
                f.asset.asset_id + ' — ' + f.asset.name[:40],
                f.get_status_display(),
                f.assigned_to.username if f.assigned_to else '',
                f.assigned_team.name if f.assigned_team else '',
                f.discovered_date.strftime('%Y-%m-%d') if f.discovered_date else '',
                f.sla_due_date.strftime('%Y-%m-%d') if f.sla_due_date else '',
                'Yes' if f.is_overdue else 'No',
            ])
        return headers, rows

    def build_pdf_context(self):
        qs = list(self.get_queryset())
        return {
            'findings': qs,
            'total': len(qs),
            'open_count': sum(1 for f in qs if f.status not in f.CLOSED_STATUSES),
            'overdue_count': sum(1 for f in qs if f.is_overdue),
        }
    
class FindingDetailView(DepartmentScopedMixin, DetailView):
    model = Finding
    template_name = 'vulnerabilities/finding_detail.html'
    context_object_name = 'finding'
    department_field = 'owner_dept'


# ============================================================
# VULNERABILITY CATALOG
# ============================================================

class VulnerabilityListView(ListView):
    model = Vulnerability
    template_name = 'vulnerabilities/vulnerability_list.html'
    context_object_name = 'vulnerabilities'
    paginate_by = 30

    def get_queryset(self):
        from django.db.models import Count
        qs = super().get_queryset().annotate(finding_count=Count('findings'))
        q = self.request.GET.get('q', '').strip()
        if q:
            qs = qs.filter(Q(cve_id__icontains=q) | Q(title__icontains=q) | Q(description__icontains=q))
        severity = self.request.GET.get('severity')
        if severity:
            qs = qs.filter(cvss_severity=severity)
        kev = self.request.GET.get('kev')
        if kev == '1':
            qs = qs.filter(kev_status=True)
        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['severities'] = Vulnerability.SEVERITY_CHOICES
        ctx['search_query'] = self.request.GET.get('q', '')
        ctx['selected_severity'] = self.request.GET.get('severity', '')
        ctx['kev_filter'] = self.request.GET.get('kev', '')
        return ctx


class VulnerabilityDetailView(DetailView):
    model = Vulnerability
    template_name = 'vulnerabilities/vulnerability_detail.html'
    context_object_name = 'vulnerability'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['findings'] = self.object.findings.select_related('asset', 'owner_dept')
        return ctx


# ============================================================
# ENRICHMENT + CASCADE ACTIONS
# ============================================================

@require_POST
def enrich_vulnerability_view(request, pk):
    vuln = get_object_or_404(Vulnerability, pk=pk)
    results = enrich_vulnerability(vuln)

    ok_count = sum(1 for r in results.values() if r.get('ok'))
    msgs = []
    for source, r in results.items():
        status = '✓' if r.get('ok') else '✗'
        msgs.append(f"{source.upper()}: {status} {r.get('message') or r.get('error')}")

    if ok_count:
        messages.success(request, ' | '.join(msgs))
    else:
        messages.error(request, ' | '.join(msgs))

    return redirect('vulnerabilities:vulnerability_detail', pk=pk)


@require_POST
def cascade_finding_view(request, pk):
    finding = get_object_or_404(Finding, pk=pk)
    risk, created = cascade_finding_to_risk(finding)
    if created:
        messages.success(request, f'Risk created: "{risk.title[:80]}"')
    else:
        messages.info(request, f'Risk already exists: "{risk.title[:80]}"')
    return redirect('risks:detail', pk=risk.pk)


# ============================================================
# LIVE CVE FEED
# ============================================================

class LiveCVEFeedView(LoginRequiredMixin, ListView):
    model = Vulnerability
    template_name = 'vulnerabilities/live_feed.html'
    context_object_name = 'cves'
    paginate_by = 30

    def get_queryset(self):
        qs = Vulnerability.objects.exclude(cve_id__isnull=True).exclude(cve_id='').filter(source='nvd')

        severity = self.request.GET.get('severity')
        if severity:
            qs = qs.filter(cvss_severity=severity)

        kev = self.request.GET.get('kev')
        if kev == '1':
            qs = qs.filter(kev_status=True)

        days = self.request.GET.get('days')
        if days:
            try:
                cutoff = timezone.now().date() - timedelta(days=int(days))
                qs = qs.filter(published_date__gte=cutoff)
            except ValueError:
                pass

        q = self.request.GET.get('q', '').strip()
        if q:
            qs = qs.filter(Q(cve_id__icontains=q) | Q(title__icontains=q) | Q(description__icontains=q))

        return qs.order_by('-published_date', '-created_at')

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)

        base = Vulnerability.objects.filter(source='nvd').exclude(cve_id__isnull=True)
        last_7_days = timezone.now().date() - timedelta(days=7)
        recent = base.filter(published_date__gte=last_7_days)

        ctx['total_synced'] = base.count()
        ctx['last_7_days'] = recent.count()
        ctx['critical_7d'] = recent.filter(cvss_severity='critical').count()
        ctx['kev_7d'] = recent.filter(kev_status=True).count()
        ctx['last_sync'] = base.order_by('-last_enriched').values_list('last_enriched', flat=True).first()

        ctx['severities'] = Vulnerability.SEVERITY_CHOICES
        ctx['search_query'] = self.request.GET.get('q', '')
        ctx['selected_severity'] = self.request.GET.get('severity', '')
        ctx['kev_filter'] = self.request.GET.get('kev', '')
        ctx['days_filter'] = self.request.GET.get('days', '')
        return ctx


# ============================================================
# MANUAL VULNERABILITY ENTRY
# ============================================================

from django.contrib.auth.mixins import LoginRequiredMixin as _LRM5
from django.views.generic import FormView as _FV5
from django.urls import reverse_lazy as _RL5
from .forms import ManualVulnerabilityForm
from django.utils import timezone as _tz5


class ManualVulnerabilityCreateView(_LRM5, _FV5):
    form_class = ManualVulnerabilityForm
    template_name = 'vulnerabilities/manual_entry.html'
    success_url = _RL5('vulnerabilities:finding_list')

    def form_valid(self, form):
        data = form.cleaned_data

        # Reuse existing vulnerability if CVE matches, else create new
        existing = data.get('existing_vulnerability')
        if existing:
            vuln = existing
        else:
            cve_id = (data.get('cve_id') or '').strip() or None
            vuln = Vulnerability.objects.create(
                cve_id=cve_id,
                title=data['title'][:500],
                description=data.get('description', ''),
                cvss_score=data['cvss_score'],
                cvss_severity=data['cvss_severity'],
                source='manual',
                created_by=self.request.user,
                updated_by=self.request.user,
            )

        # Compute SLA if not given
        sla = data.get('sla_due_date')
        if not sla:
            from datetime import timedelta
            days = Finding.SLA_DAYS.get(data['cvss_severity'], 90)
            sla = data['discovered_date'] + timedelta(days=days)

        finding = Finding(
            vulnerability=vuln,
            asset=data['asset'],
            owner_dept=data['asset'].owner_dept,
            port=data.get('port', ''),
            evidence=data.get('evidence', ''),
            status=data['status'],
            discovered_date=data['discovered_date'],
            sla_due_date=sla,
            assigned_to=data.get('assigned_to'),
            assigned_team=data.get('assigned_team'),
            solution=data.get('solution', ''),
            remediation_notes=data.get('remediation_notes', ''),
            created_by=self.request.user,
            updated_by=self.request.user,
        )
        finding.save()

        messages.success(self.request, f'Vulnerability logged: {vuln} on {finding.asset.asset_id}')
        return redirect('vulnerabilities:finding_detail', pk=finding.pk)

    def get_initial(self):
        return {
            'discovered_date': _tz5.now().date(),
            'status': 'new',
            'cvss_severity': 'medium',
            'cvss_score': 5.0,
        }
