from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import Q, Count
from django.urls import reverse_lazy
from django.views.generic import ListView, DetailView, CreateView, UpdateView

from core.mixins import DepartmentScopedMixin
from .models import KRI, KRIReading


class KRIListView(DepartmentScopedMixin, ListView):
    model = KRI
    template_name = 'kris/kri_list.html'
    context_object_name = 'kris'
    paginate_by = 25
    department_field = 'owner_dept'

    def get_queryset(self):
        qs = super().get_queryset().select_related('owner_dept', 'owner_user')
        q = self.request.GET.get('q', '').strip()
        if q:
            qs = qs.filter(Q(name__icontains=q) | Q(description__icontains=q))
        cat = self.request.GET.get('category')
        if cat:
            qs = qs.filter(category=cat)
        trend = self.request.GET.get('trend')
        if trend:
            qs = qs.filter(trend=trend)
        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        base = super().get_queryset()
        user = self.request.user
        if not user.is_superuser and user.department_id:
            base = base.filter(owner_dept=user.department)

        # Compute RAG counts by iterating (property is Python-side)
        all_kris = list(base)
        ctx['rag_counts'] = {
            'green': sum(1 for k in all_kris if k.rag_status == 'green'),
            'amber': sum(1 for k in all_kris if k.rag_status == 'amber'),
            'red':   sum(1 for k in all_kris if k.rag_status == 'red'),
        }
        ctx['total_count'] = len(all_kris)

        ctx['categories'] = KRI.CATEGORY_CHOICES
        ctx['trends'] = KRI.TREND_CHOICES
        ctx['search_query'] = self.request.GET.get('q', '')
        ctx['selected_category'] = self.request.GET.get('category', '')
        ctx['selected_trend'] = self.request.GET.get('trend', '')
        return ctx


class KRIDetailView(DepartmentScopedMixin, DetailView):
    model = KRI
    template_name = 'kris/kri_detail.html'
    context_object_name = 'kri'
    department_field = 'owner_dept'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['readings'] = self.object.readings.order_by('reading_date')[:30]
        return ctx


class KRICreateView(DepartmentScopedMixin, CreateView):
    model = KRI
    template_name = 'kris/kri_form.html'
    fields = [
        'name', 'description', 'category', 'kri_type',
        'current_value', 'unit', 'direction',
        'amber_threshold', 'red_threshold',
        'frequency', 'trend', 'owner_dept', 'owner_user',
        'linked_risks', 'linked_appetites',
    ]
    success_url = reverse_lazy('kris:list')
    department_field = 'owner_dept'

    def get_initial(self):
        initial = super().get_initial()
        user = self.request.user
        if not user.is_superuser and user.department_id:
            initial['owner_dept'] = user.department
        return initial


class KRIUpdateView(DepartmentScopedMixin, UpdateView):
    model = KRI
    template_name = 'kris/kri_form.html'
    fields = [
        'name', 'description', 'category', 'kri_type',
        'current_value', 'unit', 'direction',
        'amber_threshold', 'red_threshold',
        'frequency', 'trend', 'owner_dept', 'owner_user',
        'linked_risks', 'linked_appetites',
    ]
    success_url = reverse_lazy('kris:list')
    department_field = 'owner_dept'
