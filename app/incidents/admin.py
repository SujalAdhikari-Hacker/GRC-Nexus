from django.contrib import admin
from simple_history.admin import SimpleHistoryAdmin

from .models import Incident


@admin.register(Incident)
class IncidentAdmin(SimpleHistoryAdmin):
    list_display = (
        'reference', 'title', 'incident_type', 'severity', 'status',
        'owner_dept', 'handler', 'detected_at', 'closed_at', 'nis2_significant',
    )
    list_filter = (
        'severity', 'status', 'incident_type', 'source', 'owner_dept',
        'nis2_significant',
    )
    search_fields = ('reference', 'title', 'description', 'root_cause')
    filter_horizontal = ('affected_assets', 'risks')
    readonly_fields = ('reference', 'created_at', 'updated_at', 'created_by', 'updated_by')
    date_hierarchy = 'detected_at'

    fieldsets = (
        (None, {'fields': ('reference', 'title', 'description')}),
        ('Classification', {
            'fields': ('incident_type', 'source', 'severity', 'status'),
        }),
        ('Ownership', {'fields': ('owner_dept', 'handler')}),
        ('Timeline', {
            'fields': ('detected_at', 'triaged_at', 'contained_at',
                       'resolved_at', 'closed_at'),
        }),
        ('Impact', {'fields': ('affected_assets', 'data_subjects_affected')}),
        ('Regulatory', {
            'fields': ('regulatory_notification_required', 'regulatory_notified_at'),
        }),
        ('NIS2 Article 23', {
            'fields': (
                'nis2_significant',
                'nis2_early_warning_submitted_at',
                'nis2_notification_submitted_at',
                'nis2_final_report_submitted_at',
            ),
            'description': 'Deadlines derive from the detection time: 24 h, '
                           '72 h and 30 days.',
        }),
        ('Closure record', {
            'fields': ('root_cause', 'lessons_learned'),
        }),
        ('Links', {'fields': ('risks',)}),
        ('Provenance', {
            'fields': ('created_at', 'created_by', 'updated_at', 'updated_by'),
            'classes': ('collapse',),
        }),
    )
