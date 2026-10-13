from django.contrib import admin
from django.utils.html import format_html
from simple_history.admin import SimpleHistoryAdmin
from .models import Audit, EvidenceItem, EvidenceScore, ControlTest, AuditFinding, ActionItem


# ============================================================
# Action items (declared first so it can be inlined)
# ============================================================

class ActionItemInline(admin.TabularInline):
    model = ActionItem
    extra = 0
    fields = ('action_id', 'title', 'priority', 'status', 'owner_user', 'due_date', 'progress_percent')
    readonly_fields = ('action_id',)
    show_change_link = True


@admin.register(ActionItem)
class ActionItemAdmin(SimpleHistoryAdmin):
    list_display = (
        'action_id', 'title', 'finding', 'priority_badge', 'status_badge',
        'owner_user', 'owner_dept', 'due_date', 'progress_percent'
    )
    list_filter = ('status', 'priority', 'owner_dept', 'due_date')
    search_fields = ('action_id', 'title', 'description', 'notes', 'finding__title')
    readonly_fields = ('action_id', 'created_at', 'updated_at')
    date_hierarchy = 'due_date'
    autocomplete_fields = ('finding',)

    fieldsets = (
        ('Identification', {
            'fields': ('action_id', 'finding', 'title', 'description')
        }),
        ('Assignment', {
            'fields': ('owner_user', 'owner_dept', 'priority')
        }),
        ('Status & dates', {
            'fields': ('status', 'progress_percent', 'due_date', 'completed_date')
        }),
        ('Notes', {
            'fields': ('notes',)
        }),
        ('Audit', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )

    @admin.display(description='Priority')
    def priority_badge(self, obj):
        colors = {1: '#6B7280', 2: '#0284C7', 3: '#D97706', 4: '#DC2626'}
        return format_html(
            '<span style="display:inline-block;padding:2px 8px;border-radius:10px;background:{};color:#fff;font-size:11px;">{}</span>',
            colors.get(obj.priority, '#6B7280'), obj.get_priority_display()
        )

    @admin.display(description='Status')
    def status_badge(self, obj):
        return format_html(
            '<span style="display:inline-block;padding:2px 8px;border-radius:10px;background:{};color:#fff;font-size:11px;">{}</span>',
            obj.status_color, obj.get_status_display()
        )


# ============================================================
# Audit + findings
# ============================================================

class AuditFindingInline(admin.TabularInline):
    model = AuditFinding
    extra = 0
    fields = ('title', 'severity', 'status', 'related_control', 'owner_user', 'due_date')
    show_change_link = True


@admin.register(Audit)
class AuditAdmin(SimpleHistoryAdmin):
    list_display = ('name', 'audit_type', 'status', 'auditor_lead', 'start_date', 'end_date', 'finding_count')
    list_filter = ('audit_type', 'status', 'owner_dept', 'frameworks')
    search_fields = ('name', 'scope', 'notes')
    filter_horizontal = ('frameworks',)
    date_hierarchy = 'start_date'
    inlines = [AuditFindingInline]


@admin.register(AuditFinding)
class AuditFindingAdmin(SimpleHistoryAdmin):
    list_display = (
        'title', 'severity', 'status', 'source',
        'related_control', 'owner_user', 'owner_dept', 'due_date', 'action_count'
    )
    list_filter = ('severity', 'status', 'source', 'owner_dept')
    search_fields = ('title', 'description', 'recommendation')
    date_hierarchy = 'due_date'
    inlines = [ActionItemInline]

    @admin.display(description='Actions')
    def action_count(self, obj):
        return obj.action_items.count()


# ============================================================
# Evidence + scoring + testing
# ============================================================

class EvidenceScoreInline(admin.StackedInline):
    model = EvidenceScore
    extra = 0
    readonly_fields = ('total_score', 'scored_at')
    fields = (
        'relevance', 'completeness', 'timeliness',
        'reliability', 'sufficiency', 'total_score',
        'assessor', 'assessor_notes'
    )


@admin.register(EvidenceItem)
class EvidenceItemAdmin(SimpleHistoryAdmin):
    list_display = ('title', 'evidence_type', 'related_control', 'owner_user', 'owner_dept', 'score_display', 'created_at')
    list_filter = ('evidence_type', 'owner_dept', 'audit')
    search_fields = ('title', 'notes', 'url_location')
    inlines = [EvidenceScoreInline]

    @admin.display(description='Score')
    def score_display(self, obj):
        s = obj.score
        if not s:
            return '—'
        return f"{s.total_score}/100 ({s.rating})"


@admin.register(EvidenceScore)
class EvidenceScoreAdmin(SimpleHistoryAdmin):
    list_display = (
        'evidence', 'relevance', 'completeness', 'timeliness',
        'reliability', 'sufficiency', 'total_score', 'rating_display', 'assessor'
    )
    list_filter = ('assessor',)
    readonly_fields = ('total_score', 'scored_at')

    @admin.display(description='Rating')
    def rating_display(self, obj):
        return obj.rating


@admin.register(ControlTest)
class ControlTestAdmin(SimpleHistoryAdmin):
    list_display = ('control', 'test_date', 'result', 'tester', 'owner_dept', 'audit')
    list_filter = ('result', 'test_date', 'owner_dept')
    search_fields = ('control__code', 'control__name', 'procedure_notes')
    date_hierarchy = 'test_date'
