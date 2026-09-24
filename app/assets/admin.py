from django import forms
from django.contrib import admin
from django.utils.html import format_html
from django.utils import timezone
from simple_history.admin import SimpleHistoryAdmin

from .models import Asset, AssetCategory
from core.correlation import (
    get_policies_for_asset,
    get_controls_for_asset,
    get_framework_coverage_for_asset,
)


def _render_link_list(items):
    items = list(items)
    if not items:
        return format_html('<em style="color:#888;">None</em>')
    rows = ''.join(f'<li>{item}</li>' for item in items)
    return format_html(
        '<ul style="margin:0;padding-left:1.2em;">{}</ul>',
        format_html(rows)
    )


class AssetAdminForm(forms.ModelForm):
    linked_vendors = forms.ModelMultipleChoiceField(
        queryset=None,
        required=False,
        widget=forms.SelectMultiple(attrs={'class': 'admin-select-multiple', 'size': 8}),
        help_text='Vendors that supply, host, or support this asset. Selecting here updates the vendor asset list automatically.',
    )
    create_assessments_for = forms.ModelMultipleChoiceField(
        queryset=None,
        required=False,
        widget=forms.SelectMultiple(attrs={'class': 'admin-select-multiple', 'size': 8}),
        help_text='Tick vendors to auto-create a draft Vendor Assessment (status = Pending, score = 50).',
    )

    class Meta:
        model = Asset
        fields = '__all__'

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        from vendors.models import Vendor
        qs = Vendor.objects.filter(is_active=True).order_by('name')
        self.fields['linked_vendors'].queryset = qs
        self.fields['create_assessments_for'].queryset = qs
        if self.instance and self.instance.pk:
            self.fields['linked_vendors'].initial = self.instance.vendors.all()


@admin.register(AssetCategory)
class AssetCategoryAdmin(SimpleHistoryAdmin):
    list_display = ('name',)
    search_fields = ('name',)


@admin.register(Asset)
class AssetAdmin(SimpleHistoryAdmin):
    form = AssetAdminForm
    list_display = (
        'name', 'category', 'owner_dept', 'criticality',
        'cia_score', 'is_active', 'vendor_count', 'created_at'
    )
    list_filter = ('category', 'owner_dept', 'criticality', 'is_active')
    search_fields = ('name', 'description')
    filter_horizontal = ('policies',)
    readonly_fields = (
        'created_at', 'updated_at', 'cia_score',
        'correlated_risks', 'correlated_controls',
        'correlated_policies', 'correlated_frameworks',
    )

    fieldsets = (
        (None, {
            'fields': ('name', 'description', 'category', 'owner_dept', 'is_active')
        }),
        ('Risk ratings', {
            'fields': ('criticality', 'confidentiality', 'integrity', 'availability', 'value')
        }),
        ('Vendor linkage', {
            'fields': ('linked_vendors', 'create_assessments_for'),
            'description': 'Link this asset to the vendors that supply it. Ticking a vendor in the second box auto-creates a draft assessment.'
        }),
        ('Governance', {
            'fields': ('policies',)
        }),
        ('Correlated items (auto)', {
            'fields': (
                'correlated_risks', 'correlated_controls',
                'correlated_policies', 'correlated_frameworks',
            ),
            'description': 'Auto-derived from risks, controls, and policies linked to this asset.'
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at', 'cia_score'),
            'classes': ('collapse',),
        }),
    )

    def save_related(self, request, form, formsets, change):
        super().save_related(request, form, formsets, change)
        from vendors.models import Vendor, VendorAssessment

        asset = form.instance
        selected_vendors = list(form.cleaned_data.get('linked_vendors') or [])

        for vendor in Vendor.objects.filter(provides_assets=asset):
            if vendor not in selected_vendors:
                vendor.provides_assets.remove(asset)

        for vendor in selected_vendors:
            vendor.provides_assets.add(asset)

        auto_vendors = form.cleaned_data.get('create_assessments_for') or []
        for vendor in auto_vendors:
            existing = vendor.assessments.filter(
                assessment_date__year=timezone.now().year,
                status__in=['pending', 'in_review'],
            ).exists()
            if not existing:
                VendorAssessment.objects.create(
                    vendor=vendor,
                    assessment_date=timezone.now().date(),
                    score=50,
                    status='pending',
                    findings=f'Auto-created when asset "{asset.name}" was linked to this vendor on {timezone.now().date()}.',
                    assessed_by=request.user if request.user.is_authenticated else None,
                )
                self.message_user(
                    request,
                    f'Draft assessment created for vendor "{vendor.name}".',
                    level='INFO',
                )

    @admin.display(description='Vendors')
    def vendor_count(self, obj):
        return obj.vendors.count()

    @admin.display(description='Risks affecting this asset')
    def correlated_risks(self, obj):
        if not obj.pk:
            return '-'
        return _render_link_list(obj.risks.all())

    @admin.display(description='Controls (via risks)')
    def correlated_controls(self, obj):
        if not obj.pk:
            return '-'
        return _render_link_list(get_controls_for_asset(obj))

    @admin.display(description='Applicable policies')
    def correlated_policies(self, obj):
        if not obj.pk:
            return '-'
        return _render_link_list(get_policies_for_asset(obj))

    @admin.display(description='Framework coverage')
    def correlated_frameworks(self, obj):
        if not obj.pk:
            return '-'
        return _render_link_list(get_framework_coverage_for_asset(obj))
