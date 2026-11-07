from django.contrib import admin
from .models import Ticket, TicketStatus, PriorityStatus

@admin.register(Ticket)
class TicketAdmin(admin.ModelAdmin):
    list_display = ('ticket_id', 'subject', 'priority', 'status', 'assignee', 'organization', 'created_at')
    list_filter = ('priority', 'status', 'organization')
    search_fields = ('ticket_id', 'subject', 'description')

@admin.register(TicketStatus)
class TicketStatusAdmin(admin.ModelAdmin):
    list_display = ('name', 'organization', 'color', 'position')
    list_filter = ('organization',)
    search_fields = ('name',)

@admin.register(PriorityStatus)
class PriorityStatusAdmin(admin.ModelAdmin):
    list_display = ('name', 'organization', 'color', 'position')
    list_filter = ('organization',)
    search_fields = ('name',)
