from django.views.generic import ListView, DetailView, TemplateView

from core.correlation import (
    get_framework_coverage,
    get_control_coverage_by_control_for_framework,
)
from .models import Framework


class FrameworkListView(ListView):
    model = Framework
    template_name = 'frameworks/framework_list.html'
    context_object_name = 'frameworks'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        rows = []
        for fw in self.object_list:
            rows.append((fw, get_framework_coverage(fw)))
        ctx['frameworks_with_coverage'] = rows
        return ctx


class FrameworkDetailView(DetailView):
    model = Framework
    template_name = 'frameworks/framework_detail.html'
    context_object_name = 'framework'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['coverage'] = get_framework_coverage(self.object)
        ctx['control_rows'] = get_control_coverage_by_control_for_framework(self.object)
        return ctx


class ComplianceStatusView(TemplateView):
    template_name = 'frameworks/compliance_status.html'

    def get_context_data(self, **kwargs):
        from controls.models import Control

        ctx = super().get_context_data(**kwargs)

        frameworks = list(Framework.objects.all().order_by('name'))

        rows = []
        total_weighted = 0.0
        total_requirements = 0

        for fw in frameworks:
            cov = get_framework_coverage(fw)
            rows.append({'framework': fw, 'cov': cov})
            total_weighted += (cov['percent'] / 100.0) * cov['total'] if cov['total'] else 0
            total_requirements += cov['total']

        overall_percent = round((total_weighted / total_requirements) * 100) if total_requirements else 0

        # Which controls contribute to most frameworks?
        top_controls = []
        for c in Control.objects.all().prefetch_related('framework_mappings', 'framework_controls'):
            count = c.framework_controls.count() + c.framework_mappings.count()
            if count > 0:
                top_controls.append({'control': c, 'count': count})
        top_controls.sort(key=lambda x: -x['count'])
        top_controls = top_controls[:10]

        # Requirements not covered (across all frameworks)
        from frameworks.models import FrameworkControl
        from controls.models import ControlFrameworkMapping

        covered_fc_ids = set(
            Control.objects.values_list('framework_controls__pk', flat=True)
        ) | set(
            ControlFrameworkMapping.objects.values_list('framework_control__pk', flat=True)
        )
        uncovered = FrameworkControl.objects.exclude(pk__in=covered_fc_ids).select_related('framework')

        ctx.update({
            'rows': rows,
            'overall_percent': overall_percent,
            'total_frameworks': len(frameworks),
            'total_requirements': total_requirements,
            'top_controls': top_controls,
            'uncovered': uncovered[:20],
            'uncovered_count': uncovered.count(),
        })
        return ctx
