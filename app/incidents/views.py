from django.contrib import messages
from django.db.models import Q
from django.urls import reverse, reverse_lazy
from django.utils import timezone
from django.views.generic import CreateView, DetailView, ListView, UpdateView, View
from django.views.generic.detail import SingleObjectMixin
from datetime import timedelta

from core.input_validation import boolean, choice, search_query
from core.mixins import (
    ChangeScopedMixin,
    CsvExportMixin,
    DepartmentCreateMixin,
    DepartmentPinnedMixin,
    DepartmentScopedMixin,
    SavedViewsMixin,
)
from .forms import IncidentForm
from .models import TRIAGE_SLA_HOURS, Incident

_OPEN_STATUSES = ('detected', 'triaged', 'contained', 'mitigated')


class IncidentListView(CsvExportMixin, SavedViewsMixin, DepartmentScopedMixin, ListView):
    model = Incident
    template_name = 'incidents/incident_list.html'
    context_object_name = 'incidents'
    paginate_by = 25
    department_field = 'owner_dept'

    csv_filename = 'security_incidents.csv'
    csv_fields = [
        ('Reference', 'reference'),
        ('Title', 'title'),
        ('Type', 'get_incident_type_display'),
        ('Source', 'get_source_display'),
        ('Severity', 'get_severity_display'),
        ('Status', 'get_status_display'),
        ('Owner dept', lambda i: i.owner_dept.name if i.owner_dept else ''),
        ('Handler', lambda i: i.handler.get_full_name() if i.handler else ''),
        ('Detected', lambda i: i.detected_at.strftime('%Y-%m-%d %H:%M') if i.detected_at else ''),
        ('Closed', lambda i: i.closed_at.strftime('%Y-%m-%d %H:%M') if i.closed_at else ''),
        ('Assets affected', lambda i: i.affected_assets.count()),
        ('Data subjects affected', 'data_subjects_affected'),
        ('Regulatory notification', lambda i: 'yes' if i.regulatory_notification_required else 'no'),
        ('NIS2 significant', lambda i: 'yes' if i.nis2_significant else 'no'),
        ('NIS2 next report', lambda i: i.nis2_phase if i.nis2_significant else ''),
        ('Root cause', 'root_cause'),
    ]

    def get_queryset(self):
        qs = super().get_queryset().select_related('owner_dept', 'handler')
        params = self.request.GET

        q = search_query(params.get('q'))
        if q:
            qs = qs.filter(Q(title__icontains=q) | Q(description__icontains=q)
                           | Q(reference__icontains=q) | Q(root_cause__icontains=q))
        status = choice(
            params.get('status'),
            {value for value, _label in Incident.STATUS_CHOICES},
            'status', allow_blank=True,
        )
        if status:
            qs = qs.filter(status=status)
        severity = choice(
            params.get('severity'),
            {value for value, _label in Incident.SEVERITY_CHOICES},
            'severity', allow_blank=True,
        )
        if severity:
            qs = qs.filter(severity=severity)
        incident_type = choice(
            params.get('incident_type'),
            {value for value, _label in Incident.TYPE_CHOICES},
            'incident_type', allow_blank=True,
        )
        if incident_type:
            qs = qs.filter(incident_type=incident_type)
        if boolean(params.get('open'), 'open', default=False):
            qs = qs.filter(status__in=_OPEN_STATUSES)
        return qs.order_by('-detected_at')

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        scoped = Incident.objects.all()
        if not self.request.user.is_superuser:
            scoped = scoped.filter(owner_dept=self.request.user.department)
        ctx['open_count'] = scoped.filter(status__in=_OPEN_STATUSES).count()
        ctx['total_count'] = scoped.count()
        ctx['breach_count'] = scoped.filter(
            incident_type='data_breach', status__in=_OPEN_STATUSES
        ).count()
        ctx['overdue_count'] = scoped.filter(
            incident_type='data_breach', status__in=_OPEN_STATUSES,
            regulatory_notification_required=True, regulatory_notified_at__isnull=True,
            detected_at__lt=timezone.now() - timedelta(hours=72),
        ).count()
        ctx['form_status_choices'] = Incident.STATUS_CHOICES
        ctx['form_severity_choices'] = Incident.SEVERITY_CHOICES
        return ctx


class IncidentDetailView(DepartmentScopedMixin, DetailView):
    model = Incident
    template_name = 'incidents/incident_detail.html'
    context_object_name = 'incident'

    def get_queryset(self):
        return super().get_queryset().select_related('owner_dept', 'handler')

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        incident = self.object
        ctx['history_entries'] = incident.history.select_related('history_user')[:50]
        ctx['can_change'] = self.request.user.is_superuser or (
            self.request.user.department_id == incident.owner_dept_id
        )
        ctx['age_hours'] = incident.age_hours
        ctx['lifecycle'] = Incident.STATUS_CHOICES
        ctx['lifecycle_position'] = [s for s, _ in Incident.STATUS_CHOICES].index(
            incident.status
        )
        ctx['incidents_sla'] = f'{TRIAGE_SLA_HOURS.get(incident.severity, 24)}h'
        ctx['nis2_clocks'] = (
            incident.nis2_clocks if incident.nis2_significant else []
        )
        ctx['nis2_breach'] = incident.nis2_breach
        return ctx


class IncidentCreateView(DepartmentCreateMixin, DepartmentScopedMixin, CreateView):
    model = Incident
    form_class = IncidentForm
    template_name = 'incidents/incident_form.html'
    success_url = reverse_lazy('incidents:list')

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['user'] = self.request.user
        return kwargs

    def form_valid(self, form):
        if form.cleaned_data.get('owner_dept'):
            form.instance.owner_dept = form.cleaned_data['owner_dept']
        form.instance.created_by = self.request.user
        form.instance.updated_by = self.request.user
        response = super().form_valid(form)
        messages.success(
            self.request,
            f'Incident {self.object.reference} filed — the department has been notified.'
        )
        return response


class IncidentUpdateView(DepartmentPinnedMixin, ChangeScopedMixin, UpdateView):
    model = Incident
    form_class = IncidentForm
    template_name = 'incidents/incident_form.html'

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['user'] = self.request.user
        return kwargs

    def form_valid(self, form):
        form.instance.updated_by = self.request.user
        response = super().form_valid(form)
        messages.success(
            self.request, f'Incident {self.object.reference} updated.'
        )
        return response

    def get_success_url(self):
        return reverse('incidents:detail', args=[self.object.pk])


class IncidentCloseView(ChangeScopedMixin, UpdateView):
    """Close an incident - requires a root cause (validated by the model).

    POST-only; the confirmation page explains what closing means.
    """
    model = Incident
    fields = ['root_cause', 'lessons_learned']
    template_name = 'incidents/incident_close.html'

    def get_queryset(self):
        # Only open incidents can be closed.
        return super().get_queryset().exclude(status='closed')

    def form_valid(self, form):
        form.instance.updated_by = self.request.user
        form.instance.status = 'closed'
        response = super().form_valid(form)
        messages.success(
            self.request,
            f'Incident {self.object.reference} closed. Lessons learned stay on the record.'
        )
        return response

    def get_success_url(self):
        return reverse('incidents:detail', args=[self.object.pk])


class IncidentRaiseRiskView(ChangeScopedMixin, SingleObjectMixin, View):
    """File a risk-register entry from an investigated incident.

    Explicit user action (not an automatic cascade) because whether an
    incident deserves a register entry is a human call. The new risk is
    linked back so the two records travel together. POST-only, and refuses
    to create a second entry while one from this incident is still open.
    """
    model = Incident
    template_name = 'incidents/incident_raise_risk.html'

    def get(self, request, *args, **kwargs):
        from django.shortcuts import render
        incident = self.get_object()
        return render(request, self.template_name, {'incident': incident})

    def post(self, request, *args, **kwargs):
        from django.shortcuts import redirect, get_object_or_404
        from risks.models import Risk, RiskCategory

        incident = get_object_or_404(self.get_queryset(), pk=kwargs['pk'])
        existing = incident.risks.exclude(status__in=['closed'])
        if existing.exists():
            messages.info(
                request,
                'This incident is already linked to an open risk-register entry.'
            )
            return redirect('incidents:detail', pk=incident.pk)

        category, _ = RiskCategory.objects.get_or_create(
            name='Security incident',
            defaults={'description': 'Risks raised from the incident register.'},
        )
        severity_to_score = {'critical': 5, 'high': 4, 'medium': 3, 'low': 2}
        risk = Risk.objects.create(
            title=f'[{incident.reference}] {incident.title[:270]}',
            description=(
                f'Raised from security incident {incident.reference}.\n\n'
                f'{incident.description[:2000]}'
            ),
            category=category,
            owner_dept=incident.owner_dept,
            owner_user=incident.handler or request.user,
            likelihood=3,
            impact=severity_to_score.get(incident.severity, 3),
            identified_date=timezone.localdate(),
        )
        risk.assets.set(incident.affected_assets.all())
        incident.risks.add(risk)
        messages.success(
            request,
            f'Risk #{risk.pk} raised from incident {incident.reference}.'
        )
        return redirect('risks:detail', pk=risk.pk)

