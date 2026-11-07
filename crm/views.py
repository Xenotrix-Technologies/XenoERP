"""
CRM App Views & Backward-Compatibility Gateway
----------------------------------------------
Hosts executive ERP dashboard and dynamic status dispatcher, and re-exports
all domain-specific views from modular apps (core, leads, services, support,
projects, activities, campaigns, content_tracker, finance) ensuring 100%
backward compatibility.
"""
import json
import csv
from datetime import datetime, date, timedelta
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_POST
from django.http import JsonResponse, HttpResponse
from django.db.models import Sum, Count, Q, Avg, F
from django.contrib import messages
from django.utils import timezone

# Model imports needed for Executive Dashboard & Dynamic Statuses
from core.models import Organization, UserProfile, SystemNotification
from core.permissions import page_permission_required
from core.utils import get_or_create_dynamic_statuses

from leads.models import Lead, LeadStatus
from services.models import Service
from support.models import Ticket, TicketStatus, PriorityStatus
from projects.models import ClientStatus, ProjectStatus, Agreement, AgreementVersion
from activities.models import Task, Event, Activity, CalendarStatus
from campaigns.models import Campaign, CampaignStatus
from content_tracker.models import ContentItem, ContentDropdownOption
from finance.models import (
    Income, Expense, PartnerPayout, Quotation, Invoice, InvoiceStatus,
    FinancePaymentMethod, FinanceExpenseCategory
)

# ==============================================================================
# 1. EXECUTIVE ERP DASHBOARD
# ==============================================================================
@page_permission_required('dashboard')
def dashboard_view(request):
    org = request.user.profile.organization
    
    period = request.GET.get('period', 'all')
    chart_metric = request.GET.get('chart_metric', 'revenue') # 'revenue', 'deals', 'leads'
    chart_range = request.GET.get('chart_range', '6m') # '7d', '30d', '6m', '1y', 'all'
    is_ajax = (request.headers.get('x-requested-with') == 'XMLHttpRequest') or (request.GET.get('format') == 'json')

    now = timezone.now()
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    
    start_date = None
    end_date = None
    prev_start_date = None
    prev_end_date = None

    if period == 'today':
        start_date = today_start
        end_date = now
        prev_start_date = today_start - timedelta(days=1)
        prev_end_date = today_start
    elif period == '7d':
        start_date = now - timedelta(days=7)
        end_date = now
        prev_start_date = now - timedelta(days=14)
        prev_end_date = start_date
    elif period == '30d':
        start_date = now - timedelta(days=30)
        end_date = now
        prev_start_date = now - timedelta(days=60)
        prev_end_date = start_date
    elif period == 'this_month':
        start_date = today_start.replace(day=1)
        end_date = now
        last_month_end = start_date - timedelta(microseconds=1)
        prev_start_date = last_month_end.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        prev_end_date = start_date
    elif period == 'last_month':
        this_month_start = today_start.replace(day=1)
        last_month_end = this_month_start - timedelta(microseconds=1)
        start_date = last_month_end.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        end_date = this_month_start
        prev_month_end = start_date - timedelta(microseconds=1)
        prev_start_date = prev_month_end.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        prev_end_date = start_date
    elif period == 'this_quarter':
        q_month = ((now.month - 1) // 3) * 3 + 1
        start_date = today_start.replace(month=q_month, day=1)
        end_date = now
        prev_q_end = start_date - timedelta(microseconds=1)
        prev_q_month = ((prev_q_end.month - 1) // 3) * 3 + 1
        prev_start_date = prev_q_end.replace(month=prev_q_month, day=1, hour=0, minute=0, second=0, microsecond=0)
        prev_end_date = start_date
    elif period == 'this_year':
        start_date = today_start.replace(month=1, day=1)
        end_date = now
        prev_start_date = today_start.replace(year=now.year - 1, month=1, day=1)
        prev_end_date = start_date
    else: # 'all'
        period = 'all'
        start_date = None
        end_date = None
        prev_start_date = None
        prev_end_date = None

    # Base QuerySets across ERP Modules
    leads_all_qs = Lead.objects.filter(organization=org)
    invoices_all_qs = Invoice.objects.filter(organization=org)
    incomes_all_qs = Income.objects.filter(organization=org)
    expenses_all_qs = Expense.objects.filter(organization=org)
    tasks_all_qs = Task.objects.filter(Q(organization=org) | Q(lead__organization=org))
    quotations_all_qs = Quotation.objects.filter(organization=org)
    agreements_all_qs = Agreement.objects.filter(organization=org)
    campaigns_all_qs = Campaign.objects.filter(organization=org)

    if start_date:
        s_date = start_date.date()
        e_date = end_date.date() if end_date else now.date()
        period_leads_qs = leads_all_qs.filter(created_at__gte=start_date, created_at__lte=end_date)
        period_incomes_qs = incomes_all_qs.filter(date__gte=s_date, date__lte=e_date)
        period_invoices_qs = invoices_all_qs.filter(invoice_date__gte=s_date, invoice_date__lte=e_date)
        period_expenses_qs = expenses_all_qs.filter(date__gte=s_date, date__lte=e_date)
    else:
        period_leads_qs = leads_all_qs
        period_incomes_qs = incomes_all_qs
        period_invoices_qs = invoices_all_qs
        period_expenses_qs = expenses_all_qs

    if prev_start_date and prev_end_date:
        prev_s_date = prev_start_date.date()
        prev_e_date = prev_end_date.date()
        prev_leads_qs = leads_all_qs.filter(created_at__gte=prev_start_date, created_at__lt=prev_end_date)
        prev_incomes_qs = incomes_all_qs.filter(date__gte=prev_s_date, date__lt=prev_e_date)
        prev_invoices_qs = invoices_all_qs.filter(invoice_date__gte=prev_s_date, invoice_date__lt=prev_e_date)
    else:
        prev_leads_qs = None
        prev_incomes_qs = None
        prev_invoices_qs = None

    # 1. Total Revenue & Finance Aggregates (Real financial data from Incomes & Invoices)
    inc_sum = float(period_incomes_qs.aggregate(Sum('amount'))['amount__sum'] or 0.0)
    inv_billed_sum = float(period_invoices_qs.aggregate(Sum('grand_total'))['grand_total__sum'] or 0.0)
    inv_paid_sum = float(period_invoices_qs.aggregate(Sum('amount_paid'))['amount_paid__sum'] or 0.0)
    inv_due_sum = float(period_invoices_qs.aggregate(Sum('balance_due'))['balance_due__sum'] or 0.0)
    exp_sum = float(period_expenses_qs.aggregate(Sum('amount'))['amount__sum'] or 0.0)

    # All-time aggregates for complete context
    all_time_income = float(incomes_all_qs.aggregate(Sum('amount'))['amount__sum'] or 0.0)
    all_time_invoiced = float(invoices_all_qs.aggregate(Sum('grand_total'))['grand_total__sum'] or 0.0)
    all_time_paid = float(invoices_all_qs.aggregate(Sum('amount_paid'))['amount_paid__sum'] or 0.0)
    all_time_due = float(invoices_all_qs.aggregate(Sum('balance_due'))['balance_due__sum'] or 0.0)
    all_time_expenses = float(expenses_all_qs.aggregate(Sum('amount'))['amount__sum'] or 0.0)
    all_time_profit = (all_time_income if all_time_income > 0 else all_time_paid) - all_time_expenses

    # Total Revenue prioritizes real Income received, else Invoice billing, else won lead values
    if inc_sum > 0:
        total_revenue = inc_sum
    elif inv_billed_sum > 0:
        total_revenue = inv_billed_sum
    else:
        won_leads_period = period_leads_qs.filter(stage='Won')
        total_revenue = float(won_leads_period.aggregate(Sum('value'))['value__sum'] or 0.0)

    total_invoiced = inv_billed_sum if period != 'all' else all_time_invoiced
    total_invoiced_paid = inv_paid_sum if period != 'all' else all_time_paid
    total_invoiced_due = inv_due_sum if period != 'all' else all_time_due
    total_expenses = exp_sum if period != 'all' else all_time_expenses
    net_profit = (inc_sum if inc_sum > 0 else inv_paid_sum) - exp_sum if period != 'all' else all_time_profit

    # Revenue Trend
    if prev_incomes_qs is not None:
        prev_rev = float(prev_incomes_qs.aggregate(Sum('amount'))['amount__sum'] or 0.0)
        if prev_rev == 0:
            prev_rev = float(prev_invoices_qs.aggregate(Sum('grand_total'))['grand_total__sum'] or 0.0)
        if prev_rev > 0:
            revenue_trend = round(((total_revenue - prev_rev) / prev_rev) * 100, 1)
        else:
            revenue_trend = 100.0 if total_revenue > 0 else 0.0
    else:
        first_day_this_month = today_start.replace(day=1)
        last_day_last_month = first_day_this_month - timedelta(days=1)
        first_day_last_month = last_day_last_month.replace(day=1)
        rev_m1 = float(incomes_all_qs.filter(date__gte=first_day_this_month.date()).aggregate(Sum('amount'))['amount__sum'] or 0.0)
        rev_m2 = float(incomes_all_qs.filter(date__gte=first_day_last_month.date(), date__lt=first_day_this_month.date()).aggregate(Sum('amount'))['amount__sum'] or 0.0)
        if rev_m1 == 0 and rev_m2 == 0:
            rev_m1 = float(invoices_all_qs.filter(invoice_date__gte=first_day_this_month.date()).aggregate(Sum('grand_total'))['grand_total__sum'] or 0.0)
            rev_m2 = float(invoices_all_qs.filter(invoice_date__gte=first_day_last_month.date(), invoice_date__lt=first_day_this_month.date()).aggregate(Sum('grand_total'))['grand_total__sum'] or 0.0)
        if rev_m1 == 0 and rev_m2 > 0:
            month_before = (first_day_last_month - timedelta(days=1)).replace(day=1)
            rev_m0 = float(incomes_all_qs.filter(date__gte=month_before.date(), date__lt=first_day_last_month.date()).aggregate(Sum('amount'))['amount__sum'] or 0.0)
            revenue_trend = round(((rev_m2 - rev_m0) / rev_m0 * 100) if rev_m0 > 0 else 0.0, 1)
        else:
            revenue_trend = round(((rev_m1 - rev_m2) / rev_m2 * 100) if rev_m2 > 0 else (100.0 if rev_m1 > 0 else 0.0), 1)

    # 2. Total Leads (Active Prospects)
    total_leads = period_leads_qs.filter(is_client=False).count()
    first_day_this_month = today_start.replace(day=1)
    leads_this_month = leads_all_qs.filter(is_client=False, created_at__gte=first_day_this_month).count()
    
    if prev_leads_qs is not None:
        prev_leads_count = prev_leads_qs.filter(is_client=False).count()
        if prev_leads_count > 0:
            leads_trend = round(((total_leads - prev_leads_count) / prev_leads_count) * 100, 1)
        else:
            leads_trend = 100.0 if total_leads > 0 else 0.0
    else:
        last_day_last_month = first_day_this_month - timedelta(days=1)
        first_day_last_month = last_day_last_month.replace(day=1)
        leads_last_month = leads_all_qs.filter(is_client=False, created_at__gte=first_day_last_month, created_at__lt=first_day_this_month).count()
        leads_trend = round(((leads_this_month - leads_last_month) / leads_last_month * 100) if leads_last_month > 0 else (100.0 if leads_this_month > 0 else 0.0), 1)

    # 3. Conversion Rate (All Accounts converted to Clients)
    total_clients_in_period = period_leads_qs.filter(is_client=True).count()
    all_accounts_in_period = period_leads_qs.count()
    if period == 'all' or all_accounts_in_period == 0:
        total_accounts_count = leads_all_qs.count()
        total_clients_count = leads_all_qs.filter(is_client=True).count()
        conversion_rate = round((total_clients_count / total_accounts_count * 100) if total_accounts_count > 0 else 0.0, 1)
    else:
        conversion_rate = round((total_clients_in_period / all_accounts_in_period * 100) if all_accounts_in_period > 0 else 0.0, 1)
    conversion_trend = 0.0

    # 4. Tasks (Includes organization tasks + lead tasks)
    tasks_qs = tasks_all_qs
    active_tasks_count = tasks_qs.filter(completed=False).count()
    completed_tasks_count = tasks_qs.filter(completed=True).count()
    tasks_due_today = tasks_qs.filter(completed=False, due_date=today_start.date()).count() if hasattr(Task, 'due_date') else 0
    total_tasks_count = tasks_qs.count()
    task_completion_rate = round((completed_tasks_count / total_tasks_count * 100) if total_tasks_count > 0 else 0.0, 1)

    pending_tasks_list = []
    for t in tasks_qs.filter(completed=False).order_by('due_date', '-created_at')[:8]:
        pending_tasks_list.append({
            'id': t.id,
            'title': t.title,
            'lead_name': t.lead.name if t.lead else 'Internal Company Task',
            'lead_id': t.lead.id if t.lead else None,
            'due_date': t.due_date.strftime('%b %d') if hasattr(t, 'due_date') and t.due_date else None,
            'is_overdue': bool(hasattr(t, 'due_date') and t.due_date and t.due_date < today_start.date()),
            'priority': getattr(t, 'priority', 'Normal') or 'Normal',
        })

    # 5. Sales Documents
    quotation_count = quotations_all_qs.count()
    agreement_count = agreements_all_qs.count()
    invoice_count = invoices_all_qs.count()

    # 6. Active Deals & Calculated Pipeline Value (Includes services pricing if value is blank)
    active_deals_qs = leads_all_qs.filter(is_client=False).exclude(stage__in=['Won', 'Lost'])
    active_deals_count = active_deals_qs.count()
    active_deals_value = 0.0
    for lead in active_deals_qs:
        if lead.value and float(lead.value) > 0:
            active_deals_value += float(lead.value)
        else:
            srv_sum = float(lead.services.aggregate(Sum('price'))['price__sum'] or 0.0)
            active_deals_value += srv_sum

    # 7. Total Clients & Retained Portfolio Value
    total_clients_count = leads_all_qs.filter(is_client=True).count()
    active_clients_count = leads_all_qs.filter(is_client=True).exclude(status='Lost').count()
    new_clients_this_month = leads_all_qs.filter(is_client=True, created_at__gte=first_day_this_month).count()
    new_clients_in_period = period_leads_qs.filter(is_client=True).count()
    client_portfolio_value = 0.0
    for cl in leads_all_qs.filter(is_client=True):
        if cl.value and float(cl.value) > 0:
            client_portfolio_value += float(cl.value)
        else:
            srv_sum = float(cl.services.aggregate(Sum('price'))['price__sum'] or 0.0)
            client_portfolio_value += srv_sum

    # Marketing Campaigns Overview
    campaigns_count = campaigns_all_qs.count()
    active_campaigns_count = campaigns_all_qs.filter(status='Active').count()
    total_campaign_budget = float(campaigns_all_qs.aggregate(Sum('budget'))['budget__sum'] or 0.0)

    # 8. Real Leads Sparkline (Always lively and informative)
    sparkline_labels = []
    sparkline_values = []
    recent_7d_count = leads_all_qs.filter(is_client=False, created_at__gte=today_start - timedelta(days=7)).count()
    if recent_7d_count > 0:
        for i in range(6, -1, -1):
            day_date = today_start.date() - timedelta(days=i)
            day_start = timezone.make_aware(datetime.combine(day_date, datetime.min.time()))
            day_end = timezone.make_aware(datetime.combine(day_date, datetime.max.time()))
            day_cnt = leads_all_qs.filter(is_client=False, created_at__gte=day_start, created_at__lte=day_end).count()
            sparkline_labels.append(day_date.strftime('%a'))
            sparkline_values.append(day_cnt)
    else:
        for i in range(6, -1, -1):
            w_start = today_start - timedelta(weeks=i+1)
            w_end = today_start - timedelta(weeks=i)
            w_cnt = leads_all_qs.filter(is_client=False, created_at__gte=w_start, created_at__lt=w_end).count()
            sparkline_labels.append(f"W{7-i}")
            sparkline_values.append(w_cnt)

    # 9. Dynamic Revenue & Performance Chart Series (Incomes, Invoices, Won Clients & Leads)
    trend_labels = []
    trend_revenue = []
    trend_deals = []
    trend_leads = []

    if chart_range == '7d':
        for i in range(6, -1, -1):
            d = today_start.date() - timedelta(days=i)
            d_start = timezone.make_aware(datetime.combine(d, datetime.min.time()))
            d_end = timezone.make_aware(datetime.combine(d, datetime.max.time()))
            d_rev = float(incomes_all_qs.filter(date=d).aggregate(Sum('amount'))['amount__sum'] or 0.0)
            if d_rev == 0:
                d_rev = float(invoices_all_qs.filter(invoice_date=d).aggregate(Sum('grand_total'))['grand_total__sum'] or 0.0)
            d_cnt = leads_all_qs.filter(is_client=True, created_at__gte=d_start, created_at__lte=d_end).count()
            d_leads_cnt = leads_all_qs.filter(is_client=False, created_at__gte=d_start, created_at__lte=d_end).count()
            
            trend_labels.append(d.strftime('%b %d'))
            trend_revenue.append(d_rev)
            trend_deals.append(d_cnt)
            trend_leads.append(d_leads_cnt)
    elif chart_range == '30d':
        for i in range(29, -1, -1):
            d = today_start.date() - timedelta(days=i)
            d_start = timezone.make_aware(datetime.combine(d, datetime.min.time()))
            d_end = timezone.make_aware(datetime.combine(d, datetime.max.time()))
            d_rev = float(incomes_all_qs.filter(date=d).aggregate(Sum('amount'))['amount__sum'] or 0.0)
            if d_rev == 0:
                d_rev = float(invoices_all_qs.filter(invoice_date=d).aggregate(Sum('grand_total'))['grand_total__sum'] or 0.0)
            d_cnt = leads_all_qs.filter(is_client=True, created_at__gte=d_start, created_at__lte=d_end).count()
            d_leads_cnt = leads_all_qs.filter(is_client=False, created_at__gte=d_start, created_at__lte=d_end).count()
            
            trend_labels.append(d.strftime('%b %d'))
            trend_revenue.append(d_rev)
            trend_deals.append(d_cnt)
            trend_leads.append(d_leads_cnt)
    elif chart_range == '1y':
        for i in range(11, -1, -1):
            m_date = (today_start.replace(day=1) - timedelta(days=i*30)).replace(day=1)
            if m_date.month == 12:
                next_m = m_date.replace(year=m_date.year+1, month=1)
            else:
                next_m = m_date.replace(month=m_date.month+1)
            m_rev = float(incomes_all_qs.filter(date__gte=m_date.date(), date__lt=next_m.date()).aggregate(Sum('amount'))['amount__sum'] or 0.0)
            if m_rev == 0:
                m_rev = float(invoices_all_qs.filter(invoice_date__gte=m_date.date(), invoice_date__lt=next_m.date()).aggregate(Sum('grand_total'))['grand_total__sum'] or 0.0)
            m_cnt = leads_all_qs.filter(is_client=True, created_at__gte=m_date, created_at__lt=next_m).count()
            m_leads_cnt = leads_all_qs.filter(is_client=False, created_at__gte=m_date, created_at__lt=next_m).count()
            
            trend_labels.append(m_date.strftime('%b %y').upper())
            trend_revenue.append(m_rev)
            trend_deals.append(m_cnt)
            trend_leads.append(m_leads_cnt)
    else: # '6m' default or 'all'
        for i in range(5, -1, -1):
            m_date = (today_start.replace(day=1) - timedelta(days=i*30)).replace(day=1)
            if m_date.month == 12:
                next_m = m_date.replace(year=m_date.year+1, month=1)
            else:
                next_m = m_date.replace(month=m_date.month+1)
            m_rev = float(incomes_all_qs.filter(date__gte=m_date.date(), date__lt=next_m.date()).aggregate(Sum('amount'))['amount__sum'] or 0.0)
            if m_rev == 0:
                m_rev = float(invoices_all_qs.filter(invoice_date__gte=m_date.date(), invoice_date__lt=next_m.date()).aggregate(Sum('grand_total'))['grand_total__sum'] or 0.0)
            m_cnt = leads_all_qs.filter(is_client=True, created_at__gte=m_date, created_at__lt=next_m).count()
            m_leads_cnt = leads_all_qs.filter(is_client=False, created_at__gte=m_date, created_at__lt=next_m).count()
            
            trend_labels.append(m_date.strftime('%b').upper())
            trend_revenue.append(m_rev)
            trend_deals.append(m_cnt)
            trend_leads.append(m_leads_cnt)

    # 10. Funnel Stats
    client_statuses = get_or_create_dynamic_statuses(org, 'clients', ClientStatus)
    funnel_items = []
    prospects_count = 0
    if client_statuses.exists():
        prospects_count = period_leads_qs.filter(is_client=True, status=client_statuses.first().name).count()
        if prospects_count == 0:
            prospects_count = period_leads_qs.filter(is_client=True).count()
        
    for idx, cs in enumerate(client_statuses):
        count = period_leads_qs.filter(is_client=True, status=cs.name).count()
        if idx == 0:
            rate = 100.0 if count > 0 else 0.0
        else:
            rate = (count / prospects_count * 100) if prospects_count > 0 else 0.0
            
        funnel_items.append({
            'name': cs.name,
            'color': cs.color_hex or '#2563eb',
            'count': count,
            'rate': round(rate, 1)
        })

    # 11. Leads by Service Distribution
    services_qs = Service.objects.filter(organization=org)
    service_labels = []
    service_data = []
    for s in services_qs:
        count = period_leads_qs.filter(services=s).count()
        if count > 0:
            service_labels.append(s.name)
            service_data.append(count)
    if not service_labels:
        service_labels = ["General / Uncategorized"]
        service_data = [period_leads_qs.count() or 0]

    # 12. Leads by Stage Distribution
    stage_counts = {}
    for stage_choice in ['New', 'Contacted', 'Qualified', 'Discussion', 'Proposal', 'Won', 'Lost']:
        cnt = period_leads_qs.filter(stage=stage_choice).count()
        if cnt > 0:
            stage_counts[stage_choice] = cnt
    stage_labels = list(stage_counts.keys()) or ['New']
    stage_data = list(stage_counts.values()) or [0]

    # 13. Recent Leads
    recent_leads_qs = period_leads_qs.filter(is_client=False).order_by('-created_at')[:8]
    recent_leads_data = []
    for l in recent_leads_qs:
        recent_leads_data.append({
            'id': l.id,
            'name': l.name,
            'email': l.email or '',
            'company': l.company or '',
            'stage': l.stage or 'New',
            'value': float(l.value or 0),
            'profile_image_url': l.profile_image_url if hasattr(l, 'profile_image_url') and l.profile_image_url else None,
            'created_at_formatted': l.created_at.strftime('%b %d, %Y') if l.created_at else '',
        })

    # 14. Recent Activities
    recent_activities_qs = Activity.objects.filter(lead__organization=org).order_by('-timestamp')[:6]
    recent_activities_data = []
    for a in recent_activities_qs:
        recent_activities_data.append({
            'description': a.description,
            'lead_name': a.lead.name if a.lead else 'General',
            'timestamp_str': a.timestamp.strftime('%d %b, %H:%M') if a.timestamp else '',
            'timesince': f"{int((now - a.timestamp).total_seconds() // 60)}m ago" if a.timestamp and (now - a.timestamp).total_seconds() < 3600 else (f"{int((now - a.timestamp).total_seconds() // 3600)}h ago" if a.timestamp and (now - a.timestamp).total_seconds() < 86400 else (a.timestamp.strftime('%b %d') if a.timestamp else '')),
        })

    # 15. Upcoming Meetings
    upcoming_meetings_qs = Event.objects.filter(
        organization=org, 
        start_time__gte=timezone.now(),
        color__in=['#004ac6', '#10b981']
    ).order_by('start_time')[:4]
    
    upcoming_meetings_data = []
    for m in upcoming_meetings_qs:
        upcoming_meetings_data.append({
            'title': m.title,
            'month': m.start_time.strftime('%b'),
            'day': m.start_time.strftime('%d'),
            'time_str': m.start_time.strftime('%I:%M %p'),
            'owner_name': m.owner.get_full_name() or m.owner.username if m.owner else 'Team',
        })

    # If AJAX request, return structured JSON
    if is_ajax:
        return JsonResponse({
            'success': True,
            'period': period,
            'chart_range': chart_range,
            'chart_metric': chart_metric,
            'metrics': {
                'total_revenue': total_revenue,
                'revenue_trend': revenue_trend,
                'total_invoiced': total_invoiced,
                'total_invoiced_paid': total_invoiced_paid,
                'total_invoiced_due': total_invoiced_due,
                'total_expenses': total_expenses,
                'net_profit': net_profit,
                'total_leads': total_leads,
                'leads_trend': leads_trend,
                'leads_this_month': leads_this_month,
                'conversion_rate': conversion_rate,
                'conversion_trend': conversion_trend,
                'active_tasks_count': active_tasks_count,
                'completed_tasks_count': completed_tasks_count,
                'tasks_due_today': tasks_due_today,
                'task_completion_rate': task_completion_rate,
                'active_deals_count': active_deals_count,
                'active_deals_value': active_deals_value,
                'total_clients_count': total_clients_count,
                'active_clients_count': active_clients_count,
                'new_clients_this_month': new_clients_this_month,
                'new_clients_in_period': new_clients_in_period,
                'client_portfolio_value': client_portfolio_value,
                'quotation_count': quotation_count,
                'agreement_count': agreement_count,
                'invoice_count': invoice_count,
                'campaigns_count': campaigns_count,
                'active_campaigns_count': active_campaigns_count,
                'total_campaign_budget': total_campaign_budget,
            },
            'sparkline': {
                'labels': sparkline_labels,
                'values': sparkline_values,
            },
            'chart': {
                'labels': trend_labels,
                'revenue': trend_revenue,
                'deals': trend_deals,
                'leads': trend_leads,
            },
            'funnel': funnel_items,
            'services': {
                'labels': service_labels,
                'data': service_data,
            },
            'stages': {
                'labels': stage_labels,
                'data': stage_data,
            },
            'recent_leads': recent_leads_data,
            'pending_tasks': pending_tasks_list,
            'recent_activities': recent_activities_data,
            'upcoming_meetings': upcoming_meetings_data,
        })

    context = {
        'period': period,
        'chart_range': chart_range,
        'chart_metric': chart_metric,
        'revenue_trend': revenue_trend,
        'leads_trend': leads_trend,
        'conversion_trend': conversion_trend,
        'total_revenue': total_revenue,
        'total_invoiced': total_invoiced,
        'total_invoiced_paid': total_invoiced_paid,
        'total_invoiced_due': total_invoiced_due,
        'total_expenses': total_expenses,
        'net_profit': net_profit,
        'total_leads': total_leads,
        'leads_this_month': leads_this_month,
        'conversion_rate': conversion_rate,
        'active_tasks_count': active_tasks_count,
        'completed_tasks_count': completed_tasks_count,
        'tasks_due_today': tasks_due_today,
        'task_completion_rate': task_completion_rate,
        'active_deals_count': active_deals_count,
        'active_deals_value': active_deals_value,
        'total_clients_count': total_clients_count,
        'active_clients_count': active_clients_count,
        'new_clients_this_month': new_clients_this_month,
        'new_clients_in_period': new_clients_in_period,
        'client_portfolio_value': client_portfolio_value,
        'quotation_count': quotation_count,
        'agreement_count': agreement_count,
        'invoice_count': invoice_count,
        'campaigns_count': campaigns_count,
        'active_campaigns_count': active_campaigns_count,
        'total_campaign_budget': total_campaign_budget,
        'new_leads': recent_leads_qs,
        'pending_tasks': pending_tasks_list,
        'recent_activities': recent_activities_qs,
        'upcoming_meetings': upcoming_meetings_qs,
        'funnel_items': funnel_items,
        'sparkline_labels': json.dumps(sparkline_labels),
        'sparkline_values': json.dumps(sparkline_values),
        'trend_labels': json.dumps(trend_labels),
        'trend_values': json.dumps(trend_revenue),
        'trend_deals': json.dumps(trend_deals),
        'trend_leads': json.dumps(trend_leads),
        'service_labels': json.dumps(service_labels),
        'service_data': json.dumps(service_data),
        'stage_labels': json.dumps(stage_labels),
        'stage_data': json.dumps(stage_data),
    }
    
    return render(request, 'dashboard.html', context)




# ==============================================================================
# 2. DYNAMIC STATUS MANAGEMENT DISPATCHER
# ==============================================================================
CATEGORY_PERM_MAP = {
    'leads': 'lead_statuses',
    'clients': 'clients_status',
    'projects': 'projects_status',
    'campaigns': 'campaigns_status',
    'calendar': 'calendar_status',
    'tickets': 'support_status',
    'support': 'support_status',
    'priority': 'support_status',
    'ticket_priorities': 'support_status',
    'invoices': 'finance_status',
}

def get_dynamic_model_class(category):
    return {
        'clients': ClientStatus,
        'projects': ProjectStatus,
        'campaigns': CampaignStatus,
        'calendar': CalendarStatus,
        'tickets': TicketStatus,
        'priority': PriorityStatus,
        'ticket_priorities': PriorityStatus,
        'invoices': InvoiceStatus,
    }.get(category)

def check_dynamic_status_perm(request, category):
    if request.user and request.user.is_superuser:
        return True
    profile = getattr(request.user, 'profile', None)
    if not profile:
        return False
    perm_name = CATEGORY_PERM_MAP.get(category, 'lead_statuses')
    return profile.check_page_permission(perm_name) or profile.check_page_permission('leads_settings') or profile.check_page_permission('settings')

@login_required
def add_dynamic_status(request, category):
    if request.method == 'POST':
        if not check_dynamic_status_perm(request, category):
            return JsonResponse({'success': False, 'error': 'You do not have permission for this action.'}, status=403)
        org = request.user.profile.organization
        model_class = get_dynamic_model_class(category)
        if not model_class:
            return JsonResponse({'success': False, 'error': 'Invalid category.'})
        
        name = request.POST.get('name', '').strip()
        color = request.POST.get('color', '#64748b')
        if not name:
            return JsonResponse({'success': False, 'error': 'Status name is required.'})
        if model_class.objects.filter(organization=org, name=name).exists():
            return JsonResponse({'success': False, 'error': f"Status '{name}' already exists."})
        
        max_pos = model_class.objects.filter(organization=org).count()
        model_class.objects.create(organization=org, name=name, color=color, position=max_pos)
        return JsonResponse({'success': True, 'message': f"Status '{name}' created."})
    return JsonResponse({'success': False, 'error': 'Invalid request method.'})

@login_required
def edit_dynamic_status(request, category, status_id):
    if request.method == 'POST':
        if not check_dynamic_status_perm(request, category):
            return JsonResponse({'success': False, 'error': 'You do not have permission for this action.'}, status=403)
        org = request.user.profile.organization
        model_class = get_dynamic_model_class(category)
        if not model_class:
            return JsonResponse({'success': False, 'error': 'Invalid category.'})
        
        try:
            status_obj = model_class.objects.get(id=status_id, organization=org)
        except model_class.DoesNotExist:
            return JsonResponse({'success': False, 'error': 'Status not found.'})
            
        new_name = request.POST.get('name', '').strip()
        new_color = request.POST.get('color', status_obj.color)
        if not new_name:
            return JsonResponse({'success': False, 'error': 'Status name is required.'})
        if model_class.objects.filter(organization=org, name=new_name).exclude(id=status_id).exists():
            return JsonResponse({'success': False, 'error': f"Status '{new_name}' already exists."})
            
        status_obj.name = new_name
        status_obj.color = new_color
        status_obj.save()
        return JsonResponse({'success': True, 'message': f"Status updated to '{new_name}'."})
    return JsonResponse({'success': False, 'error': 'Invalid request method.'})

@login_required
def delete_dynamic_status(request, category, status_id):
    if request.method == 'POST':
        if not check_dynamic_status_perm(request, category):
            return JsonResponse({'success': False, 'error': 'You do not have permission for this action.'}, status=403)
        org = request.user.profile.organization
        model_class = get_dynamic_model_class(category)
        if not model_class:
            return JsonResponse({'success': False, 'error': 'Invalid category.'})
            
        try:
            status_obj = model_class.objects.get(id=status_id, organization=org)
        except model_class.DoesNotExist:
            return JsonResponse({'success': False, 'error': 'Status not found.'})
            
        if model_class.objects.filter(organization=org).count() <= 1:
            return JsonResponse({'success': False, 'error': 'Cannot delete the last remaining status.'})
            
        deleted_name = status_obj.name
        status_obj.delete()
        return JsonResponse({'success': True, 'message': f"Status '{deleted_name}' deleted."})
    return JsonResponse({'success': False, 'error': 'Invalid request method.'})

@login_required
def reorder_dynamic_statuses(request, category):
    if request.method == 'POST':
        if not check_dynamic_status_perm(request, category):
            return JsonResponse({'success': False, 'error': 'You do not have permission for this action.'}, status=403)
        import json
        org = request.user.profile.organization
        model_class = get_dynamic_model_class(category)
        if not model_class:
            return JsonResponse({'success': False, 'error': 'Invalid category.'})
            
        try:
            body = json.loads(request.body)
            order = body.get('order', [])
        except (json.JSONDecodeError, AttributeError):
            order = request.POST.getlist('order[]')
            
        for idx, sid in enumerate(order):
            model_class.objects.filter(id=sid, organization=org).update(position=idx)
        return JsonResponse({'success': True, 'message': 'Statuses reordered.'})
    return JsonResponse({'success': False, 'error': 'Invalid request method.'})

@login_required
def generic_status_settings_view(request, category, model_class, category_title, add_url, edit_url_prefix, delete_url_prefix, reorder_url):
    org = request.user.profile.organization
    if category == 'leads':
        statuses = get_or_create_default_statuses(org)
    else:
        statuses = get_or_create_dynamic_statuses(org, category, model_class)
    
    return render(request, 'generic_status_settings.html', {
        'category_title': category_title,
        'statuses': statuses,
        'add_url': add_url,
        'edit_url_prefix': edit_url_prefix,
        'delete_url_prefix': delete_url_prefix,
        'reorder_url': reorder_url
    })




# ==============================================================================
# 3. OFFLINE VIEW
# ==============================================================================
def offline_view(request):
    """Offline page rendered when user loses internet connection."""
    return render(request, 'offline.html')


# ==============================================================================
# 4. RE-EXPORTS FROM MODULAR APPS (FOR BACKWARD COMPATIBILITY)
# ==============================================================================
from core.permissions import page_permission_required

from core.views import *
from leads.views import *
from services.views import *
from support.views import *
from projects.views import *
from activities.views import *
from campaigns.views import *
from content_tracker.views import *
from finance.views import *
from finance.invoice_views import *
from finance.document_views import *

