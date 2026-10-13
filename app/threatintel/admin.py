from django.contrib import admin
from django.utils.html import format_html
from simple_history.admin import SimpleHistoryAdmin
from .models import Tactic, Technique, ThreatActor, IOC, IOCFeedSync


@admin.register(Tactic)
class TacticAdmin(SimpleHistoryAdmin):
    list_display = ('attack_id', 'name', 'shortname', 'order', 'technique_count')
    search_fields = ('attack_id', 'name', 'shortname')
    ordering = ('order',)

    @admin.display(description='Techniques')
    def technique_count(self, obj):
        return obj.techniques.count()


@admin.register(Technique)
class TechniqueAdmin(SimpleHistoryAdmin):
    list_display = ('attack_id', 'name', 'is_subtechnique', 'parent', 'platforms_display', 'deprecated')
    list_filter = ('is_subtechnique', 'deprecated', 'tactics')
    search_fields = ('attack_id', 'name', 'description')
    filter_horizontal = ('tactics',)
    readonly_fields = ('stix_id',)

    @admin.display(description='Platforms')
    def platforms_display(self, obj):
        return ', '.join(obj.platforms or [])[:80]


@admin.register(ThreatActor)
class ThreatActorAdmin(SimpleHistoryAdmin):
    list_display = ('name', 'attack_id', 'aliases_display', 'technique_count')
    search_fields = ('name', 'attack_id', 'description')
    filter_horizontal = ('techniques',)

    @admin.display(description='Aliases')
    def aliases_display(self, obj):
        return ', '.join((obj.aliases or [])[:5])

    @admin.display(description='Techniques')
    def technique_count(self, obj):
        return obj.techniques.count()


@admin.register(IOC)
class IOCAdmin(SimpleHistoryAdmin):
    list_display = (
        'value_short', 'ioc_type', 'threat_type_badge', 'confidence_badge',
        'source', 'malware_family', 'first_seen', 'is_active'
    )
    list_filter = ('ioc_type', 'threat_type', 'confidence', 'source', 'is_active', 'is_whitelisted')
    search_fields = ('value', 'malware_family', 'source_id', 'notes')
    filter_horizontal = ('techniques', 'related_cves')
    readonly_fields = ('created_at', 'updated_at')
    date_hierarchy = 'first_seen'

    fieldsets = (
        ('Indicator', {
            'fields': ('value', 'ioc_type', 'threat_type', 'confidence')
        }),
        ('Attribution', {
            'fields': ('malware_family', 'threat_actor', 'techniques', 'related_cves')
        }),
        ('Source', {
            'fields': ('source', 'source_id', 'first_seen', 'last_seen', 'tags')
        }),
        ('Status', {
            'fields': ('is_active', 'is_whitelisted', 'notes')
        }),
        ('Audit', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )

    @admin.display(description='Value')
    def value_short(self, obj):
        return obj.value[:60]

    @admin.display(description='Threat')
    def threat_type_badge(self, obj):
        return format_html(
            '<span style="display:inline-block;padding:2px 8px;border-radius:10px;'
            'background:{};color:#fff;font-size:11px;">{}</span>',
            obj.threat_type_color, obj.get_threat_type_display()
        )

    @admin.display(description='Confidence')
    def confidence_badge(self, obj):
        return format_html(
            '<span style="display:inline-block;padding:2px 8px;border-radius:10px;'
            'background:{};color:#fff;font-size:11px;">{}</span>',
            obj.confidence_color, obj.get_confidence_display()
        )


@admin.register(IOCFeedSync)
class IOCFeedSyncAdmin(SimpleHistoryAdmin):
    list_display = (
        'source', 'started_at', 'finished_at', 'status',
        'items_fetched', 'items_created', 'items_updated', 'items_skipped'
    )
    list_filter = ('source', 'status')
    readonly_fields = ('started_at', 'finished_at')
