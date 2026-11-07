from django.urls import path
from . import views
from . import invoice_views
from . import document_views

urlpatterns = [
    # Finance Dashboard & Ledger
    path('finance/dashboard/', views.finance_dashboard_view, name='finance_dashboard'),
    path('finance/income/', views.finance_income_view, name='finance_income'),
    path('finance/income/add/', views.finance_add_income_view, name='finance_add_income'),
    path('finance/income/edit/<int:income_id>/', views.finance_edit_income, name='finance_edit_income'),
    path('finance/income/bulk-delete/', views.bulk_delete_incomes, name='bulk_delete_incomes'),
    path('finance/income/restore/<int:deleted_id>/', views.restore_deleted_income, name='restore_deleted_income'),

    path('finance/expenses/', views.finance_expenses_view, name='finance_expenses'),
    path('finance/expenses/add/', views.finance_add_expense_view, name='finance_add_expense'),
    path('finance/expenses/edit/<int:expense_id>/', views.finance_edit_expense, name='finance_edit_expense'),
    path('finance/expenses/bulk-delete/', views.bulk_delete_expenses, name='bulk_delete_expenses'),
    path('finance/expenses/restore/<int:deleted_id>/', views.restore_deleted_expense, name='restore_deleted_expense'),

    path('finance/reports/', views.finance_reports_view, name='finance_reports'),
    path('finance/partner-payouts/', views.partner_payout_view, name='partner_payouts'),
    path('finance/partner-payouts/add/', views.partner_payout_add_view, name='partner_payout_add'),
    path('finance/partner-payouts/delete/<int:payout_id>/', views.partner_payout_delete_view, name='partner_payout_delete'),
    path('finance/settings/', views.finance_settings_view, name='finance_settings'),

    # Finance Payment Methods & Expense Categories
    path('statuses/finance-method/add/', views.add_finance_method, name='add_finance_method'),
    path('statuses/finance-method/<int:method_id>/edit/', views.edit_finance_method, name='edit_finance_method'),
    path('statuses/finance-method/<int:method_id>/delete/', views.delete_finance_method, name='delete_finance_method'),
    path('statuses/finance-category/add/', views.add_finance_category, name='add_finance_category'),
    path('statuses/finance-category/<int:cat_id>/edit/', views.edit_finance_category, name='edit_finance_category'),
    path('statuses/finance-category/<int:cat_id>/delete/', views.delete_finance_category, name='delete_finance_category'),

    # Invoices & Bills
    path('finance/invoices/', invoice_views.invoice_dashboard, name='invoice_dashboard'),
    path('finance/invoices/create/', invoice_views.invoice_create, name='invoice_create'),
    path('finance/invoices/<int:invoice_id>/', invoice_views.invoice_detail, name='invoice_detail'),
    path('finance/invoices/<int:invoice_id>/edit/', invoice_views.invoice_edit, name='invoice_edit'),
    path('finance/invoices/<int:invoice_id>/delete/', invoice_views.invoice_delete, name='invoice_delete'),
    path('finance/invoices/<int:invoice_id>/update-status/', invoice_views.invoice_update_status, name='invoice_update_status'),

    # Quotations & Documents
    path('quotations/', document_views.quotation_list, name='quotations'),
    path('quotations/list/', document_views.quotation_list, name='quotation_list'),
    path('quotations/create/', document_views.quotation_create, name='quotation_create'),
    path('quotations/quick-client/', document_views.quotation_quick_create_client, name='quotation_quick_create_client'),
    path('quotations/<int:quotation_id>/', document_views.quotation_detail, name='quotation_detail'),
    path('quotations/<int:quotation_id>/edit/', document_views.quotation_edit, name='quotation_edit'),
    path('quotations/<int:quotation_id>/duplicate/', document_views.quotation_duplicate, name='quotation_duplicate'),
    path('quotations/<int:quotation_id>/status/', document_views.quotation_update_status, name='quotation_update_status'),
    path('quotations/<int:quotation_id>/convert-to-agreement/', document_views.quotation_convert_to_agreement, name='quotation_convert_to_agreement'),
    path('quotations/<int:quotation_id>/delete/', document_views.quotation_delete, name='quotation_delete'),
    path('quotation/view/<str:public_token>/', document_views.public_quotation_view, name='public_quotation_view'),
    path('quotation/view/<str:public_token>/accept/', document_views.public_quotation_accept, name='public_quotation_accept'),
    path('quotation/view/<str:public_token>/reject/', document_views.public_quotation_reject, name='public_quotation_reject'),
    path('settings/documents/', document_views.document_settings_view, name='document_settings'),
    path('settings/templates/', document_views.document_templates_view, name='document_templates'),
    path('settings/templates/<int:template_id>/delete/', document_views.document_template_delete, name='document_template_delete'),
    path('lead/<int:lead_id>/convert-to-client/', document_views.convert_lead_to_client, name='convert_lead_to_client'),
]

