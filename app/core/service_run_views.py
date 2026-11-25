"""Read-only history of the scheduled services (cron commands).

See :mod:`core.service_runs` for how rows are written. This page exists so an
operator can answer "did last night's sweep run, and did it work?" without
shell access. Superusers only: the rows name internal jobs and can carry raw
error text.
"""
from django.views.generic import ListView

from .input_validation import choice
from .mixins import SuperuserOnlyMixin
from .models import ServiceRun

STATUS_CHOICES = ServiceRun.STATUS_CHOICES


class ServiceRunListView(SuperuserOnlyMixin, ListView):
    model = ServiceRun
    template_name = 'core/service_run_list.html'
    context_object_name = 'runs'
    paginate_by = 50

    def get(self, request, *args, **kwargs):
        self.services = list(
            ServiceRun.objects.order_by('service')
            .values_list('service', flat=True).distinct()
        )
        self.selected_service = choice(
            request.GET.get('service'), set(self.services), 'service',
            allow_blank=True,
        )
        self.selected_status = choice(
            request.GET.get('status'), {value for value, _label in STATUS_CHOICES},
            'status', allow_blank=True,
        )
        return super().get(request, *args, **kwargs)

    def get_queryset(self):
        queryset = super().get_queryset()
        if self.selected_service:
            queryset = queryset.filter(service=self.selected_service)
        if self.selected_status:
            queryset = queryset.filter(status=self.selected_status)
        return queryset

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx.update({
            'services': self.services,
            'status_choices': STATUS_CHOICES,
            'selected_service': self.selected_service,
            'selected_status': self.selected_status,
        })
        return ctx
