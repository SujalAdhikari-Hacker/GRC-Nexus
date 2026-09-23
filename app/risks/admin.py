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
    list_display = ('__str__', 'max_inherent_score', 'max_residual_score', 'department', 'category')
    list_filter = ('department', 'category')


class RiskTreatmentInline(admin.TabularInline):
    model = RiskTreatment
    extra = 0


@admin.register(Risk)
class RiskAdmin(SimpleHistoryAdmin):
    list_display = (
        'title', 'category', 'owner_dept', 'likelihood', 'impact',
        'inherent_score', 'residual_score', 'appetite_breached',
        'status', 'treatment_strategy'
    )
    list_filter = (
        'category', 'owner_dept', 'status', 'treatment_strategy',
        'appetite_breached', 'inherent_score'
    )
    search_fields = ('title', 'description')
    filter_horizontal = ('assets', 'controls')
    readonly_fields = (
        'inherent_score', 'residual_score', 'appetite_breached',
        'created_at', 'updated_at', 'related_risks_view',
    )
    inlines = [RiskTreatmentInline]
    date_hierarchy = 'identified_date'

    fieldsets = (
        (None, {
            'fields': ('title', 'description', 'category', 'owner_dept', 'owner_user')
        }),
        ('Scoring', {
            'fields': (
                'likelihood', 'impact', 'inherent_score',
                'residual_score', 'appetite_breached',
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
    list_display = ('risk', 'status', 'owner_user', 'due_date', 'completed_date')
    list_filter = ('status', 'due_date')
    search_fields = ('risk__title', 'action_plan')