from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.shortcuts import get_object_or_404, redirect
from django.utils import timezone
from django.views.decorators.http import require_POST
from django.views.generic import ListView

from .notifications import Notification
from .notification_registry import refresh_notifications


class NotificationListView(LoginRequiredMixin, ListView):
    model = Notification
    template_name = 'core/notifications.html'
    context_object_name = 'notifications'
    paginate_by = 50

    def get_queryset(self):
        user = self.request.user
        # Lazy clear first — mark fixed notifications as cleared
        refresh_notifications(
            dept=user.department,
            is_super=user.is_superuser,
        )

        qs = Notification.objects.filter(is_cleared=False)
        if not user.is_superuser:
            qs = qs.filter(owner_dept=user.department)

        # Filter by kind if requested
        kind = self.request.GET.get('kind')
        if kind:
            qs = qs.filter(kind=kind)

        # Filter by read state
        state = self.request.GET.get('state')
        if state == 'unread':
            qs = qs.filter(is_read=False)
        elif state == 'read':
            qs = qs.filter(is_read=True)

        return qs.order_by('-created_at')

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        user = self.request.user

        base = Notification.objects.filter(is_cleared=False)
        if not user.is_superuser:
            base = base.filter(owner_dept=user.department)

        ctx['unread_count'] = base.filter(is_read=False).count()
        ctx['total_count'] = base.count()
        ctx['selected_kind'] = self.request.GET.get('kind', '')
        ctx['selected_state'] = self.request.GET.get('state', '')

        # Auto-mark all as read
        base.filter(is_read=False).update(is_read=True, read_at=timezone.now())

        return ctx


@require_POST
@login_required
def notification_dismiss(request, pk):
    n = get_object_or_404(Notification, pk=pk)
    user = request.user
    if not user.is_superuser and n.owner_dept_id != user.department_id:
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
    if not user.is_superuser and n.owner_dept_id != user.department_id:
        messages.error(request, 'Not allowed.')
        return redirect('core:notifications')
    n.mark_read()
    return redirect(n.action_url or 'core:notifications')


@require_POST
@login_required
def notification_mark_all_read(request):
    user = request.user
    qs = Notification.objects.filter(is_cleared=False, is_read=False)
    if not user.is_superuser:
        qs = qs.filter(owner_dept=user.department)
    count = qs.update(is_read=True, read_at=timezone.now())
    messages.success(request, f'{count} notification(s) marked as read.')
    return redirect('core:notifications')
