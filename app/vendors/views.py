from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import Q
from django.urls import reverse_lazy
from django.utils import timezone
from django.views.generic import ListView, DetailView, CreateView, UpdateView

from core.mixins import DepartmentScopedMixin, CsvExportMixin
from core.correlation import get_full_vendor_context
from .models import Vendor, VendorAssessment
from .forms import VendorForm, VendorAssessmentForm


class VendorListView(DepartmentScopedMixin, CsvExportMixin, ListView):
    model = Vendor
    template_name = 'vendors/vendor_list.html'
    context_object_name = 'vendors'
    paginate_by = 20

    csv_filename = 'vendors.csv'
    csv_fields = [
        ('Name', 'name'),
        ('Tier', 'get_tier_display'),
        ('Criticality', 'get_vendor_criticality_display'),
        ('Data Sensitivity', 'get_data_sensitivity_display'),
        ('Owner Dept', lambda v: v.owner_dept.name),
        ('Contact Name', 'contact_name'),
        ('Contact Email', 'contact_email'),
        ('Contact Phone', 'contact_phone'),
        ('Latest Score', lambda v: v.latest_score if v.latest_score is not None else ''),
        ('Assets', lambda v: v.provides_assets.count()),
        ('Contract Start', lambda v: v.contract_start or ''),
        ('Contract End', lambda v: v.contract_end or ''),
        ('Active', lambda v: 'Yes' if v.is_active else 'No'),
    ]

    def get_queryset(self):
        qs = super().get_queryset()
        q = self.request.GET.get('q', '').strip()
        if q:
            qs = qs.filter(Q(name__icontains=q) | Q(description__icontains=q) | Q(contact_name__icontains=q))
        tier = self.request.GET.get('tier')
        if tier:
            qs = qs.filter(tier=tier)
        sens = self.request.GET.get('sensitivity')
        if sens:
            qs = qs.filter(data_sensitivity=sens)
        return qs.order_by('name')

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['tiers'] = Vendor.TIER_CHOICES
        ctx['sensitivities'] = Vendor.SENSITIVITY_CHOICES
        ctx['search_query'] = self.request.GET.get('q', '')
        ctx['selected_tier'] = self.request.GET.get('tier', '')
        ctx['selected_sensitivity'] = self.request.GET.get('sensitivity', '')
        return ctx


class VendorDetailView(DepartmentScopedMixin, DetailView):
    model = Vendor
    template_name = 'vendors/vendor_detail.html'
    context_object_name = 'vendor'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx.update(get_full_vendor_context(self.object))
        return ctx


class VendorCreateView(DepartmentScopedMixin, CreateView):
    model = Vendor
    form_class = VendorForm
    template_name = 'vendors/vendor_form.html'
    success_url = reverse_lazy('vendors:list')

    def get_initial(self):
        initial = super().get_initial()
        user = self.request.user
        if not user.is_superuser and user.department_id:
            initial['owner_dept'] = user.department
        return initial


class VendorUpdateView(DepartmentScopedMixin, UpdateView):
    model = Vendor
    form_class = VendorForm
    template_name = 'vendors/vendor_form.html'
    success_url = reverse_lazy('vendors:list')


class VendorAssessmentListView(DepartmentScopedMixin, CsvExportMixin, ListView):
    model = VendorAssessment
    template_name = 'vendors/assessment_list.html'
    context_object_name = 'assessments'
    paginate_by = 25
    department_field = 'vendor__owner_dept'

    csv_filename = 'vendor_assessments.csv'
    csv_fields = [
        ('Assessment ID', 'assessment_id'),
        ('Vendor', lambda a: a.vendor.name),
        ('Criticality', 'get_vendor_criticality_display'),
        ('Financial', 'financial_risk'),
        ('Operational', 'operational_risk'),
        ('Regulatory', 'regulatory_risk'),
        ('Cybersecurity', 'cybersecurity_risk'),
        ('Reputational', 'reputational_risk'),
        ('Overall Score', 'overall_score'),
        ('Rating', 'get_overall_risk_rating_display'),
        ('Assessed By', lambda a: a.assessor.username if a.assessor else ''),
        ('Assessment Date', 'assessment_date'),
        ('Next Assessment', lambda a: a.next_assessment_date or ''),
    ]

    def get_queryset(self):
        qs = super().get_queryset().select_related('vendor', 'assessor')
        q = self.request.GET.get('q', '').strip()
        if q:
            qs = qs.filter(Q(vendor__name__icontains=q) | Q(key_findings__icontains=q))
        status = self.request.GET.get('status')
        if status:
            qs = qs.filter(status=status)
        return qs.order_by('-assessment_date')

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['statuses'] = VendorAssessment.STATUS_CHOICES
        ctx['search_query'] = self.request.GET.get('q', '')
        ctx['selected_status'] = self.request.GET.get('status', '')

        base = super().get_queryset()
        user = self.request.user
        if not user.is_superuser and user.department_id:
            base = base.filter(vendor__owner_dept=user.department)
        ctx['total_count'] = base.count()
        ctx['high_risk_count'] = base.filter(overall_risk_rating__in=['high', 'critical']).count()
        ctx['pending_count'] = base.filter(status='pending').count()
        ctx['now_date'] = timezone.now().date()
        ctx['overdue_count'] = base.filter(
            next_assessment_date__lt=timezone.now().date()
        ).count()
        return ctx


class VendorAssessmentCreateView(LoginRequiredMixin, CreateView):
    model = VendorAssessment
    form_class = VendorAssessmentForm
    template_name = 'vendors/assessment_form.html'

    def dispatch(self, request, *args, **kwargs):
        self.vendor = None
        vendor_pk = kwargs.get('vendor_pk')
        if vendor_pk:
            self.vendor = Vendor.objects.get(pk=vendor_pk)
        return super().dispatch(request, *args, **kwargs)

    def get_initial(self):
        initial = super().get_initial()
        initial['assessor'] = self.request.user
        initial['assessment_date'] = timezone.now().date()
        if self.vendor:
            initial['vendor'] = self.vendor
            initial['vendor_criticality'] = self.vendor.vendor_criticality
        return initial

    def form_valid(self, form):
        if self.vendor:
            form.instance.vendor = self.vendor
        form.instance.assessor = self.request.user
        return super().form_valid(form)

    def get_success_url(self):
        return reverse_lazy('vendors:detail', kwargs={'pk': self.object.vendor.pk})

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['vendor'] = self.vendor or (self.object.vendor if self.object else None)
        return ctx


class VendorAssessmentUpdateView(LoginRequiredMixin, UpdateView):
    model = VendorAssessment
    form_class = VendorAssessmentForm
    template_name = 'vendors/assessment_form.html'

    def get_success_url(self):
        return reverse_lazy('vendors:detail', kwargs={'pk': self.object.vendor.pk})

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['vendor'] = self.object.vendor
        return ctx
