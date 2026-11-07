from django.contrib import admin
from .models import Service

@admin.register(Service)
class ServiceAdmin(admin.ModelAdmin):
    list_display = ('name', 'organization', 'price')
    list_filter = ('organization',)
    search_fields = ('name', 'description')
