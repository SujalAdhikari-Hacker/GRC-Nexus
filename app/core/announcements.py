"""Compose-and-send notifications from the app.

A HOD or a superuser writes a message and picks an audience:

* **every department** (superusers only) — one row per department;
* **my department** — one row for the sender's own department;
* **specific departments** (superusers only) — one row per chosen department;
* **specific people** — one row per person, addressed to them alone.

Delivery reuses :class:`core.notifications.Notification`, so announcements show
up in the bell, on the notifications page and in the unread badge exactly like
every other alert, and are scoped by the same rules. Nothing new needs to be
added to the notification list.

Authorization is enforced twice: the form only offers departments and people the
sender may reach, and :func:`resolve_targets` re-checks the audience before any
row is written.
"""
from django.db import transaction

from .models import Department, User
from .notifications import Notification

ANNOUNCEMENT_KIND = 'announcement'

AUDIENCE_ALL = 'all'
AUDIENCE_MY_DEPARTMENT = 'my_department'
AUDIENCE_DEPARTMENTS = 'departments'
AUDIENCE_USERS = 'users'


def allowed_audiences(user):
    """Audience keys this user may pick, in display order."""
    if user.is_superuser:
        choices = [AUDIENCE_ALL]
        if user.department_id:
            choices.append(AUDIENCE_MY_DEPARTMENT)
        choices.extend([AUDIENCE_DEPARTMENTS, AUDIENCE_USERS])
        return choices
    return [AUDIENCE_MY_DEPARTMENT, AUDIENCE_USERS]


def audience_label(user, key):
    """Short label for an audience key."""
    if key == AUDIENCE_ALL:
        return 'Every department'
    if key == AUDIENCE_MY_DEPARTMENT:
        return 'My department'
    if key == AUDIENCE_DEPARTMENTS:
        return 'Specific departments'
    return 'Specific people'


def audience_description(user, key):
    """One line explaining who an audience reaches."""
    if key == AUDIENCE_ALL:
        return 'Everyone in every department.'
    if key == AUDIENCE_MY_DEPARTMENT:
        if user.department_id:
            return f'Everyone in {user.department}.'
        return 'Everyone in your department.'
    if key == AUDIENCE_DEPARTMENTS:
        return 'Tick the departments that should receive it.'
    return 'Tick the people who should receive it.'


def audience_options(user):
    """Radio options for the composer: key, label and explanation."""
    return [
        {
            'key': key,
            'label': audience_label(user, key),
            'description': audience_description(user, key),
        }
        for key in allowed_audiences(user)
    ]


def visible_departments(user):
    """Departments this user may address."""
    qs = Department.objects.order_by('name')
    if user.is_superuser:
        return qs
    if user.department_id:
        return qs.filter(pk=user.department_id)
    return qs.none()


def selectable_users(user):
    """People this user may message directly."""
    qs = User.objects.filter(is_active=True).select_related('department')
    if user.is_superuser:
        return qs.order_by('username')
    if user.department_id:
        return qs.filter(department_id=user.department_id).order_by('username')
    return qs.none()


def resolve_targets(user, audience, departments=(), users=()):
    """Return ``[(owner_dept, recipient), ...]`` for one announcement.

    ``owner_dept`` is ``None`` for a direct message so that only the named
    person sees it — a department must never be implied by the recipient.
    """
    if audience == AUDIENCE_ALL:
        if not user.is_superuser:
            raise PermissionError('Only a superuser may notify every department.')
        return [(dept, None) for dept in Department.objects.order_by('name')]

    if audience == AUDIENCE_MY_DEPARTMENT:
        if not user.department_id:
            raise ValueError('Your account has no department to notify.')
        return [(user.department, None)]

    if audience == AUDIENCE_DEPARTMENTS:
        if not user.is_superuser:
            raise PermissionError('Only a superuser may notify other departments.')
        allowed = set(
            Department.objects.values_list('pk', flat=True)
        )
        chosen = [d for d in departments if d.pk in allowed]
        return [(dept, None) for dept in chosen]

    if audience == AUDIENCE_USERS:
        reachable = set(selectable_users(user).values_list('pk', flat=True))
        return [
            (None, person)
            for person in users
            if person.pk in reachable
        ]

    raise ValueError(f'Unknown audience {audience!r}')


def send_announcement(user, title, body='', audience=AUDIENCE_MY_DEPARTMENT,
                      departments=(), users=(), email=False):
    """Create the notification rows for one announcement.

    Returns the list of created notifications. When ``email`` is true each row
    is also mailed to the people who can see it, after the transaction commits.
    """
    title = (title or '').strip()
    if not title:
        raise ValueError('An announcement needs a title.')

    pairs = resolve_targets(user, audience, departments, users)
    if not pairs:
        return []

    created = []
    with transaction.atomic():
        for owner_dept, recipient in pairs:
            created.append(Notification.objects.create(
                kind=ANNOUNCEMENT_KIND,
                owner_dept=owner_dept,
                recipient=recipient,
                title=title,
                body=(body or '').strip(),
                sent_by=user,
            ))

        if email:
            from .email_config import schedule_announcement_email
            for notification in created:
                schedule_announcement_email(notification)

    return created


def recipients_for(notification):
    """Every active user who can see ``notification``."""
    if notification.recipient_id:
        return [notification.recipient]
    if notification.owner_dept_id:
        return list(User.objects.filter(
            department_id=notification.owner_dept_id, is_active=True,
        ))
    return []
