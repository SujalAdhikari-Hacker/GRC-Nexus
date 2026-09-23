from django.db.models import Q, Count
from django.views.generic import ListView, DetailView

from core.mixins import DepartmentScopedMixin, CsvExportMixin
from .models import Vulnerability, Finding


class FindingListView(DepartmentScopedMixin, CsvExportMixin, ListView):
    model = Finding
    template_name = 'vulnerabilities/finding_list.html'
    context_object_name = 'findings'
    paginate_by = 25
    department_field = 'owner_dept'

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
        ctx['open_count'] = base.filter(status='open').count()
        ctx['critical_count'] = base.filter(vulnerability__cvss_severity='critical').count()
        ctx['kev_count'] = base.filter(vulnerability__kev_status=True).count()
        return ctx


class FindingDetailView(DepartmentScopedMixin, DetailView):
    model = Finding
    template_name = 'vulnerabilities/finding_detail.html'
    context_object_name = 'finding'
    department_field = 'owner_dept'


class VulnerabilityListView(ListView):
    model = Vulnerability
    template_name = 'vulnerabilities/vulnerability_list.html'
    context_object_name = 'vulnerabilities'
    paginate_by = 30

    def get_queryset(self):
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
