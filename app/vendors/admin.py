from django.contrib import admin
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
        'vendor_id', 'name', 'service', 'tier', 'data_sensitivity',
        'status', 'owner_dept', 'latest_score', 'contract_renewal_date'
    )
    list_filter = ('service', 'tier', 'data_sensitivity', 'status', 'owner_dept')
    search_fields = ('vendor_id', 'name', 'contact_name', 'contact_email', 'notes')
    filter_horizontal = ('compliance_attestations', 'provides_assets')
    readonly_fields = ('vendor_id', 'created_at', 'updated_at')
    inlines = [VendorAssessmentInline]

    fieldsets = (
        ('Identification', {
            'fields': ('vendor_id', 'name', 'description')
        }),
        ('Classification', {
            'fields': ('service', 'tier', 'data_sensitivity', 'status')
        }),
        ('Ownership', {
            'fields': ('owner_dept', 'owner_user')
        }),
        ('Contact', {
            'fields': ('contact_name', 'contact_email', 'contact_phone')
        }),
        ('Contract', {
            'fields': ('contract_start', 'contract_renewal_date')
        }),
        ('Compliance', {
            'fields': ('compliance_attestations', 'compliance_notes'),
            'description': 'Which frameworks has this vendor attested to?'
        }),
        ('Assets provided', {
            'fields': ('provides_assets',)
        }),
        ('Notes', {
            'fields': ('notes',)
        }),
        ('Audit', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )


@admin.register(VendorAssessment)
class VendorAssessmentAdmin(SimpleHistoryAdmin):
    list_display = (
        'assessment_id', 'vendor', 'vendor_tier',
        'security_score', 'compliance_score', 'financial_score',
        'reputation_score', 'operational_score',
        'overall_score', 'overall_risk_rating',
        'assessment_date', 'assessor'
    )
    list_filter = (
        'overall_risk_rating', 'vendor_tier', 'status',
        'assessment_date', 'vendor__owner_dept'
    )
    search_fields = ('assessment_id', 'vendor__name', 'key_findings', 'recommended_mitigation')
    readonly_fields = ('assessment_id', 'overall_score', 'overall_risk_rating', 'created_at', 'updated_at')
    date_hierarchy = 'assessment_date'
    autocomplete_fields = ('vendor',)

    fieldsets = (
        ('Identification', {
            'fields': ('assessment_id', 'vendor', 'vendor_tier', 'assessment_date', 'status')
        }),
        ('Risk dimensions', {
            'fields': (
                'security_score', 'compliance_score', 'financial_score',
                'reputation_score', 'operational_score',
            ),
            'description': 'Each dimension 0-25. Total score = sum (0-100).'
        }),
        ('Computed', {
            'fields': ('overall_score', 'overall_risk_rating')
        }),
        ('Findings', {
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