from django.views.generic import ListView, DetailView

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