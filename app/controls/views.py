from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib import messages
from django.db.models import Q
from django.shortcuts import redirect, get_object_or_404
from django.urls import reverse_lazy
from django.views.decorators.http import require_POST
from django.views.generic import ListView, DetailView, CreateView, UpdateView, TemplateView

from core.mixins import DepartmentScopedMixin, CsvExportMixin
from core.correlation import get_full_control_context, get_framework_coverage
from .models import Control, ControlEvidence, ControlFrameworkMapping
from .forms import ControlForm, ControlEvidenceForm, ControlFrameworkMappingForm


class ControlListView(DepartmentScopedMixin, CsvExportMixin, ListView):
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
        ctx['statuses'] = Control.STATUS_CHOICES
        ctx['categories_choices'] = Control.CATEGORY_CHOICES
        ctx['lifecycle_choices'] = Control.LIFECYCLE_CHOICES
        ctx['effectiveness_choices'] = Control.EFFECTIVENESS_RATING_CHOICES
        ctx['search_query'] = self.request.GET.get('q', '')
        ctx['selected_status'] = self.request.GET.get('status', '')
        ctx['selected_category'] = self.request.GET.get('category', '')
        ctx['selected_lifecycle'] = self.request.GET.get('lifecycle', '')
        ctx['selected_effectiveness'] = self.request.GET.get('effectiveness', '')

        base = super().get_queryset()
        user = self.request.user
        if not user.is_superuser and user.department_id:
            base = base.filter(owner_dept=user.department)
        all_controls = list(base)
        ctx['total_count'] = len(all_controls)
        ctx['effective_count'] = sum(1 for c in all_controls if c.effectiveness_rating == 'effective')
        ctx['not_tested_count'] = sum(1 for c in all_controls if c.effectiveness_rating == 'not_tested')
        ctx['operational_count'] = sum(1 for c in all_controls if c.lifecycle_status in ['operational', 'monitored', 'reviewed'])
        return ctx


class ControlDetailView(DepartmentScopedMixin, DetailView):
    model = Control
    template_name = 'controls/control_detail.html'
    context_object_name = 'control'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx.update(get_full_control_context(self.object))
        ctx['framework_mappings'] = self.object.framework_mappings.select_related('framework_control__framework')
        ctx['audit_tests'] = self.object.audit_tests.select_related('tester', 'audit').order_by('-test_date')[:10]  # ← ADD THIS
        return ctx


class ControlCreateView(DepartmentScopedMixin, CreateView):
    model = Control
    form_class = ControlForm
    template_name = 'controls/control_form.html'
    success_url = reverse_lazy('controls:list')

    def get_initial(self):
        initial = super().get_initial()
        user = self.request.user
        if not user.is_superuser and user.department_id:
            initial['owner_dept'] = user.department
        return initial

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        return _framework_context(self, ctx)


class ControlUpdateView(DepartmentScopedMixin, UpdateView):
    model = Control
    form_class = ControlForm
    template_name = 'controls/control_form.html'
    success_url = reverse_lazy('controls:list')

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        return _framework_context(self, ctx)


class ControlEvidenceCreateView(LoginRequiredMixin, CreateView):
    model = ControlEvidence
    form_class = ControlEvidenceForm
    template_name = 'controls/evidence_form.html'

    def dispatch(self, request, *args, **kwargs):
        self.control = Control.objects.get(pk=kwargs['control_pk'])
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
        self.control = Control.objects.get(pk=kwargs['control_pk'])
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
        user = self.request.user

        controls = Control.objects.all().prefetch_related(
            'framework_controls', 'framework_mappings__framework_control__framework'
        )
        if not user.is_superuser and user.department_id:
            controls = controls.filter(owner_dept=user.department)
        controls = controls.order_by('code')

        frameworks = list(Framework.objects.all().order_by('name'))

        # Build a list of {framework, cov} tuples for the template
        framework_rows = []
        for fw in frameworks:
            framework_rows.append({
                'framework': fw,
                'cov': get_framework_coverage(fw),
            })

        # Matrix cells
        matrix_rows = []
        for c in controls:
            direct_fc_ids = set(c.framework_controls.values_list('pk', flat=True))
            mapped_fc_ids = set(
                c.framework_mappings.values_list('framework_control__pk', flat=True)
            )
            all_fc_ids = direct_fc_ids | mapped_fc_ids

            row_cells = []
            for fw in frameworks:
                matching = list(FrameworkControl.objects.filter(pk__in=all_fc_ids, framework=fw))
                row_cells.append({
                    'framework': fw,
                    'covered': len(matching) > 0,
                    'count': len(matching),
                    'details': matching[:3],
                })

            matrix_rows.append({
                'control': c,
                'cells': row_cells,
            })

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
        user = self.request.user

        controls = Control.objects.all().select_related('owner_dept', 'owner_user')
        if not user.is_superuser and user.department_id:
            controls = controls.filter(owner_dept=user.department)

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

        ctx['stages'] = stages
        ctx['total_controls'] = controls.count()

        all_controls = list(controls)
        ctx['operational_count'] = sum(
            1 for c in all_controls if c.lifecycle_status in ['operational', 'monitored', 'reviewed']
        )
        ctx['early_count'] = sum(
            1 for c in all_controls if c.lifecycle_status in ['proposed', 'designed', 'implemented']
        )
        ctx['retired_count'] = sum(1 for c in all_controls if c.lifecycle_status == 'retired')
        return ctx


@require_POST
def advance_lifecycle_view(request, pk):
    control = get_object_or_404(Control, pk=pk)
    stages = [s[0] for s in Control.LIFECYCLE_CHOICES]
    try:
        idx = stages.index(control.lifecycle_status)
    except ValueError:
        idx = 0
    if idx < len(stages) - 1:
        control.lifecycle_status = stages[idx + 1]
        control.save()
        messages.success(request, f'{control.code} advanced to "{control.get_lifecycle_status_display()}".')
    else:
        messages.info(request, f'{control.code} is already at the final stage.')
    return redirect(request.META.get('HTTP_REFERER') or 'controls:list')


@require_POST
def regress_lifecycle_view(request, pk):
    control = get_object_or_404(Control, pk=pk)
    stages = [s[0] for s in Control.LIFECYCLE_CHOICES]
    try:
        idx = stages.index(control.lifecycle_status)
    except ValueError:
        idx = 0
    if idx > 0:
        control.lifecycle_status = stages[idx - 1]
        control.save()
        messages.warning(request, f'{control.code} moved back to "{control.get_lifecycle_status_display()}".')
    else:
        messages.info(request, f'{control.code} is already at the first stage.')
    return redirect(request.META.get('HTTP_REFERER') or 'controls:list')


@require_POST
def set_lifecycle_view(request, pk):
    control = get_object_or_404(Control, pk=pk)
    target = request.POST.get('target')
    valid = [s[0] for s in Control.LIFECYCLE_CHOICES]
    if target in valid:
        control.lifecycle_status = target
        control.save()
        messages.success(request, f'{control.code} set to "{control.get_lifecycle_status_display()}".')
    return redirect(request.META.get('HTTP_REFERER') or 'controls:list')

class ControlEffectivenessView(DepartmentScopedMixin, TemplateView):
    template_name = 'controls/effectiveness.html'
    department_field = 'owner_dept'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        user = self.request.user

        qs = Control.objects.all().select_related('owner_dept')
        if not user.is_superuser and user.department_id:
            qs = qs.filter(owner_dept=user.department)

        buckets = []
        for code, label in Control.EFFECTIVENESS_RATING_CHOICES:
            items = list(qs.filter(effectiveness_rating=code).order_by('code'))
            buckets.append({
                'code': code, 'label': label,
                'count': len(items), 'controls': items,
            })

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
