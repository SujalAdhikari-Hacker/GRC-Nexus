from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse_lazy
from django.utils import timezone
from django.views.decorators.http import require_POST
from django.views.generic import (
    CreateView,
    DetailView,
    ListView,
    TemplateView,
    UpdateView,
)

from core.input_validation import (
    choice, integer, positive_int, search_query, text,
)
from core.mixins import (
    ChangeScopedMixin,
    BulkActionsMixin,
    CsvExportMixin,
    DepartmentCreateMixin,
    DepartmentPinnedMixin,
    DepartmentScopedMixin,
    SavedViewsMixin,
    scope_queryset,
    user_can_change,
)
from core.media import serve_stored_file
from core.reports import render_pdf

from .forms import (
    ActionItemForm,
    AuditFindingForm,
    AuditForm,
    ControlTestForm,
    EvidenceItemForm,
    EvidenceScoreForm,
)
from .models import (
    ActionItem,
    Audit,
    AuditFinding,
    ControlTest,
    EvidenceItem,
    EvidenceScore,
    EvidenceVersion,
)


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
        q = search_query(self.request.GET.get('q', ''))
        if q:
            qs = qs.filter(Q(name__icontains=q) | Q(scope__icontains=q))
        atype = choice(
            self.request.GET.get('type'),
            {value for value, _label in Audit.TYPE_CHOICES},
            'type', allow_blank=True,
        )
        if atype:
            qs = qs.filter(audit_type=atype)
        status = choice(
            self.request.GET.get('status'),
            {value for value, _label in Audit.STATUS_CHOICES},
            'status', allow_blank=True,
        )
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

        base = scope_queryset(Audit.objects.all(), self.request.user)
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


class AuditCreateView(DepartmentCreateMixin, DepartmentScopedMixin, CreateView):
    model = Audit
    form_class = AuditForm
    template_name = 'audits/audit_form.html'
    success_url = reverse_lazy('audits:list')

    def get_initial(self):
        initial = super().get_initial()
        if self.request.user.department_id:
            initial['owner_dept'] = self.request.user.department
        initial['start_date'] = timezone.localdate()
        return initial


class AuditUpdateView(DepartmentPinnedMixin, ChangeScopedMixin, UpdateView):
    model = Audit
    form_class = AuditForm
    template_name = 'audits/audit_form.html'
    success_url = reverse_lazy('audits:list')
    department_field = 'owner_dept'


class AuditTimelineView(DepartmentScopedMixin, TemplateView):
    template_name = 'audits/audit_timeline.html'
    department_field = 'owner_dept'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        qs = scope_queryset(
            Audit.objects.all().select_related('auditor_lead', 'owner_dept'),
            self.request.user,
        )

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
        ('Score', lambda e: e.score.total_score if getattr(e, 'score', None) else ''),
        ('Created', lambda e: e.created_at.strftime('%Y-%m-%d')),
    ]

    def get_queryset(self):
        qs = super().get_queryset().select_related('related_control', 'owner_user', 'owner_dept', 'audit')
        q = search_query(self.request.GET.get('q', ''))
        if q:
            qs = qs.filter(Q(title__icontains=q) | Q(notes__icontains=q))
        etype = choice(
            self.request.GET.get('type'),
            {value for value, _label in EvidenceItem.TYPE_CHOICES},
            'type', allow_blank=True,
        )
        if etype:
            qs = qs.filter(evidence_type=etype)
        control = self.request.GET.get('control')
        if control:
            qs = qs.filter(
                related_control_id=positive_int(control, 'control')
            )
        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['evidence_types'] = EvidenceItem.TYPE_CHOICES
        ctx['search_query'] = self.request.GET.get('q', '')
        ctx['selected_type'] = self.request.GET.get('type', '')

        base = scope_queryset(EvidenceItem.objects.all(), self.request.user)
        all_items = list(base)
        ctx['total_count'] = len(all_items)
        ctx['scored_count'] = sum(1 for e in all_items if hasattr(e, 'scoring'))
        ctx['unscored_count'] = ctx['total_count'] - ctx['scored_count']
        ctx['strong_count'] = sum(
            1 for e in all_items if hasattr(e, 'scoring') and e.scoring.total_score >= 75
        )
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


class EvidenceCreateView(DepartmentCreateMixin, DepartmentScopedMixin, CreateView):
    model = EvidenceItem
    form_class = EvidenceItemForm
    template_name = 'audits/evidence_form.html'
    success_url = reverse_lazy('audits:evidence_list')

    def get_initial(self):
        initial = super().get_initial()
        if self.request.user.department_id:
            initial['owner_dept'] = self.request.user.department
        control = self.request.GET.get('control')
        if control:
            initial['related_control'] = positive_int(control, 'control')
        audit = self.request.GET.get('audit')
        if audit:
            initial['audit'] = positive_int(audit, 'audit')
        return initial

    def form_valid(self, form):
        # Stamped before save so the upload's version row names its uploader.
        form.instance.created_by = self.request.user
        form.instance.updated_by = self.request.user
        return super().form_valid(form)


class EvidenceUpdateView(DepartmentPinnedMixin, ChangeScopedMixin, UpdateView):
    model = EvidenceItem
    form_class = EvidenceItemForm
    template_name = 'audits/evidence_form.html'
    success_url = reverse_lazy('audits:evidence_list')
    department_field = 'owner_dept'

    def form_valid(self, form):
        form.instance.updated_by = self.request.user
        return super().form_valid(form)


@login_required
def evidence_version_download(request, pk, version):
    """Serve one recorded version of an evidence file.

    Authorisation goes through the evidence item, so a guessed version number
    still 404s for anyone who cannot see the record.
    """
    item = get_object_or_404(
        scope_queryset(EvidenceItem.objects.all(), request.user), pk=pk
    )
    stored = get_object_or_404(EvidenceVersion, evidence=item, version=version)
    response = serve_stored_file(stored.file_path)
    response['X-Checksum-SHA256'] = stored.sha256
    return response


class EvidenceScoreCreateView(LoginRequiredMixin, CreateView):
    model = EvidenceScore
    form_class = EvidenceScoreForm
    template_name = 'audits/evidence_score_form.html'

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return self.handle_no_permission()
        self.evidence = get_object_or_404(EvidenceItem, pk=kwargs['evidence_pk'])
        if not user_can_change(request.user, self.evidence):
            raise PermissionDenied
        return super().dispatch(request, *args, **kwargs)

    def form_valid(self, form):
        form.instance.evidence = self.evidence
        form.instance.assessor = self.request.user
        return super().form_valid(form)

    def get_success_url(self):
        return reverse_lazy('audits:evidence_detail', kwargs={'pk': self.evidence.pk})

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['evidence'] = self.evidence
        return ctx


class EvidenceScoreUpdateView(DepartmentPinnedMixin, ChangeScopedMixin, UpdateView):
    model = EvidenceScore
    form_class = EvidenceScoreForm
    template_name = 'audits/evidence_score_form.html'
    department_field = 'evidence__owner_dept'

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
        q = search_query(self.request.GET.get('q', ''))
        if q:
            qs = qs.filter(
                Q(control__code__icontains=q)
                | Q(control__name__icontains=q)
                | Q(procedure_notes__icontains=q)
            )
        result = choice(
            self.request.GET.get('result'),
            {value for value, _label in ControlTest.RESULT_CHOICES},
            'result', allow_blank=True,
        )
        if result:
            qs = qs.filter(result=result)
        return qs.order_by('-test_date')

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['results'] = ControlTest.RESULT_CHOICES
        ctx['search_query'] = self.request.GET.get('q', '')
        ctx['selected_result'] = self.request.GET.get('result', '')

        base = scope_queryset(ControlTest.objects.all(), self.request.user)
        ctx['total_count'] = base.count()
        ctx['pass_count'] = base.filter(result='pass').count()
        ctx['fail_count'] = base.filter(result='fail').count()
        ctx['partial_count'] = base.filter(result='partial').count()
        return ctx


class ControlTestCreateView(DepartmentCreateMixin, DepartmentScopedMixin, CreateView):
    model = ControlTest
    form_class = ControlTestForm
    template_name = 'audits/test_form.html'
    success_url = reverse_lazy('audits:test_list')

    def get_initial(self):
        initial = super().get_initial()
        if self.request.user.department_id:
            initial['owner_dept'] = self.request.user.department
        control = self.request.GET.get('control')
        if control:
            initial['control'] = positive_int(control, 'control')
        audit = self.request.GET.get('audit')
        if audit:
            initial['audit'] = positive_int(audit, 'audit')
        return initial

    def form_valid(self, form):
        form.instance.tester = self.request.user
        return super().form_valid(form)


class ControlTestUpdateView(DepartmentPinnedMixin, ChangeScopedMixin, UpdateView):
    model = ControlTest
    form_class = ControlTestForm
    template_name = 'audits/test_form.html'
    success_url = reverse_lazy('audits:test_list')
    department_field = 'owner_dept'


# ==================================================================
# AUDIT FINDINGS
# ==================================================================

class FindingListView(BulkActionsMixin, SavedViewsMixin, DepartmentScopedMixin, CsvExportMixin, ListView):
    model = AuditFinding
    template_name = 'audits/finding_list.html'
    context_object_name = 'findings'
    paginate_by = 25
    department_field = 'owner_dept'

    # Bulk edits never offer 'closed': closure must go through the verification
    # loop, which a bulk queryset.update() would bypass.
    bulk_actions = {
        'set_severity': {
            'label': 'Set severity',
            'field': 'severity',
            'choices': AuditFinding.SEVERITY_CHOICES,
        },
        'set_status': {
            'label': 'Set status',
            'field': 'status',
            'choices': lambda: [
                choice for choice in AuditFinding.STATUS_CHOICES
                if choice[0] != 'closed'
            ],
        },
    }

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
        q = search_query(self.request.GET.get('q', ''))
        if q:
            qs = qs.filter(Q(title__icontains=q) | Q(description__icontains=q))
        severity = choice(
            self.request.GET.get('severity'),
            {value for value, _label in AuditFinding.SEVERITY_CHOICES},
            'severity', allow_blank=True,
        )
        if severity:
            qs = qs.filter(severity=severity)
        status = choice(
            self.request.GET.get('status'),
            {value for value, _label in AuditFinding.STATUS_CHOICES},
            'status', allow_blank=True,
        )
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
        ctx['now_date'] = timezone.localdate()

        base = scope_queryset(AuditFinding.objects.all(), self.request.user)
        ctx['total_count'] = base.count()
        ctx['open_count'] = base.filter(status='open').count()
        ctx['critical_count'] = base.filter(severity='critical').count()
        ctx['overdue_count'] = base.filter(
            due_date__lt=timezone.localdate()
        ).exclude(status__in=['resolved', 'closed', 'accepted']).count()
        return ctx


class FindingDetailView(DepartmentScopedMixin, DetailView):
    model = AuditFinding
    template_name = 'audits/finding_detail.html'
    context_object_name = 'finding'
    department_field = 'owner_dept'


class FindingCreateView(DepartmentCreateMixin, DepartmentScopedMixin, CreateView):
    model = AuditFinding
    form_class = AuditFindingForm
    template_name = 'audits/finding_form.html'
    success_url = reverse_lazy('audits:finding_list')

    def get_initial(self):
        initial = super().get_initial()
        if self.request.user.department_id:
            initial['owner_dept'] = self.request.user.department
        audit = self.request.GET.get('audit')
        if audit:
            initial['audit'] = positive_int(audit, 'audit')
        control = self.request.GET.get('control')
        if control:
            initial['related_control'] = positive_int(control, 'control')
        return initial


class FindingUpdateView(DepartmentPinnedMixin, ChangeScopedMixin, UpdateView):
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
        q = search_query(self.request.GET.get('q', ''))
        if q:
            qs = qs.filter(
                Q(evidence__title__icontains=q)
                | Q(evidence__related_control__code__icontains=q)
            )
        rating = choice(
            self.request.GET.get('rating'),
            {'excellent', 'good', 'partial', 'weak'},
            'rating', allow_blank=True,
        )
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

        base = scope_queryset(EvidenceScore.objects.all(), self.request.user, field='evidence__owner_dept')
        all_scores = list(base)
        ctx['total_count'] = len(all_scores)
        ctx['excellent_count'] = sum(1 for s in all_scores if s.total_score >= 90)
        ctx['good_count'] = sum(1 for s in all_scores if 75 <= s.total_score < 90)
        ctx['partial_count'] = sum(1 for s in all_scores if 50 <= s.total_score < 75)
        ctx['weak_count'] = sum(1 for s in all_scores if s.total_score < 50)
        ctx['avg_score'] = (
            round(sum(s.total_score for s in all_scores) / len(all_scores), 1)
            if all_scores else 0
        )
        return ctx


# ============================================================
# ACTION ITEMS (Remediation sub-tasks under findings)
# ============================================================

class ActionItemListView(DepartmentScopedMixin, ListView):
    model = ActionItem
    template_name = 'audits/action_list.html'
    context_object_name = 'actions'
    paginate_by = 30
    department_field = 'owner_dept'

    def get_queryset(self):
        qs = super().get_queryset().select_related('finding', 'owner_user', 'owner_dept')
        q = search_query(self.request.GET.get('q', ''))
        if q:
            qs = qs.filter(
                Q(title__icontains=q) | Q(description__icontains=q) | Q(finding__title__icontains=q)
            )
        status = choice(
            self.request.GET.get('status'),
            {value for value, _label in ActionItem.STATUS_CHOICES},
            'status', allow_blank=True,
        )
        if status:
            qs = qs.filter(status=status)
        # ActionItem priority is stored as an integer (1-4).
        priority = integer(
            self.request.GET.get('priority'), 'priority',
            minimum=1, maximum=4, default=0,
        )
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

        all_a = list(scope_queryset(ActionItem.objects.all(), self.request.user))
        ctx['total_count'] = len(all_a)
        ctx['open_count'] = sum(1 for a in all_a if a.status not in ('completed', 'cancelled'))
        ctx['in_progress_count'] = sum(1 for a in all_a if a.status == 'in_progress')
        ctx['completed_count'] = sum(1 for a in all_a if a.status == 'completed')
        ctx['overdue_count'] = sum(1 for a in all_a if a.is_overdue)
        return ctx


class ActionItemDetailView(DepartmentScopedMixin, DetailView):
    model = ActionItem
    template_name = 'audits/action_detail.html'
    context_object_name = 'action'
    department_field = 'owner_dept'


class ActionItemCreateView(DepartmentCreateMixin, DepartmentScopedMixin, CreateView):
    model = ActionItem
    form_class = ActionItemForm
    template_name = 'audits/action_form.html'

    def get_initial(self):
        initial = super().get_initial()
        finding_pk = self.request.GET.get('finding')
        if finding_pk:
            finding = AuditFinding.objects.filter(
                pk=positive_int(finding_pk, 'finding')
            ).first()
            if finding and user_can_change(self.request.user, finding):
                initial['finding'] = finding
                initial['owner_dept'] = finding.owner_dept
        return initial

    def get_success_url(self):
        return reverse_lazy('audits:action_detail', kwargs={'pk': self.object.pk})

    def form_valid(self, form):
        finding = form.cleaned_data.get('finding')
        if finding and not user_can_change(self.request.user, finding):
            raise PermissionDenied
        response = super().form_valid(form)
        messages.success(self.request, f'Action item {self.object.action_id} created.')
        return response


class ActionItemUpdateView(DepartmentPinnedMixin, ChangeScopedMixin, UpdateView):
    model = ActionItem
    form_class = ActionItemForm
    template_name = 'audits/action_form.html'
    department_field = 'owner_dept'

    def get_success_url(self):
        return reverse_lazy('audits:action_detail', kwargs={'pk': self.object.pk})


@login_required
@require_POST
def action_mark_complete(request, pk):
    action = get_object_or_404(ActionItem, pk=pk)
    if not user_can_change(request.user, action):
        raise PermissionDenied
    action.status = 'completed'
    action.progress_percent = 100
    action.completed_date = timezone.localdate()
    action.save()
    messages.success(request, f'{action.action_id} marked complete.')
    return redirect('audits:action_detail', pk=pk)


@login_required
@require_POST
def finding_verify(request, pk):
    """Close the loop on a resolved finding: verify the fix, or reject it.

    Verifying requires a department head or superuser — the person who owns the
    remediation should not be the only one signing it off. Verification is only
    offered on a *resolved* finding, and a verified finding is closed in the
    same step. A rejection sends the finding back to ``in_progress``.
    """
    finding = get_object_or_404(AuditFinding, pk=pk)
    if not user_can_change(request.user, finding):
        raise PermissionDenied
    if not (request.user.is_superuser or request.user.is_hod):
        raise PermissionDenied

    decision = choice(
        request.POST.get('decision'), {'verified', 'rejected'}, 'decision'
    )
    notes = text(
        request.POST.get('verification_notes'), 'verification_notes', 2000,
        allow_blank=True, strip=True,
    )

    if decision == 'verified':
        if finding.status != 'resolved':
            messages.error(request, 'Only a resolved finding can be verified.')
            return redirect('audits:finding_detail', pk=pk)
        finding.verification_status = 'verified'
        finding.verified_by = request.user
        finding.verified_at = timezone.now()
        finding.verification_notes = notes
        finding.status = 'closed'
        finding.save()
        messages.success(request, 'Remediation verified — finding closed.')
    elif decision == 'rejected':
        finding.verification_status = 'rejected'
        finding.verified_by = request.user
        finding.verified_at = timezone.now()
        finding.verification_notes = notes
        if finding.status in ('resolved', 'closed'):
            finding.status = 'in_progress'
        finding.save()
        messages.warning(
            request, 'Verification rejected — finding returned for remediation.'
        )
    else:
        messages.error(request, 'Unknown verification decision.')

    return redirect('audits:finding_detail', pk=pk)


# ============================================================
# AUDIT PDF REPORT
# ============================================================

class AuditReportView(DepartmentScopedMixin, DetailView):
    """Renders a full audit engagement report as PDF."""
    model = Audit
    department_field = 'owner_dept'

    def get(self, request, *args, **kwargs):
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
        safe_name = ''.join(c if c.isalnum() else '_' for c in audit.name)[:40]
        filename = f'audit_{audit.pk}_{safe_name}_{timezone.now().strftime("%Y%m%d")}.pdf'
        return render_pdf(request, 'reports/audit_report.html', ctx, filename)
