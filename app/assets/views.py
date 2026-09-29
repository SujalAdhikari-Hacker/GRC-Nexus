import json
from collections import defaultdict

from django.db.models import Q
from django.views.generic import ListView, DetailView, TemplateView
from django.contrib.auth.mixins import LoginRequiredMixin

from core.mixins import DepartmentScopedMixin, CsvExportMixin
from core.correlation import get_full_asset_context
from core.reports import ReportMixin
from .models import Asset, AssetCategory


# ============================================================
# ASSET LIST + DETAIL
# ============================================================

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


# ============================================================
# ASSET CLASSIFICATION VIEW
# ============================================================

class AssetClassificationView(DepartmentScopedMixin, TemplateView):
    template_name = 'assets/asset_classification.html'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        user = self.request.user
        qs = Asset.objects.filter(is_active=True).select_related('owner_dept', 'vendor')

        if not user.is_superuser and user.department_id:
            qs = qs.filter(owner_dept=user.department)

        buckets = []
        for code, label in Asset.CLASSIFICATION_CHOICES:
            items = qs.filter(classification=code).order_by('asset_id')
            buckets.append({
                'code': code,
                'label': label,
                'count': items.count(),
                'assets': items,
            })

        ctx['buckets'] = buckets
        ctx['total'] = qs.count()
        return ctx


# ============================================================
# ASSET OWNERS VIEW
# ============================================================

class AssetOwnersView(DepartmentScopedMixin, TemplateView):
    template_name = 'assets/asset_owners.html'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        user = self.request.user
        qs = Asset.objects.filter(is_active=True).select_related('owner_dept', 'owner_user', 'vendor')

        if not user.is_superuser and user.department_id:
            qs = qs.filter(owner_dept=user.department)

        mode = self.request.GET.get('view', 'department')
        ctx['mode'] = mode

        groups = defaultdict(list)

        if mode == 'user':
            for a in qs:
                key = a.owner_user.username if a.owner_user else 'Unassigned'
                groups[key].append(a)
        else:
            for a in qs:
                groups[a.owner_dept.name].append(a)

        ctx['groups'] = [
            {'label': k, 'assets': v, 'count': len(v)}
            for k, v in sorted(groups.items())
        ]
        ctx['total'] = qs.count()
        return ctx


# ============================================================
# RELATIONSHIP EXPLORER
# ============================================================

class AssetExplorerPickerView(DepartmentScopedMixin, ListView):
    model = Asset
    template_name = 'assets/explorer_picker.html'
    context_object_name = 'assets'
    paginate_by = 40

    def get_queryset(self):
        qs = super().get_queryset().filter(is_active=True).select_related('owner_dept')
        q = self.request.GET.get('q', '').strip()
        if q:
            qs = qs.filter(Q(asset_id__icontains=q) | Q(name__icontains=q))
        return qs.order_by('asset_id')

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['search_query'] = self.request.GET.get('q', '')
        return ctx


class AssetExplorerView(DepartmentScopedMixin, DetailView):
    model = Asset
    template_name = 'assets/explorer.html'
    context_object_name = 'asset'

    def get_context_data(self, **kwargs):
        from core.correlation import get_policies_for_asset

        ctx = super().get_context_data(**kwargs)
        asset = self.object

        nodes = []
        edges = []
        seen = set()

        def add_node(node_id, label, group, url=None, title=None, size=20):
            if node_id in seen:
                return
            seen.add(node_id)
            nodes.append({
                'id': node_id,
                'label': label,
                'group': group,
                'url': url or '#',
                'title': title or label,
                'size': size,
            })

        def add_edge(a, b, label='', dashes=False):
            edges.append({'from': a, 'to': b, 'label': label, 'dashes': dashes})

        add_node(
            f'asset-{asset.pk}',
            f'{asset.asset_id}\n{asset.name}',
            'asset',
            url=f'/assets/{asset.pk}/',
            title=f'{asset.asset_id} — {asset.name}',
            size=40,
        )

        for v in asset.vendors.all():
            nid = f'vendor-{v.pk}'
            add_node(nid, v.name, 'vendor', url=f'/vendors/{v.pk}/', size=26)
            add_edge(f'asset-{asset.pk}', nid, 'supplied by')

        for r in asset.risks.all():
            nid = f'risk-{r.pk}'
            prefix = '! ' if r.appetite_breached else ''
            add_node(
                nid,
                f'{prefix}{r.title[:28]}',
                'risk',
                url=f'/risks/{r.pk}/',
                title=f'Residual {r.residual_score} · {"BREACH" if r.appetite_breached else "in appetite"}',
                size=22,
            )
            add_edge(f'asset-{asset.pk}', nid, 'affects')

            for c in r.controls.all():
                cid = f'control-{c.pk}'
                add_node(
                    cid, c.code, 'control',
                    url=f'/controls/{c.pk}/',
                    title=f'{c.code} — {c.name}',
                    size=18,
                )
                add_edge(nid, cid, 'mitigated by')

                for fc in c.framework_controls.all():
                    fcid = f'fc-{fc.pk}'
                    add_node(
                        fcid,
                        f'{fc.framework.name}\n{fc.code}',
                        'framework',
                        url=f'/frameworks/{fc.framework.pk}/',
                        title=f'{fc.framework.name} {fc.code} — {fc.title}',
                        size=14,
                    )
                    add_edge(cid, fcid, 'satisfies', dashes=True)

        for p in get_policies_for_asset(asset):
            nid = f'policy-{p.pk}'
            add_node(nid, p.code, 'policy', url=f'/policies/{p.pk}/', title=p.title, size=18)
            add_edge(f'asset-{asset.pk}', nid, 'governed by', dashes=True)

        for f in asset.findings.all():
            nid = f'finding-{f.pk}'
            label = f.vulnerability.cve_id or f.vulnerability.title[:18]
            add_node(
                nid, label, 'finding',
                url=f'/vulnerabilities/findings/{f.pk}/',
                title=f'CVSS {f.vulnerability.cvss_score} · composite {f.composite_score}',
                size=16,
            )
            add_edge(f'asset-{asset.pk}', nid, 'has vuln', dashes=True)

        ctx['graph_nodes_json'] = json.dumps(nodes)
        ctx['graph_edges_json'] = json.dumps(edges)
        ctx['node_count'] = len(nodes)
        ctx['edge_count'] = len(edges)
        return ctx
