from django.contrib import admin
from django.utils.html import format_html
from simple_history.admin import SimpleHistoryAdmin
from .models import KRI, KRIReading


class KRIReadingInline(admin.TabularInline):
    model = KRIReading
    extra = 0
    fields = ('reading_date', 'value', 'notes', 'recorded_by')


@admin.register(KRI)
class KRIAdmin(SimpleHistoryAdmin):
    list_display = (
        'name', 'category', 'kri_type', 'current_value', 'unit',
        'rag_badge', 'amber_threshold', 'red_threshold', 'frequency',
        'trend', 'owner_dept'
    )
    list_filter = (
        'category', 'kri_type', 'direction', 'frequency',
        'trend', 'owner_dept'
    )
    search_fields = ('name', 'description')
    filter_horizontal = ('linked_risks', 'linked_appetites')
    readonly_fields = ('created_at', 'updated_at', 'rag_badge')
    inlines = [KRIReadingInline]

    fieldsets = (
        (None, {
            'fields': ('name', 'description')
        }),
        ('Classification', {
            'fields': ('category', 'kri_type', 'frequency', 'trend')
        }),
        ('Measurement', {
            'fields': ('current_value', 'unit', 'direction', 'rag_badge')
        }),
        ('Thresholds', {
            'fields': ('amber_threshold', 'red_threshold'),
            'description': 'For "higher is worse": amber < red. For "higher is better": red < amber.'
        }),
        ('Ownership', {
            'fields': ('owner_dept', 'owner_user')
        }),
        ('Links', {
            'fields': ('linked_risks', 'linked_appetites')
        }),
        ('Audit', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )

    @admin.display(description='RAG')
    def rag_badge(self, obj):
        colors = {'green': '#059669', 'amber': '#D97706', 'red': '#DC2626'}
        return format_html(
            '<span style="display:inline-block;padding:3px 10px;border-radius:10px;'
            'background:{};color:#fff;font-size:11px;font-weight:600;">{}</span>',
            colors[obj.rag_status], obj.rag_status.upper()
        )


@admin.register(KRIReading)
class KRIReadingAdmin(SimpleHistoryAdmin):
    list_display = ('kri', 'reading_date', 'value', 'recorded_by')
    list_filter = ('reading_date', 'kri__category')
    search_fields = ('kri__name', 'notes')
    date_hierarchy = 'reading_date'
