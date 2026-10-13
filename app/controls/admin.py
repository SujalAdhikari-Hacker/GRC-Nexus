from django.contrib import admin
from simple_history.admin import SimpleHistoryAdmin
from .models import Control, ControlEvidence, ControlFrameworkMapping


class ControlEvidenceInline(admin.TabularInline):
    model = ControlEvidence
    extra = 0
    readonly_fields = ('uploaded_at',)


class ControlFrameworkMappingInline(admin.TabularInline):
    model = ControlFrameworkMapping
    extra = 0
    autocomplete_fields = ('framework_control',)


@admin.register(Control)
class ControlAdmin(SimpleHistoryAdmin):
    list_display = (
        'code', 'name', 'control_type', 'category',
        'lifecycle_status', 'effectiveness_rating', 'frequency',
        'owner_dept', 'primary_framework', 'is_shared'
    )
    list_filter = (
        'control_type', 'category', 'status', 'lifecycle_status',
        'effectiveness_rating', 'frequency', 'owner_dept', 'is_shared',
        'primary_framework'
    )
    search_fields = ('code', 'name', 'description', 'reference')
    filter_horizontal = ('framework_controls',)
    readonly_fields = ('created_at', 'updated_at', 'effectiveness')
    inlines = [ControlFrameworkMappingInline, ControlEvidenceInline]

    fieldsets = (
        (None, {
            'fields': ('name', 'code', 'description')
        }),
        ('Classification', {
            'fields': ('control_type', 'category', 'frequency')
        }),
        ('Lifecycle & effectiveness', {
            'fields': ('status', 'lifecycle_status', 'effectiveness_rating', 'effectiveness')
        }),
        ('Framework', {
            'fields': ('primary_framework', 'reference', 'framework_controls')
        }),
        ('Ownership', {
            'fields': ('owner_dept', 'owner_user', 'is_shared')
        }),
        ('Testing', {
            'fields': ('last_tested', 'next_test_date', 'implementation_notes')
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )


@admin.register(ControlEvidence)
class ControlEvidenceAdmin(SimpleHistoryAdmin):
    list_display = ('control', 'description', 'uploaded_by', 'uploaded_at')
    list_filter = ('uploaded_at',)


@admin.register(ControlFrameworkMapping)
class ControlFrameworkMappingAdmin(SimpleHistoryAdmin):
    list_display = ('control', 'framework_control', 'relationship')
    list_filter = ('relationship', 'framework_control__framework')
    search_fields = ('control__code', 'framework_control__code', 'framework_control__title')
    autocomplete_fields = ('control', 'framework_control')
