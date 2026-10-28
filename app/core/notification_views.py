from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST
from django.views import View
from django.views.generic import ListView

from .announcements import AUDIENCE_USERS, send_announcement
from .input_validation import choice
from .mixins import HODOrSuperuserMixin
from .notification_forms import NotificationComposeForm
from .notifications import Notification
from .notification_registry import refresh_notifications_throttled


def _scoped(qs, user):
    """Limit notifications to what ``user`` may see.

    A user sees their department's notifications plus anything addressed to
    them directly (a department-less user still sees their own targeted items).
    """
    from django.db.models import Q

    if user.is_superuser:
        return qs
    cond = Q(recipient=user)
    if user.department_id:
        cond |= Q(owner_dept_id=user.department_id)
    return qs.filter(cond)


class NotificationListView(LoginRequiredMixin, ListView):
    model = Notification
    template_name = 'core/notifications.html'
    context_object_name = 'notifications'
    paginate_by = 50

    def get_queryset(self):
        user = self.request.user
        # Lazy clear first — mark fixed notifications as cleared. Throttled so
        # it does not run a second time in the context processors for this
        # same request.
        refresh_notifications_throttled(
            dept=user.department,
            is_super=user.is_superuser,
        )

        qs = _scoped(Notification.objects.filter(is_cleared=False), user)

        # Filter by kind if requested
        kind = choice(
            self.request.GET.get('kind'),
            {value for value, _label in Notification.KIND_CHOICES},
            'kind', allow_blank=True,
        )
        if kind:
            qs = qs.filter(kind=kind)

        # Filter by read state
        state = choice(
            self.request.GET.get('state'), {'unread', 'read'}, 'state',
            allow_blank=True,
        )
        if state == 'unread':
            qs = qs.filter(is_read=False)
        elif state == 'read':
            qs = qs.filter(is_read=True)

        return qs.order_by('-created_at')

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        user = self.request.user

        base = _scoped(Notification.objects.filter(is_cleared=False), user)

        ctx['unread_count'] = base.filter(is_read=False).count()
        ctx['total_count'] = base.count()
        ctx['selected_kind'] = self.request.GET.get('kind', '')
        ctx['selected_state'] = self.request.GET.get('state', '')

        # NOTE: deliberately does NOT auto-mark-as-read on view. Marking is an
        # explicit action (per-item or "mark all read") so unread stays a real
        # work queue.
        return ctx


@require_POST
@login_required
def notification_dismiss(request, pk):
    n = get_object_or_404(Notification, pk=pk)
    user = request.user
    if not user.is_superuser and n.recipient_id != user.pk and n.owner_dept_id != user.department_id:
        messages.error(request, 'Not allowed.')
        return redirect('core:notifications')
    n.mark_cleared()
    messages.success(request, 'Notification dismissed.')
    return redirect('core:notifications')


@require_POST
@login_required
def notification_mark_read(request, pk):
    n = get_object_or_404(Notification, pk=pk)
    user = request.user
    if not user.is_superuser and n.recipient_id != user.pk and n.owner_dept_id != user.department_id:
        messages.error(request, 'Not allowed.')
        return redirect('core:notifications')
    n.mark_read()
    return redirect(n.action_url or 'core:notifications')


@require_POST
@login_required
def notification_mark_all_read(request):
    user = request.user
    qs = _scoped(Notification.objects.filter(is_cleared=False, is_read=False), user)
    count = qs.update(is_read=True, read_at=timezone.now())
    messages.success(request, f'{count} notification(s) marked as read.')
    return redirect('core:notifications')


class NotificationComposeView(HODOrSuperuserMixin, View):
    """Send a notification to departments or individual people.

    Superusers may address every department; a HOD is limited to their own
    department and to people inside it. The form scopes both querysets, so the
    limit is enforced before anything is written.
    """

    template_name = 'core/notification_compose.html'

    def _render(self, request, form):
        return render(request, self.template_name, {
            'form': form,
            'is_superuser': request.user.is_superuser,
            'own_department': request.user.department,
            # Keeps the matching picker open when a submission fails, even
            # before the page's script runs.
            'selected_audience': request.POST.get('audience', ''),
        })

    def get(self, request):
        user = request.user
        if not user.is_superuser and not user.department_id:
            messages.error(
                request,
                'Your account has no department, so there is nobody to notify. '
                'Ask an administrator to assign you to one.',
            )
            return redirect('core:notifications')
        return self._render(request, NotificationComposeForm(user=user))

    def post(self, request):
        user = request.user
        form = NotificationComposeForm(request.POST, user=user)
        if not form.is_valid():
            messages.error(request, 'Please fix the errors below.')
            return self._render(request, form)

        payload = form.targets()
        created = send_announcement(
            user,
            title=form.cleaned_data['title'],
            body=form.cleaned_data.get('body', ''),
            **payload,
        )

        if not created:
            messages.warning(
                request,
                'Nothing was sent — the chosen audience had no recipients.',
            )
            return redirect('core:notifications')

        noun = 'person' if payload['audience'] == AUDIENCE_USERS else 'department'
        plural = '' if len(created) == 1 else 's'
        message = f'Notification sent to {len(created)} {noun}{plural}.'
        if payload['email']:
            message += ' An email copy will go to everyone who allows email.'
        messages.success(request, message)
        return redirect('core:notifications')
