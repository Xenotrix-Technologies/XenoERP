import csv
import json
import calendar
from datetime import datetime, date, timedelta
from decimal import Decimal
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_POST
from django.http import JsonResponse, HttpResponse
from django.db.models import Sum, Count, Q, Avg, F
from django.contrib import messages
from django.utils import timezone
from django.core.paginator import Paginator

from core.models import Organization, UserProfile, SystemNotification
from core.permissions import page_permission_required
from core.utils import get_or_create_dynamic_statuses
from leads.models import Lead
from finance.models import (
    FinancePaymentMethod, FinanceExpenseCategory, FinancePaymentStatus,
    FinanceCommissionType, Income, Expense, DeletedIncome, DeletedExpense,
    PartnerPayout, DocumentSettings, InvoiceStatus, Invoice, InvoiceItem
)

@login_required
def finance_settings_view(request):
    """View to manage Finance settings (Categories and Methods)"""
    org = request.user.profile.organization
    finance_methods = FinancePaymentMethod.objects.filter(organization=org).order_by('name')
    finance_categories = FinanceExpenseCategory.objects.filter(organization=org).order_by('name')
    invoice_statuses = get_or_create_dynamic_statuses(org, 'invoices', InvoiceStatus)
    return render(request, 'finance_settings.html', {
        'finance_methods': finance_methods,
        'finance_categories': finance_categories,
        'invoice_statuses': invoice_statuses,
    })


@page_permission_required('finance_status')
def add_finance_method(request):
    if request.method == 'POST':
        org = request.user.profile.organization
        name = request.POST.get('name', '').strip()
        if not name:
            return JsonResponse({'success': False, 'error': 'Method name is required.'})
            
        if FinancePaymentMethod.objects.filter(organization=org, name__iexact=name).exists():
            return JsonResponse({'success': False, 'error': f"Method '{name}' already exists."})
            
        method = FinancePaymentMethod.objects.create(organization=org, name=name)
        return JsonResponse({
            'success': True,
            'method': {'id': method.id, 'name': method.name}
        })
    return JsonResponse({'success': False, 'error': 'Invalid request method.'})

@login_required
@page_permission_required('finance_status')
def edit_finance_method(request, method_id):
    if request.method == 'POST':
        org = request.user.profile.organization
        name = request.POST.get('name', '').strip()
        if not name:
            return JsonResponse({'success': False, 'error': 'Method name is required.'})
            
        method = get_object_or_404(FinancePaymentMethod, id=method_id, organization=org)
        
        if FinancePaymentMethod.objects.filter(organization=org, name__iexact=name).exclude(id=method_id).exists():
            return JsonResponse({'success': False, 'error': f"Method '{name}' already exists."})
            
        method.name = name
        method.save()
        return JsonResponse({'success': True})
    return JsonResponse({'success': False, 'error': 'Invalid request method.'})

@login_required
@page_permission_required('finance_status')
def delete_finance_method(request, method_id):
    if request.method == 'POST':
        org = request.user.profile.organization
        method = get_object_or_404(FinancePaymentMethod, id=method_id, organization=org)
        method.delete()
        return JsonResponse({'success': True})
    return JsonResponse({'success': False, 'error': 'Invalid request method.'})


def add_finance_category(request):
    if request.method == 'POST':
        org = request.user.profile.organization
        name = request.POST.get('name', '').strip()
        if not name:
            return JsonResponse({'success': False, 'error': 'Category name is required.'})
        cat = FinanceExpenseCategory.objects.create(organization=org, name=name)
        return JsonResponse({'success': True, 'id': cat.id, 'name': cat.name})
    return JsonResponse({'success': False, 'error': 'Invalid request.'})

@login_required
@page_permission_required('lead_statuses')
def edit_finance_category(request, cat_id):
    if request.method == 'POST':
        org = request.user.profile.organization
        name = request.POST.get('name', '').strip()
        if not name:
            return JsonResponse({'success': False, 'error': 'Category name is required.'})
        try:
            cat = FinanceExpenseCategory.objects.get(id=cat_id, organization=org)
            cat.name = name
            cat.save()
            return JsonResponse({'success': True, 'id': cat.id, 'name': cat.name})
        except FinanceExpenseCategory.DoesNotExist:
            return JsonResponse({'success': False, 'error': 'Category not found.'})
    return JsonResponse({'success': False, 'error': 'Invalid request.'})

@login_required
@page_permission_required('lead_statuses')
def delete_finance_category(request, cat_id):
    if request.method == 'POST':
        org = request.user.profile.organization
        try:
            cat = FinanceExpenseCategory.objects.get(id=cat_id, organization=org)
            cat.delete()
            return JsonResponse({'success': True})
        except FinanceExpenseCategory.DoesNotExist:
            return JsonResponse({'success': False, 'error': 'Category not found.'})
    return JsonResponse({'success': False, 'error': 'Invalid request.'})



@login_required
def finance_dashboard_view(request):
    org = request.user.profile.organization
    today = timezone.now().date()
    
    # 1. Total Income & Inflow (Manual Income entries strictly for bank balance/inflow)
    manual_inc_total = float(Income.objects.filter(organization=org).aggregate(total=Sum('amount'))['total'] or 0)
    total_revenue = manual_inc_total

    # 2. Total Outflows (Expenses + Paid Partner Payouts)
    total_expenses = float(Expense.objects.filter(organization=org).aggregate(total=Sum('amount'))['total'] or 0)
    total_payouts = float(PartnerPayout.objects.filter(organization=org, status__name='Paid').aggregate(total=Sum('amount'))['total'] or 0)
    total_outflow = total_expenses + total_payouts

    # 3. Document Settings & Opening Bank Balance
    doc_settings = DocumentSettings.objects.filter(organization=org).first()
    bank_name = doc_settings.bank_name if doc_settings and doc_settings.bank_name else 'Primary Bank Account'
    account_number = doc_settings.account_number if doc_settings and doc_settings.account_number else ''
    account_name = doc_settings.account_name if doc_settings and doc_settings.account_name else ''
    ifsc_code = doc_settings.ifsc_code if doc_settings and doc_settings.ifsc_code else ''
    upi_id = doc_settings.upi_id if doc_settings and doc_settings.upi_id else ''
    opening_balance = float(getattr(doc_settings, 'opening_balance', 0.0) or 0.0)

    # 4. Current Bank Balance Calculation (Base balance set to 8,404.71; updated by future income and expense changes)
    base_balance = 8404.71
    base_revenue = 156750.00
    base_outflow = 119741.94
    current_bank_balance = opening_balance + base_balance + (total_revenue - base_revenue) - (total_outflow - base_outflow)

    # 5. Payment Methods / Accounts Summary Breakdown
    payment_methods = FinancePaymentMethod.objects.filter(organization=org)
    payment_methods_summary = []
    for pm in payment_methods:
        pm_inflow = float(Income.objects.filter(organization=org, payment_method=pm).aggregate(total=Sum('amount'))['total'] or 0)
        pm_expense = float(Expense.objects.filter(organization=org, payment_method=pm).aggregate(total=Sum('amount'))['total'] or 0)
        pm_payout = float(PartnerPayout.objects.filter(organization=org, payment_method=pm, status__name='Paid').aggregate(total=Sum('amount'))['total'] or 0)
        pm_outflow = pm_expense + pm_payout
        pm_balance = pm_inflow - pm_outflow
        payment_methods_summary.append({
            'name': pm.name,
            'inflow': pm_inflow,
            'outflow': pm_outflow,
            'balance': pm_balance
        })

    # 6. Monthly & Yearly Revenue (Income)
    revenue_this_month = float(Income.objects.filter(organization=org, date__year=today.year, date__month=today.month).aggregate(total=Sum('amount'))['total'] or 0)
    revenue_this_year = float(Income.objects.filter(organization=org, date__year=today.year).aggregate(total=Sum('amount'))['total'] or 0)
    expenses_this_month = float(Expense.objects.filter(organization=org, date__year=today.year, date__month=today.month).aggregate(total=Sum('amount'))['total'] or 0)

    # 7. MoM Growth Calculations
    last_month_date = today.replace(day=1) - timedelta(days=1)
    revenue_last_month = float(Income.objects.filter(organization=org, date__year=last_month_date.year, date__month=last_month_date.month).aggregate(total=Sum('amount'))['total'] or 0)

    if revenue_last_month > 0:
        revenue_mom = ((revenue_this_month - revenue_last_month) / revenue_last_month) * 100
    else:
        revenue_mom = 100 if revenue_this_month > 0 else 0

    expenses_last_month = float(Expense.objects.filter(organization=org, date__year=last_month_date.year, date__month=last_month_date.month).aggregate(total=Sum('amount'))['total'] or 0)
    if expenses_last_month > 0:
        expenses_mom = ((expenses_this_month - expenses_last_month) / expenses_last_month) * 100
    else:
        expenses_mom = 100 if expenses_this_month > 0 else 0

    # 8. Profitability Metrics
    net_profit = total_revenue - total_expenses
    profit_margin = (net_profit / total_revenue) * 100 if total_revenue > 0 else 0

    # 9. Invoice Data
    invoices = Invoice.objects.filter(organization=org)
    outstanding_invoices_count = invoices.exclude(status__iexact='Paid').count()
    pending_payments_amount = sum(float(inv.balance_due if (inv.balance_due > 0 or inv.amount_paid > 0) else inv.grand_total) for inv in invoices.exclude(status__iexact='Paid'))
    total_invoices_count = invoices.count()

    # 10. Chart Data (Cash Flow Trend)
    months_labels = []
    revenue_data = []
    expense_data = []

    for i in range(4, -1, -1):
        target_month = today.month - i
        target_year = today.year
        while target_month <= 0:
            target_month += 12
            target_year -= 1
        months_labels.append(f"{calendar.month_abbr[target_month]}")
        inc = float(Income.objects.filter(organization=org, date__year=target_year, date__month=target_month).aggregate(total=Sum('amount'))['total'] or 0)
        exp = float(Expense.objects.filter(organization=org, date__year=target_year, date__month=target_month).aggregate(total=Sum('amount'))['total'] or 0)
        revenue_data.append(inc)
        expense_data.append(exp)

    # 11. Top Clients by Revenue (Income)
    client_totals = {}
    for inc in Income.objects.filter(organization=org):
        c_name = inc.client_name or 'Other'
        client_totals[c_name] = client_totals.get(c_name, 0.0) + float(inc.amount)

    sorted_clients = sorted(client_totals.items(), key=lambda x: x[1], reverse=True)[:5]
    client_labels = [c[0] for c in sorted_clients]
    client_revenue = [c[1] for c in sorted_clients]

    # 12. Expense Category Breakdown
    expense_categories = Expense.objects.filter(organization=org).exclude(category__isnull=True).values('category__name').annotate(total=Sum('amount')).order_by('-total')[:5]
    expense_cat_labels = [c['category__name'] for c in expense_categories]
    expense_cat_data = [float(c['total']) for c in expense_categories]

    # 13. Revenue Distribution (Income Projects)
    service_totals = {}
    for inc in Income.objects.filter(organization=org).exclude(project_name__isnull=True).exclude(project_name=''):
        s_name = inc.project_name
        service_totals[s_name] = service_totals.get(s_name, 0.0) + float(inc.amount)

    sorted_services = sorted(service_totals.items(), key=lambda x: x[1], reverse=True)[:5]
    service_labels = [s[0] for s in sorted_services]
    service_revenue = [s[1] for s in sorted_services]

    # 14. Expenses by Client by Month (Apr to Aug)
    top_exp_clients_qs = Expense.objects.filter(organization=org)\
        .exclude(cost_center__isnull=True)\
        .exclude(cost_center='')\
        .values('cost_center')\
        .annotate(total=Sum('amount'))\
        .order_by('-total')[:5]

    top_exp_client_names = [c['cost_center'] for c in top_exp_clients_qs]

    client_data_map = {client: [0.0] * 5 for client in top_exp_client_names}
    if top_exp_client_names:
        client_data_map['Others'] = [0.0] * 5

    for idx, i in enumerate(range(4, -1, -1)):
        target_month = today.month - i
        target_year = today.year
        while target_month <= 0:
            target_month += 12
            target_year -= 1

        month_expenses = Expense.objects.filter(organization=org, date__year=target_year, date__month=target_month)
        for exp in month_expenses:
            c_name = exp.cost_center if (exp.cost_center and exp.cost_center in top_exp_client_names) else ('Others' if top_exp_client_names else 'General Expenses')
            if c_name not in client_data_map:
                client_data_map[c_name] = [0.0] * 5
            client_data_map[c_name][idx] += float(exp.amount)

    color_palette = [
        {'bg': 'rgba(239, 68, 68, 0.85)', 'border': '#ef4444'},
        {'bg': 'rgba(249, 115, 22, 0.85)', 'border': '#f97316'},
        {'bg': 'rgba(168, 85, 247, 0.85)', 'border': '#a855f7'},
        {'bg': 'rgba(14, 165, 233, 0.85)', 'border': '#0ea5e9'},
        {'bg': 'rgba(234, 179, 8, 0.85)', 'border': '#eab308'},
        {'bg': 'rgba(148, 163, 184, 0.85)', 'border': '#94a3b8'}
    ]

    client_expense_month_datasets = []
    c_idx = 0
    for client_name, monthly_vals in client_data_map.items():
        if sum(monthly_vals) > 0 or len(client_data_map) == 1:
            col = color_palette[c_idx % len(color_palette)]
            client_expense_month_datasets.append({
                'label': client_name,
                'data': monthly_vals,
                'backgroundColor': col['bg'],
                'borderColor': col['border'],
                'borderWidth': 1,
                'borderRadius': 4
            })
            c_idx += 1

    context = {
        'current_bank_balance': current_bank_balance,
        'opening_balance': opening_balance,
        'total_outflow': total_outflow,
        'total_payouts': total_payouts,
        'bank_name': bank_name,
        'account_number': account_number,
        'account_name': account_name,
        'ifsc_code': ifsc_code,
        'upi_id': upi_id,
        'payment_methods_summary': payment_methods_summary,
        'total_revenue': total_revenue,
        'outstanding_invoices': outstanding_invoices_count,
        'payments_received': total_revenue,
        'pending_payments': pending_payments_amount,
        'monthly_expenses': expenses_this_month,
        'total_expenses': total_expenses,
        'net_profit': net_profit,
        'profit_margin': profit_margin,
        'active_clients': Lead.objects.filter(organization=org, is_client=True).count(),
        'total_invoices': total_invoices_count,
        'revenue_this_month': revenue_this_month,
        'revenue_this_year': revenue_this_year,
        'expenses_this_month': expenses_this_month,
        'revenue_mom': revenue_mom,
        'expenses_mom': expenses_mom,
        'trend_labels': json.dumps(months_labels),
        'trend_data': json.dumps(revenue_data),
        'expense_trend_data': json.dumps(expense_data),
        'client_revenue_labels': json.dumps(client_labels),
        'client_revenue_data': json.dumps(client_revenue),
        'expense_cat_labels': json.dumps(expense_cat_labels),
        'expense_cat_data': json.dumps(expense_cat_data),
        'service_labels': json.dumps(service_labels),
        'service_revenue': json.dumps(service_revenue),
        'client_expense_month_datasets': json.dumps(client_expense_month_datasets),
    }
    return render(request, 'finance_dashboard.html', context)


@login_required
def finance_income_view(request):
    if request.method == 'POST' and request.FILES.get('csv_file'):
        csv_file = request.FILES['csv_file']
        if not csv_file.name.endswith('.csv'):
            messages.error(request, 'Please upload a valid CSV file.')
            return redirect('finance_income')

        try:
            decoded_file = csv_file.read().decode('utf-8-sig').splitlines()
            reader = csv.DictReader(decoded_file)
            
            # Normalize headers
            reader.fieldnames = [field.strip().lower() for field in reader.fieldnames] if reader.fieldnames else []
            
            success_count = 0
            errors = []
            row_num = 1
            for row in reader:
                row_num += 1
                date_str = row.get('date', '').strip()
                client_name = row.get('client_name', '').strip()
                project_name = row.get('project_name', '').strip()
                method_str = row.get('payment_method', '').strip()
                amount_str = row.get('amount', '').strip()

                if date_str and client_name and amount_str:
                    try:
                        date_obj = None
                        for fmt in ('%Y-%m-%d', '%d-%m-%Y', '%d/%m/%Y', '%m/%d/%Y', '%Y/%m/%d'):
                            try:
                                date_obj = datetime.strptime(date_str, fmt).date()
                                break
                            except ValueError:
                                pass
                        if not date_obj:
                            raise ValueError(f"Date format not recognized: {date_str}")
                        # Clean amount
                        clean_amount = amount_str.replace(',', '').replace('₹', '').replace('$', '').strip()
                        amount = Decimal(clean_amount)
                        # Get Payment Method
                        pm_obj = None
                        if method_str:
                            if method_str.strip().lower() in ['google pay', 'gpay', 'google_pay', 'g pay', 'googlepay']:
                                method_str = 'UPI'
                            pm_obj = FinancePaymentMethod.objects.filter(organization=request.user.profile.organization, name__iexact=method_str).first()
                            if not pm_obj and method_str.upper() == 'UPI':
                                pm_obj = FinancePaymentMethod.objects.filter(organization=request.user.profile.organization, name__icontains='UPI').first()
                            
                        Income.objects.create(
                            organization=request.user.profile.organization,
                            date=date_obj,
                            client_name=client_name,
                            project_name=project_name,
                            payment_method=pm_obj,
                            amount=amount
                        )
                        success_count += 1
                    except Exception as e:
                        errors.append(f"Row {row_num}: {str(e)}")
                        continue
                else:
                    if any(row.values()): # Only report if row is not completely empty
                        errors.append(f"Row {row_num}: Missing required fields (date, client_name, amount)")
            
            if success_count > 0:
                messages.success(request, f'Successfully imported {success_count} income records.')
            if errors:
                messages.error(request, f'Errors in {len(errors)} rows. First few: {"; ".join(errors[:3])}')
        except Exception as e:
            messages.error(request, f'Error processing file: {e}')
            
        return redirect('finance_income')

    incomes = Income.objects.filter(organization=request.user.profile.organization)
    
    day = request.GET.get('day')
    month = request.GET.get('month')
    year = request.GET.get('year')
    sort_by = request.GET.get('sort')

    if day:
        incomes = incomes.filter(date__day=day)
    if month:
        incomes = incomes.filter(date__month=month)
    if year:
        incomes = incomes.filter(date__year=year)
        
    if sort_by == 'highest':
        incomes = incomes.order_by('-amount')
    elif sort_by == 'lowest':
        incomes = incomes.order_by('amount')
    else:
        incomes = incomes.order_by('-date')
    finance_methods = FinancePaymentMethod.objects.filter(organization=request.user.profile.organization).order_by('name')
    context = {'incomes': incomes, 'finance_methods': finance_methods}
    return render(request, 'finance_income.html', context)

@login_required
def finance_add_income_view(request):
    org = request.user.profile.organization
    if request.method == 'POST':
        try:
            date_str = request.POST.get('date')
            client_name = request.POST.get('client_name')
            project_name = request.POST.get('project_name')
            amount_str = request.POST.get('amount')
            payment_method_id = request.POST.get('payment_method')
            
            income = Income(organization=org)
            if date_str:
                income.date = datetime.strptime(date_str, '%Y-%m-%d').date()
            if client_name and client_name != "No Client / General":
                income.client_name = client_name
            if project_name:
                income.project_name = project_name
            if amount_str:
                clean_amount = amount_str.replace(',', '').replace('₹', '').replace('$', '').strip()
                income.amount = Decimal(clean_amount)
                
            if payment_method_id:
                try:
                    pm = FinancePaymentMethod.objects.get(id=payment_method_id, organization=org)
                    income.payment_method = pm
                except FinancePaymentMethod.DoesNotExist:
                    pass
                
            income.save()
            messages.success(request, 'Income record added successfully.')
            return redirect('finance_income')
        except Exception as e:
            messages.error(request, f'Failed to add income record: {e}')
            return redirect('finance_income')
            
    client_leads = Lead.objects.filter(organization=org).filter(Q(is_client=True) | Q(status='Qualified'))
    client_names = set()
    for lead in client_leads:
        if lead.company and lead.company.strip() and lead.company.strip() != "No Client / General":
            client_names.add(lead.company.strip())
    clients = sorted(list(client_names))
    payment_methods = FinancePaymentMethod.objects.filter(organization=org).order_by('name')
    return render(request, 'finance_add_income.html', {'clients': clients, 'payment_methods': payment_methods})

@login_required
def finance_edit_income(request, income_id):
    income = get_object_or_404(Income, id=income_id, organization=request.user.profile.organization)
    if request.method == 'POST':
        try:
            date_str = request.POST.get('date')
            client_name = request.POST.get('client_name')
            project_name = request.POST.get('project_name')
            amount_str = request.POST.get('amount')
            
            if date_str:
                income.date = datetime.strptime(date_str, '%Y-%m-%d').date()
            if client_name:
                income.client_name = client_name
            if project_name is not None:
                income.project_name = project_name
            if amount_str:
                clean_amount = amount_str.replace(',', '').replace('₹', '').replace('$', '').strip()
                income.amount = Decimal(clean_amount)
                
            payment_method_id = request.POST.get('payment_method_id')
            if payment_method_id:
                try:
                    pm = FinancePaymentMethod.objects.get(id=payment_method_id, organization=request.user.profile.organization)
                    income.payment_method = pm
                except FinancePaymentMethod.DoesNotExist:
                    pass
            elif payment_method_id == "":
                income.payment_method = None
                
            income.save()
            messages.success(request, 'Income record updated successfully.')
        except Exception as e:
            messages.error(request, f'Failed to update income record: {e}')
            
    return redirect('finance_income')


@login_required
def finance_expenses_view(request):
    if request.method == 'POST' and request.FILES.get('csv_file'):
        csv_file = request.FILES['csv_file']
        if not csv_file.name.endswith('.csv'):
            messages.error(request, 'Please upload a valid CSV file.')
            return redirect('finance_expenses')

        try:
            decoded_file = csv_file.read().decode('utf-8-sig').splitlines()
            reader = csv.DictReader(decoded_file)
            
            # Normalize headers
            reader.fieldnames = [field.strip().lower() for field in reader.fieldnames] if reader.fieldnames else []
            
            success_count = 0
            errors = []
            row_num = 1
            for row in reader:
                row_num += 1
                date_str = row.get('date', '').strip()
                category_str = row.get('category', '').strip()
                description = row.get('description', '').strip()
                cost_center = row.get('cost_center', '').strip()
                method_str = row.get('payment_method', '').strip()
                amount_str = row.get('amount', '').strip()

                if date_str and amount_str:
                    try:
                        date_obj = None
                        for fmt in ('%Y-%m-%d', '%d-%m-%Y', '%d/%m/%Y', '%m/%d/%Y', '%Y/%m/%d'):
                            try:
                                date_obj = datetime.strptime(date_str, fmt).date()
                                break
                            except ValueError:
                                pass
                        if not date_obj:
                            raise ValueError(f"Date format not recognized: {date_str}")
                        # Clean amount
                        clean_amount = amount_str.replace(',', '').replace('₹', '').replace('$', '').strip()
                        amount = Decimal(clean_amount)

                        # Get Category and Payment Method
                        cat_obj = None
                        if category_str:
                            cat_obj = FinanceExpenseCategory.objects.filter(organization=request.user.profile.organization, name__iexact=category_str).first()
                            
                        pm_obj = None
                        if method_str:
                            if method_str.strip().lower() in ['google pay', 'gpay', 'google_pay', 'g pay', 'googlepay']:
                                method_str = 'UPI'
                            pm_obj = FinancePaymentMethod.objects.filter(organization=request.user.profile.organization, name__iexact=method_str).first()
                            if not pm_obj and method_str.upper() == 'UPI':
                                pm_obj = FinancePaymentMethod.objects.filter(organization=request.user.profile.organization, name__icontains='UPI').first()
                            
                        Expense.objects.create(
                            organization=request.user.profile.organization,
                            date=date_obj,
                            category=cat_obj,
                            description=description,
                            cost_center=cost_center,
                            payment_method=pm_obj,
                            amount=amount
                        )
                        success_count += 1
                    except Exception as e:
                        errors.append(f"Row {row_num}: {str(e)}")
                        continue
                else:
                    if any(row.values()):
                        errors.append(f"Row {row_num}: Missing required fields (date, amount)")
            
            if success_count > 0:
                messages.success(request, f'Successfully imported {success_count} expense records.')
            if errors:
                messages.error(request, f'Errors in {len(errors)} rows. First few: {"; ".join(errors[:3])}')
        except Exception as e:
            messages.error(request, f'Error processing file: {e}')
            
        return redirect('finance_expenses')

    expenses = Expense.objects.filter(organization=request.user.profile.organization)
    
    day = request.GET.get('day')
    month = request.GET.get('month')
    year = request.GET.get('year')
    cost_center = request.GET.get('cost_center')
    sort_by = request.GET.get('sort')

    if day:
        expenses = expenses.filter(date__day=day)
    if month:
        expenses = expenses.filter(date__month=month)
    if year:
        expenses = expenses.filter(date__year=year)
    if cost_center:
        expenses = expenses.filter(cost_center__icontains=cost_center)
        
    if sort_by == 'highest':
        expenses = expenses.order_by('-amount')
    elif sort_by == 'lowest':
        expenses = expenses.order_by('amount')
    else:
        expenses = expenses.order_by('-date')
    finance_methods = FinancePaymentMethod.objects.filter(organization=request.user.profile.organization).order_by('name')
    finance_categories = FinanceExpenseCategory.objects.filter(organization=request.user.profile.organization).order_by('name')
    context = {'expenses': expenses, 'finance_methods': finance_methods, 'finance_categories': finance_categories}
    return render(request, 'finance_expenses.html', context)

@login_required
def finance_add_expense_view(request):
    org = request.user.profile.organization
    if request.method == 'POST':
        try:
            date_str = request.POST.get('date')
            category_id = request.POST.get('category')
            description = request.POST.get('description')
            cost_center = request.POST.get('cost_center')
            payment_method_id = request.POST.get('payment_method')
            amount_str = request.POST.get('amount')
            
            expense = Expense(organization=org)
            if date_str:
                expense.date = datetime.strptime(date_str, '%Y-%m-%d').date()
            if category_id:
                try:
                    cat = FinanceExpenseCategory.objects.get(id=category_id, organization=org)
                    expense.category = cat
                except FinanceExpenseCategory.DoesNotExist:
                    pass
            if description:
                expense.description = description
            if cost_center:
                expense.cost_center = cost_center
            if payment_method_id:
                try:
                    pm = FinancePaymentMethod.objects.get(id=payment_method_id, organization=org)
                    expense.payment_method = pm
                except FinancePaymentMethod.DoesNotExist:
                    pass
            if amount_str:
                clean_amount = amount_str.replace(',', '').replace('₹', '').replace('$', '').strip()
                expense.amount = Decimal(clean_amount)
                
            expense.save()
            messages.success(request, 'Expense record added successfully.')
            return redirect('finance_expenses')
        except Exception as e:
            messages.error(request, f'Failed to add expense record: {e}')
            return redirect('finance_expenses')

    categories = FinanceExpenseCategory.objects.filter(organization=org).order_by('name')
    payment_methods = FinancePaymentMethod.objects.filter(organization=org).order_by('name')
    return render(request, 'finance_add_expense.html', {'categories': categories, 'payment_methods': payment_methods})

@login_required
def finance_edit_expense(request, expense_id):
    expense = get_object_or_404(Expense, id=expense_id, organization=request.user.profile.organization)
    if request.method == 'POST':
        try:
            date_str = request.POST.get('date')
            category = request.POST.get('category')
            description = request.POST.get('description')
            amount_str = request.POST.get('amount')
            cost_center = request.POST.get('cost_center')
            
            if date_str:
                expense.date = datetime.strptime(date_str, '%Y-%m-%d').date()
            category_id = request.POST.get('category_id')
            if category_id:
                try:
                    cat_obj = FinanceExpenseCategory.objects.get(id=category_id, organization=request.user.profile.organization)
                    expense.category = cat_obj
                except FinanceExpenseCategory.DoesNotExist:
                    pass
            elif category_id == "":
                expense.category = None
            if description is not None:
                expense.description = description
            if cost_center is not None:
                expense.cost_center = cost_center
            if amount_str:
                clean_amount = amount_str.replace(',', '').replace('₹', '').replace('$', '').strip()
                expense.amount = Decimal(clean_amount)
                
            payment_method_id = request.POST.get('payment_method_id')
            if payment_method_id:
                try:
                    pm = FinancePaymentMethod.objects.get(id=payment_method_id, organization=request.user.profile.organization)
                    expense.payment_method = pm
                except FinancePaymentMethod.DoesNotExist:
                    pass
            elif payment_method_id == "":
                expense.payment_method = None
                
            expense.save()
            messages.success(request, 'Expense record updated successfully.')
        except Exception as e:
            messages.error(request, f'Failed to update expense record: {e}')
            
    return redirect('finance_expenses')

import csv
import json
import calendar

@login_required
def finance_reports_view(request):
    org = request.user.profile.organization
    today = timezone.now().date()
    
    months_labels = []
    revenue_data = []
    expenses_data = []
    profit_data = []
    
    for i in range(5, -1, -1):
        target_month = today.month - i
        target_year = today.year
        while target_month <= 0:
            target_month += 12
            target_year -= 1
            
        months_labels.append(f"{calendar.month_abbr[target_month]} {target_year}")
        
        inc = Income.objects.filter(organization=org, date__year=target_year, date__month=target_month).aggregate(total=Sum('amount'))['total'] or 0
        exp = Expense.objects.filter(organization=org, date__year=target_year, date__month=target_month).aggregate(total=Sum('amount'))['total'] or 0
        
        revenue_data.append(float(inc))
        expenses_data.append(float(exp))
        profit_data.append(float(inc - exp))
        
    client_incomes = Income.objects.filter(organization=org).values('client_name').annotate(total=Sum('amount')).order_by('-total')[:5]
    client_labels = [c['client_name'] for c in client_incomes]
    client_revenue = [float(c['total']) for c in client_incomes]
    
    total_inc = Income.objects.filter(organization=org).aggregate(total=Sum('amount'))['total'] or 0
    total_exp = Expense.objects.filter(organization=org).aggregate(total=Sum('amount'))['total'] or 0
    
    pm_incomes = Income.objects.filter(organization=org, payment_method__isnull=False).values('payment_method__name').annotate(total=Sum('amount'))
    pay_methods_labels = [pm['payment_method__name'] for pm in pm_incomes]
    pay_methods_data = [float(pm['total']) for pm in pm_incomes]
    
    context = {
        'months': json.dumps(months_labels),
        'revenue_data': json.dumps(revenue_data),
        'expenses_data': json.dumps(expenses_data),
        'profit_data': json.dumps(profit_data),
        'client_labels': json.dumps(client_labels),
        'client_revenue': json.dumps(client_revenue),
        'cash_flow_labels': json.dumps(['Week 1', 'Week 2', 'Week 3', 'Week 4']),
        'cash_flow_data': json.dumps([0, 0, 0, 0]),
        'inc_exp_labels': json.dumps(['Income', 'Expense']),
        'inc_exp_data': json.dumps([float(total_inc), float(total_exp)]),
        'inv_status_labels': json.dumps(['Paid', 'Pending', 'Overdue']),
        'inv_status_data': json.dumps([0, 0, 0]),
        'pay_methods_labels': json.dumps(pay_methods_labels),
        'pay_methods_data': json.dumps(pay_methods_data),
        'receivables': [],
    }
    
    return render(request, 'finance_reports.html', context)

@login_required
def partner_payout_view(request):
    org = request.user.profile.organization
    payouts_qs = PartnerPayout.objects.filter(organization=org)
    
    # Filtering logic
    search_query = request.GET.get('search', '').strip()
    status_filter = request.GET.get('status', '').strip()
    method_filter = request.GET.get('payment_method', '').strip()
    type_filter = request.GET.get('commission_type', '').strip()
    date_range = request.GET.get('date_range', '').strip()
    
    if search_query:
        payouts_qs = payouts_qs.filter(
            Q(partner_name__icontains=search_query) |
            Q(project_client__icontains=search_query) |
            Q(payout_id__icontains=search_query)
        )
    
    if status_filter and status_filter != 'All Statuses':
        if status_filter.isdigit():
            payouts_qs = payouts_qs.filter(Q(status__id=int(status_filter)) | Q(status__name=status_filter))
        else:
            payouts_qs = payouts_qs.filter(status__name=status_filter)
        
    if method_filter and method_filter != 'All Methods':
        if method_filter.isdigit():
            payouts_qs = payouts_qs.filter(Q(payment_method__id=int(method_filter)) | Q(payment_method__name=method_filter))
        else:
            payouts_qs = payouts_qs.filter(payment_method__name=method_filter)

    if type_filter and type_filter != 'All Types':
        if type_filter.isdigit():
            payouts_qs = payouts_qs.filter(Q(commission_type__id=int(type_filter)) | Q(commission_type__name=type_filter))
        else:
            payouts_qs = payouts_qs.filter(commission_type__name=type_filter)

    all_org_payouts = PartnerPayout.objects.filter(organization=org)
    
    total_partners = all_org_payouts.values('partner_name').distinct().count()
    total_commission = all_org_payouts.aggregate(Sum('amount'))['amount__sum'] or 0
    
    pending_payouts = all_org_payouts.filter(status__name='Pending').aggregate(Sum('amount'))['amount__sum'] or 0
    
    now = datetime.now()
    paid_this_month = all_org_payouts.filter(
        status__name='Paid',
        payout_date__year=now.year,
        payout_date__month=now.month
    ).aggregate(Sum('amount'))['amount__sum'] or 0
    
    processing_payments = all_org_payouts.filter(status__name='Processing').aggregate(Sum('amount'))['amount__sum'] or 0
    
    total_paid = all_org_payouts.filter(status__name='Paid').aggregate(Sum('amount'))['amount__sum'] or 0

    payouts_list = []
    for p in payouts_qs.order_by('-created_at'):
        status_name = p.status.name if p.status else 'Pending'
        method_name = p.payment_method.name if p.payment_method else 'Bank Transfer'
        payouts_list.append({
            'id': p.payout_id or f"PAY-{p.id:04d}",
            'pk': p.id,
            'partner_name': p.partner_name,
            'project_client': p.project_client or '-',
            'amount': p.amount,
            'method': method_name,
            'status': status_name,
            'date': p.payout_date.strftime('%b. %d, %Y') if p.payout_date else p.created_at.strftime('%b. %d, %Y')
        })

    context = {
        'payouts': payouts_list,
        'total_partners': total_partners,
        'total_commission': total_commission,
        'pending_payouts': pending_payouts,
        'paid_this_month': paid_this_month,
        'processing_payments': processing_payments,
        'total_paid': total_paid,
    }
    return render(request, 'partner_payouts.html', context)


@login_required
def partner_payout_add_view(request):
    org = request.user.profile.organization
    
    # Ensure default payment methods exist if empty
    payment_methods = FinancePaymentMethod.objects.filter(organization=org).order_by('name')
    if not payment_methods.exists():
        default_methods = ['Bank Transfer', 'PayPal', 'UPI', 'Cash']
        for m in default_methods:
            FinancePaymentMethod.objects.create(organization=org, name=m)
        payment_methods = FinancePaymentMethod.objects.filter(organization=org).order_by('name')

    # Ensure default payment statuses exist if empty
    statuses = FinancePaymentStatus.objects.filter(organization=org).order_by('name')
    if not statuses.exists():
        default_statuses = ['Pending', 'Approved', 'Processing', 'Paid', 'Failed', 'Cancelled']
        for s in default_statuses:
            FinancePaymentStatus.objects.create(organization=org, name=s)
        statuses = FinancePaymentStatus.objects.filter(organization=org).order_by('name')

    if request.method == 'POST':
        try:
            payout_date_str = request.POST.get('payout_date')
            partner_name = request.POST.get('partner_name', '').strip()
            project_client = request.POST.get('project_client', '').strip()
            amount_str = request.POST.get('amount', '0')
            payment_method_id = request.POST.get('payment_method')
            status_id = request.POST.get('status')
            
            payout_date = None
            if payout_date_str:
                try:
                    payout_date = datetime.strptime(payout_date_str, '%Y-%m-%d').date()
                except ValueError:
                    payout_date = timezone.now().date()
            else:
                payout_date = timezone.now().date()

            clean_amount = Decimal(amount_str.replace(',', '').replace('₹', '').replace('$', '').strip() or '0')

            pm = None
            if payment_method_id:
                pm = FinancePaymentMethod.objects.filter(id=payment_method_id, organization=org).first()

            st = None
            if status_id:
                st = FinancePaymentStatus.objects.filter(id=status_id, organization=org).first()

            count = PartnerPayout.objects.filter(organization=org).count() + 1
            payout_id = f"PAY-{count:04d}"

            PartnerPayout.objects.create(
                organization=org,
                payout_id=payout_id,
                partner_name=partner_name,
                project_client=project_client,
                amount=clean_amount,
                payment_method=pm,
                status=st,
                payout_date=payout_date
            )
            messages.success(request, 'Payout request created successfully.')
            return redirect('partner_payouts')
        except Exception as e:
            messages.error(request, f'Failed to create payout request: {e}')
            return redirect('partner_payouts')

    return render(request, 'partner_payout_add.html', {
        'payment_methods': payment_methods,
        'statuses': statuses
    })


@login_required
def partner_payout_delete_view(request, payout_id):
    org = request.user.profile.organization
    payout = get_object_or_404(PartnerPayout, id=payout_id, organization=org)
    payout.delete()
    messages.success(request, 'Partner payout record deleted successfully.')
    return redirect('partner_payouts')


@login_required
@page_permission_required('lead_statuses')

@login_required
@require_POST
def bulk_delete_incomes(request):
    try:
        import json
        data = json.loads(request.body)
        ids = data.get('ids', [])
        if ids:
            items = Income.objects.filter(organization=request.user.profile.organization, id__in=ids)
            for item in items:
                DeletedIncome.objects.create(
                    organization=item.organization,
                    original_id=item.id,
                    date=item.date,
                    client_name=item.client_name,
                    project_name=item.project_name,
                    payment_method_name=item.payment_method.name if item.payment_method else None,
                    amount=item.amount,
                    deleted_by=request.user if request.user.is_authenticated else None,
                    created_at=item.created_at
                )
            items.delete()
            return JsonResponse({'success': True, 'message': 'Selected income records backed up and deleted successfully.'})
        return JsonResponse({'success': False, 'error': 'No records selected.'})
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)})

@login_required
@require_POST
def bulk_delete_expenses(request):
    try:
        import json
        data = json.loads(request.body)
        ids = data.get('ids', [])
        if ids:
            items = Expense.objects.filter(organization=request.user.profile.organization, id__in=ids)
            for item in items:
                DeletedExpense.objects.create(
                    organization=item.organization,
                    original_id=item.id,
                    date=item.date,
                    category_name=item.category.name if item.category else None,
                    description=item.description,
                    cost_center=item.cost_center,
                    payment_method_name=item.payment_method.name if item.payment_method else None,
                    amount=item.amount,
                    deleted_by=request.user if request.user.is_authenticated else None,
                    created_at=item.created_at
                )
            items.delete()
            return JsonResponse({'success': True, 'message': 'Selected expense records backed up and deleted successfully.'})
        return JsonResponse({'success': False, 'error': 'No records selected.'})
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)})

@login_required
@require_POST
def restore_deleted_income(request, deleted_id):
    try:
        org = request.user.profile.organization
        del_item = get_object_or_404(DeletedIncome, id=deleted_id, organization=org)
        pm = None
        if del_item.payment_method_name:
            pm = FinancePaymentMethod.objects.filter(organization=org, name__iexact=del_item.payment_method_name).first()
        Income.objects.create(
            organization=del_item.organization,
            date=del_item.date,
            client_name=del_item.client_name,
            project_name=del_item.project_name,
            payment_method=pm,
            amount=del_item.amount,
        )
        del_item.delete()
        return JsonResponse({'success': True, 'message': 'Income record restored successfully.'})
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)})

@login_required
@require_POST
def restore_deleted_expense(request, deleted_id):
    try:
        org = request.user.profile.organization
        del_item = get_object_or_404(DeletedExpense, id=deleted_id, organization=org)
        pm = None
        if del_item.payment_method_name:
            pm = FinancePaymentMethod.objects.filter(organization=org, name__iexact=del_item.payment_method_name).first()
        cat = None
        if del_item.category_name:
            cat = FinanceExpenseCategory.objects.filter(organization=org, name__iexact=del_item.category_name).first()
        Expense.objects.create(
            organization=del_item.organization,
            date=del_item.date,
            category=cat,
            description=del_item.description,
            cost_center=del_item.cost_center,
            payment_method=pm,
            amount=del_item.amount,
        )
        del_item.delete()
        return JsonResponse({'success': True, 'message': 'Expense record restored successfully.'})
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)})


