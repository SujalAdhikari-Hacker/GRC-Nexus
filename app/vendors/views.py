from django.db.models import Q
from django.views.generic import ListView, DetailView

from core.mixins import DepartmentScopedMixin, CsvExportMixin
from core.correlation import get_full_vendor_context
from .models import Vendor


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
