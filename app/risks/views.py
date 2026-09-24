from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import Q
from django.http import HttpResponse
from django.shortcuts import render
from django.urls import reverse_lazy
from django.utils import timezone
from django.views.generic import ListView, DetailView, CreateView, UpdateView

from core.mixins import DepartmentScopedMixin, HODOrSuperuserMixin, CsvExportMixin
from core.correlation import get_full_risk_context
from .models import Risk, RiskCategory, RiskAppetite, RiskTreatment
from .services import recalculate_risk
from .forms import RiskForm, RiskTreatmentForm, RiskTreatmentUpdateForm


# ============================================================
# RISK LIST / DETAIL / CREATE / UPDATE
# ============================================================

class RiskListView(DepartmentScopedMixin, CsvExportMixin, ListView):
    model = Risk
    template_name = 'risks/risk_list.html'
    context_object_name = 'risks'
    paginate_by = 20

    csv_filename = 'risks.csv'
    csv_fields = [
        ('Title', 'title'),
        ('Category', lambda r: r.category.name),
        ('Department', lambda r: r.owner_dept.name),
        ('Owner', lambda r: r.owner_user.username if r.owner_user else ''),
        ('Likelihood', 'likelihood'),
        ('Impact', 'impact'),
        ('Inherent', 'inherent_score'),
        ('Residual', 'residual_score'),
        ('Appetite Breach', lambda r: 'Yes' if r.appetite_breached else 'No'),
        ('Treatment', 'get_treatment_strategy_display'),
        ('Status', 'get_status_display'),
        ('Identified', lambda r: r.identified_date or ''),
        ('Assets', lambda r: ', '.join(a.name for a in r.assets.all())),
        ('Controls', lambda r: ', '.join(c.code for c in r.controls.all())),
    ]

    def get_queryset(self):
        qs = super().get_queryset()
        q = self.request.GET.get('q', '').strip()
        if q:
            qs = qs.filter(Q(title__icontains=q) | Q(description__icontains=q))
        cat = self.request.GET.get('category')
        if cat:
            qs = qs.filter(category_id=cat)
        status = self.request.GET.get('status')
        if status:
            qs = qs.filter(status=status)
        breach = self.request.GET.get('breach')
        if breach == '1':
            qs = qs.filter(appetite_breached=True)
        return qs.order_by('-residual_score')

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['categories'] = RiskCategory.objects.all()
        ctx['statuses'] = Risk.STATUS_CHOICES
        ctx['search_query'] = self.request.GET.get('q', '')
        ctx['selected_category'] = self.request.GET.get('category', '')
        ctx['selected_status'] = self.request.GET.get('status', '')
        ctx['breach_filter'] = self.request.GET.get('breach', '')
        return ctx


class RiskDetailView(DepartmentScopedMixin, DetailView):
    model = Risk
    template_name = 'risks/risk_detail.html'
    context_object_name = 'risk'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx.update(get_full_risk_context(self.object))
        return ctx


class RiskCreateView(DepartmentScopedMixin, CreateView):
    model = Risk
    form_class = RiskForm
    template_name = 'risks/risk_form.html'
    success_url = reverse_lazy('risks:list')

    def form_valid(self, form):
        response = super().form_valid(form)
        recalculate_risk(self.object)
        return response


class RiskUpdateView(DepartmentScopedMixin, UpdateView):
    model = Risk
    form_class = RiskForm
    template_name = 'risks/risk_form.html'
    success_url = reverse_lazy('risks:list')

    def form_valid(self, form):
        response = super().form_valid(form)
        recalculate_risk(self.object)
        return response


# ============================================================
# HTMX SCORE PREVIEW
# ============================================================

def risk_score_preview(request):
    try:
        likelihood = int(request.GET.get('likelihood', 1))
        impact = int(request.GET.get('impact', 1))
    except ValueError:
        likelihood, impact = 1, 1
    likelihood = max(1, min(5, likelihood))
    impact = max(1, min(5, impact))
    inherent = likelihood * impact
    control_ids = request.GET.getlist('controls')
    residual = inherent
    if control_ids:
        from controls.models import Control
        controls = Control.objects.filter(pk__in=control_ids, status='implemented')
        if controls.exists():
            avg_eff = sum(c.effectiveness for c in controls) / (controls.count() * 5.0)
            residual = round(inherent * (1 - avg_eff))
            residual = max(0, min(25, residual))
    if inherent >= 20:
        band, color = 'Critical', '#dc3545'
    elif inherent >= 12:
        band, color = 'High', '#fd7e14'
    elif inherent >= 6:
        band, color = 'Medium', '#ffc107'
    else:
        band, color = 'Low', '#198754'
    return render(request, 'risks/_score_preview.html', {
        'likelihood': likelihood, 'impact': impact,
        'inherent': inherent, 'residual': residual,
        'band': band, 'color': color,
    })


# ============================================================
# TREATMENTS
# ============================================================

class TreatmentListView(DepartmentScopedMixin, ListView):
    model = RiskTreatment
    template_name = 'risks/treatment_list.html'
    context_object_name = 'treatments'
    paginate_by = 25
    department_field = 'risk__owner_dept'

    def get_queryset(self):
        qs = super().get_queryset().select_related('risk', 'owner_user').prefetch_related('controls')
        q = self.request.GET.get('q', '').strip()
        if q:
            qs = qs.filter(Q(action_plan__icontains=q) | Q(risk__title__icontains=q))
        status = self.request.GET.get('status')
        if status:
            qs = qs.filter(status=status)
        strategy = self.request.GET.get('strategy')
        if strategy:
            qs = qs.filter(strategy=strategy)
        return qs.order_by('due_date')

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['statuses'] = RiskTreatment.STATUS_CHOICES
        ctx['strategies'] = RiskTreatment.STRATEGY_CHOICES
        ctx['search_query'] = self.request.GET.get('q', '')
        ctx['selected_status'] = self.request.GET.get('status', '')
        ctx['selected_strategy'] = self.request.GET.get('strategy', '')

        base = super().get_queryset()
        user = self.request.user
        if not user.is_superuser and user.department_id:
            base = base.filter(risk__owner_dept=user.department)
        ctx['total_count'] = base.count()
        ctx['planned_count'] = base.filter(status='planned').count()
        ctx['in_progress_count'] = base.filter(status='in_progress').count()
        ctx['completed_count'] = base.filter(status='completed').count()
        return ctx


class RiskTreatmentCreateView(LoginRequiredMixin, CreateView):
    model = RiskTreatment
    form_class = RiskTreatmentForm
    template_name = 'risks/treatment_form.html'

    def dispatch(self, request, *args, **kwargs):
        self.risk = Risk.objects.get(pk=kwargs['risk_pk'])
        return super().dispatch(request, *args, **kwargs)

    def form_valid(self, form):
        form.instance.risk = self.risk
        response = super().form_valid(form)
        from .services import recalculate_risk
        recalculate_risk(self.risk)
        return response

    def get_success_url(self):
        return reverse_lazy('risks:detail', kwargs={'pk': self.risk.pk})

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['risk'] = self.risk
        return ctx


class RiskTreatmentUpdateView(LoginRequiredMixin, UpdateView):
    model = RiskTreatment
    form_class = RiskTreatmentUpdateForm
    template_name = 'risks/treatment_form.html'

    def form_valid(self, form):
        response = super().form_valid(form)
        from .services import recalculate_risk
        recalculate_risk(self.object.risk)
        return response

    def get_success_url(self):
        return reverse_lazy('risks:detail', kwargs={'pk': self.object.risk.pk})

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['risk'] = self.object.risk
        return ctx


# ============================================================
# RISK APPETITE
# ============================================================

class RiskAppetiteListView(HODOrSuperuserMixin, ListView):
    model = RiskAppetite
    template_name = 'risks/appetite_list.html'
    context_object_name = 'appetites'

    def get_queryset(self):
        qs = super().get_queryset()
        user = self.request.user
        if user.is_superuser:
            return qs
        return qs.filter(department=user.department)


class RiskAppetiteCreateView(HODOrSuperuserMixin, CreateView):
    model = RiskAppetite
    template_name = 'risks/appetite_form.html'
    fields = [
        'department', 'category', 'appetite_level', 'appetite_statement',
        'max_inherent_score', 'max_residual_score', 'risk_capacity',
        'board_approved', 'approved_by', 'review_date', 'description',
    ]
    success_url = reverse_lazy('risks:appetite_list')

    def get_initial(self):
        initial = super().get_initial()
        user = self.request.user
        if not user.is_superuser and user.department_id:
            initial['department'] = user.department
        return initial


class RiskAppetiteUpdateView(HODOrSuperuserMixin, UpdateView):
    model = RiskAppetite
    template_name = 'risks/appetite_form.html'
    fields = [
        'department', 'category', 'appetite_level', 'appetite_statement',
        'max_inherent_score', 'max_residual_score', 'risk_capacity',
        'board_approved', 'approved_by', 'review_date', 'description',
    ]
    success_url = reverse_lazy('risks:appetite_list')
