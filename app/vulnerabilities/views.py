from datetime import timedelta

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import PermissionDenied
from django.core.management import call_command
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404, redirect
from django.utils import timezone
from django.views.decorators.http import require_POST
from django.views.generic import DeleteView, DetailView, FormView, ListView
from django.urls import reverse, reverse_lazy

from core.input_validation import boolean, choice, integer, search_query
from core.mixins import (
    ChangeScopedMixin,
    CsvExportMixin,
    DepartmentScopedMixin,
    HODOrSuperuserMixin,
    exclude_anonymous_user_from_form,
    scope_queryset,
    user_can_change,
)
from core.reports import ReportMixin

from .forms import ManualVulnerabilityForm, ScannerImportForm
from .models import Finding, Vulnerability, composite_score_breakdown
from .scanner_import import import_scanner_upload
from .services import cascade_finding_to_risk, enrich_vulnerability


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
        q = search_query(self.request.GET.get('q', ''))
        if q:
            qs = qs.filter(
                Q(vulnerability__cve_id__icontains=q) |
                Q(vulnerability__title__icontains=q) |
                Q(asset__name__icontains=q)
            )
        status = choice(
            self.request.GET.get('status'),
            {value for value, _label in Finding.STATUS_CHOICES},
            'status', allow_blank=True,
        )
        if status:
            qs = qs.filter(status=status)
        severity = choice(
            self.request.GET.get('severity'),
            {value for value, _label in Vulnerability.SEVERITY_CHOICES},
            'severity', allow_blank=True,
        )
        if severity:
            qs = qs.filter(vulnerability__cvss_severity=severity)
        kev = boolean(self.request.GET.get('kev'), 'kev', default=False)
        if kev:
            qs = qs.filter(vulnerability__kev_status=True)
        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        base = self.get_queryset()
        ctx['statuses'] = Finding.STATUS_CHOICES
        ctx['severities'] = Vulnerability.SEVERITY_CHOICES
        ctx['search_query'] = self.request.GET.get('q', '')
        ctx['selected_status'] = self.request.GET.get('status', '')
        ctx['selected_severity'] = self.request.GET.get('severity', '')
        ctx['kev_filter'] = self.request.GET.get('kev', '')
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
            'critical_count': sum(1 for f in qs if f.vulnerability.cvss_severity == 'critical'),
            'kev_count': sum(1 for f in qs if f.vulnerability.kev_status),
            'overdue_count': sum(1 for f in qs if f.is_overdue),
        }


class FindingDetailView(DepartmentScopedMixin, DetailView):
    model = Finding
    template_name = 'vulnerabilities/finding_detail.html'
    context_object_name = 'finding'
    department_field = 'owner_dept'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['score_breakdown'] = composite_score_breakdown(self.object)
        return ctx


# ============================================================
# VULNERABILITY CATALOG (internal — any signed-in user)
# ============================================================

class VulnerabilityListView(LoginRequiredMixin, ListView):
    model = Vulnerability
    template_name = 'vulnerabilities/vulnerability_list.html'
    context_object_name = 'vulnerabilities'
    paginate_by = 30

    def get_queryset(self):
        qs = super().get_queryset().annotate(finding_count=Count('findings'))
        q = search_query(self.request.GET.get('q', ''))
        if q:
            qs = qs.filter(Q(cve_id__icontains=q) | Q(title__icontains=q) | Q(description__icontains=q))
        severity = choice(
            self.request.GET.get('severity'),
            {value for value, _label in Vulnerability.SEVERITY_CHOICES},
            'severity', allow_blank=True,
        )
        if severity:
            qs = qs.filter(cvss_severity=severity)
        if boolean(self.request.GET.get('kev'), 'kev', default=False):
            qs = qs.filter(kev_status=True)
        return qs.order_by('-cvss_score', '-published_date')

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['severities'] = Vulnerability.SEVERITY_CHOICES
        ctx['search_query'] = self.request.GET.get('q', '')
        ctx['selected_severity'] = self.request.GET.get('severity', '')
        ctx['kev_filter'] = self.request.GET.get('kev', '')
        return ctx


class VulnerabilityDetailView(LoginRequiredMixin, DetailView):
    model = Vulnerability
    template_name = 'vulnerabilities/vulnerability_detail.html'
    context_object_name = 'vulnerability'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        # Only show findings the user is allowed to see.
        ctx['findings'] = scope_queryset(
            self.object.findings.select_related('asset', 'owner_dept'), self.request.user
        )
        return ctx


# ============================================================
# ENRICHMENT + CASCADE ACTIONS
# ============================================================

def _require_enricher(user):
    if not (user.is_superuser or user.is_hod):
        raise PermissionDenied


@login_required
@require_POST
def enrich_vulnerability_view(request, pk):
    _require_enricher(request.user)
    vuln = get_object_or_404(Vulnerability, pk=pk)
    results = enrich_vulnerability(vuln)

    msgs = []
    for source, r in results.items():
        status = '✓' if r.get('ok') else '✗'
        msgs.append(f"{source.upper()}: {status} {r.get('message') or r.get('error')}")

    if any(r.get('ok') for r in results.values()):
        messages.success(request, ' | '.join(msgs))
    else:
        messages.error(request, ' | '.join(msgs))

    return redirect('vulnerabilities:vulnerability_detail', pk=pk)


@login_required
@require_POST
def cascade_finding_view(request, pk):
    finding = get_object_or_404(Finding, pk=pk)
    if not user_can_change(request.user, finding):
        raise PermissionDenied
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

        severity = choice(
            self.request.GET.get('severity'),
            {value for value, _label in Vulnerability.SEVERITY_CHOICES},
            'severity', allow_blank=True,
        )
        if severity:
            qs = qs.filter(cvss_severity=severity)

        if boolean(self.request.GET.get('kev'), 'kev', default=False):
            qs = qs.filter(kev_status=True)

        days = integer(
            self.request.GET.get('days'), 'days',
            minimum=1, maximum=3650, default=0,
        )
        if days:
            cutoff = timezone.localdate() - timedelta(days=days)
            qs = qs.filter(published_date__gte=cutoff)

        q = search_query(self.request.GET.get('q', ''))
        if q:
            qs = qs.filter(Q(cve_id__icontains=q) | Q(title__icontains=q) | Q(description__icontains=q))

        return qs.order_by('-published_date', '-created_at')

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)

        base = Vulnerability.objects.filter(source='nvd').exclude(cve_id__isnull=True)
        recent = base.filter(published_date__gte=timezone.localdate() - timedelta(days=7))

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


@login_required
@require_POST
def sync_recent_cves_view(request):
    """Superuser-only trigger to pull recent CVEs from NVD."""
    if not request.user.is_superuser:
        raise PermissionDenied('Only superadmins can sync live CVE feeds.')

    try:
        call_command('sync_recent_cves', days=7)
        synced = Vulnerability.objects.filter(source='nvd').exclude(cve_id__isnull=True).count()
        messages.success(request, f'Live CVE feed synced ({synced} NVD CVE(s) in catalog).')
    except Exception:
        messages.warning(request, 'Live NVD sync could not complete right now. Check container logs or network connectivity.')
    return redirect('vulnerabilities:live_feed')


# ============================================================
# MANUAL VULNERABILITY ENTRY
# ============================================================

class ManualVulnerabilityCreateView(LoginRequiredMixin, FormView):
    form_class = ManualVulnerabilityForm
    template_name = 'vulnerabilities/manual_entry.html'
    success_url = reverse_lazy('vulnerabilities:finding_list')

    def form_valid(self, form):
        data = form.cleaned_data
        asset = data['asset']
        if not user_can_change(self.request.user, asset):
            raise PermissionDenied

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

        sla = data.get('sla_due_date')
        if not sla:
            days = Finding.SLA_DAYS.get(data['cvss_severity'], 90)
            sla = data['discovered_date'] + timedelta(days=days)

        finding = Finding(
            vulnerability=vuln,
            asset=asset,
            owner_dept=asset.owner_dept,
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

    def get_form(self, form_class=None):
        form = super().get_form(form_class)
        return exclude_anonymous_user_from_form(form, user=self.request.user)

    def get_initial(self):
        return {
            'discovered_date': timezone.localdate(),
            'status': 'new',
            'cvss_severity': 'medium',
            'cvss_score': 5.0,
        }


class ScannerImportView(LoginRequiredMixin, FormView):
    """Upload CSV or JSON scanner outputs into department-scoped Findings."""

    template_name = 'vulnerabilities/scanner_import.html'
    form_class = ScannerImportForm

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['user'] = self.request.user
        return kwargs

    def form_valid(self, form):
        result = import_scanner_upload(
            form.cleaned_data['file'],
            self.request.user,
            default_asset=form.cleaned_data.get('default_asset'),
            scanner_label=form.cleaned_data.get('scanner_label', '').strip(),
        )
        if 'error' in result:
            messages.error(self.request, result['error'])
        elif result['skipped']:
            messages.warning(
                self.request,
                f"Imported {result['created']} new and {result['updated']} updated finding(s); "
                f"skipped {result['skipped']} row(s).",
            )
        else:
            messages.success(
                self.request,
                f"Imported {result['created']} new and {result['updated']} updated finding(s).",
            )
        return self.render_to_response(self.get_context_data(form=form, result=result))


class FindingDeleteView(HODOrSuperuserMixin, ChangeScopedMixin, DeleteView):
    model = Finding
    template_name = 'core/confirm_delete.html'
    success_url = reverse_lazy('vulnerabilities:finding_list')
    department_field = 'owner_dept'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['object_verbose_name'] = 'vulnerability finding'
        ctx['cancel_url'] = reverse('vulnerabilities:finding_detail', kwargs={'pk': self.object.pk})
        ctx['related_warning'] = (
            'Deleting this finding also removes any unassessed cascaded risks and '
            'cancels linked open alert tickets.'
        )
        return ctx

    def form_valid(self, form):
        label = str(self.object)
        response = super().form_valid(form)
        messages.success(self.request, f'Vulnerability finding "{label}" deleted.')
        return response
