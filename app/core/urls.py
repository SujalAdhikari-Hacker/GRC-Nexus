from django.urls import path, re_path
from .settings_views import settings_view, send_test_email
from .media import download_media
from .object_views import share_object, saved_view_save, saved_view_delete
from .notification_views import (
    NotificationListView, notification_dismiss,
    notification_mark_read, notification_mark_all_read,
)
from .views import (
    DashboardView, global_search,
    UserListView, UserCreateView, UserUpdateView,
    DepartmentListView, DepartmentCreateView, DepartmentUpdateView,
    RolesPermissionsView,
    ExecutiveReportView,
)
from .history_views import HistoryListView

app_name = 'core'

urlpatterns = [
    path('', DashboardView.as_view(), name='dashboard'),
    path('search/', global_search, name='search'),

    # Authorised media downloads (evidence, policy documents). Replaces raw
    # /media/ serving so files are department-scoped.
    re_path(r'^media/(?P<path>.+)$', download_media, name='secure_media'),

    path('reports/executive/', ExecutiveReportView.as_view(), name='executive_report'),

    path('admin-ui/users/', UserListView.as_view(), name='users_list'),
    path('admin-ui/users/new/', UserCreateView.as_view(), name='user_create'),
    path('admin-ui/users/<int:pk>/edit/', UserUpdateView.as_view(), name='user_update'),

    path('admin-ui/departments/', DepartmentListView.as_view(), name='departments_list'),
    path('admin-ui/departments/new/', DepartmentCreateView.as_view(), name='department_create'),
    path('admin-ui/departments/<int:pk>/edit/', DepartmentUpdateView.as_view(), name='department_update'),

    path('admin-ui/roles/', RolesPermissionsView.as_view(), name='roles_permissions'),

    # Notifications
    path('notifications/', NotificationListView.as_view(), name='notifications'),
    path('notifications/<int:pk>/dismiss/', notification_dismiss, name='notification_dismiss'),
    path('notifications/<int:pk>/read/', notification_mark_read, name='notification_mark_read'),
    path('notifications/mark-all-read/', notification_mark_all_read, name='notification_mark_all_read'),
    path('settings/', settings_view, name='settings'),
    path('settings/test-email/', send_test_email, name='send_test_email'),
    path('history/', HistoryListView.as_view(), name='history'),

    # Object-level sharing (django-guardian)
    path(
        'share/<str:app_label>/<str:model_name>/<int:pk>/',
        share_object, name='object_share',
    ),

    # Per-user saved list views
    path('views/save/', saved_view_save, name='saved_view_save'),
    path('views/<int:pk>/delete/', saved_view_delete, name='saved_view_delete'),
]
