from django.db.models import Q
from django.views.generic import ListView, DetailView

from core.mixins import DepartmentScopedMixin, CsvExportMixin
from core.correlation import get_full_asset_context
from core.views import ReportMixin
from .models import Asset, AssetCategory


class AssetListView(ReportMixin, DepartmentScopedMixin, CsvExportMixin, ListView):
    model = Asset
    template_name = 'assets/asset_list.html'
    context_object_name = 'assets'
    paginate_by = 20

    report_title = 'Asset Inventory'
    report_filename_base = 'asset_inventory'
    pdf_template = 'reports/asset_inventory_pdf.html'

    csv_filename = 'assets.csv'
    csv_fields = [
        ('Asset ID', 'asset_id'),
        ('Name', 'name'),
        ('Hostname', 'hostname'),
        ('IP Address', 'ip_address'),
        ('FQDN', 'fqdn'),
        ('Type', 'get_asset_type_display'),
        ('Hosting', 'get_hosting_display'),
        ('Cloud Provider', 'get_cloud_provider_display'),
        ('Cloud Region', 'cloud_region'),
        ('Location', 'location'),
        ('OS Family', 'get_os_family_display'),
        ('OS Version', 'os_version'),
        ('Vendor', lambda a: a.vendor.name if a.vendor else ''),
        ('Classification', 'get_classification_display'),
        ('Owner Dept', lambda a: a.owner_dept.name),
        ('Owner User', lambda a: a.owner_user.username if a.owner_user else ''),
        ('Environment', 'get_environment_display'),
        ('Criticality', 'get_criticality_display'),
        ('CIA Avg', 'cia_score'),
        ('Description', 'description'),
        ('Created', lambda a: a.created_at.strftime('%Y-%m-%d')),
    ]

    def get_queryset(self):
        qs = super().get_queryset().select_related('owner_dept', 'vendor', 'owner_user')
        q = self.request.GET.get('q', '').strip()
        if q:
            qs = qs.filter(
                Q(asset_id__icontains=q) | Q(name__icontains=q) |
                Q(hostname__icontains=q) | Q(ip_address__icontains=q) |
                Q(description__icontains=q)
            )
        atype = self.request.GET.get('type')
        if atype:
            qs = qs.filter(asset_type=atype)
        classification = self.request.GET.get('classification')
        if classification:
            qs = qs.filter(classification=classification)
        environment = self.request.GET.get('environment')
        if environment:
            qs = qs.filter(environment=environment)
        cloud = self.request.GET.get('cloud')
        if cloud:
            qs = qs.filter(cloud_provider=cloud)
        os_family = self.request.GET.get('os')
        if os_family:
            qs = qs.filter(os_family=os_family)
        return qs.order_by('asset_id')

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['categories'] = AssetCategory.objects.all()
        ctx['search_query'] = self.request.GET.get('q', '')
        ctx['selected_type'] = self.request.GET.get('type', '')
        ctx['selected_classification'] = self.request.GET.get('classification', '')
        ctx['selected_environment'] = self.request.GET.get('environment', '')
        ctx['selected_cloud'] = self.request.GET.get('cloud', '')
        ctx['selected_os'] = self.request.GET.get('os', '')
        return ctx

    def build_rows(self):
        headers = ['Asset ID', 'Name', 'Hostname', 'IP', 'Type', 'Hosting', 'Cloud',
                   'Region', 'OS', 'Vendor', 'Classification', 'Owner', 'Env', 'Criticality']
        qs = self.get_queryset()
        rows = []
        for a in qs:
            rows.append([
                a.asset_id,
                a.name,
                a.hostname,
                a.ip_address or '',
                a.get_asset_type_display(),
                a.get_hosting_display(),
                a.get_cloud_provider_display(),
                a.cloud_region,
                f"{a.get_os_family_display()}{(' — ' + a.os_version) if a.os_version else ''}",
                a.vendor.name if a.vendor else '',
                a.get_classification_display(),
                a.owner_dept.name if a.owner_dept else '',
                a.get_environment_display(),
                a.get_criticality_display(),
            ])
        return headers, rows

    def build_pdf_context(self):
        qs = list(self.get_queryset())
        return {'assets': qs, 'total': len(qs)}


class AssetDetailView(DepartmentScopedMixin, DetailView):
    model = Asset
    template_name = 'assets/asset_detail.html'
    context_object_name = 'asset'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx.update(get_full_asset_context(self.object))
        return ctx
