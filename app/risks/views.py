from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import Q
from django.http import HttpResponse
from django.shortcuts import render
from django.urls import reverse_lazy
from django.utils import timezone
from django.views.generic import ListView, DetailView, CreateView, UpdateView, TemplateView
from core.reports import ReportMixin
from core.mixins import DepartmentScopedMixin, HODOrSuperuserMixin, CsvExportMixin
from core.correlation import get_full_risk_context
from .models import Risk, RiskCategory, RiskAppetite, RiskTreatment
from .services import recalculate_risk
from .forms import (
    RiskForm, RiskTreatmentForm, RiskTreatmentUpdateForm,
    RiskExceptionForm, RiskAppetiteForm,
)
from django.shortcuts import get_object_or_404, redirect
from django.contrib import messages
from django.views.decorators.http import require_POST
from .forms import RiskForm, RiskTreatmentForm, RiskTreatmentUpdateForm, RiskExceptionForm, RiskAppetiteForm
from .models import RiskException
from .forms import RiskExceptionForm

class RiskListView(ReportMixin, DepartmentScopedMixin, CsvExportMixin, ListView):
    model = Risk
    template_name = 'risks/risk_list.html'
    context_object_name = 'risks'
    paginate_by = 20

    report_title = 'Risk Register'
    report_filename_base = 'risk_register'
    pdf_template = 'reports/risk_register_pdf.html'

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
        likelihood = self.request.GET.get('likelihood')
        if likelihood:
            qs = qs.filter(likelihood=likelihood)
        impact = self.request.GET.get('impact')
        if impact:
            qs = qs.filter(impact=impact)
        assessed = self.request.GET.get('assessed')
        if assessed == '1':
            qs = qs.exclude(status='identified')
        elif assessed == '0':
            qs = qs.filter(status='identified')
        return qs.order_by('-residual_score')

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['categories'] = RiskCategory.objects.all()
        ctx['statuses'] = Risk.STATUS_CHOICES
        ctx['search_query'] = self.request.GET.get('q', '')
        ctx['selected_category'] = self.request.GET.get('category', '')
        ctx['selected_status'] = self.request.GET.get('status', '')
        ctx['breach_filter'] = self.request.GET.get('breach', '')
        ctx['filter_likelihood'] = self.request.GET.get('likelihood', '')
        ctx['filter_impact'] = self.request.GET.get('impact', '')
        ctx['filter_assessed'] = self.request.GET.get('assessed', '')
        return ctx

    def build_rows(self):
        headers = ['ID', 'Title', 'Category', 'Dept', 'L', 'I', 'Inherent', 'Residual',
                   'Breach', 'Treatment', 'Status', 'Owner', 'Identified']
        rows = []
        for r in self.get_queryset():
            rows.append([
                r.pk,
                r.title,
                r.category.name if r.category else '',
                r.owner_dept.name if r.owner_dept else '',
                r.likelihood,
                r.impact,
                r.inherent_score,
                r.residual_score,
                'Yes' if r.appetite_breached else 'No',
                r.get_treatment_strategy_display(),
                r.get_status_display(),
                r.owner_user.username if r.owner_user else '',
                r.identified_date.strftime('%Y-%m-%d') if r.identified_date else '',
            ])
        return headers, rows

    def build_pdf_context(self):
        qs = list(self.get_queryset())
        return {
            'risks': qs,
            'total': len(qs),
            'breached_count': sum(1 for r in qs if r.appetite_breached),
        }

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

    def get_initial(self):
        initial = super().get_initial()
        user = self.request.user
        if not user.is_superuser and user.department_id:
            initial['owner_dept'] = user.department
        likelihood = self.request.GET.get('likelihood')
        if likelihood and likelihood.isdigit() and 1 <= int(likelihood) <= 5:
            initial['likelihood'] = int(likelihood)
        impact = self.request.GET.get('impact')
        if impact and impact.isdigit() and 1 <= int(impact) <= 5:
            initial['impact'] = int(impact)
        if likelihood and impact:
            initial['title'] = f'New risk (L{likelihood} x I{impact})'
        return initial

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['prefilled_likelihood'] = self.request.GET.get('likelihood', '')
        ctx['prefilled_impact'] = self.request.GET.get('impact', '')
        return ctx

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


class RiskMatrixView(LoginRequiredMixin, TemplateView):
    template_name = 'risks/risk_matrix.html'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        user = self.request.user
        show_only_assessed = self.request.GET.get('assessed') == '1'

        all_risks = Risk.objects.all()
        if not user.is_superuser and user.department_id:
            all_risks = all_risks.filter(owner_dept=user.department)

        assessed_risks = all_risks.exclude(status='identified')
        unassessed_risks = all_risks.filter(status='identified')

        source = assessed_risks if show_only_assessed else all_risks

        def severity_band(score):
            if score >= 20:
                return 'critical'
            if score >= 12:
                return 'high'
            if score >= 6:
                return 'medium'
            return 'low'

        inherent_grid = []
        for impact in range(5, 0, -1):
            row = []
            for likelihood in range(1, 6):
                score = likelihood * impact
                cell_risks = [r for r in source if r.likelihood == likelihood and r.impact == impact]
                row.append({
                    'likelihood': likelihood,
                    'impact': impact,
                    'score': score,
                    'band': severity_band(score),
                    'count': len(cell_risks),
                    'unassessed_count': sum(1 for r in cell_risks if r.status == 'identified'),
                    'breached_count': sum(1 for r in cell_risks if r.appetite_breached),
                })
            inherent_grid.append(row)

        residual_grid = []
        for impact in range(5, 0, -1):
            row = []
            for likelihood in range(1, 6):
                cell_risks = [r for r in source if r.likelihood == likelihood and r.impact == impact]
                if cell_risks:
                    max_residual = max(r.residual_score for r in cell_risks)
                    cell_band = severity_band(max_residual)
                    avg_residual = round(sum(r.residual_score for r in cell_risks) / len(cell_risks), 1)
                else:
                    cell_band = severity_band(likelihood * impact)
                    avg_residual = 0
                row.append({
                    'likelihood': likelihood,
                    'impact': impact,
                    'score': likelihood * impact,
                    'band': cell_band,
                    'count': len(cell_risks),
                    'avg_residual': avg_residual,
                    'max_residual': max((r.residual_score for r in cell_risks), default=0),
                })
            residual_grid.append(row)

        total = all_risks.count()
        assessed = assessed_risks.count()
        unassessed = unassessed_risks.count()
        pct_assessed = round((assessed / total * 100)) if total else 0
        top_unassessed = unassessed_risks.order_by('-created_at')[:5]

        ctx.update({
            'inherent_grid': inherent_grid,
            'residual_grid': residual_grid,
            'total_risks': total,
            'assessed_count': assessed,
            'unassessed_count': unassessed,
            'pct_assessed': pct_assessed,
            'breached_count': all_risks.filter(appetite_breached=True).count(),
            'top_unassessed': top_unassessed,
            'show_only_assessed': show_only_assessed,
            'has_any_risks': total > 0,
            'has_assessed_risks': assessed > 0,
        })
        return ctx


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
        recalculate_risk(self.object.risk)
        return response

    def get_success_url(self):
        return reverse_lazy('risks:detail', kwargs={'pk': self.object.risk.pk})

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['risk'] = self.object.risk
        return ctx


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
    form_class = RiskAppetiteForm
    template_name = 'risks/appetite_form.html'
    success_url = reverse_lazy('risks:appetite_list')

    def get_initial(self):
        initial = super().get_initial()
        user = self.request.user
        if not user.is_superuser and user.department_id:
            initial['department'] = user.department
        return initial

    def form_valid(self, form):
        if form.cleaned_data.get('board_approved') and not form.instance.approved_by_id:
            form.instance.approved_by = self.request.user
        return super().form_valid(form)


class RiskAppetiteUpdateView(HODOrSuperuserMixin, UpdateView):
    model = RiskAppetite
    form_class = RiskAppetiteForm
    template_name = 'risks/appetite_form.html'
    success_url = reverse_lazy('risks:appetite_list')

class RiskExceptionListView(DepartmentScopedMixin, ListView):
    model = RiskException
    template_name = 'risks/exception_list.html'
    context_object_name = 'exceptions'
    paginate_by = 25
    department_field = 'risk__owner_dept'

    def get_queryset(self):
        qs = super().get_queryset().select_related('risk', 'approver', 'requested_by')
        q = self.request.GET.get('q', '').strip()
        if q:
            qs = qs.filter(Q(title__icontains=q) | Q(justification__icontains=q))
        status = self.request.GET.get('status')
        if status:
            qs = qs.filter(status=status)
        return qs.order_by('-created_at')

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['statuses'] = RiskException.STATUS_CHOICES
        ctx['search_query'] = self.request.GET.get('q', '')
        ctx['selected_status'] = self.request.GET.get('status', '')

        base = super().get_queryset()
        user = self.request.user
        if not user.is_superuser and user.department_id:
            base = base.filter(risk__owner_dept=user.department)

        # Compute expired/expiring counts (Python-side, since they depend on today)
        all_exc = list(base)
        ctx['total_count'] = len(all_exc)
        ctx['pending_count'] = sum(1 for e in all_exc if e.status == 'pending')
        ctx['active_count'] = sum(1 for e in all_exc if e.status == 'active')
        ctx['expired_count'] = sum(1 for e in all_exc if e.status == 'expired' or e.is_expired)
        ctx['expiring_soon_count'] = sum(1 for e in all_exc if e.status == 'active' and e.is_expiring_soon)
        return ctx


class RiskExceptionDetailView(DepartmentScopedMixin, DetailView):
    model = RiskException
    template_name = 'risks/exception_detail.html'
    context_object_name = 'exception'
    department_field = 'risk__owner_dept'


class RiskExceptionCreateView(LoginRequiredMixin, CreateView):
    model = RiskException
    form_class = RiskExceptionForm
    template_name = 'risks/exception_form.html'

    def get_initial(self):
        initial = super().get_initial()
        initial['requested_by'] = self.request.user
        risk_pk = self.request.GET.get('risk')
        if risk_pk:
            try:
                initial['risk'] = Risk.objects.get(pk=risk_pk)
            except Risk.DoesNotExist:
                pass
        return initial

    def form_valid(self, form):
        if not form.instance.requested_by_id:
            form.instance.requested_by = self.request.user
        return super().form_valid(form)

    def get_success_url(self):
        return reverse_lazy('risks:exception_detail', kwargs={'pk': self.object.pk})


class RiskExceptionUpdateView(LoginRequiredMixin, UpdateView):
    model = RiskException
    form_class = RiskExceptionForm
    template_name = 'risks/exception_form.html'

    def get_success_url(self):
        return reverse_lazy('risks:exception_detail', kwargs={'pk': self.object.pk})


@require_POST
def exception_approve(request, pk):
    exc = get_object_or_404(RiskException, pk=pk)
    exc.status = 'active'
    exc.approver = request.user
    exc.approval_date = timezone.now().date()
    exc.save()
    messages.success(request, f'{exc.exception_id} approved and now active.')
    return redirect('risks:exception_detail', pk=pk)


@require_POST
def exception_revoke(request, pk):
    exc = get_object_or_404(RiskException, pk=pk)
    exc.status = 'revoked'
    exc.save()
    messages.warning(request, f'{exc.exception_id} revoked.')
    return redirect('risks:exception_detail', pk=pk)
# ============================================================
# RISK EXCEPTIONS
# ============================================================

from django.contrib.auth.mixins import LoginRequiredMixin
from django.shortcuts import get_object_or_404, redirect
from django.contrib import messages
from django.views.decorators.http import require_POST

from .models import RiskException
from .forms import RiskExceptionForm


class RiskExceptionListView(DepartmentScopedMixin, ListView):
    model = RiskException
    template_name = 'risks/exception_list.html'
    context_object_name = 'exceptions'
    paginate_by = 25
    department_field = 'risk__owner_dept'

    def get_queryset(self):
        qs = super().get_queryset().select_related('risk', 'approver', 'requested_by')
        q = self.request.GET.get('q', '').strip()
        if q:
            qs = qs.filter(Q(title__icontains=q) | Q(justification__icontains=q))
        status = self.request.GET.get('status')
        if status:
            qs = qs.filter(status=status)
        return qs.order_by('-created_at')

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['statuses'] = RiskException.STATUS_CHOICES
        ctx['search_query'] = self.request.GET.get('q', '')
        ctx['selected_status'] = self.request.GET.get('status', '')

        base = super().get_queryset()
        user = self.request.user
        if not user.is_superuser and user.department_id:
            base = base.filter(risk__owner_dept=user.department)

        all_exc = list(base)
        ctx['total_count'] = len(all_exc)
        ctx['pending_count'] = sum(1 for e in all_exc if e.status == 'pending')
        ctx['active_count'] = sum(1 for e in all_exc if e.status == 'active')
        ctx['expired_count'] = sum(1 for e in all_exc if e.status == 'expired' or e.is_expired)
        ctx['expiring_soon_count'] = sum(1 for e in all_exc if e.status == 'active' and e.is_expiring_soon)
        return ctx


class RiskExceptionDetailView(DepartmentScopedMixin, DetailView):
    model = RiskException
    template_name = 'risks/exception_detail.html'
    context_object_name = 'exception'
    department_field = 'risk__owner_dept'


class RiskExceptionCreateView(LoginRequiredMixin, CreateView):
    model = RiskException
    form_class = RiskExceptionForm
    template_name = 'risks/exception_form.html'

    def get_initial(self):
        initial = super().get_initial()
        initial['requested_by'] = self.request.user
        risk_pk = self.request.GET.get('risk')
        if risk_pk:
            try:
                initial['risk'] = Risk.objects.get(pk=risk_pk)
            except Risk.DoesNotExist:
                pass
        return initial

    def form_valid(self, form):
        if not form.instance.requested_by_id:
            form.instance.requested_by = self.request.user
        return super().form_valid(form)

    def get_success_url(self):
        return reverse_lazy('risks:exception_detail', kwargs={'pk': self.object.pk})


class RiskExceptionUpdateView(LoginRequiredMixin, UpdateView):
    model = RiskException
    form_class = RiskExceptionForm
    template_name = 'risks/exception_form.html'

    def get_success_url(self):
        return reverse_lazy('risks:exception_detail', kwargs={'pk': self.object.pk})


@require_POST
def exception_approve(request, pk):
    exc = get_object_or_404(RiskException, pk=pk)
    exc.status = 'active'
    exc.approver = request.user
    exc.approval_date = timezone.now().date()
    exc.save()
    messages.success(request, f'{exc.exception_id} approved and now active.')
    return redirect('risks:exception_detail', pk=pk)


@require_POST
def exception_revoke(request, pk):
    exc = get_object_or_404(RiskException, pk=pk)
    exc.status = 'revoked'
    exc.save()
    messages.warning(request, f'{exc.exception_id} revoked.')
    return redirect('risks:exception_detail', pk=pk)

# ============================================================
# RISK EXCEPTIONS
# ============================================================

from django.contrib.auth.mixins import LoginRequiredMixin as _LRM2
from django.shortcuts import get_object_or_404, redirect
from django.contrib import messages
from django.views.decorators.http import require_POST
from django.utils import timezone
from .models import RiskException
from .forms import RiskExceptionForm


class RiskExceptionListView(DepartmentScopedMixin, ListView):
    model = RiskException
    template_name = 'risks/exception_list.html'
    context_object_name = 'exceptions'
    paginate_by = 25
    department_field = 'risk__owner_dept'

    def get_queryset(self):
        qs = super().get_queryset().select_related('risk', 'approver', 'requested_by')
        q = self.request.GET.get('q', '').strip()
        if q:
            qs = qs.filter(Q(title__icontains=q) | Q(justification__icontains=q))
        status = self.request.GET.get('status')
        if status:
            qs = qs.filter(status=status)
        return qs.order_by('-created_at')

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['statuses'] = RiskException.STATUS_CHOICES
        ctx['search_query'] = self.request.GET.get('q', '')
        ctx['selected_status'] = self.request.GET.get('status', '')

        base = super().get_queryset()
        user = self.request.user
        if not user.is_superuser and user.department_id:
            base = base.filter(risk__owner_dept=user.department)

        all_exc = list(base)
        ctx['total_count'] = len(all_exc)
        ctx['pending_count'] = sum(1 for e in all_exc if e.status == 'pending')
        ctx['active_count'] = sum(1 for e in all_exc if e.status == 'active')
        ctx['expired_count'] = sum(1 for e in all_exc if e.status == 'expired' or e.is_expired)
        ctx['expiring_soon_count'] = sum(1 for e in all_exc if e.status == 'active' and e.is_expiring_soon)
        return ctx


class RiskExceptionDetailView(DepartmentScopedMixin, DetailView):
    model = RiskException
    template_name = 'risks/exception_detail.html'
    context_object_name = 'exception'
    department_field = 'risk__owner_dept'


class RiskExceptionCreateView(_LRM2, CreateView):
    model = RiskException
    form_class = RiskExceptionForm
    template_name = 'risks/exception_form.html'

    def get_initial(self):
        initial = super().get_initial()
        initial['requested_by'] = self.request.user
        risk_pk = self.request.GET.get('risk')
        if risk_pk:
            try:
                initial['risk'] = Risk.objects.get(pk=risk_pk)
            except Risk.DoesNotExist:
                pass
        return initial

    def form_valid(self, form):
        if not form.instance.requested_by_id:
            form.instance.requested_by = self.request.user
        return super().form_valid(form)

    def get_success_url(self):
        return reverse_lazy('risks:exception_detail', kwargs={'pk': self.object.pk})


class RiskExceptionUpdateView(_LRM2, UpdateView):
    model = RiskException
    form_class = RiskExceptionForm
    template_name = 'risks/exception_form.html'

    def get_success_url(self):
        return reverse_lazy('risks:exception_detail', kwargs={'pk': self.object.pk})


@require_POST
def exception_approve(request, pk):
    exc = get_object_or_404(RiskException, pk=pk)
    exc.status = 'active'
    exc.approver = request.user
    exc.approval_date = timezone.now().date()
    exc.save()
    messages.success(request, f'{exc.exception_id} approved and now active.')
    return redirect('risks:exception_detail', pk=pk)


@require_POST
def exception_revoke(request, pk):
    exc = get_object_or_404(RiskException, pk=pk)
    exc.status = 'revoked'
    exc.save()
    messages.warning(request, f'{exc.exception_id} revoked.')
    return redirect('risks:exception_detail', pk=pk)

