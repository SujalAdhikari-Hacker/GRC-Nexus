from django.db.models import Q
from django.views.generic import ListView, DetailView

from core.mixins import DepartmentScopedMixin
from core.correlation import get_full_control_context
from .models import Control


class ControlListView(DepartmentScopedMixin, ListView):
    model = Control
    template_name = 'controls/control_list.html'
    context_object_name = 'controls'
    paginate_by = 25

    def get_queryset(self):
        qs = super().get_queryset()
        q = self.request.GET.get('q', '').strip()
        if q:
            qs = qs.filter(Q(name__icontains=q) | Q(code__icontains=q))
        status = self.request.GET.get('status')
        if status:
            qs = qs.filter(status=status)
        category = self.request.GET.get('category')
        if category:
            qs = qs.filter(category=category)
        return qs.order_by('code')

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['statuses'] = Control.STATUS_CHOICES
        ctx['categories_choices'] = Control.CATEGORY_CHOICES
        ctx['search_query'] = self.request.GET.get('q', '')
        ctx['selected_status'] = self.request.GET.get('status', '')
        ctx['selected_category'] = self.request.GET.get('category', '')
        return ctx


class ControlDetailView(DepartmentScopedMixin, DetailView):
    model = Control
    template_name = 'controls/control_detail.html'
    context_object_name = 'control'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx.update(get_full_control_context(self.object))
        return ctx