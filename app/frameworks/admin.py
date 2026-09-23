from django.contrib import admin
from .models import Framework, FrameworkControl
from simple_history.admin import SimpleHistoryAdmin

class FrameworkControlInline(admin.TabularInline):
    model = FrameworkControl
    extra = 0


@admin.register(Framework)
class FrameworkAdmin(SimpleHistoryAdmin):
    list_display = ('name', 'version', 'created_at')
    search_fields = ('name',)
    inlines = [FrameworkControlInline]


@admin.register(FrameworkControl)
class FrameworkControlAdmin(SimpleHistoryAdmin):
    list_display = ('framework', 'code', 'title')
    list_filter = ('framework',)
    search_fields = ('code', 'title')