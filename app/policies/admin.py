from django.contrib import admin
from .models import Policy, PolicyCategory
from simple_history.admin import SimpleHistoryAdmin

@admin.register(PolicyCategory)
class PolicyCategoryAdmin(SimpleHistoryAdmin):
    list_display = ('name',)
    search_fields = ('name',)


@admin.register(Policy)
class PolicyAdmin(SimpleHistoryAdmin):
    list_display = (
        'code', 'title', 'category', 'version', 'status',
        'owner_dept', 'approval_date', 'next_review_date',
        'created_by', 'updated_by'
    )
    list_filter = ('status', 'category', 'owner_dept')
    search_fields = ('code', 'title', 'description')
    filter_horizontal = ('applies_to_departments',)
    readonly_fields = ('created_at', 'updated_at', 'created_by', 'updated_by')
    date_hierarchy = 'approval_date'