from django.contrib import admin
from django.utils.html import format_html
from simple_history.admin import SimpleHistoryAdmin
from .models import Vulnerability, Finding


@admin.register(Vulnerability)
class VulnerabilityAdmin(SimpleHistoryAdmin):
    list_display = (
        'cve_id', 'title', 'cvss_score', 'cvss_severity',
        'epss_score', 'kev_status', 'source', 'published_date', 'findings_count'
    )
    list_filter = ('cvss_severity', 'kev_status', 'source')
    search_fields = ('cve_id', 'title', 'description')
    readonly_fields = ('created_at', 'last_enriched')

    @admin.display(description='Findings')
    def findings_count(self, obj):
        return obj.findings.count()


@admin.register(Finding)
class FindingAdmin(SimpleHistoryAdmin):
    list_display = (
        'vulnerability_short', 'asset', 'owner_dept', 'assigned_to',
        'assigned_team', 'status_badge', 'composite_score',
        'sla_due_date', 'is_overdue_display'
    )
    list_filter = ('status', 'owner_dept', 'assigned_team', 'discovered_date')
    search_fields = ('vulnerability__cve_id', 'vulnerability__title',
                     'asset__name', 'evidence', 'solution', 'remediation_notes')
    readonly_fields = ('composite_score', 'created_at', 'updated_at')
    date_hierarchy = 'discovered_date'
    autocomplete_fields = ('asset',)

    fieldsets = (
        ('Vulnerability', {
            'fields': ('vulnerability', 'asset', 'port')
        }),
        ('Assignment', {
            'fields': ('owner_dept', 'assigned_to', 'assigned_team')
        }),
        ('Workflow', {
            'fields': ('status', 'discovered_date', 'sla_due_date',
                       'remediated_date', 'verified_date')
        }),
        ('Evidence & solution', {
            'fields': ('evidence', 'solution', 'remediation_notes')
        }),
        ('Scoring', {
            'fields': ('composite_score',),
        }),
        ('Audit', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',),
        }),
    )

    @admin.display(description='Vulnerability')
    def vulnerability_short(self, obj):
        return str(obj.vulnerability)[:60]

    @admin.display(description='Status')
    def status_badge(self, obj):
        return format_html(
            '<span style="display:inline-block;padding:2px 8px;border-radius:10px;'
            'background:{};color:#fff;font-size:11px;">{}</span>',
            obj.status_color, obj.get_status_display()
        )

    @admin.display(description='Overdue')
    def is_overdue_display(self, obj):
        if obj.is_overdue:
            return format_html('<span style="color:#DC2626;font-weight:700;">OVERDUE</span>')
        if obj.is_due_soon:
            return format_html('<span style="color:#D97706;font-weight:600;">Due soon</span>')
        return '—'
