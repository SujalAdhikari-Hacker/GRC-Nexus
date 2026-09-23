from django.contrib import admin
from .models import Vendor, VendorAssessment
from simple_history.admin import SimpleHistoryAdmin

class VendorAssessmentInline(admin.TabularInline):
    model = VendorAssessment
    extra = 0
    readonly_fields = ('created_at',)


@admin.register(Vendor)
class VendorAdmin(SimpleHistoryAdmin):
    list_display = (
        'name', 'tier', 'data_sensitivity', 'owner_dept',
        'latest_score', 'is_active', 'contract_end'
    )
    list_filter = ('tier', 'data_sensitivity', 'owner_dept', 'is_active')
    search_fields = ('name', 'contact_name', 'contact_email')
    filter_horizontal = ('provides_assets',)
    readonly_fields = ('created_at', 'updated_at')
    inlines = [VendorAssessmentInline]


@admin.register(VendorAssessment)
class VendorAssessmentAdmin(SimpleHistoryAdmin):
    list_display = ('vendor', 'assessment_date', 'score', 'status', 'assessed_by')
    list_filter = ('status', 'assessment_date')
    search_fields = ('vendor__name', 'findings')
    date_hierarchy = 'assessment_date'