from django.urls import path
from .views import (
    DashboardView, global_search,
    UserListView, UserCreateView, UserUpdateView,
    DepartmentListView, DepartmentCreateView, DepartmentUpdateView,
    RolesPermissionsView,
    ExecutiveReportView,
)

app_name = 'core'

urlpatterns = [
    path('', DashboardView.as_view(), name='dashboard'),
    path('search/', global_search, name='search'),

    path('reports/executive/', ExecutiveReportView.as_view(), name='executive_report'),

    path('admin-ui/users/', UserListView.as_view(), name='users_list'),
    path('admin-ui/users/new/', UserCreateView.as_view(), name='user_create'),
    path('admin-ui/users/<int:pk>/edit/', UserUpdateView.as_view(), name='user_update'),

    path('admin-ui/departments/', DepartmentListView.as_view(), name='departments_list'),
    path('admin-ui/departments/new/', DepartmentCreateView.as_view(), name='department_create'),
    path('admin-ui/departments/<int:pk>/edit/', DepartmentUpdateView.as_view(), name='department_update'),

    path('admin-ui/roles/', RolesPermissionsView.as_view(), name='roles_permissions'),
]
