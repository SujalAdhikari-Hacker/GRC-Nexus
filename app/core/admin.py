from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import User, Department
from simple_history.admin import SimpleHistoryAdmin
from .models import OrganisationProfile

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


@admin.register(OrganisationProfile)
class OrganisationProfileAdmin(SimpleHistoryAdmin):
    list_display = ('__str__', 'executive_sponsor', 'annual_revenue', 'annual_security_budget', 'updated_at')

    fieldsets = (
        ('Governance', {
            'fields': ('executive_sponsor', 'security_committee_chair', 'last_board_report_date')
        }),
        ('Financial', {
            'fields': ('annual_revenue', 'annual_security_budget')
        }),
        ('People', {
            'fields': ('total_employees', 'security_headcount', 'grc_headcount')
        }),
        ('Narrative', {
            'fields': ('posture_statement',)
        }),
        ('Audit', {
            'fields': ('updated_at', 'updated_by'),
            'classes': ('collapse',)
        }),
    )

    def save_model(self, request, obj, form, change):
        obj.updated_by = request.user
        super().save_model(request, obj, form, change)

    def has_add_permission(self, request):
        # Prevent adding a second row
        return not OrganisationProfile.objects.exists()

    def has_delete_permission(self, request, obj=None):
        return False
