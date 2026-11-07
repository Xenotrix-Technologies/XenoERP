from django.contrib import admin
from .models import ContentItem, ContentDropdownOption


@admin.register(ContentItem)
class ContentItemAdmin(admin.ModelAdmin):
    list_display = ('video_title', 'organization', 'client', 'editor', 'status', 'priority', 'due_date', 'created_at')
    list_filter = ('organization', 'status', 'priority')
    search_fields = ('video_title', 'notes', 'client__name', 'client__company')
    ordering = ('-due_date', '-created_at')


@admin.register(ContentDropdownOption)
class ContentDropdownOptionAdmin(admin.ModelAdmin):
    list_display = ('value', 'organization', 'category', 'display_order', 'is_active')
    list_filter = ('organization', 'category', 'is_active')
    search_fields = ('value',)
    ordering = ('organization', 'category', 'display_order', 'value')
