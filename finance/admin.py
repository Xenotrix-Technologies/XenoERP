from django.contrib import admin
from .models import (
    FinancePaymentMethod, FinanceExpenseCategory, FinancePaymentStatus,
    FinanceCommissionType, Income, Expense, DeletedIncome, DeletedExpense,
    PartnerPayout, DocumentSettings, DocumentTemplate, Quotation, QuotationItem,
    InvoiceStatus, Invoice, InvoiceItem
)


@admin.register(FinancePaymentMethod)
class FinancePaymentMethodAdmin(admin.ModelAdmin):
    list_display = ('name', 'organization')
    list_filter = ('organization',)
    search_fields = ('name',)


@admin.register(FinanceExpenseCategory)
class FinanceExpenseCategoryAdmin(admin.ModelAdmin):
    list_display = ('name', 'organization')
    list_filter = ('organization',)
    search_fields = ('name',)


@admin.register(Income)
class IncomeAdmin(admin.ModelAdmin):
    list_display = ('client_name', 'project_name', 'organization', 'amount', 'date', 'payment_method')
    list_filter = ('organization', 'date', 'payment_method')
    search_fields = ('client_name', 'project_name')
    ordering = ('-date', '-created_at')


@admin.register(Expense)
class ExpenseAdmin(admin.ModelAdmin):
    list_display = ('category', 'organization', 'amount', 'date', 'cost_center', 'payment_method')
    list_filter = ('organization', 'date', 'category', 'payment_method')
    search_fields = ('description', 'cost_center')
    ordering = ('-date', '-created_at')


@admin.register(DeletedIncome)
class DeletedIncomeAdmin(admin.ModelAdmin):
    list_display = ('client_name', 'organization', 'amount', 'date', 'deleted_at', 'deleted_by')
    list_filter = ('organization', 'deleted_at')
    search_fields = ('client_name',)


@admin.register(DeletedExpense)
class DeletedExpenseAdmin(admin.ModelAdmin):
    list_display = ('category_name', 'organization', 'amount', 'date', 'deleted_at', 'deleted_by')
    list_filter = ('organization', 'deleted_at')
    search_fields = ('description',)


@admin.register(PartnerPayout)
class PartnerPayoutAdmin(admin.ModelAdmin):
    list_display = ('partner_name', 'organization', 'amount', 'status', 'payout_date', 'commission_type')
    list_filter = ('organization', 'status', 'commission_type')
    search_fields = ('partner_name', 'project_client')


@admin.register(DocumentSettings)
class DocumentSettingsAdmin(admin.ModelAdmin):
    list_display = ('company_name', 'quotation_prefix', 'agreement_prefix')
    search_fields = ('company_name',)


@admin.register(DocumentTemplate)
class DocumentTemplateAdmin(admin.ModelAdmin):
    list_display = ('title', 'category', 'organization', 'is_default', 'is_active')
    list_filter = ('organization', 'category', 'is_default', 'is_active')
    search_fields = ('title',)


class QuotationItemInline(admin.TabularInline):
    model = QuotationItem
    extra = 1


@admin.register(Quotation)
class QuotationAdmin(admin.ModelAdmin):
    list_display = ('quotation_number', 'project_title', 'client_name', 'company_name', 'organization', 'status', 'grand_total', 'created_at')
    list_filter = ('organization', 'status')
    search_fields = ('quotation_number', 'project_title', 'client_name', 'company_name')
    inlines = [QuotationItemInline]


@admin.register(InvoiceStatus)
class InvoiceStatusAdmin(admin.ModelAdmin):
    list_display = ('name', 'organization', 'color', 'position')
    list_filter = ('organization',)
    search_fields = ('name',)


class InvoiceItemInline(admin.TabularInline):
    model = InvoiceItem
    extra = 1


@admin.register(Invoice)
class InvoiceAdmin(admin.ModelAdmin):
    list_display = ('invoice_number', 'customer_name', 'company_name', 'organization', 'status', 'grand_total', 'amount_paid', 'balance_due', 'invoice_date')
    list_filter = ('organization', 'status', 'currency')
    search_fields = ('invoice_number', 'customer_name', 'company_name', 'phone_number')
    inlines = [InvoiceItemInline]
