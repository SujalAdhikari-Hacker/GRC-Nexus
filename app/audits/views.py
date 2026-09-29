from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import Q
from django.shortcuts import redirect, get_object_or_404
from django.urls import reverse_lazy
from django.views.generic import ListView, DetailView, CreateView, UpdateView, TemplateView
from django.utils import timezone
from core.mixins import DepartmentScopedMixin, CsvExportMixin
from .models import Audit, EvidenceItem, EvidenceScore, ControlTest, AuditFinding
from .forms import EvidenceItemForm, EvidenceScoreForm, ControlTestForm, AuditFindingForm


# ==================================================================
# AUDIT
# ==================================================================

class AuditListView(DepartmentScopedMixin, CsvExportMixin, ListView):
    model = Audit
    template_name = 'audits/audit_list.html'
    context_object_name = 'audits'
    paginate_by = 25
    department_field = 'owner_dept'

    csv_filename = 'audits.csv'
    csv_fields = [
        ('Name', 'name'),
        ('Type', 'get_audit_type_display'),
        ('Status', 'get_status_display'),
        ('Auditor Lead', lambda a: a.auditor_lead.username if a.auditor_lead else ''),
        ('Owner Dept', lambda a: a.owner_dept.name),
        ('Start', lambda a: a.start_date or ''),
        ('End', lambda a: a.end_date or ''),
        ('Findings', lambda a: a.findings.count()),
    ]

    def get_queryset(self):
        qs = super().get_queryset().select_related('auditor_lead', 'owner_dept')
        q = self.request.GET.get('q', '').strip()
        if q:
            qs = qs.filter(Q(name__icontains=q) | Q(scope__icontains=q))
        atype = self.request.GET.get('type')
        if atype:
            qs = qs.filter(audit_type=atype)
        status = self.request.GET.get('status')
        if status:
            qs = qs.filter(status=status)
        return qs.order_by('-start_date', 'name')

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['audit_types'] = Audit.TYPE_CHOICES
        ctx['statuses'] = Audit.STATUS_CHOICES
        ctx['search_query'] = self.request.GET.get('q', '')
        ctx['selected_type'] = self.request.GET.get('type', '')
        ctx['selected_status'] = self.request.GET.get('status', '')

        base = super().get_queryset()
        user = self.request.user
        if not user.is_superuser and user.department_id:
            base = base.filter(owner_dept=user.department)
        all_audits = list(base)
        ctx['total_count'] = len(all_audits)
        ctx['planned_count'] = sum(1 for a in all_audits if a.status == 'planned')
        ctx['in_progress_count'] = sum(1 for a in all_audits if a.status in ['planning', 'in_progress'])
        ctx['complete_count'] = sum(1 for a in all_audits if a.status == 'complete')
        ctx['open_findings_count'] = AuditFinding.objects.filter(
            audit__in=all_audits
        ).exclude(status__in=['resolved', 'closed', 'accepted']).count()
        return ctx


class AuditDetailView(DepartmentScopedMixin, DetailView):
    model = Audit
    template_name = 'audits/audit_detail.html'
    context_object_name = 'audit'
    department_field = 'owner_dept'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['findings'] = self.object.findings.select_related('related_control', 'owner_user').all()
        ctx['evidence_items'] = self.object.evidence_items.select_related('related_control', 'owner_user')[:20]
        ctx['tests'] = self.object.control_tests.select_related('control', 'tester')[:20]
        return ctx


class AuditCreateView(DepartmentScopedMixin, CreateView):
    model = Audit
    template_name = 'audits/audit_form.html'
    fields = [
        'name', 'owner_dept', 'audit_type', 'status',
        'auditor_lead', 'start_date', 'end_date',
        'scope', 'frameworks', 'notes',
    ]
    success_url = reverse_lazy('audits:list')

    def get_initial(self):
        initial = super().get_initial()
        user = self.request.user
        if not user.is_superuser and user.department_id:
            initial['owner_dept'] = user.department
        return initial


class AuditUpdateView(DepartmentScopedMixin, UpdateView):
    model = Audit
    template_name = 'audits/audit_form.html'
    fields = [
        'name', 'owner_dept', 'audit_type', 'status',
        'auditor_lead', 'start_date', 'end_date',
        'scope', 'frameworks', 'notes',
    ]
    success_url = reverse_lazy('audits:list')
    department_field = 'owner_dept'


class AuditTimelineView(DepartmentScopedMixin, TemplateView):
    template_name = 'audits/audit_timeline.html'
    department_field = 'owner_dept'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        user = self.request.user
        qs = Audit.objects.all().select_related('auditor_lead', 'owner_dept')
        if not user.is_superuser and user.department_id:
            qs = qs.filter(owner_dept=user.department)

        columns = []
        for code, label in Audit.STATUS_CHOICES:
            audits = list(qs.filter(status=code).order_by('-start_date'))
            columns.append({'code': code, 'label': label, 'audits': audits, 'count': len(audits)})

        ctx['columns'] = columns
        ctx['total_count'] = qs.count()
        return ctx


# ==================================================================
# EVIDENCE LIBRARY + SCORING
# ==================================================================

class EvidenceListView(DepartmentScopedMixin, CsvExportMixin, ListView):
    model = EvidenceItem
    template_name = 'audits/evidence_list.html'
    context_object_name = 'items'
    paginate_by = 25
    department_field = 'owner_dept'

    csv_filename = 'evidence.csv'
    csv_fields = [
        ('Title', 'title'),
        ('Type', 'get_evidence_type_display'),
        ('Control', lambda e: e.related_control.code if e.related_control else ''),
        ('Audit', lambda e: e.audit.name if e.audit else ''),
        ('Owner', lambda e: e.owner_user.username if e.owner_user else ''),
        ('Department', lambda e: e.owner_dept.name),
        ('Score', lambda e: e.score.total_score if e.score else ''),
        ('Created', lambda e: e.created_at.strftime('%Y-%m-%d')),
    ]

    def get_queryset(self):
        qs = super().get_queryset().select_related('related_control', 'owner_user', 'owner_dept', 'audit')
        q = self.request.GET.get('q', '').strip()
        if q:
            qs = qs.filter(Q(title__icontains=q) | Q(notes__icontains=q))
        etype = self.request.GET.get('type')
        if etype:
            qs = qs.filter(evidence_type=etype)
        control = self.request.GET.get('control')
        if control:
            qs = qs.filter(related_control_id=control)
        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['evidence_types'] = EvidenceItem.TYPE_CHOICES
        ctx['search_query'] = self.request.GET.get('q', '')
        ctx['selected_type'] = self.request.GET.get('type', '')

        base = super().get_queryset()
        user = self.request.user
        if not user.is_superuser and user.department_id:
            base = base.filter(owner_dept=user.department)
        all_items = list(base)
        ctx['total_count'] = len(all_items)
        ctx['scored_count'] = sum(1 for e in all_items if hasattr(e, 'scoring'))
        ctx['unscored_count'] = ctx['total_count'] - ctx['scored_count']
        strong = sum(1 for e in all_items if hasattr(e, 'scoring') and e.scoring.total_score >= 75)
        ctx['strong_count'] = strong
        return ctx


class EvidenceDetailView(DepartmentScopedMixin, DetailView):
    model = EvidenceItem
    template_name = 'audits/evidence_detail.html'
    context_object_name = 'item'
    department_field = 'owner_dept'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['score'] = getattr(self.object, 'scoring', None)
        return ctx


class EvidenceCreateView(DepartmentScopedMixin, CreateView):
    model = EvidenceItem
    form_class = EvidenceItemForm
    template_name = 'audits/evidence_form.html'
    success_url = reverse_lazy('audits:evidence_list')

    def get_initial(self):
        initial = super().get_initial()
        user = self.request.user
        if not user.is_superuser and user.department_id:
            initial['owner_dept'] = user.department
        # Pre-fill from query params
        control = self.request.GET.get('control')
        if control:
            initial['related_control'] = control
        audit = self.request.GET.get('audit')
        if audit:
            initial['audit'] = audit
        return initial


class EvidenceUpdateView(DepartmentScopedMixin, UpdateView):
    model = EvidenceItem
    form_class = EvidenceItemForm
    template_name = 'audits/evidence_form.html'
    success_url = reverse_lazy('audits:evidence_list')
    department_field = 'owner_dept'


class EvidenceScoreCreateView(LoginRequiredMixin, CreateView):
    model = EvidenceScore
    form_class = EvidenceScoreForm
    template_name = 'audits/evidence_score_form.html'

    def dispatch(self, request, *args, **kwargs):
        self.evidence = EvidenceItem.objects.get(pk=kwargs['evidence_pk'])
        return super().dispatch(request, *args, **kwargs)

    def get_initial(self):
        initial = super().get_initial()
        initial['assessor'] = self.request.user
        return initial

    def form_valid(self, form):
        form.instance.evidence = self.evidence
        return super().form_valid(form)

    def get_success_url(self):
        return reverse_lazy('audits:evidence_detail', kwargs={'pk': self.evidence.pk})

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['evidence'] = self.evidence
        return ctx


class EvidenceScoreUpdateView(LoginRequiredMixin, UpdateView):
    model = EvidenceScore
    form_class = EvidenceScoreForm
    template_name = 'audits/evidence_score_form.html'

    def get_success_url(self):
        return reverse_lazy('audits:evidence_detail', kwargs={'pk': self.object.evidence.pk})

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['evidence'] = self.object.evidence
        return ctx


# ==================================================================
# CONTROL TESTING
# ==================================================================

class ControlTestListView(DepartmentScopedMixin, CsvExportMixin, ListView):
    model = ControlTest
    template_name = 'audits/test_list.html'
    context_object_name = 'tests'
    paginate_by = 25
    department_field = 'owner_dept'

    csv_filename = 'control_tests.csv'
    csv_fields = [
        ('Control', lambda t: t.control.code),
        ('Control Name', lambda t: t.control.name),
        ('Date', 'test_date'),
        ('Result', 'get_result_display'),
        ('Tester', lambda t: t.tester.username if t.tester else ''),
        ('Notes', 'procedure_notes'),
    ]

    def get_queryset(self):
        qs = super().get_queryset().select_related('control', 'tester', 'owner_dept', 'audit')
        q = self.request.GET.get('q', '').strip()
        if q:
            qs = qs.filter(Q(control__code__icontains=q) | Q(control__name__icontains=q) | Q(procedure_notes__icontains=q))
        result = self.request.GET.get('result')
        if result:
            qs = qs.filter(result=result)
        return qs.order_by('-test_date')

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['results'] = ControlTest.RESULT_CHOICES
        ctx['search_query'] = self.request.GET.get('q', '')
        ctx['selected_result'] = self.request.GET.get('result', '')

        base = super().get_queryset()
        user = self.request.user
        if not user.is_superuser and user.department_id:
            base = base.filter(owner_dept=user.department)
        ctx['total_count'] = base.count()
        ctx['pass_count'] = base.filter(result='pass').count()
        ctx['fail_count'] = base.filter(result='fail').count()
        ctx['partial_count'] = base.filter(result='partial').count()
        return ctx


class ControlTestCreateView(DepartmentScopedMixin, CreateView):
    model = ControlTest
    form_class = ControlTestForm
    template_name = 'audits/test_form.html'
    success_url = reverse_lazy('audits:test_list')

    def get_initial(self):
        initial = super().get_initial()
        user = self.request.user
        if not user.is_superuser and user.department_id:
            initial['owner_dept'] = user.department
        control = self.request.GET.get('control')
        if control:
            initial['control'] = control
        return initial


class ControlTestUpdateView(DepartmentScopedMixin, UpdateView):
    model = ControlTest
    form_class = ControlTestForm
    template_name = 'audits/test_form.html'
    success_url = reverse_lazy('audits:test_list')
    department_field = 'owner_dept'


# ==================================================================
# AUDIT FINDINGS
# ==================================================================

class FindingListView(DepartmentScopedMixin, CsvExportMixin, ListView):
    model = AuditFinding
    template_name = 'audits/finding_list.html'
    context_object_name = 'findings'
    paginate_by = 25
    department_field = 'owner_dept'

    csv_filename = 'audit_findings.csv'
    csv_fields = [
        ('Title', 'title'),
        ('Severity', 'get_severity_display'),
        ('Status', 'get_status_display'),
        ('Source', 'get_source_display'),
        ('Control', lambda f: f.related_control.code if f.related_control else ''),
        ('Owner', lambda f: f.owner_user.username if f.owner_user else ''),
        ('Department', lambda f: f.owner_dept.name),
        ('Due', lambda f: f.due_date or ''),
    ]

    def get_queryset(self):
        qs = super().get_queryset().select_related('related_control', 'owner_user', 'owner_dept', 'audit')
        q = self.request.GET.get('q', '').strip()
        if q:
            qs = qs.filter(Q(title__icontains=q) | Q(description__icontains=q))
        severity = self.request.GET.get('severity')
        if severity:
            qs = qs.filter(severity=severity)
        status = self.request.GET.get('status')
        if status:
            qs = qs.filter(status=status)
        return qs.order_by('-created_at')

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['severities'] = AuditFinding.SEVERITY_CHOICES
        ctx['statuses'] = AuditFinding.STATUS_CHOICES
        ctx['search_query'] = self.request.GET.get('q', '')
        ctx['selected_severity'] = self.request.GET.get('severity', '')
        ctx['selected_status'] = self.request.GET.get('status', '')
        ctx['now_date'] = timezone.now().date()

        base = super().get_queryset()
        user = self.request.user
        if not user.is_superuser and user.department_id:
            base = base.filter(owner_dept=user.department)
        ctx['total_count'] = base.count()
        ctx['open_count'] = base.filter(status='open').count()
        ctx['critical_count'] = base.filter(severity='critical').count()
        ctx['overdue_count'] = base.filter(
            due_date__lt=__import__('django').utils.timezone.now().date()
        ).exclude(status__in=['resolved', 'closed', 'accepted']).count()
        return ctx


class FindingDetailView(DepartmentScopedMixin, DetailView):
    model = AuditFinding
    template_name = 'audits/finding_detail.html'
    context_object_name = 'finding'
    department_field = 'owner_dept'


class FindingCreateView(DepartmentScopedMixin, CreateView):
    model = AuditFinding
    form_class = AuditFindingForm
    template_name = 'audits/finding_form.html'
    success_url = reverse_lazy('audits:finding_list')

    def get_initial(self):
        initial = super().get_initial()
        user = self.request.user
        if not user.is_superuser and user.department_id:
            initial['owner_dept'] = user.department

        # Pre-fill from query params
        audit = self.request.GET.get('audit')
        if audit:
            initial['audit'] = audit
        control = self.request.GET.get('control')
        if control:
            initial['related_control'] = control

        return initial


class FindingUpdateView(DepartmentScopedMixin, UpdateView):
    model = AuditFinding
    form_class = AuditFindingForm
    template_name = 'audits/finding_form.html'
    success_url = reverse_lazy('audits:finding_list')
    department_field = 'owner_dept'

class EvidenceScoreListView(DepartmentScopedMixin, ListView):
    model = EvidenceScore
    template_name = 'audits/score_list.html'
    context_object_name = 'scores'
    paginate_by = 30
    department_field = 'evidence__owner_dept'

    def get_queryset(self):
        qs = super().get_queryset().select_related(
            'evidence', 'evidence__related_control', 'evidence__owner_dept', 'assessor'
        )
        q = self.request.GET.get('q', '').strip()
        if q:
            qs = qs.filter(
                Q(evidence__title__icontains=q)
                | Q(evidence__related_control__code__icontains=q)
            )
        rating = self.request.GET.get('rating')
        if rating == 'excellent':
            qs = qs.filter(total_score__gte=90)
        elif rating == 'good':
            qs = qs.filter(total_score__gte=75, total_score__lt=90)
        elif rating == 'partial':
            qs = qs.filter(total_score__gte=50, total_score__lt=75)
        elif rating == 'weak':
            qs = qs.filter(total_score__lt=50)
        return qs.order_by('-total_score')

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['search_query'] = self.request.GET.get('q', '')
        ctx['selected_rating'] = self.request.GET.get('rating', '')

        base = super().get_queryset()
        user = self.request.user
        if not user.is_superuser and user.department_id:
            base = base.filter(evidence__owner_dept=user.department)
        all_scores = list(base)
        ctx['total_count'] = len(all_scores)
        ctx['excellent_count'] = sum(1 for s in all_scores if s.total_score >= 90)
        ctx['good_count'] = sum(1 for s in all_scores if 75 <= s.total_score < 90)
        ctx['partial_count'] = sum(1 for s in all_scores if 50 <= s.total_score < 75)
        ctx['weak_count'] = sum(1 for s in all_scores if s.total_score < 50)
        if all_scores:
            ctx['avg_score'] = round(sum(s.total_score for s in all_scores) / len(all_scores), 1)
        else:
            ctx['avg_score'] = 0
        return ctx

# ============================================================
# ACTION ITEMS (Remediation sub-tasks under findings)
# ============================================================

from django.contrib.auth.mixins import LoginRequiredMixin as _LRM3
from django.shortcuts import get_object_or_404, redirect
from django.contrib import messages
from django.views.decorators.http import require_POST
from django.utils import timezone as _tz2

from .models import ActionItem
from .forms import ActionItemForm


class ActionItemListView(DepartmentScopedMixin, ListView):
    model = ActionItem
    template_name = 'audits/action_list.html'
    context_object_name = 'actions'
    paginate_by = 30
    department_field = 'owner_dept'

    def get_queryset(self):
        qs = super().get_queryset().select_related('finding', 'owner_user', 'owner_dept')
        q = self.request.GET.get('q', '').strip()
        if q:
            qs = qs.filter(Q(title__icontains=q) | Q(description__icontains=q) | Q(finding__title__icontains=q))
        status = self.request.GET.get('status')
        if status:
            qs = qs.filter(status=status)
        priority = self.request.GET.get('priority')
        if priority:
            qs = qs.filter(priority=priority)
        return qs.order_by('due_date', '-priority')

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['statuses'] = ActionItem.STATUS_CHOICES
        ctx['priorities'] = ActionItem.PRIORITY_CHOICES
        ctx['search_query'] = self.request.GET.get('q', '')
        ctx['selected_status'] = self.request.GET.get('status', '')
        ctx['selected_priority'] = self.request.GET.get('priority', '')

        base = super().get_queryset()
        user = self.request.user
        if not user.is_superuser and user.department_id:
            base = base.filter(owner_dept=user.department)
        all_a = list(base)
        ctx['total_count'] = len(all_a)
        ctx['open_count'] = sum(1 for a in all_a if a.status not in ('completed', 'cancelled'))
        ctx['in_progress_count'] = sum(1 for a in all_a if a.status == 'in_progress')
        ctx['completed_count'] = sum(1 for a in all_a if a.status == 'completed')
        ctx['overdue_count'] = sum(1 for a in all_a if a.is_overdue)
        return ctx


class ActionItemDetailView(_LRM3, DetailView):
    model = ActionItem
    template_name = 'audits/action_detail.html'
    context_object_name = 'action'


class ActionItemCreateView(_LRM3, CreateView):
    model = ActionItem
    form_class = ActionItemForm
    template_name = 'audits/action_form.html'

    def get_initial(self):
        initial = super().get_initial()
        finding_pk = self.request.GET.get('finding')
        if finding_pk:
            try:
                f = AuditFinding.objects.get(pk=finding_pk)
                initial['finding'] = f
                initial['owner_dept'] = f.owner_dept
            except AuditFinding.DoesNotExist:
                pass
        return initial

    def get_success_url(self):
        return reverse_lazy('audits:action_detail', kwargs={'pk': self.object.pk})

    def form_valid(self, form):
        response = super().form_valid(form)
        messages.success(self.request, f'Action item {self.object.action_id} created.')
        return response


class ActionItemUpdateView(_LRM3, UpdateView):
    model = ActionItem
    form_class = ActionItemForm
    template_name = 'audits/action_form.html'

    def get_success_url(self):
        return reverse_lazy('audits:action_detail', kwargs={'pk': self.object.pk})


@require_POST
def action_mark_complete(request, pk):
    action = get_object_or_404(ActionItem, pk=pk)
    action.status = 'completed'
    action.progress_percent = 100
    action.completed_date = _tz2.now().date()
    action.save()
    messages.success(request, f'{action.action_id} marked complete.')
    return redirect('audits:action_detail', pk=pk)


# ============================================================
# AUDIT PDF REPORT
# ============================================================

from core.reports import render_pdf as _render_pdf_audit


class AuditReportView(LoginRequiredMixin, DetailView):
    """Renders a full audit engagement report as PDF."""
    model = Audit

    def get(self, request, *args, **kwargs):
        from django.utils import timezone
        audit = self.get_object()
        findings = audit.findings.select_related(
            'related_control', 'owner_user'
        ).prefetch_related('action_items').order_by('-severity')
        tests = audit.control_tests.select_related('control', 'tester').order_by('-test_date')
        evidence_items = audit.evidence_items.select_related(
            'related_control', 'owner_user'
        ).prefetch_related('scoring')

        ctx = {
            'audit': audit,
            'findings': findings,
            'tests': tests,
            'evidence_items': evidence_items,
            'generated_at': timezone.now(),
            'generated_by': request.user,
        }
        filename = f'audit_{audit.pk}_{audit.name[:40].replace(" ", "_")}_{timezone.now().strftime("%Y%m%d")}.pdf'
        return _render_pdf_audit(request, 'reports/audit_report.html', ctx, filename)