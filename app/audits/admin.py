from django.contrib import admin
from simple_history.admin import SimpleHistoryAdmin
from .models import Audit, EvidenceItem, EvidenceScore, ControlTest, AuditFinding


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

    fieldsets = (
        (None, {'fields': ('name', 'owner_dept')}),
        ('Classification', {'fields': ('audit_type', 'status', 'auditor_lead')}),
        ('Timeline', {'fields': ('start_date', 'end_date')}),
        ('Scope', {'fields': ('scope', 'frameworks', 'notes')}),
    )


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


@admin.register(AuditFinding)
class AuditFindingAdmin(SimpleHistoryAdmin):
    list_display = (
        'title', 'severity', 'status', 'source',
        'related_control', 'owner_user', 'owner_dept', 'due_date'
    )
    list_filter = ('severity', 'status', 'source', 'owner_dept')
    search_fields = ('title', 'description', 'recommendation')
    date_hierarchy = 'due_date'
    fieldsets = (
        (None, {'fields': ('title', 'audit', 'owner_dept')}),
        ('Classification', {'fields': ('severity', 'status', 'source')}),
        ('Linkage', {'fields': ('related_control', 'owner_user')}),
        ('Timeline', {'fields': ('due_date', 'closed_date')}),
        ('Content', {'fields': ('description', 'recommendation')}),
    )
