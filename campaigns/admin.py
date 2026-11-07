from django.contrib import admin
from .models import Campaign, CampaignStatus


@admin.register(CampaignStatus)
class CampaignStatusAdmin(admin.ModelAdmin):
    list_display = ('name', 'organization', 'color', 'position')
    list_filter = ('organization',)
    search_fields = ('name',)
    ordering = ('organization', 'position', 'id')


@admin.register(Campaign)
class CampaignAdmin(admin.ModelAdmin):
    list_display = ('name', 'organization', 'status', 'is_active', 'platform', 'spend', 'budget', 'results_count', 'created_at')
    list_filter = ('organization', 'status', 'is_active', 'platform')
    search_fields = ('name', 'cost_center')
    ordering = ('-created_at',)
