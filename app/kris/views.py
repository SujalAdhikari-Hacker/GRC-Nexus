from django.db.models import Q
from django.urls import reverse_lazy
from django.views.generic import CreateView, DetailView, ListView, UpdateView

from core.input_validation import choice, search_query
from core.mixins import (
    ChangeScopedMixin,
    CsvExportMixin,
    DepartmentCreateMixin,
    DepartmentPinnedMixin,
    DepartmentScopedMixin,
    SavedViewsMixin,
)
from .models import KRI


class KRIListView(CsvExportMixin, SavedViewsMixin, DepartmentScopedMixin, ListView):
    model = KRI
    template_name = 'kris/kri_list.html'
    context_object_name = 'kris'
    paginate_by = 25
    department_field = 'owner_dept'

    csv_filename = 'key_risk_indicators.csv'
    csv_fields = [
        ('KRI', 'name'),
        ('Category', 'get_category_display'),
        ('Type', 'get_kri_type_display'),
        ('Current', 'current_value'),
        ('Unit', 'unit'),
        ('Amber threshold', 'amber_threshold'),
        ('Red threshold', 'red_threshold'),
        ('Trend', 'get_trend_display'),
        ('RAG', 'rag_status'),
        ('Owner dept', lambda k: k.owner_dept.name if k.owner_dept else ''),
    ]

    def get_queryset(self):
        qs = super().get_queryset().select_related('owner_dept', 'owner_user')
        q = search_query(self.request.GET.get('q', ''))
        if q:
            qs = qs.filter(Q(name__icontains=q) | Q(description__icontains=q))
        cat = choice(
            self.request.GET.get('category'),
            {value for value, _label in KRI.CATEGORY_CHOICES},
            'category', allow_blank=True,
        )
        if cat:
            qs = qs.filter(category=cat)
        trend = choice(
            self.request.GET.get('trend'),
            {value for value, _label in KRI.TREND_CHOICES},
            'trend', allow_blank=True,
        )
        if trend:
            qs = qs.filter(trend=trend)
        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        # DepartmentScopedMixin already scoped this queryset.
        base = super().get_queryset()

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


class KRICreateView(DepartmentCreateMixin, DepartmentScopedMixin, CreateView):
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


class KRIUpdateView(DepartmentPinnedMixin, ChangeScopedMixin, UpdateView):
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
