from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import Q
from django.urls import reverse_lazy
from django.utils import timezone
from django.views.generic import ListView, DetailView, CreateView

from core.mixins import DepartmentScopedMixin, CsvExportMixin
from core.correlation import get_full_vendor_context
from .models import Vendor, VendorAssessment
from .forms import VendorAssessmentForm


class VendorListView(DepartmentScopedMixin, CsvExportMixin, ListView):
    model = Vendor
    template_name = 'vendors/vendor_list.html'
    context_object_name = 'vendors'
    paginate_by = 20

    csv_filename = 'vendors.csv'
    csv_fields = [
        ('Name', 'name'),
        ('Tier', 'get_tier_display'),
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


class VendorAssessmentCreateView(LoginRequiredMixin, CreateView):
    model = VendorAssessment
    form_class = VendorAssessmentForm
    template_name = 'vendors/assessment_form.html'

    def dispatch(self, request, *args, **kwargs):
        self.vendor = Vendor.objects.get(pk=kwargs['vendor_pk'])
        return super().dispatch(request, *args, **kwargs)

    def form_valid(self, form):
        form.instance.vendor = self.vendor
        form.instance.assessed_by = self.request.user
        if not form.instance.assessment_date:
            form.instance.assessment_date = timezone.now().date()
        return super().form_valid(form)

    def get_success_url(self):
        return reverse_lazy('vendors:detail', kwargs={'pk': self.vendor.pk})

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['vendor'] = self.vendor
        return ctx
