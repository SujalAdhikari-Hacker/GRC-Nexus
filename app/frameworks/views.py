from django.views.generic import ListView, DetailView, TemplateView
from django.urls import reverse_lazy
from django.views.generic import CreateView, UpdateView
from django.contrib import messages
from .forms import FrameworkForm, FrameworkControlForm
from core.correlation import (
    get_framework_coverage,
    get_control_coverage_by_control_for_framework,
)
from .models import Framework, FrameworkControl


class FrameworkListView(ListView):
    model = Framework
    template_name = 'frameworks/framework_list.html'
    context_object_name = 'frameworks'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        rows = []
        for fw in self.object_list:
            rows.append((fw, get_framework_coverage(fw)))
        ctx['frameworks_with_coverage'] = rows
        return ctx


class FrameworkDetailView(DetailView):
    model = Framework
    template_name = 'frameworks/framework_detail.html'
    context_object_name = 'framework'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['coverage'] = get_framework_coverage(self.object)
        ctx['control_rows'] = get_control_coverage_by_control_for_framework(self.object)
        return ctx


class ComplianceStatusView(TemplateView):
    template_name = 'frameworks/compliance_status.html'

    def get_context_data(self, **kwargs):
        from controls.models import Control

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

        # Which controls contribute to most frameworks?
        top_controls = []
        for c in Control.objects.all().prefetch_related('framework_mappings', 'framework_controls'):
            count = c.framework_controls.count() + c.framework_mappings.count()
            if count > 0:
                top_controls.append({'control': c, 'count': count})
        top_controls.sort(key=lambda x: -x['count'])
        top_controls = top_controls[:10]

        # Requirements not covered (across all frameworks)
        from frameworks.models import FrameworkControl
        from controls.models import ControlFrameworkMapping

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
            'top_controls': top_controls,
            'uncovered': uncovered[:20],
            'uncovered_count': uncovered.count(),
        })
        return ctx


# ============================================================
# COMPLIANCE ASSESSMENTS
# ============================================================

from django.contrib.auth.mixins import LoginRequiredMixin
from django.shortcuts import get_object_or_404, redirect
from django.contrib import messages
from django.urls import reverse_lazy
from django.utils import timezone
from django.db.models import Q
from django.views.generic import ListView, DetailView, CreateView, UpdateView

from .models import ComplianceAssessment, ComplianceAssessmentItem
from .forms import ComplianceAssessmentForm, ComplianceAssessmentItemForm
from core.mixins import DepartmentScopedMixin


class ComplianceAssessmentListView(DepartmentScopedMixin, ListView):
    model = ComplianceAssessment
    template_name = 'frameworks/assessment_list.html'
    context_object_name = 'assessments'
    paginate_by = 25
    department_field = 'owner_dept'

    def get_queryset(self):
        qs = super().get_queryset().select_related('framework', 'assessor', 'owner_dept')
        q = self.request.GET.get('q', '').strip()
        if q:
            qs = qs.filter(Q(name__icontains=q) | Q(assessment_id__icontains=q))
        status = self.request.GET.get('status')
        if status:
            qs = qs.filter(status=status)
        return qs.order_by('-assessment_date')

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['statuses'] = ComplianceAssessment.STATUS_CHOICES
        ctx['search_query'] = self.request.GET.get('q', '')
        ctx['selected_status'] = self.request.GET.get('status', '')

        base = super().get_queryset()
        user = self.request.user
        if not user.is_superuser and user.department_id:
            base = base.filter(owner_dept=user.department)
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
        items = self.object.items.select_related('framework_control', 'owner_user').order_by('framework_control__code')

        status_filter = self.request.GET.get('item_status')
        if status_filter:
            items = items.filter(status=status_filter)

        ctx['items'] = items
        ctx['total_items'] = self.object.total_items
        ctx['status_filter'] = status_filter or ''
        ctx['now_date'] = timezone.now().date()
        return ctx


class ComplianceAssessmentCreateView(DepartmentScopedMixin, CreateView):
    model = ComplianceAssessment
    form_class = ComplianceAssessmentForm
    template_name = 'frameworks/assessment_form.html'
    success_url = reverse_lazy('frameworks:assessment_list')

    def get_initial(self):
        initial = super().get_initial()
        user = self.request.user
        if not user.is_superuser and user.department_id:
            initial['owner_dept'] = user.department
        initial['assessor'] = user
        initial['assessment_date'] = timezone.now().date()
        return initial

    def form_valid(self, form):
        form.instance.created_by = self.request.user
        form.instance.updated_by = self.request.user
        response = super().form_valid(form)
        # Auto-populate one item per framework control, inheriting accountability
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


class ComplianceAssessmentUpdateView(DepartmentScopedMixin, UpdateView):
    model = ComplianceAssessment
    form_class = ComplianceAssessmentForm
    template_name = 'frameworks/assessment_form.html'
    department_field = 'owner_dept'

    def get_success_url(self):
        return reverse_lazy('frameworks:assessment_detail', kwargs={'pk': self.object.pk})


class ComplianceAssessmentItemUpdateView(LoginRequiredMixin, UpdateView):
    model = ComplianceAssessmentItem
    form_class = ComplianceAssessmentItemForm
    template_name = 'frameworks/assessment_item_form.html'
    context_object_name = 'item'

    def get_success_url(self):
        return reverse_lazy('frameworks:assessment_detail', kwargs={'pk': self.object.assessment.pk})

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['assessment'] = self.object.assessment
        return ctx


from django.views.decorators.http import require_POST


@require_POST
def assessment_item_quick_status(request, pk):
    """HTMX-free inline status updater: POST form on the detail page redirects back."""
    item = get_object_or_404(ComplianceAssessmentItem, pk=pk)
    new_status = request.POST.get('status')
    valid = [s[0] for s in ComplianceAssessmentItem.STATUS_CHOICES]
    if new_status in valid:
        item.status = new_status
        item.save(update_fields=['status', 'updated_at'])
    return redirect('frameworks:assessment_detail', pk=item.assessment.pk)


# ============================================================
# FRAMEWORK CREATE / UPDATE
# ============================================================

class FrameworkCreateView(CreateView):
    model = Framework
    form_class = FrameworkForm
    template_name = 'frameworks/framework_form.html'

    def get_success_url(self):
        return reverse_lazy('frameworks:detail', kwargs={'pk': self.object.pk})

    def form_valid(self, form):
        response = super().form_valid(form)
        messages.success(self.request, f'Framework "{self.object.name}" created.')
        return response


class FrameworkUpdateView(UpdateView):
    model = Framework
    form_class = FrameworkForm
    template_name = 'frameworks/framework_form.html'

    def get_success_url(self):
        return reverse_lazy('frameworks:detail', kwargs={'pk': self.object.pk})

    def form_valid(self, form):
        response = super().form_valid(form)
        messages.success(self.request, f'Framework "{self.object.name}" updated.')
        return response


# ============================================================
# FRAMEWORK CONTROL CREATE / UPDATE
# ============================================================

class FrameworkControlCreateView(CreateView):
    model = FrameworkControl
    form_class = FrameworkControlForm
    template_name = 'frameworks/framework_control_form.html'

    def get_initial(self):
        initial = super().get_initial()
        fw_pk = self.request.GET.get('framework')
        if fw_pk:
            initial['framework'] = fw_pk
        return initial

    def get_success_url(self):
        return reverse_lazy('frameworks:detail', kwargs={'pk': self.object.framework.pk})

    def form_valid(self, form):
        response = super().form_valid(form)
        messages.success(self.request, f'Requirement {self.object.code} added.')
        return response


class FrameworkControlUpdateView(UpdateView):
    model = FrameworkControl
    form_class = FrameworkControlForm
    template_name = 'frameworks/framework_control_form.html'

    def get_success_url(self):
        return reverse_lazy('frameworks:detail', kwargs={'pk': self.object.framework.pk})

    def form_valid(self, form):
        response = super().form_valid(form)
        messages.success(self.request, f'Requirement {self.object.code} updated.')
        return response
