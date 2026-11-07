from django.contrib import admin
from .models import (
    CalendarStatus, Activity, WhatsAppMessage, Task, TaskTodo,
    TaskFile, TaskMilestone, TaskComment, Meeting, Event
)

@admin.register(Activity)
class ActivityAdmin(admin.ModelAdmin):
    list_display = ('lead', 'type', 'timestamp', 'description')
    list_filter = ('type', 'timestamp')
    search_fields = ('lead__name', 'description')

@admin.register(Task)
class TaskAdmin(admin.ModelAdmin):
    list_display = ('title', 'lead', 'due_date', 'priority', 'completed')
    list_filter = ('priority', 'completed', 'due_date')
    search_fields = ('title', 'description', 'lead__name')

@admin.register(Meeting)
class MeetingAdmin(admin.ModelAdmin):
    list_display = ('title', 'organization', 'lead', 'date_time', 'location')
    list_filter = ('date_time', 'location')
    search_fields = ('title', 'lead__name')

@admin.register(Event)
class EventAdmin(admin.ModelAdmin):
    list_display = ('title', 'organization', 'start_time', 'end_time', 'recurring')
    list_filter = ('recurring', 'start_time')
    search_fields = ('title', 'description')

@admin.register(CalendarStatus)
class CalendarStatusAdmin(admin.ModelAdmin):
    list_display = ('name', 'organization', 'color', 'position')
    list_filter = ('organization',)
    search_fields = ('name',)

@admin.register(WhatsAppMessage)
class WhatsAppMessageAdmin(admin.ModelAdmin):
    list_display = ('recipient_phone', 'organization', 'status', 'sent_at')
    list_filter = ('status', 'sent_at')
    search_fields = ('recipient_phone', 'message_content')
