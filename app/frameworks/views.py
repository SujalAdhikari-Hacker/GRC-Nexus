from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import PermissionDenied
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse_lazy
from django.utils import timezone
from django.views.decorators.http import require_POST
from django.views.generic import (
    CreateView, DetailView, ListView, TemplateView, UpdateView,
)

from controls.models import Control, ControlFrameworkMapping
from core.correlation import (
    get_control_coverage_by_control_for_framework,
    get_framework_coverage,
)
from core.input_validation import choice, positive_int, search_query
from core.mixins import (
    ChangeScopedMixin,
    DepartmentCreateMixin,
    DepartmentPinnedMixin,
    DepartmentScopedMixin,
    SuperuserOnlyMixin,
    user_can_change,
)

from .forms import (
    ComplianceAssessmentForm,
    ComplianceAssessmentItemForm,
    FrameworkControlForm,
    FrameworkForm,
)
from .models import ComplianceAssessment, ComplianceAssessmentItem, Framework, FrameworkControl


# ============================================================
# FRAMEWORKS — readable by any signed-in user, editable by superusers
# ============================================================

class FrameworkListView(LoginRequiredMixin, ListView):
    model = Framework
    template_name = 'frameworks/framework_list.html'
    context_object_name = 'frameworks'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['frameworks_with_coverage'] = [
            (fw, get_framework_coverage(fw)) for fw in self.object_list
        ]
        return ctx


class FrameworkDetailView(LoginRequiredMixin, DetailView):
    model = Framework
    template_name = 'frameworks/framework_detail.html'
    context_object_name = 'framework'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['coverage'] = get_framework_coverage(self.object)
        direct_ids = set(
            Control.objects.filter(framework_controls__framework=self.object)
            .values_list('framework_controls__pk', flat=True)
        )
        full_mapped_ids = set(
            ControlFrameworkMapping.objects.filter(
                framework_control__framework=self.object,
                relationship__in=('equal', 'superset'),
            ).values_list('framework_control_id', flat=True)
        )
        rows = []
        for fc, controls in get_control_coverage_by_control_for_framework(self.object):
            if not controls:
                tier = 'gap'
            elif fc.pk in direct_ids or fc.pk in full_mapped_ids:
                tier = 'full'
            else:
                tier = 'partial'
            rows.append((fc, controls, tier))
        ctx['control_rows'] = rows
        return ctx


class ComplianceStatusView(LoginRequiredMixin, TemplateView):
    template_name = 'frameworks/compliance_status.html'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)

        frameworks = list(Framework.objects.all().order_by('name'))

        rows = []
        total_weighted = 0.0
        total_requirements = 0
        for fw in frameworks:
            cov = get_framework_coverage(fw)
            rows.append({'framework': fw, 'cov': cov})
            total_weighted += (cov['percent'] / 100.0) * cov['total'] if cov['total'] else 0
            total_requirements += cov['total']

        overall_percent = round((total_weighted / total_requirements) * 100) if total_requirements else 0

        top_controls = []
        for c in Control.objects.all().prefetch_related('framework_mappings', 'framework_controls'):
            count = c.framework_controls.count() + c.framework_mappings.count()
            if count > 0:
                top_controls.append({'control': c, 'count': count})
        top_controls.sort(key=lambda x: -x['count'])

        covered_fc_ids = set(
            Control.objects.values_list('framework_controls__pk', flat=True)
        ) | set(
            ControlFrameworkMapping.objects.values_list('framework_control__pk', flat=True)
        )
        uncovered = FrameworkControl.objects.exclude(pk__in=covered_fc_ids).select_related('framework')

        ctx.update({
            'rows': rows,
            'overall_percent': overall_percent,
            'total_frameworks': len(frameworks),
            'total_requirements': total_requirements,
            'top_controls': top_controls[:10],
            'uncovered': uncovered[:20],
            'uncovered_count': uncovered.count(),
        })
        return ctx


# ============================================================
# FRAMEWORK CREATE / UPDATE (platform configuration — superuser only)
# ============================================================

class FrameworkCreateView(SuperuserOnlyMixin, CreateView):
    model = Framework
    form_class = FrameworkForm
    template_name = 'frameworks/framework_form.html'

    def form_valid(self, form):
        response = super().form_valid(form)
        messages.success(self.request, f'Framework "{self.object.name}" created.')
        return response

    def get_success_url(self):
        return reverse_lazy('frameworks:detail', kwargs={'pk': self.object.pk})


class FrameworkUpdateView(SuperuserOnlyMixin, UpdateView):
    model = Framework
    form_class = FrameworkForm
    template_name = 'frameworks/framework_form.html'

    def form_valid(self, form):
        response = super().form_valid(form)
        messages.success(self.request, f'Framework "{self.object.name}" updated.')
        return response

    def get_success_url(self):
        return reverse_lazy('frameworks:detail', kwargs={'pk': self.object.pk})


class FrameworkControlCreateView(SuperuserOnlyMixin, CreateView):
    model = FrameworkControl
    form_class = FrameworkControlForm
    template_name = 'frameworks/framework_control_form.html'

    def get_initial(self):
        initial = super().get_initial()
        fw_pk = self.request.GET.get('framework')
        if fw_pk:
            initial['framework'] = positive_int(fw_pk, 'framework')
        return initial

    def form_valid(self, form):
        response = super().form_valid(form)
        messages.success(self.request, f'Requirement {self.object.code} added.')
        return response

    def get_success_url(self):
        return reverse_lazy('frameworks:detail', kwargs={'pk': self.object.framework.pk})


class FrameworkControlUpdateView(SuperuserOnlyMixin, UpdateView):
    model = FrameworkControl
    form_class = FrameworkControlForm
    template_name = 'frameworks/framework_control_form.html'

    def form_valid(self, form):
        response = super().form_valid(form)
        messages.success(self.request, f'Requirement {self.object.code} updated.')
        return response

    def get_success_url(self):
        return reverse_lazy('frameworks:detail', kwargs={'pk': self.object.framework.pk})


# ============================================================
# COMPLIANCE ASSESSMENTS — department scoped
# ============================================================

class ComplianceAssessmentListView(DepartmentScopedMixin, ListView):
    model = ComplianceAssessment
    template_name = 'frameworks/assessment_list.html'
    context_object_name = 'assessments'
    paginate_by = 25
    department_field = 'owner_dept'

    def get_queryset(self):
        qs = super().get_queryset().select_related('framework', 'assessor', 'owner_dept')
        q = search_query(self.request.GET.get('q', ''))
        if q:
            qs = qs.filter(Q(name__icontains=q) | Q(assessment_id__icontains=q))
        status = choice(
            self.request.GET.get('status'),
            {value for value, _label in ComplianceAssessment.STATUS_CHOICES},
            'status', allow_blank=True,
        )
        if status:
            qs = qs.filter(status=status)
        return qs.order_by('-assessment_date')

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        base = self.get_queryset()
        ctx['statuses'] = ComplianceAssessment.STATUS_CHOICES
        ctx['search_query'] = self.request.GET.get('q', '')
        ctx['selected_status'] = self.request.GET.get('status', '')
        ctx['total_count'] = base.count()
        ctx['in_progress_count'] = base.filter(status='in_progress').count()
        ctx['completed_count'] = base.filter(status='completed').count()
        ctx['draft_count'] = base.filter(status='draft').count()
        return ctx


class ComplianceAssessmentDetailView(DepartmentScopedMixin, DetailView):
    model = ComplianceAssessment
    template_name = 'frameworks/assessment_detail.html'
    context_object_name = 'assessment'
    department_field = 'owner_dept'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        items = self.object.items.select_related(
            'framework_control', 'owner_user'
        ).order_by('framework_control__code')

        status_filter = choice(
            self.request.GET.get('item_status'),
            {value for value, _label in ComplianceAssessmentItem.STATUS_CHOICES},
            'item_status', allow_blank=True,
        )
        if status_filter:
            items = items.filter(status=status_filter)

        ctx['items'] = items
        ctx['total_items'] = self.object.total_items
        ctx['status_filter'] = status_filter or ''
        ctx['now_date'] = timezone.localdate()
        return ctx


class ComplianceAssessmentCreateView(DepartmentCreateMixin, DepartmentScopedMixin, CreateView):
    model = ComplianceAssessment
    form_class = ComplianceAssessmentForm
    template_name = 'frameworks/assessment_form.html'
    success_url = reverse_lazy('frameworks:assessment_list')

    def get_initial(self):
        initial = super().get_initial()
        user = self.request.user
        if user.department_id:
            initial['owner_dept'] = user.department
        initial['assessor'] = user
        initial['assessment_date'] = timezone.localdate()
        return initial

    def form_valid(self, form):
        form.instance.created_by = self.request.user
        form.instance.updated_by = self.request.user
        response = super().form_valid(form)
        items = [
            ComplianceAssessmentItem(
                assessment=self.object,
                framework_control=fc,
                status='not_assessed',
                created_by=self.request.user,
                updated_by=self.request.user,
            )
            for fc in self.object.framework.controls.all()
        ]
        if items:
            ComplianceAssessmentItem.objects.bulk_create(items)
        messages.success(
            self.request,
            f'Assessment {self.object.assessment_id} created with {self.object.total_items} checklist items.'
        )
        return response

    def get_success_url(self):
        return reverse_lazy('frameworks:assessment_detail', kwargs={'pk': self.object.pk})


class ComplianceAssessmentUpdateView(DepartmentPinnedMixin, ChangeScopedMixin, UpdateView):
    model = ComplianceAssessment
    form_class = ComplianceAssessmentForm
    template_name = 'frameworks/assessment_form.html'
    department_field = 'owner_dept'

    def get_success_url(self):
        return reverse_lazy('frameworks:assessment_detail', kwargs={'pk': self.object.pk})


class ComplianceAssessmentItemUpdateView(DepartmentPinnedMixin, ChangeScopedMixin, UpdateView):
    model = ComplianceAssessmentItem
    form_class = ComplianceAssessmentItemForm
    template_name = 'frameworks/assessment_item_form.html'
    context_object_name = 'item'
    department_field = 'assessment__owner_dept'

    def get_success_url(self):
        return reverse_lazy('frameworks:assessment_detail', kwargs={'pk': self.object.assessment.pk})

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['assessment'] = self.object.assessment
        return ctx


@login_required
@require_POST
def assessment_item_quick_status(request, pk):
    """Inline status updater used by the assessment detail page."""
    item = get_object_or_404(
        ComplianceAssessmentItem.objects.select_related('assessment'), pk=pk
    )
    if not user_can_change(request.user, item.assessment):
        raise PermissionDenied
    new_status = choice(
        request.POST.get('status'),
        {value for value, _label in ComplianceAssessmentItem.STATUS_CHOICES},
        'status',
    )
    item.status = new_status
    item.save(update_fields=['status', 'updated_at'])
    return redirect('frameworks:assessment_detail', pk=item.assessment.pk)
