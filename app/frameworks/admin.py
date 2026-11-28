from django.contrib import admin
from .models import Framework, FrameworkControl
from simple_history.admin import SimpleHistoryAdmin

class FrameworkControlInline(admin.TabularInline):
    model = FrameworkControl
    extra = 0


@admin.register(Framework)
class FrameworkAdmin(SimpleHistoryAdmin):
    list_display = ('name', 'version', 'created_at')
    search_fields = ('name',)
    inlines = [FrameworkControlInline]


@admin.register(FrameworkControl)
class FrameworkControlAdmin(SimpleHistoryAdmin):
    list_display = ('framework', 'code', 'title')
    list_filter = ('framework',)
    search_fields = ('code', 'title')
from .models import ComplianceAssessment, ComplianceAssessmentItem


class ComplianceAssessmentItemInline(admin.TabularInline):
    model = ComplianceAssessmentItem
    extra = 0
    fields = ('framework_control', 'status', 'owner_user', 'target_remediation_date')
    readonly_fields = ('framework_control',)
    show_change_link = True


@admin.register(ComplianceAssessment)
class ComplianceAssessmentAdmin(SimpleHistoryAdmin):
    list_display = (
        'assessment_id', 'name', 'framework', 'status',
        'assessor', 'assessment_date', 'readiness_display'
    )
    list_filter = ('status', 'framework', 'owner_dept', 'assessment_date')
    search_fields = ('assessment_id', 'name', 'description', 'notes')
    readonly_fields = ('assessment_id', 'created_at', 'updated_at', 'readiness_display')
    date_hierarchy = 'assessment_date'
    inlines = [ComplianceAssessmentItemInline]

    fieldsets = (
        ('Identification', {
            'fields': ('assessment_id', 'name', 'framework', 'status')
        }),
        ('Details', {
            'fields': ('description', 'owner_dept', 'assessor')
        }),
        ('Dates', {
            'fields': ('assessment_date', 'target_completion_date', 'completed_date')
        }),
        ('Progress', {
            'fields': ('readiness_display',)
        }),
        ('Notes', {
            'fields': ('notes',)
        }),
        ('Audit', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )

    @admin.display(description='Readiness')
    def readiness_display(self, obj):
        if not obj.pk:
            return '—'
        pct = f'{obj.readiness_percent}%' if obj.readiness_percent is not None else 'N/A'
        return f'{pct} ({obj.compliant_count}✓ {obj.partial_count}~ {obj.non_compliant_count}✗)'


@admin.register(ComplianceAssessmentItem)
class ComplianceAssessmentItemAdmin(SimpleHistoryAdmin):
    list_display = ('assessment', 'framework_control', 'status', 'owner_user', 'target_remediation_date')
    list_filter = ('status', 'assessment', 'assessment__framework')
    search_fields = ('assessment__name', 'framework_control__code', 'notes')
    autocomplete_fields = ('framework_control',)
