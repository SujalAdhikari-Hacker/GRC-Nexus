from django.contrib import admin
from django.utils.html import format_html
from simple_history.admin import SimpleHistoryAdmin

from .models import Ticket, TicketComment


class TicketCommentInline(admin.TabularInline):
    model = TicketComment
    extra = 0
    readonly_fields = ('author', 'created_at')


@admin.register(Ticket)
class TicketAdmin(SimpleHistoryAdmin):
    list_display = (
        'ticket_id', 'title', 'priority_badge', 'status_badge',
        'owner_dept', 'assigned_to', 'due_date', 'is_open_display',
    )
    list_filter = ('status', 'priority', 'source', 'owner_dept')
    search_fields = ('ticket_id', 'title', 'description')
    readonly_fields = (
        'ticket_id',
        'linked_object_display',
        'created_by', 'updated_by',
        'created_at', 'updated_at', 'resolved_at', 'closed_at',
    )
    date_hierarchy = 'created_at'
    inlines = [TicketCommentInline]

    fieldsets = (
        ('Identification', {
            'fields': ('ticket_id', 'title', 'description')
        }),
        ('Source', {
            'fields': ('source',),
            'description': 'Where this ticket came from. The linked record (if any) is shown below.'
        }),
        ('Linked record', {
            'fields': ('linked_object_display',),
            'classes': ('collapse',),
        }),
        ('Status & priority', {
            'fields': ('priority', 'status')
        }),
        ('Assignment', {
            'fields': ('owner_dept', 'assigned_to', 'assigned_by')
        }),
        ('Dates', {
            'fields': ('due_date', 'resolved_at', 'closed_at')
        }),
        ('Resolution', {
            'fields': ('resolution_notes',)
        }),
        ('Audit', {
            'fields': ('created_by', 'updated_by', 'created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )

    @admin.display(description='Priority')
    def priority_badge(self, obj):
        colors = {1: '#6B7280', 2: '#0284C7', 3: '#D97706', 4: '#DC2626'}
        return format_html(
            '<span style="display:inline-block;padding:2px 8px;border-radius:10px;'
            'background:{};color:#fff;font-size:11px;">{}</span>',
            colors.get(obj.priority, '#6B7280'), obj.get_priority_display()
        )

    @admin.display(description='Status')
    def status_badge(self, obj):
        return format_html(
            '<span style="display:inline-block;padding:2px 8px;border-radius:10px;'
            'background:{};color:#fff;font-size:11px;">{}</span>',
            obj.status_color, obj.get_status_display()
        )

    @admin.display(description='Open?', boolean=True)
    def is_open_display(self, obj):
        return obj.is_open

    @admin.display(description='Linked record')
    def linked_object_display(self, obj):
        if not obj.pk or not obj.linked_object:
            return '—'
        linked = obj.linked_object
        return format_html(
            '<strong>{}</strong> — {}',
            linked._meta.verbose_name.title(),
            str(linked)[:80]
        )


@admin.register(TicketComment)
class TicketCommentAdmin(SimpleHistoryAdmin):
    list_display = ('ticket', 'author', 'created_at')
    search_fields = ('ticket__ticket_id', 'body')
    date_hierarchy = 'created_at'