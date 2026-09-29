from django.contrib import admin
from django.utils.html import format_html
from simple_history.admin import SimpleHistoryAdmin
from .models import Vendor, VendorAssessment


class VendorAssessmentInline(admin.TabularInline):
    model = VendorAssessment
    extra = 0
    fields = ('assessment_id', 'assessment_date', 'overall_score', 'overall_risk_rating', 'status', 'assessor')
    readonly_fields = ('assessment_id', 'overall_score', 'overall_risk_rating')
    show_change_link = True


@admin.register(Vendor)
class VendorAdmin(SimpleHistoryAdmin):
    list_display = (
        'name', 'tier', 'vendor_criticality', 'data_sensitivity',
        'owner_dept', 'latest_score', 'is_active', 'contract_end'
    )
    list_filter = ('tier', 'vendor_criticality', 'data_sensitivity', 'owner_dept', 'is_active')
    search_fields = ('name', 'contact_name', 'contact_email')
    filter_horizontal = ('provides_assets',)
    readonly_fields = ('created_at', 'updated_at')
    inlines = [VendorAssessmentInline]

    fieldsets = (
        (None, {
            'fields': ('name', 'description')
        }),
        ('Classification', {
            'fields': ('tier', 'vendor_criticality', 'data_sensitivity', 'owner_dept', 'is_active')
        }),
        ('Contact', {
            'fields': ('contact_name', 'contact_email', 'contact_phone')
        }),
        ('Assets provided', {
            'fields': ('provides_assets',)
        }),
        ('Contract', {
            'fields': ('contract_start', 'contract_end')
        }),
        ('Audit', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )


@admin.register(VendorAssessment)
class VendorAssessmentAdmin(SimpleHistoryAdmin):
    list_display = (
        'assessment_id', 'vendor', 'vendor_criticality',
        'financial_risk', 'operational_risk', 'regulatory_risk',
        'cybersecurity_risk', 'reputational_risk',
        'overall_score', 'overall_risk_rating',
        'assessment_date', 'assessor'
    )
    list_filter = (
        'overall_risk_rating', 'vendor_criticality', 'status',
        'assessment_date', 'vendor__owner_dept'
    )
    search_fields = ('assessment_id', 'vendor__name', 'key_findings', 'recommended_mitigation')
    readonly_fields = ('assessment_id', 'overall_score', 'overall_risk_rating', 'created_at', 'updated_at')
    date_hierarchy = 'assessment_date'
    autocomplete_fields = ('vendor',)

    fieldsets = (
        ('Identification', {
            'fields': ('assessment_id', 'vendor', 'vendor_criticality', 'assessment_date', 'status')
        }),
        ('Risk dimensions', {
            'fields': (
                'financial_risk', 'operational_risk', 'regulatory_risk',
                'cybersecurity_risk', 'reputational_risk'
            ),
            'description': 'Each dimension: 1 = Low risk, 5 = Very Critical risk.'
        }),
        ('Overall score', {
            'fields': ('overall_score', 'overall_risk_rating'),
            'description': 'Auto-computed as the average of the 5 dimensions.'
        }),
        ('Findings & mitigation', {
            'fields': ('key_findings', 'recommended_mitigation')
        }),
        ('Schedule', {
            'fields': ('next_assessment_date', 'assessor')
        }),
        ('Audit', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
