from django.contrib import admin
from .models import (
    ClientStatus, ProjectStatus, Agreement, AgreementVersion,
    AgreementService, ClientResponsibility, Deliverable
)

class AgreementServiceInline(admin.TabularInline):
    model = AgreementService
    extra = 1

class ClientResponsibilityInline(admin.TabularInline):
    model = ClientResponsibility
    extra = 1

class DeliverableInline(admin.TabularInline):
    model = Deliverable
    extra = 1

@admin.register(Agreement)
class AgreementAdmin(admin.ModelAdmin):
    list_display = ('agreement_number', 'client_name', 'service', 'monthly_fee', 'status', 'date')
    list_filter = ('status', 'date', 'organization')
    search_fields = ('agreement_number', 'client_name', 'company_name')
    inlines = [AgreementServiceInline, DeliverableInline, ClientResponsibilityInline]

@admin.register(AgreementVersion)
class AgreementVersionAdmin(admin.ModelAdmin):
    list_display = ('agreement', 'version_number', 'created_at')

@admin.register(ClientStatus)
class ClientStatusAdmin(admin.ModelAdmin):
    list_display = ('name', 'organization', 'color', 'position')
    list_filter = ('organization',)
    search_fields = ('name',)

@admin.register(ProjectStatus)
class ProjectStatusAdmin(admin.ModelAdmin):
    list_display = ('name', 'organization', 'color', 'position')
    list_filter = ('organization',)
    search_fields = ('name',)
