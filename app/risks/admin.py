from django.contrib import admin
from django.utils.html import format_html
from simple_history.admin import SimpleHistoryAdmin
from .models import Risk, RiskCategory, RiskAppetite, RiskTreatment
from core.correlation import get_related_risks


@admin.register(RiskCategory)
class RiskCategoryAdmin(SimpleHistoryAdmin):
    list_display = ('name',)
    search_fields = ('name',)


@admin.register(RiskAppetite)
class RiskAppetiteAdmin(SimpleHistoryAdmin):
    list_display = (
        '__str__', 'appetite_level', 'max_inherent_score',
        'max_residual_score', 'risk_capacity',
        'board_approved', 'review_date', 'department', 'category'
    )
    list_filter = ('appetite_level', 'board_approved', 'department', 'category')
    fieldsets = (
        (None, {
            'fields': ('department', 'category')
        }),
        ('Appetite', {
            'fields': ('appetite_level', 'appetite_statement')
        }),
        ('Thresholds', {
            'fields': ('max_inherent_score', 'max_residual_score', 'risk_capacity')
        }),
        ('Governance', {
            'fields': ('board_approved', 'approved_by', 'review_date')
        }),
        ('Notes', {
            'fields': ('description',)
        }),
    )


class RiskTreatmentInline(admin.TabularInline):
    model = RiskTreatment
    extra = 0
    filter_horizontal = ('controls',)


@admin.register(Risk)
class RiskAdmin(SimpleHistoryAdmin):
    list_display = (
        'title', 'category', 'owner_dept', 'likelihood', 'impact',
        'inherent_score', 'residual_score', 'appetite_breached', 'escalated',
        'status', 'treatment_strategy'
    )
    list_filter = (
        'category', 'owner_dept', 'status', 'treatment_strategy',
        'appetite_breached', 'escalated', 'inherent_score'
    )
    search_fields = ('title', 'description', 'threat', 'vulnerability')
    filter_horizontal = ('assets', 'controls')
    readonly_fields = (
        'inherent_score', 'residual_score', 'appetite_breached',
        'created_at', 'updated_at', 'related_risks_view',
    )
    inlines = [RiskTreatmentInline]
    date_hierarchy = 'identified_date'

    fieldsets = (
        (None, {
            'fields': ('title', 'description')
        }),
        ('Risk statement', {
            'fields': ('threat', 'vulnerability', 'impact_description'),
            'description': 'Format: [Threat] exploits [Vulnerability], causing [Impact] to [Asset]'
        }),
        ('Classification', {
            'fields': ('category', 'owner_dept', 'owner_user')
        }),
        ('Scoring', {
            'fields': (
                'likelihood', 'impact', 'inherent_score',
                'residual_score', 'appetite_breached', 'escalated', 'escalated_at'
            )
        }),
        ('Treatment', {
            'fields': (
                'treatment_strategy', 'status', 'identified_date',
                'target_close_date', 'closed_date'
            )
        }),
        ('Links', {
            'fields': ('assets', 'controls')
        }),
        ('Correlated (auto)', {
            'fields': ('related_risks_view',),
            'description': 'Risks sharing at least one asset or control with this one.'
        }),
        ('Audit', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',),
        }),
    )

    @admin.display(description='Related risks')
    def related_risks_view(self, obj):
        if not obj.pk:
            return '—'
        related = get_related_risks(obj)
        if not related:
            return format_html('<em style="color:#888;">None</em>')
        rows = ''.join(
            f'<li>{r.title} <em>(inherent {r.inherent_score}, residual {r.residual_score})</em></li>'
            for r in related
        )
        return format_html(
            '<ul style="margin:0;padding-left:1.2em;">{}</ul>',
            format_html(rows)
        )


@admin.register(RiskTreatment)
class RiskTreatmentAdmin(SimpleHistoryAdmin):
    list_display = (
        'risk', 'strategy', 'status', 'owner_user',
        'due_date', 'completed_date'
    )
    list_filter = ('strategy', 'status', 'due_date')
    search_fields = ('risk__title', 'action_plan')
    filter_horizontal = ('controls',)
