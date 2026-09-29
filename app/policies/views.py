from django.db.models import Q
from django.views.generic import ListView, DetailView
from django.urls import reverse_lazy
from django.views.generic import CreateView, UpdateView
from .forms import PolicyForm
from core.mixins import DepartmentScopedMixin, CsvExportMixin
from core.correlation import get_full_policy_context
from .models import Policy, PolicyCategory


class PolicyListView(DepartmentScopedMixin, CsvExportMixin, ListView):
    model = Policy
    template_name = 'policies/policy_list.html'
    context_object_name = 'policies'
    paginate_by = 20

    csv_filename = 'policies.csv'
    csv_fields = [
        ('Code', 'code'),
        ('Title', 'title'),
        ('Category', lambda p: p.category.name if p.category else ''),
        ('Department', lambda p: p.owner_dept.name),
        ('Version', 'version'),
        ('Status', 'get_status_display'),
        ('Approved By', lambda p: p.approved_by.username if p.approved_by else ''),
        ('Approval Date', lambda p: p.approval_date or ''),
        ('Next Review', lambda p: p.next_review_date or ''),
    ]

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


# ============================================================
# POLICY CREATE / UPDATE
# ============================================================

class PolicyCreateView(DepartmentScopedMixin, CreateView):
    model = Policy
    form_class = PolicyForm
    template_name = 'policies/policy_form.html'

    def get_initial(self):
        initial = super().get_initial()
        user = self.request.user
        if not user.is_superuser and user.department_id:
            initial['owner_dept'] = user.department
        initial['version'] = '1.0'
        initial['status'] = 'draft'
        return initial

    def get_success_url(self):
        return reverse_lazy('policies:detail', kwargs={'pk': self.object.pk})

    def form_valid(self, form):
        from django.contrib import messages
        response = super().form_valid(form)
        messages.success(self.request, f'Policy {self.object.code} created.')
        return response


class PolicyUpdateView(DepartmentScopedMixin, UpdateView):
    model = Policy
    form_class = PolicyForm
    template_name = 'policies/policy_form.html'

    def get_success_url(self):
        return reverse_lazy('policies:detail', kwargs={'pk': self.object.pk})

    def form_valid(self, form):
        from django.contrib import messages
        response = super().form_valid(form)
        messages.success(self.request, f'Policy {self.object.code} updated.')
        return response