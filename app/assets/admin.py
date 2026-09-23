from django.contrib import admin
from django.utils.html import format_html
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


@admin.register(AssetCategory)
class AssetCategoryAdmin(SimpleHistoryAdmin):
    list_display = ('name',)
    search_fields = ('name',)


@admin.register(Asset)
class AssetAdmin(SimpleHistoryAdmin):
    list_display = (
        'name', 'category', 'owner_dept', 'criticality',
        'cia_score', 'is_active', 'created_at'
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

    @admin.display(description='Risks affecting this asset')
    def correlated_risks(self, obj):
        if not obj.pk:
            return '—'
        return _render_link_list(obj.risks.all())

    @admin.display(description='Controls (via risks)')
    def correlated_controls(self, obj):
        if not obj.pk:
            return '—'
        return _render_link_list(get_controls_for_asset(obj))

    @admin.display(description='Applicable policies')
    def correlated_policies(self, obj):
        if not obj.pk:
            return '—'
        return _render_link_list(get_policies_for_asset(obj))

    @admin.display(description='Framework coverage')
    def correlated_frameworks(self, obj):
        if not obj.pk:
            return '—'
        return _render_link_list(get_framework_coverage_for_asset(obj))