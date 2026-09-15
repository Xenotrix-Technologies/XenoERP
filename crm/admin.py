from django.contrib import admin
from .models import Organization, UserProfile, Lead, Activity, Task, Meeting

@admin.register(Organization)
class OrganizationAdmin(admin.ModelAdmin):
    list_display = ('id', 'name', 'created_at')
    search_fields = ('name',)

@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    list_display = ('user', 'organization', 'role')
    search_fields = ('user__username', 'user__first_name', 'user__last_name', 'role')

@admin.register(Lead)
class LeadAdmin(admin.ModelAdmin):
    list_display = ('name', 'company', 'score', 'status', 'stage', 'value', 'organization', 'owner')
    list_filter = ('status', 'stage', 'organization')
    search_fields = ('name', 'company', 'email')

@admin.register(Activity)
class ActivityAdmin(admin.ModelAdmin):
    list_display = ('lead', 'type', 'timestamp', 'description')
    list_filter = ('type', 'timestamp')
    search_fields = ('lead__name', 'description')

@admin.register(Task)
class TaskAdmin(admin.ModelAdmin):
    list_display = ('description', 'lead', 'due_date', 'priority', 'completed')
    list_filter = ('priority', 'completed', 'due_date')
    search_fields = ('description', 'lead__name')

@admin.register(Meeting)
class MeetingAdmin(admin.ModelAdmin):
    list_display = ('title', 'organization', 'lead', 'date_time', 'location')
    list_filter = ('date_time', 'location')
    search_fields = ('title', 'lead__name')


from .models import Agreement, AgreementService, ClientResponsibility, Deliverable

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

from .models import (
    Income, Expense, PartnerPayout, DeletedIncome, DeletedExpense,
    FinancePaymentMethod, FinanceExpenseCategory, FinancePaymentStatus, FinanceCommissionType,
    DocumentSettings, Quotation, QuotationSection, QuotationItem, QuotationPackage, QuotationDomainOption,
    QuotationPaymentStage, QuotationTerm, QuotationExclusion, QuotationActivity, QuotationVersion,
    AgreementVersion, DocumentTemplate
)

admin.site.register(Income)
admin.site.register(Expense)
admin.site.register(DeletedIncome)
admin.site.register(DeletedExpense)
admin.site.register(PartnerPayout)
admin.site.register(FinancePaymentMethod)
admin.site.register(FinanceExpenseCategory)
admin.site.register(FinancePaymentStatus)
admin.site.register(FinanceCommissionType)
admin.site.register(DocumentSettings)
admin.site.register(Quotation)
admin.site.register(QuotationSection)
admin.site.register(QuotationItem)
admin.site.register(QuotationPackage)
admin.site.register(QuotationDomainOption)
admin.site.register(QuotationPaymentStage)
admin.site.register(QuotationTerm)
admin.site.register(QuotationExclusion)
admin.site.register(QuotationActivity)
admin.site.register(QuotationVersion)
admin.site.register(AgreementVersion)
admin.site.register(DocumentTemplate)


