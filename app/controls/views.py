from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import PermissionDenied
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse_lazy
from django.views.decorators.http import require_POST
from django.views.generic import (
    CreateView,
    DeleteView,
    DetailView,
    ListView,
    TemplateView,
    UpdateView,
)

from core.correlation import get_framework_coverage, get_full_control_context
from core.mixins import (
    ChangeScopedMixin,
    CsvExportMixin,
    DepartmentCreateMixin,
    DepartmentPinnedMixin,
    DepartmentScopedMixin,
    HODOrSuperuserMixin,
    SavedViewsMixin,
    scope_queryset,
    user_can_change,
)

from .forms import ControlEvidenceForm, ControlForm, ControlFrameworkMappingForm
from .models import Control, ControlEvidence, ControlFrameworkMapping


def _get_control_for_change_or_403(request, pk):
    """Resolve a control for a *write* endpoint, enforcing write access.

    Every caller of this helper creates or mutates data, so it requires
    :func:`user_can_change` — a read-only share must not authorise it.
    """
    control = get_object_or_404(Control, pk=pk)
    if not user_can_change(request.user, control):
        raise PermissionDenied
    return control


class ControlListView(SavedViewsMixin, DepartmentScopedMixin, CsvExportMixin, ListView):
    model = Control
    template_name = 'controls/control_list.html'
    context_object_name = 'controls'
    paginate_by = 25

    csv_filename = 'controls.csv'
    csv_fields = [
        ('Code', 'code'),
        ('Name', 'name'),
        ('Type', 'get_control_type_display'),
        ('Category', 'get_category_display'),
        ('Status', 'get_status_display'),
        ('Lifecycle', 'get_lifecycle_status_display'),
        ('Effectiveness', 'get_effectiveness_rating_display'),
        ('Frequency', 'get_frequency_display'),
        ('Primary Framework', lambda c: c.primary_framework.name if c.primary_framework else ''),
        ('Reference', 'reference'),
        ('Department', lambda c: c.owner_dept.name),
        ('Owner', lambda c: c.owner_user.username if c.owner_user else ''),
        ('Shared', lambda c: 'Yes' if c.is_shared else 'No'),
        ('Risk Count', lambda c: c.risks.count()),
    ]

    def get_queryset(self):
        qs = super().get_queryset().select_related('owner_dept', 'primary_framework', 'owner_user')
        q = self.request.GET.get('q', '').strip()
        if q:
            qs = qs.filter(Q(name__icontains=q) | Q(code__icontains=q) | Q(reference__icontains=q))
        status = self.request.GET.get('status')
        if status:
            qs = qs.filter(status=status)
        category = self.request.GET.get('category')
        if category:
            qs = qs.filter(category=category)
        lifecycle = self.request.GET.get('lifecycle')
        if lifecycle:
            qs = qs.filter(lifecycle_status=lifecycle)
        effectiveness = self.request.GET.get('effectiveness')
        if effectiveness:
            qs = qs.filter(effectiveness_rating=effectiveness)
        return qs.order_by('code')

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        all_controls = list(self.get_queryset())
        ctx['statuses'] = Control.STATUS_CHOICES
        ctx['categories_choices'] = Control.CATEGORY_CHOICES
        ctx['lifecycle_choices'] = Control.LIFECYCLE_CHOICES
        ctx['effectiveness_choices'] = Control.EFFECTIVENESS_RATING_CHOICES
        ctx['search_query'] = self.request.GET.get('q', '')
        ctx['selected_status'] = self.request.GET.get('status', '')
        ctx['selected_category'] = self.request.GET.get('category', '')
        ctx['selected_lifecycle'] = self.request.GET.get('lifecycle', '')
        ctx['selected_effectiveness'] = self.request.GET.get('effectiveness', '')
        ctx['total_count'] = len(all_controls)
        ctx['effective_count'] = sum(1 for c in all_controls if c.effectiveness_rating == 'effective')
        ctx['not_tested_count'] = sum(1 for c in all_controls if c.effectiveness_rating == 'not_tested')
        ctx['operational_count'] = sum(
            1 for c in all_controls if c.lifecycle_status in ['operational', 'monitored', 'reviewed']
        )
        return ctx


class ControlDetailView(DepartmentScopedMixin, DetailView):
    model = Control
    template_name = 'controls/control_detail.html'
    context_object_name = 'control'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx.update(get_full_control_context(self.object))
        ctx['framework_mappings'] = self.object.framework_mappings.select_related('framework_control__framework')
        ctx['audit_tests'] = self.object.audit_tests.select_related('tester', 'audit').order_by('-test_date')[:10]
        return ctx


class _ControlSharingGateMixin:
    """Only HODs/superusers may publish a control org-wide (``is_shared``).

    Removing the field from the form (rather than trusting the template) means
    a crafted POST from a regular user cannot flag a control — and its
    evidence — as visible to every department.
    """

    def get_form(self, form_class=None):
        form = super().get_form(form_class)
        user = self.request.user
        if not (user.is_superuser or getattr(user, 'is_hod', False)):
            form.fields.pop('is_shared', None)
        return form


class ControlCreateView(
    _ControlSharingGateMixin, DepartmentCreateMixin, DepartmentScopedMixin, CreateView
):
    model = Control
    form_class = ControlForm
    template_name = 'controls/control_form.html'
    success_url = reverse_lazy('controls:list')

    def get_initial(self):
        initial = super().get_initial()
        if self.request.user.department_id:
            initial['owner_dept'] = self.request.user.department
        return initial

    def form_valid(self, form):
        form.instance.created_by = self.request.user
        form.instance.updated_by = self.request.user
        return super().form_valid(form)

    def get_context_data(self, **kwargs):
        return _framework_context(self, super().get_context_data(**kwargs))


class ControlUpdateView(
    _ControlSharingGateMixin, DepartmentPinnedMixin, ChangeScopedMixin, UpdateView
):
    model = Control
    form_class = ControlForm
    template_name = 'controls/control_form.html'
    success_url = reverse_lazy('controls:list')

    def form_valid(self, form):
        form.instance.updated_by = self.request.user
        return super().form_valid(form)

    def get_context_data(self, **kwargs):
        return _framework_context(self, super().get_context_data(**kwargs))


class ControlDeleteView(HODOrSuperuserMixin, ChangeScopedMixin, DeleteView):
    model = Control
    template_name = 'core/confirm_delete.html'
    success_url = reverse_lazy('controls:list')

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['object_verbose_name'] = 'control'
        ctx['cancel_url'] = reverse_lazy('controls:detail', kwargs={'pk': self.object.pk})
        linked = self.object.risks.count()
        if linked:
            ctx['related_warning'] = (
                f'This control mitigates {linked} risk(s). Removing it will '
                'recompute those risks (their residual score may rise).'
            )
        return ctx

    def form_valid(self, form):
        label = self.object.code
        response = super().form_valid(form)
        messages.success(self.request, f'Control {label} deleted.')
        return response


class ControlEvidenceCreateView(LoginRequiredMixin, CreateView):
    model = ControlEvidence
    form_class = ControlEvidenceForm
    template_name = 'controls/evidence_form.html'

    def dispatch(self, request, *args, **kwargs):
        # Authenticate before touching the object. Resolving first would let an
        # anonymous visitor distinguish a real ID (403) from a missing one
        # (404) — an enumeration oracle — and would skip the login redirect.
        if not request.user.is_authenticated:
            return self.handle_no_permission()
        self.control = _get_control_for_change_or_403(request, kwargs['control_pk'])
        return super().dispatch(request, *args, **kwargs)

    def form_valid(self, form):
        form.instance.control = self.control
        form.instance.uploaded_by = self.request.user
        return super().form_valid(form)

    def get_success_url(self):
        return reverse_lazy('controls:detail', kwargs={'pk': self.control.pk})

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['control'] = self.control
        return ctx


class ControlFrameworkMappingCreateView(LoginRequiredMixin, CreateView):
    model = ControlFrameworkMapping
    form_class = ControlFrameworkMappingForm
    template_name = 'controls/mapping_form.html'

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return self.handle_no_permission()
        self.control = _get_control_for_change_or_403(request, kwargs['control_pk'])
        return super().dispatch(request, *args, **kwargs)

    def form_valid(self, form):
        form.instance.control = self.control
        return super().form_valid(form)

    def get_success_url(self):
        return reverse_lazy('controls:detail', kwargs={'pk': self.control.pk})

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['control'] = self.control
        return ctx


class ControlFrameworkMatrixView(DepartmentScopedMixin, TemplateView):
    template_name = 'controls/framework_matrix.html'
    department_field = 'owner_dept'

    def get_context_data(self, **kwargs):
        from frameworks.models import Framework, FrameworkControl

        ctx = super().get_context_data(**kwargs)

        controls = scope_queryset(
            Control.objects.all().prefetch_related(
                'framework_controls', 'framework_mappings__framework_control__framework'
            ),
            self.request.user,
        ).order_by('code')

        frameworks = list(Framework.objects.all().order_by('name'))
        framework_rows = [{'framework': fw, 'cov': get_framework_coverage(fw)} for fw in frameworks]

        matrix_rows = []
        for c in controls:
            all_fc_ids = (
                set(c.framework_controls.values_list('pk', flat=True))
                | set(c.framework_mappings.values_list('framework_control__pk', flat=True))
            )
            row_cells = []
            for fw in frameworks:
                matching = list(FrameworkControl.objects.filter(pk__in=all_fc_ids, framework=fw))
                row_cells.append({
                    'framework': fw,
                    'covered': len(matching) > 0,
                    'count': len(matching),
                    'details': matching[:3],
                })
            matrix_rows.append({'control': c, 'cells': row_cells})

        ctx['matrix_rows'] = matrix_rows
        ctx['frameworks'] = frameworks
        ctx['framework_rows'] = framework_rows
        ctx['total_controls'] = controls.count()
        return ctx


class ControlLifecycleView(DepartmentScopedMixin, TemplateView):
    template_name = 'controls/lifecycle_board.html'
    department_field = 'owner_dept'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        controls = scope_queryset(
            Control.objects.all().select_related('owner_dept', 'owner_user'), self.request.user
        )

        stages = []
        for code, label in Control.LIFECYCLE_CHOICES:
            stage_controls = list(controls.filter(lifecycle_status=code).order_by('code'))
            stages.append({
                'code': code,
                'label': label,
                'controls': stage_controls,
                'count': len(stage_controls),
                'is_terminal': code == 'retired',
            })

        all_controls = list(controls)
        ctx['stages'] = stages
        ctx['total_controls'] = len(all_controls)
        ctx['operational_count'] = sum(
            1 for c in all_controls if c.lifecycle_status in ['operational', 'monitored', 'reviewed']
        )
        ctx['early_count'] = sum(
            1 for c in all_controls if c.lifecycle_status in ['proposed', 'designed', 'implemented']
        )
        ctx['retired_count'] = sum(1 for c in all_controls if c.lifecycle_status == 'retired')
        return ctx


@login_required
@require_POST
def advance_lifecycle_view(request, pk):
    control = _get_control_for_change_or_403(request, pk)
    stages = [s[0] for s in Control.LIFECYCLE_CHOICES]
    idx = stages.index(control.lifecycle_status) if control.lifecycle_status in stages else 0
    if idx < len(stages) - 1:
        control.lifecycle_status = stages[idx + 1]
        control.updated_by = request.user
        control.save()
        messages.success(request, f'{control.code} advanced to "{control.get_lifecycle_status_display()}".')
    else:
        messages.info(request, f'{control.code} is already at the final stage.')
    return redirect(request.META.get('HTTP_REFERER') or 'controls:list')


@login_required
@require_POST
def regress_lifecycle_view(request, pk):
    control = _get_control_for_change_or_403(request, pk)
    stages = [s[0] for s in Control.LIFECYCLE_CHOICES]
    idx = stages.index(control.lifecycle_status) if control.lifecycle_status in stages else 0
    if idx > 0:
        control.lifecycle_status = stages[idx - 1]
        control.updated_by = request.user
        control.save()
        messages.warning(request, f'{control.code} moved back to "{control.get_lifecycle_status_display()}".')
    else:
        messages.info(request, f'{control.code} is already at the first stage.')
    return redirect(request.META.get('HTTP_REFERER') or 'controls:list')


@login_required
@require_POST
def set_lifecycle_view(request, pk):
    control = _get_control_for_change_or_403(request, pk)
    target = request.POST.get('target')
    valid = [s[0] for s in Control.LIFECYCLE_CHOICES]
    if target in valid:
        control.lifecycle_status = target
        control.updated_by = request.user
        control.save()
        messages.success(request, f'{control.code} set to "{control.get_lifecycle_status_display()}".')
    return redirect(request.META.get('HTTP_REFERER') or 'controls:list')


class ControlEffectivenessView(DepartmentScopedMixin, TemplateView):
    template_name = 'controls/effectiveness.html'
    department_field = 'owner_dept'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        qs = scope_queryset(Control.objects.all().select_related('owner_dept'), self.request.user)

        buckets = []
        for code, label in Control.EFFECTIVENESS_RATING_CHOICES:
            items = list(qs.filter(effectiveness_rating=code).order_by('code'))
            buckets.append({'code': code, 'label': label, 'count': len(items), 'controls': items})

        all_controls = list(qs)
        total = len(all_controls)
        effective = sum(1 for c in all_controls if c.effectiveness_rating == 'effective')
        partial = sum(1 for c in all_controls if c.effectiveness_rating == 'partially_effective')
        ineffective = sum(1 for c in all_controls if c.effectiveness_rating == 'ineffective')
        not_tested = sum(1 for c in all_controls if c.effectiveness_rating == 'not_tested')

        categories = []
        for code, label in Control.CATEGORY_CHOICES:
            cat_controls = [c for c in all_controls if c.category == code]
            if not cat_controls:
                continue
            cat_effective = sum(1 for c in cat_controls if c.effectiveness_rating == 'effective')
            cat_total = len(cat_controls)
            categories.append({
                'code': code, 'label': label,
                'total': cat_total, 'effective': cat_effective,
                'percent': round(cat_effective / cat_total * 100) if cat_total else 0,
            })

        lifecycles = []
        for code, label in Control.LIFECYCLE_CHOICES:
            lc_controls = [c for c in all_controls if c.lifecycle_status == code]
            if not lc_controls:
                continue
            lc_effective = sum(1 for c in lc_controls if c.effectiveness_rating == 'effective')
            lifecycles.append({
                'code': code, 'label': label,
                'total': len(lc_controls), 'effective': lc_effective,
            })

        ctx.update({
            'buckets': buckets,
            'total': total,
            'effective_count': effective,
            'partial_count': partial,
            'ineffective_count': ineffective,
            'not_tested_count': not_tested,
            'effective_percent': round(effective / total * 100) if total else 0,
            'categories': categories,
            'lifecycles': lifecycles,
        })
        return ctx


def _framework_context(self, ctx):
    """Pass frameworks + selected FC pks to the template."""
    from frameworks.models import Framework

    ctx['all_frameworks'] = Framework.objects.prefetch_related('controls').order_by('name')

    selected = set()
    if getattr(self, 'object', None):
        selected = set(str(pk) for pk in self.object.framework_controls.values_list('pk', flat=True))
    elif self.request.method == 'POST':
        selected = set(str(pk) for pk in self.request.POST.getlist('framework_controls'))
    ctx['selected_fc_pks'] = selected
    return ctx
