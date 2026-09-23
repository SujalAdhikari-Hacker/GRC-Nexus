from django.db.models import Q
from django.views.generic import ListView, DetailView, CreateView, UpdateView
from django.urls import reverse_lazy

from core.mixins import DepartmentScopedMixin
from core.correlation import get_full_risk_context
from .models import Risk, RiskCategory
from .services import recalculate_risk


class RiskListView(DepartmentScopedMixin, ListView):
    model = Risk
    template_name = 'risks/risk_list.html'
    context_object_name = 'risks'
    paginate_by = 20

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
    template_name = 'risks/risk_form.html'
    fields = [
        'title', 'description', 'category', 'owner_dept', 'owner_user',
        'likelihood', 'impact', 'treatment_strategy', 'status',
        'assets', 'controls', 'identified_date', 'target_close_date',
    ]
    success_url = reverse_lazy('risks:list')

    def get_form(self, form_class=None):
        form = super().get_form(form_class)
        user = self.request.user
        if not user.is_superuser and user.department_id:
            form.fields['owner_dept'].initial = user.department
            form.fields['owner_dept'].widget.attrs['disabled'] = 'disabled'
        return form

    def form_valid(self, form):
        response = super().form_valid(form)
        recalculate_risk(self.object)
        return response


class RiskUpdateView(DepartmentScopedMixin, UpdateView):
    model = Risk
    template_name = 'risks/risk_form.html'
    fields = [
        'title', 'description', 'category', 'owner_dept', 'owner_user',
        'likelihood', 'impact', 'treatment_strategy', 'status',
        'assets', 'controls', 'identified_date', 'target_close_date',
    ]
    success_url = reverse_lazy('risks:list')

    def form_valid(self, form):
        response = super().form_valid(form)
        recalculate_risk(self.object)
        return response

    from django.http import HttpResponse
from django.shortcuts import render


def risk_score_preview(request):
    """
    HTMX endpoint — returns an HTML fragment showing the live score
    preview as the user changes likelihood/impact/controls.
    """
    try:
        likelihood = int(request.GET.get('likelihood', 1))
        impact = int(request.GET.get('impact', 1))
    except ValueError:
        likelihood, impact = 1, 1

    likelihood = max(1, min(5, likelihood))
    impact = max(1, min(5, impact))

    inherent = likelihood * impact

    # Simple residual preview if control IDs are provided
    control_ids = request.GET.getlist('controls')
    residual = inherent
    if control_ids:
        from controls.models import Control
        controls = Control.objects.filter(pk__in=control_ids, status='implemented')
        if controls.exists():
            avg_eff = sum(c.effectiveness for c in controls) / (controls.count() * 5.0)
            residual = round(inherent * (1 - avg_eff))
            residual = max(0, min(25, residual))

    # Severity band
    if inherent >= 20:
        band, color = 'Critical', '#dc3545'
    elif inherent >= 12:
        band, color = 'High', '#fd7e14'
    elif inherent >= 6:
        band, color = 'Medium', '#ffc107'
    else:
        band, color = 'Low', '#198754'

    return render(request, 'risks/_score_preview.html', {
        'likelihood': likelihood,
        'impact': impact,
        'inherent': inherent,
        'residual': residual,
        'band': band,
        'color': color,
    })