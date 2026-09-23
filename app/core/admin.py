from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import User, Department
from simple_history.admin import SimpleHistoryAdmin

@admin.register(Department)
class DepartmentAdmin(SimpleHistoryAdmin):
    list_display = ('name', 'parent')
    search_fields = ('name',)


@admin.register(User)
class CustomUserAdmin(UserAdmin):
    list_display = ('username', 'email', 'department', 'is_hod', 'is_staff')
    list_filter = ('department', 'is_hod', 'is_staff')
    fieldsets = UserAdmin.fieldsets + (
        ('GRC Info', {'fields': ('department', 'is_hod')}),
    )