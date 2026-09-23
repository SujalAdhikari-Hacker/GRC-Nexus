from django.contrib import admin
from simple_history.admin import SimpleHistoryAdmin
from .models import Vulnerability, Finding


@admin.register(Vulnerability)
class VulnerabilityAdmin(SimpleHistoryAdmin):
    list_display = ('cve_id', 'title', 'cvss_score', 'cvss_severity', 'epss_score', 'kev_status', 'published_date', 'findings_count')
    list_filter = ('cvss_severity', 'kev_status')
    search_fields = ('cve_id', 'title', 'description')
    readonly_fields = ('created_at', 'last_enriched')

    @admin.display(description='Findings')
    def findings_count(self, obj):
        return obj.findings.count()


@admin.register(Finding)
class FindingAdmin(SimpleHistoryAdmin):
    list_display = ('vulnerability', 'asset', 'owner_dept', 'status', 'composite_score', 'discovered_date', 'assigned_to')
    list_filter = ('status', 'owner_dept', 'discovered_date')
    search_fields = ('vulnerability__cve_id', 'vulnerability__title', 'asset__name', 'evidence')
    readonly_fields = ('composite_score', 'created_at', 'updated_at')
    date_hierarchy = 'discovered_date'
