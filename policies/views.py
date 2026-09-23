from django.db.models import Q
from django.views.generic import ListView, DetailView

from core.mixins import DepartmentScopedMixin
from core.correlation import get_full_policy_context
from .models import Policy, PolicyCategory


class PolicyListView(DepartmentScopedMixin, ListView):
    model = Policy
    template_name = 'policies/policy_list.html'
    context_object_name = 'policies'
    paginate_by = 20

    def get_queryset(self):
        qs = super().get_queryset()
        q = self.request.GET.get('q', '').strip()
        if q:
            qs = qs.filter(Q(title__icontains=q) | Q(code__icontains=q) | Q(description__icontains=q))
        cat = self.request.GET.get('category')
        if cat:
            qs = qs.filter(category_id=cat)
        status = self.request.GET.get('status')
        if status:
            qs = qs.filter(status=status)
        return qs.order_by('code')

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['categories'] = PolicyCategory.objects.all()
        ctx['statuses'] = Policy.STATUS_CHOICES
        ctx['search_query'] = self.request.GET.get('q', '')
        ctx['selected_category'] = self.request.GET.get('category', '')
        ctx['selected_status'] = self.request.GET.get('status', '')
        return ctx


class PolicyDetailView(DepartmentScopedMixin, DetailView):
    model = Policy
    template_name = 'policies/policy_detail.html'
    context_object_name = 'policy'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx.update(get_full_policy_context(self.object))
        return ctx