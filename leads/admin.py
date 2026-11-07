from django.contrib import admin
from .models import Lead, LeadStatus

@admin.register(Lead)
class LeadAdmin(admin.ModelAdmin):
    list_display = ('name', 'company', 'score', 'status', 'stage', 'value', 'organization', 'owner')
    list_filter = ('status', 'stage', 'organization')
    search_fields = ('name', 'company', 'email')

@admin.register(LeadStatus)
class LeadStatusAdmin(admin.ModelAdmin):
    list_display = ('name', 'organization', 'color', 'position', 'is_default')
    list_filter = ('organization', 'color', 'is_default')
    search_fields = ('name',)
