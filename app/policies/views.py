from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import PermissionDenied
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse_lazy
from django.utils import timezone
from django.views.generic import CreateView, DeleteView, DetailView, ListView, UpdateView, View
from django.views.generic.detail import SingleObjectMixin

from core.correlation import get_full_policy_context
from core.input_validation import choice, positive_int, search_query
from core.mixins import (
    ChangeScopedMixin,
    CsvExportMixin,
    DepartmentCreateMixin,
    DepartmentPinnedMixin,
    DepartmentScopedMixin,
    HODOrSuperuserMixin,
    SavedViewsMixin,
)

from .forms import PolicyForm
from .models import Policy, PolicyAttestation, PolicyCategory


class PolicyListView(SavedViewsMixin, DepartmentScopedMixin, CsvExportMixin, ListView):
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
        q = search_query(self.request.GET.get('q', ''))
        if q:
            qs = qs.filter(Q(title__icontains=q) | Q(code__icontains=q) | Q(description__icontains=q))
        cat = self.request.GET.get('category')
        if cat:
            qs = qs.filter(category_id=positive_int(cat, 'category'))
        status = choice(
            self.request.GET.get('status'),
            {value for value, _label in Policy.STATUS_CHOICES},
            'status', allow_blank=True,
        )
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

    def get_queryset(self):
        """A policy is visible to the departments it *applies to*, too.

        Reading is fine — attestation needs the reader to see the document —
        and a policy with no departments listed is org-wide by definition.
        Nothing here grants write access: edit/delete remain scoped to the
        owning department through ``ChangeScopedMixin``.
        """
        qs = super().get_queryset()  # owner dept + shares + guardian grants
        user = self.request.user
        if not user.is_superuser:
            audience = (
                Policy.objects.filter(applies_to_departments=user.department)
                | Policy.objects.filter(applies_to_departments__isnull=True)
            )
            qs = qs | audience
        return qs.distinct()

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx.update(get_full_policy_context(self.object))
        # Attestation register — current version only for the panel.
        attestations = self.object.attestations.select_related(
            'user', 'user__department'
        ).filter(version=self.object.version)
        ctx['attestations'] = attestations[:20]
        ctx['attestation_total'] = attestations.count()
        ctx['my_attestation'] = (attestations
                                 .filter(user=self.request.user).exists())
        return ctx


class PolicyAttestView(LoginRequiredMixin, View):
    """POST-only acknowledgement by the signed-in user of an approved policy.

    Scope rule: a policy applies to everyone when ``applies_to_departments``
    is empty; otherwise only members of the listed departments (plus the
    policy-owning department and superusers) are asked to attest.
    """

    def post(self, request, *args, **kwargs):
        from django.shortcuts import redirect, get_object_or_404
        policy = get_object_or_404(Policy, pk=kwargs['pk'])

        if policy.status != 'approved':
            messages.error(
                request, 'Only approved policies can be attested to.'
            )
            return redirect('policies:list')

        user = request.user
        applicable = list(policy.applies_to_departments.values_list('pk', flat=True))
        in_scope = (
            user.is_superuser
            or not applicable
            or user.department_id in applicable
            or user.department_id == policy.owner_dept_id
        )
        if not in_scope:
            messages.error(
                request,
                'This policy does not apply to your department, so no attestation is required.',
            )
            return redirect('policies:list')

        _, created = PolicyAttestation.objects.get_or_create(
            policy=policy, user=user, version=policy.version,
        )
        if created:
            messages.success(
                request,
                f'Attestation recorded: {policy.code} v{policy.version}.'
            )
        else:
            messages.info(
                request,
                f'You have already attested to {policy.code} v{policy.version}.'
            )
        return redirect('policies:detail', pk=policy.pk)


# ============================================================
# POLICY CREATE / UPDATE
# ============================================================

class PolicyCreateView(DepartmentCreateMixin, DepartmentScopedMixin, CreateView):
    model = Policy
    form_class = PolicyForm
    template_name = 'policies/policy_form.html'

    def get_initial(self):
        initial = super().get_initial()
        if self.request.user.department_id:
            initial['owner_dept'] = self.request.user.department
        initial['version'] = '1.0'
        initial['status'] = 'draft'
        return initial

    def get_success_url(self):
        return reverse_lazy('policies:detail', kwargs={'pk': self.object.pk})

    def form_valid(self, form):
        # Lock accountability to the logged-in user — not editable from the form
        form.instance.created_by = self.request.user
        form.instance.updated_by = self.request.user
        response = super().form_valid(form)
        messages.success(self.request, f'Policy {self.object.code} created.')
        return response


class PolicyUpdateView(DepartmentPinnedMixin, ChangeScopedMixin, UpdateView):
    model = Policy
    form_class = PolicyForm
    template_name = 'policies/policy_form.html'

    def get_success_url(self):
        return reverse_lazy('policies:detail', kwargs={'pk': self.object.pk})

    def form_valid(self, form):
        # updated_by tracks the last editor; created_by stays as the original creator
        form.instance.updated_by = self.request.user
        response = super().form_valid(form)
        messages.success(self.request, f'Policy {self.object.code} updated.')
        return response


class PolicyDeleteView(HODOrSuperuserMixin, ChangeScopedMixin, DeleteView):
    model = Policy
    template_name = 'core/confirm_delete.html'
    success_url = reverse_lazy('policies:list')

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['object_verbose_name'] = 'policy'
        ctx['cancel_url'] = reverse_lazy('policies:detail', kwargs={'pk': self.object.pk})
        return ctx

    def form_valid(self, form):
        label = self.object.code
        response = super().form_valid(form)
        messages.success(self.request, f'Policy {label} deleted.')
        return response


class PolicyTransitionView(ChangeScopedMixin, SingleObjectMixin, View):
    """POST-only 1-click policy lifecycle transitions."""

    model = Policy
    http_method_names = ['post']

    _ACTIONS = {
        'submit_review': ('review', False, 'submitted for review'),
        'approve': ('approved', True, 'approved'),
        'request_changes': ('draft', True, 'returned to Draft for changes'),
        'retire': ('retired', True, 'retired'),
        'reopen': ('draft', False, 'reopened as Draft'),
    }

    def post(self, request, *args, **kwargs):
        policy = self.get_object()
        action = (request.POST.get('action') or '').strip()
        if action not in self._ACTIONS:
            messages.error(request, 'Unsupported policy workflow action.')
            return redirect('policies:detail', pk=policy.pk)

        target_status, hod_only, verb = self._ACTIONS[action]
        if hod_only and not (request.user.is_superuser or request.user.is_hod):
            raise PermissionDenied('Only a department HOD or superadmin can perform this policy action.')

        if not policy.can_transition_to(target_status) or policy.status == target_status:
            messages.error(
                request,
                f'Cannot move policy {policy.code} from {policy.get_status_display()} to {dict(Policy.STATUS_CHOICES).get(target_status, target_status)}.',
            )
            return redirect('policies:detail', pk=policy.pk)

        policy.status = target_status
        policy.updated_by = request.user
        update_fields = ['status', 'updated_by', 'updated_at']
        if target_status == 'approved':
            policy.approved_by = request.user
            policy.approval_date = timezone.localdate()
            update_fields.extend(['approved_by', 'approval_date'])
        policy.save(update_fields=update_fields)
        messages.success(request, f'Policy {policy.code} {verb}.')
        return redirect('policies:detail', pk=policy.pk)