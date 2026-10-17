from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import PermissionDenied
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse_lazy
from django.views.decorators.http import require_POST
from django.views.generic import (
    CreateView,
    DetailView,
    ListView,
    UpdateView,
)

from core.mixins import (
    DepartmentCreateMixin,
    DepartmentScopedMixin,
    HODOrSuperuserMixin,
    scope_queryset,
    user_can_access,
)
from core.models import User

from .forms import TicketCommentForm, TicketForm
from .models import Ticket


def _get_ticket_or_403(request, pk):
    """Fetch a ticket and enforce object-level access for the requester."""
    ticket = get_object_or_404(Ticket, pk=pk)
    if not user_can_access(request.user, ticket):
        raise PermissionDenied
    return ticket


# ==================================================================
# TICKET LIST — department-scoped, filterable
# ==================================================================

class TicketListView(DepartmentScopedMixin, ListView):
    model = Ticket
    template_name = 'tickets/ticket_list.html'
    context_object_name = 'tickets'
    paginate_by = 25
    department_field = 'owner_dept'

    def get_queryset(self):
        qs = super().get_queryset().select_related(
            'owner_dept', 'assigned_to', 'assigned_by'
        )
        q = self.request.GET.get('q', '').strip()
        if q:
            qs = qs.filter(
                Q(ticket_id__icontains=q) |
                Q(title__icontains=q) |
                Q(description__icontains=q)
            )
        status = self.request.GET.get('status')
        if status:
            qs = qs.filter(status=status)
        priority = self.request.GET.get('priority')
        if priority:
            qs = qs.filter(priority=priority)
        source = self.request.GET.get('source')
        if source:
            qs = qs.filter(source=source)
        assigned = self.request.GET.get('assigned')
        if assigned == 'me':
            qs = qs.filter(assigned_to=self.request.user)
        elif assigned == 'unassigned':
            qs = qs.filter(assigned_to__isnull=True)
        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        all_tickets = list(self.get_queryset())
        user = self.request.user
        ctx['statuses'] = Ticket.STATUS_CHOICES
        ctx['priorities'] = Ticket.PRIORITY_CHOICES
        ctx['sources'] = Ticket.SOURCE_CHOICES
        ctx['search_query'] = self.request.GET.get('q', '')
        ctx['selected_status'] = self.request.GET.get('status', '')
        ctx['selected_priority'] = self.request.GET.get('priority', '')
        ctx['selected_source'] = self.request.GET.get('source', '')
        ctx['selected_assigned'] = self.request.GET.get('assigned', '')
        ctx['total_count'] = len(all_tickets)
        ctx['open_count'] = sum(1 for t in all_tickets if t.is_open)
        ctx['unassigned_count'] = sum(1 for t in all_tickets if t.is_open and not t.assigned_to_id)
        ctx['overdue_count'] = sum(1 for t in all_tickets if t.is_overdue)
        ctx['my_count'] = sum(1 for t in all_tickets if t.assigned_to_id == user.pk and t.is_open)
        return ctx


# ==================================================================
# MY TICKETS
# ==================================================================

class MyTicketsView(LoginRequiredMixin, ListView):
    model = Ticket
    template_name = 'tickets/my_tickets.html'
    context_object_name = 'tickets'
    paginate_by = 25

    def get_queryset(self):
        return Ticket.objects.filter(
            assigned_to=self.request.user
        ).select_related('owner_dept', 'assigned_by')

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        all_mine = list(self.get_queryset())
        ctx['total_count'] = len(all_mine)
        ctx['open_count'] = sum(1 for t in all_mine if t.is_open)
        ctx['overdue_count'] = sum(1 for t in all_mine if t.is_overdue)
        ctx['resolved_count'] = sum(1 for t in all_mine if t.status in ('resolved', 'closed'))
        return ctx


# ==================================================================
# AVAILABLE QUEUE — unassigned tickets I can work on
# ==================================================================

class AvailableTicketsView(LoginRequiredMixin, ListView):
    model = Ticket
    template_name = 'tickets/available_tickets.html'
    context_object_name = 'tickets'
    paginate_by = 25

    def get_queryset(self):
        qs = scope_queryset(
            Ticket.objects.filter(assigned_to__isnull=True, status='open'),
            self.request.user,
        ).select_related('owner_dept')
        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['total_count'] = self.get_queryset().count()
        return ctx


# ==================================================================
# TICKET DETAIL
# ==================================================================

class TicketDetailView(DepartmentScopedMixin, DetailView):
    model = Ticket
    template_name = 'tickets/ticket_detail.html'
    context_object_name = 'ticket'
    department_field = 'owner_dept'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['comments'] = self.object.comments.select_related('author').order_by('created_at')
        ctx['comment_form'] = TicketCommentForm()
        return ctx


# ==================================================================
# CREATE / EDIT
# ==================================================================

class TicketCreateView(DepartmentCreateMixin, HODOrSuperuserMixin, CreateView):
    model = Ticket
    form_class = TicketForm
    template_name = 'tickets/ticket_form.html'

    def get_initial(self):
        initial = super().get_initial()
        if self.request.user.department_id:
            initial['owner_dept'] = self.request.user.department
        return initial

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['user'] = self.request.user
        return kwargs

    def form_valid(self, form):
        if not self.request.user.is_superuser:
            form.instance.owner_dept = self.request.user.department
        form.instance.created_by = self.request.user
        form.instance.updated_by = self.request.user
        form.apply_link(form.instance)
        response = super().form_valid(form)
        messages.success(self.request, f'Ticket {self.object.ticket_id} created.')
        return response

    def get_success_url(self):
        return reverse_lazy('tickets:detail', kwargs={'pk': self.object.pk})


class TicketUpdateView(DepartmentScopedMixin, UpdateView):
    model = Ticket
    form_class = TicketForm
    template_name = 'tickets/ticket_form.html'
    department_field = 'owner_dept'

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['user'] = self.request.user
        return kwargs

    def form_valid(self, form):
        form.instance.updated_by = self.request.user
        form.apply_link(form.instance)
        response = super().form_valid(form)
        messages.success(self.request, f'Ticket {self.object.ticket_id} updated.')
        return response

    def get_success_url(self):
        return reverse_lazy('tickets:detail', kwargs={'pk': self.object.pk})


# ==================================================================
# ACTIONS — claim, assign, status, comment
# ==================================================================

@login_required
@require_POST
def ticket_claim(request, pk):
    """User claims an unassigned ticket for themselves."""
    ticket = _get_ticket_or_403(request, pk)

    if ticket.assigned_to_id:
        messages.warning(request, f'{ticket.ticket_id} is already assigned to {ticket.assigned_to}.')
        return redirect('tickets:detail', pk=pk)

    ticket.assigned_to = request.user
    ticket.assigned_by = request.user
    ticket.status = 'assigned'
    ticket.updated_by = request.user
    ticket.save()

    messages.success(request, f'{ticket.ticket_id} claimed by you.')
    return redirect('tickets:detail', pk=pk)


@login_required
@require_POST
def ticket_assign(request, pk):
    """HOD/admin assigns a ticket to a specific user."""
    if not (request.user.is_superuser or request.user.is_hod):
        raise PermissionDenied
    ticket = _get_ticket_or_403(request, pk)

    user_id = request.POST.get('assigned_to')
    if not user_id:
        messages.error(request, 'Please choose a user to assign.')
        return redirect('tickets:detail', pk=pk)

    try:
        assignee = User.objects.get(pk=user_id)
    except (User.DoesNotExist, ValueError):
        messages.error(request, 'User not found.')
        return redirect('tickets:detail', pk=pk)

    # A department head may only assign within their own department (and to
    # themselves); only a superuser can cross department boundaries.
    if not request.user.is_superuser:
        dept_id = request.user.department_id
        if assignee.department_id != dept_id:
            messages.error(request, 'You can only assign tickets within your department.')
            return redirect('tickets:detail', pk=pk)

    ticket.assigned_to = assignee
    ticket.assigned_by = request.user
    if ticket.status == 'open':
        ticket.status = 'assigned'
    ticket.updated_by = request.user
    ticket.save()

    messages.success(request, f'{ticket.ticket_id} assigned to {assignee.username}.')
    return redirect('tickets:detail', pk=pk)


@login_required
@require_POST
def ticket_update_status(request, pk):
    """Quick inline status update."""
    ticket = _get_ticket_or_403(request, pk)
    new_status = request.POST.get('status')

    valid = [s[0] for s in Ticket.STATUS_CHOICES]
    if new_status in valid:
        ticket.status = new_status
        ticket.updated_by = request.user

        resolution = request.POST.get('resolution_notes', '').strip()
        if resolution:
            ticket.resolution_notes = resolution

        ticket.save()
        messages.success(request, f'{ticket.ticket_id} status → {ticket.get_status_display()}.')
    else:
        messages.error(request, 'Invalid status.')

    return redirect('tickets:detail', pk=pk)


@login_required
@require_POST
def ticket_add_comment(request, pk):
    ticket = _get_ticket_or_403(request, pk)
    form = TicketCommentForm(request.POST)

    if form.is_valid():
        comment = form.save(commit=False)
        comment.ticket = ticket
        comment.author = request.user
        comment.save()
        messages.success(request, 'Comment added.')
    else:
        messages.error(request, 'Comment cannot be empty.')

    return redirect('tickets:detail', pk=pk)
