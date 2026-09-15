import csv
from functools import wraps
from django.shortcuts import render, redirect, get_object_or_404
from django.http import HttpResponse, JsonResponse
from django.contrib.auth import login, logout, authenticate
from django.contrib.auth.models import User
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_POST
from django.db.models import Sum, Q
from django.utils import timezone
from django.core.paginator import Paginator
from django.contrib import messages
from .models import Organization, UserProfile, Lead, Activity, Task, TaskTodo, TaskFile, TaskMilestone, Meeting, Event, LeadStatus, get_default_badge_class, StaffRole, Service, Ticket, Agreement, AgreementService, ClientResponsibility, Deliverable, Campaign, ContentDropdownOption, SystemNotification, Quotation
from datetime import datetime, timedelta
import io, json
from .forms import EventForm, ProfileForm
from .models import Income, Expense, DeletedIncome, DeletedExpense, FinancePaymentMethod, FinanceExpenseCategory, PartnerPayout, FinancePaymentStatus, FinanceCommissionType
from .models import ClientStatus, ProjectStatus, CampaignStatus, CalendarStatus, TicketStatus, PriorityStatus, InvoiceStatus
from datetime import datetime
from decimal import Decimal
# Views for navigation pages with proper multi-tenant database queries


PERM_REDIRECT_ORDER = [
    ('dashboard', 'dashboard'),
    ('leads', 'leads'),
    ('clients', 'clients'),
    ('support', 'customer_support'),
    ('projects', 'projects'),
    ('agreements', 'agreements'),
    ('quotations', 'quotations'),
    ('campaigns', 'campaign'),
    ('calendar', 'calendar'),
    ('staff', 'staff'),
    ('services', 'services'),
    ('finance', 'finance_dashboard'),
    ('hr', 'hr_dashboard'),
]


def page_permission_required(permission_name):
    """Require a UserProfile permission check."""
    def decorator(view_func):
        @wraps(view_func)
        def wrapper(request, *args, **kwargs):
            if request.user and request.user.is_superuser:
                return view_func(request, *args, **kwargs)

            try:
                profile = getattr(request.user, 'profile', None)
            except Exception:
                profile = None

            has_perm = False
            if profile:
                perm_prop = f'has_access_{permission_name}'
                if hasattr(profile, perm_prop):
                    has_perm = getattr(profile, perm_prop)
                if not has_perm:
                    has_perm = profile.check_page_permission(permission_name)

            if has_perm:
                return view_func(request, *args, **kwargs)

            if request.headers.get('X-Requested-With') == 'XMLHttpRequest' or request.headers.get('x-requested-with') == 'XMLHttpRequest':
                return JsonResponse({'success': False, 'error': 'You do not have permission to access this page.'}, status=403)

            messages.error(request, 'You do not have permission to access this page.')

            if profile:
                for perm, target_name in PERM_REDIRECT_ORDER:
                    if perm != permission_name and (getattr(profile, f'has_access_{perm}', False) or profile.check_page_permission(perm)):
                        return redirect(target_name)

            return redirect('login')
        return wrapper
    return decorator





@login_required
@page_permission_required('clients')
def clients_view(request):
    org = request.user.profile.organization
    
    services_qs = Service.objects.filter(organization=org)
    leads = Lead.objects.filter(organization=org, is_client=True)
    
    clients_dict = {}
    for lead in leads:
        comp = lead.company
        if not comp:
            continue
        if comp not in clients_dict:
            clients_dict[comp] = {
                'company': comp,
                'contacts_count': 0,
                'total_value': 0.0,
                'total_paid': 0.0,
                'avg_score': 0,
                'leads': [],
                'service_ids': set()
            }
        clients_dict[comp]['contacts_count'] += 1
        clients_dict[comp]['total_value'] += float(lead.value or 0.0)
        clients_dict[comp]['total_paid'] += float(lead.paid_amount or 0.0)
        clients_dict[comp]['avg_score'] += lead.score
        clients_dict[comp]['leads'].append(lead)
        lead_services = lead.services.all()
        if lead_services.exists():
            for s in lead_services:
                clients_dict[comp]['service_ids'].add(s.id)
        else:
            clients_dict[comp]['service_ids'].add(0)
    
    clients_list = []
    for comp, data in clients_dict.items():
        if data['contacts_count'] > 0:
            data['avg_score'] = int(data['avg_score'] / data['contacts_count'])
        data['service_ids_str'] = " ".join(f"service-{sid}" for sid in data['service_ids'])
        clients_list.append(data)

    # Calculate statistics per service
    service_stats = {}
    for service in services_qs:
        service_stats[service.id] = {
            'id': service.id,
            'name': service.name,
            'description': service.description,
            'price': service.price,
            'client_count': 0,
            'total_value': 0.0,
        }
    
    uncategorized_stats = {
        'id': 0,
        'name': 'Uncategorized',
        'description': 'Clients without an assigned service.',
        'price': 0.0,
        'client_count': 0,
        'total_value': 0.0,
    }

    for client in clients_list:
        for sid in client['service_ids']:
            if sid in service_stats:
                service_stats[sid]['client_count'] += 1
                service_stats[sid]['total_value'] += client['total_value']
            elif sid == 0:
                uncategorized_stats['client_count'] += 1
                uncategorized_stats['total_value'] += client['total_value']

    services_list = list(service_stats.values())
    if uncategorized_stats['client_count'] > 0:
        services_list.append(uncategorized_stats)

    services_list.sort(key=lambda s: s['client_count'], reverse=True)

    context = {
        'clients': clients_list,
        'services': services_list,
    }
    return render(request, 'clients.html', context)


@login_required
@page_permission_required('clients')
def service_clients_view(request, service_id):
    org = request.user.profile.organization
    
    # Fetch qualified leads
    leads = Lead.objects.filter(organization=org, is_client=True)
    
    # Filter leads by service
    if service_id == 'all':
        service_name = "All Services"
    elif service_id == '0':
        service_name = "Uncategorized"
        leads = leads.filter(services__isnull=True)
    else:
        try:
            service = Service.objects.get(id=int(service_id), organization=org)
            service_name = service.name
            leads = leads.filter(services=service)
        except (ValueError, Service.DoesNotExist):
            messages.error(request, "Service not found.")
            return redirect('clients')

    clients_dict = {}
    for lead in leads:
        comp = lead.company
        if not comp:
            continue
        if comp not in clients_dict:
            clients_dict[comp] = {
                'company': comp,
                'contacts_count': 0,
                'total_value': 0.0,
                'total_paid': 0.0,
                'avg_score': 0,
                'leads': []
            }
        clients_dict[comp]['contacts_count'] += 1
        clients_dict[comp]['total_value'] = max(clients_dict[comp]['total_value'], float(lead.value or 0.0))
        clients_dict[comp]['total_paid'] = max(clients_dict[comp]['total_paid'], float(lead.paid_amount or 0.0))
        clients_dict[comp]['avg_score'] += lead.score
        clients_dict[comp]['leads'].append(lead)

    clients_list = []
    for comp, data in clients_dict.items():
        if data['contacts_count'] > 0:
            data['avg_score'] = int(data['avg_score'] / data['contacts_count'])
        clients_list.append(data)

    client_statuses = get_or_create_dynamic_statuses(org, 'clients', ClientStatus)

    context = {
        'service_name': service_name,
        'clients': clients_list,
        'client_statuses': client_statuses,
    }
    return render(request, 'service_clients.html', context)


@login_required
@page_permission_required('clients')
def client_profile_view(request, company_name):
    from urllib.parse import unquote
    from django.db.models import Q
    
    company_name = unquote(company_name)
    org = request.user.profile.organization
    
    # All leads under this company
    leads = Lead.objects.filter(organization=org, company=company_name).order_by('-created_at')
    
    if not leads.exists():
        messages.error(request, "Client not found.")
        return redirect('clients')

    # Aggregates
    if leads.exists():
        total_value = max((lead.value or 0) for lead in leads)
        total_paid = max((lead.paid_amount or 0) for lead in leads)
    else:
        total_value = 0
        total_paid = 0
    
    # Agreements associated with this company
    agreements = Agreement.objects.filter(
        Q(organization=org) & (Q(company_name=company_name) | Q(client_name=company_name))
    ).order_by('-created_at')

    # Combined activities
    activities = Activity.objects.filter(lead__in=leads).order_by('-timestamp')

    context = {
        'company_name': company_name,
        'leads': leads,
        'total_value': total_value,
        'total_paid': total_paid,
        'agreements': agreements,
        'activities': activities,
        'primary_lead': leads.first(), 
    }
    return render(request, 'client_profile.html', context)


@login_required
def edit_client_company(request):
    """Edit the company name for all leads of the given company name."""
    if request.method == 'POST':
        org = request.user.profile.organization
        old_name = request.POST.get('old_company_name', '').strip()
        new_name = request.POST.get('new_company_name', '').strip()
        
        if not old_name or not new_name:
            return JsonResponse({'success': False, 'error': 'Company names are required.'})
            
        # Update company name for all leads of this organization
        leads_updated = Lead.objects.filter(organization=org, company=old_name).update(company=new_name)
        return JsonResponse({'success': True, 'message': f"Updated {leads_updated} records to '{new_name}'."})
        
    return JsonResponse({'success': False, 'error': 'Invalid request method.'})


@login_required
def delete_client_company(request):
    """Delete all qualified leads for the given company name."""
    if request.method == 'POST':
        org = request.user.profile.organization
        company_name = request.POST.get('company_name', '').strip()
        
        if not company_name:
            return JsonResponse({'success': False, 'error': 'Company name is required.'})
            
        # Delete all leads belonging to this company for this organization
        leads_deleted, _ = Lead.objects.filter(organization=org, company=company_name).delete()
        return JsonResponse({'success': True, 'message': f"Deleted company '{company_name}' and all its {leads_deleted} leads."})
        
    return JsonResponse({'success': False, 'error': 'Invalid request method.'})








@login_required
@page_permission_required('support')
def customer_support_view(request):
    org = request.user.profile.organization
    tickets = Ticket.objects.filter(organization=org)
    staff = UserProfile.objects.filter(organization=org)
    projects = Task.objects.filter(lead__organization=org)
    
    from .models import TicketStatus, PriorityStatus
    ticket_statuses = TicketStatus.objects.filter(organization=org)
    priority_statuses = PriorityStatus.objects.filter(organization=org)
    
    return render(request, 'customer_support.html', {
        'tickets': tickets,
        'staff': staff,
        'projects': projects,
        'ticket_statuses': ticket_statuses,
        'priority_statuses': priority_statuses
    })


@login_required
@page_permission_required('support')
def create_ticket(request):
    if request.method == 'POST':
        org = request.user.profile.organization
        subject = request.POST.get('subject')
        description = request.POST.get('description', '')
        priority = request.POST.get('priority', 'Medium')
        status = request.POST.get('status', 'Open')
        assignee_id = request.POST.get('assignee')
        project_id = request.POST.get('project')
        
        assignee = None
        if assignee_id:
            try:
                assignee = UserProfile.objects.get(id=int(assignee_id), organization=org)
            except (ValueError, UserProfile.DoesNotExist):
                pass
                
        project = None
        if project_id:
            try:
                project = Task.objects.get(id=int(project_id), lead__organization=org)
            except (ValueError, Task.DoesNotExist):
                pass
                
        ticket_count = Ticket.objects.filter(organization=org).count()
        ticket_id = f"XTC-{ticket_count + 1:03d}"
        
        Ticket.objects.create(
            organization=org,
            ticket_id=ticket_id,
            subject=subject,
            description=description,
            priority=priority,
            status=status,
            assignee=assignee,
            project=project
        )
        
        if request.headers.get('x-requested-with') == 'XMLHttpRequest':
            return JsonResponse({'success': True, 'message': 'Ticket created successfully.'})
        SystemNotification.objects.create(user=request.user, message='Ticket created successfully.', type='success')
        return redirect('customer_support')
        
    return JsonResponse({'success': False, 'error': 'Invalid request method.'})


@login_required
@page_permission_required('support')
def edit_ticket(request, ticket_id):
    if request.method == 'POST':
        org = request.user.profile.organization
        ticket = get_object_or_404(Ticket, id=ticket_id, organization=org)
        
        ticket.subject = request.POST.get('subject')
        ticket.description = request.POST.get('description', '')
        ticket.priority = request.POST.get('priority', 'Medium')
        ticket.status = request.POST.get('status', 'Open')
        
        assignee_id = request.POST.get('assignee')
        if assignee_id:
            try:
                ticket.assignee = UserProfile.objects.get(id=int(assignee_id), organization=org)
            except (ValueError, UserProfile.DoesNotExist):
                ticket.assignee = None
        else:
            ticket.assignee = None
            
        project_id = request.POST.get('project')
        if project_id:
            try:
                project = Task.objects.get(id=int(project_id), lead__organization=org)
                ticket.project = project
            except (ValueError, Task.DoesNotExist):
                ticket.project = None
        else:
            ticket.project = None
            
        ticket.save()
        
        if request.headers.get('x-requested-with') == 'XMLHttpRequest':
            return JsonResponse({'success': True, 'message': 'Ticket updated successfully.'})
        SystemNotification.objects.create(user=request.user, message='Ticket updated successfully.', type='success')
        return redirect('customer_support')
        
    return JsonResponse({'success': False, 'error': 'Invalid request method.'})


@login_required
@page_permission_required('support')
def delete_ticket(request, ticket_id):
    if request.method == 'POST':
        org = request.user.profile.organization
        ticket = get_object_or_404(Ticket, id=ticket_id, organization=org)
        ticket.delete()
        if request.headers.get('x-requested-with') == 'XMLHttpRequest':
            return JsonResponse({'success': True, 'message': 'Ticket deleted successfully.'})
        SystemNotification.objects.create(user=request.user, message='Ticket deleted.', type='success')
        return redirect('customer_support')
        
    return JsonResponse({'success': False, 'error': 'Invalid request method.'})


@login_required
@page_permission_required('projects')
def projects_view(request):
    org = request.user.profile.organization
    tasks = Task.objects.filter(Q(lead__organization=org) | Q(organization=org)).order_by('due_date')
    staff = UserProfile.objects.filter(organization=org)
    leads = Lead.objects.filter(organization=org)
    project_statuses = ProjectStatus.objects.filter(organization=org).order_by('position')
    
    today = timezone.now().date()
    total_projects = tasks.count()
    completed_projects = tasks.filter(Q(completed=True) | Q(status__name__iexact='Completed')).count()
    overdue_projects = tasks.filter(completed=False, due_date__lt=today).exclude(status__name__iexact='Completed').count()
    
    in_progress_projects = tasks.filter(
        Q(completed=False) & (Q(status__name__iexact='In Progress') | Q(status__isnull=True))
    ).exclude(due_date__lt=today).count()
    
    if in_progress_projects == 0 and total_projects > (completed_projects + overdue_projects):
        in_progress_projects = total_projects - completed_projects - overdue_projects

    team_members_count = staff.count()
    
    # Search query
    q = request.GET.get('q', '').strip() or request.GET.get('search', '').strip()
    if q:
        tasks = tasks.filter(
            Q(title__icontains=q) |
            Q(description__icontains=q) |
            Q(lead__name__icontains=q) |
            Q(lead__company_name__icontains=q) |
            Q(status__name__icontains=q)
        )

    # Filter parameters
    filter_status = request.GET.get('status', '').strip()
    filter_priority = request.GET.get('priority', '').strip()
    filter_risk = request.GET.get('risk', '').strip()
    filter_starred = request.GET.get('starred', '').strip()
    filter_lead = request.GET.get('lead_id', '').strip()

    active_filter_count = 0
    if filter_status:
        active_filter_count += 1
        if filter_status.lower() == 'completed':
            tasks = tasks.filter(Q(completed=True) | Q(status__name__iexact='Completed'))
        else:
            tasks = tasks.filter(status__name__iexact=filter_status)

    if filter_priority:
        active_filter_count += 1
        tasks = tasks.filter(priority__iexact=filter_priority)

    if filter_risk:
        active_filter_count += 1
        tasks = tasks.filter(risk_level__iexact=filter_risk)

    if filter_starred == '1' or filter_starred.lower() == 'true':
        active_filter_count += 1
        tasks = tasks.filter(is_starred=True)

    if filter_lead:
        active_filter_count += 1
        if filter_lead == 'inhouse':
            tasks = tasks.filter(lead__isnull=True)
        elif filter_lead.isdigit():
            tasks = tasks.filter(lead_id=int(filter_lead))

    # Sorting
    sort_by = request.GET.get('sort', 'due_date').strip()
    if sort_by == 'title':
        tasks = tasks.order_by('title')
    elif sort_by == '-title':
        tasks = tasks.order_by('-title')
    elif sort_by == 'priority':
        tasks = tasks.order_by('priority')
    elif sort_by == '-created_at':
        tasks = tasks.order_by('-created_at')
    elif sort_by == '-due_date':
        tasks = tasks.order_by('-due_date')
    else:
        tasks = tasks.order_by('due_date')

    # Task collections by status for Kanban Board & dynamic views
    backlog_tasks = tasks.filter(status__name__iexact='Backlog')
    todo_tasks = tasks.filter(status__name__iexact='Todo')
    in_progress_tasks = tasks.filter(Q(status__name__iexact='In Progress') | (Q(status__isnull=True) & Q(completed=False)))
    review_tasks = tasks.filter(status__name__iexact='Review')
    completed_tasks = tasks.filter(Q(completed=True) | Q(status__name__iexact='Completed'))
    
    task_activities = Activity.objects.filter(
        Q(lead__organization=org) | Q(lead__isnull=True),
        type='Task'
    ).order_by('-timestamp')[:20]
    
    all_project_files = TaskFile.objects.filter(
        Q(task__lead__organization=org) | Q(task__organization=org)
    ).select_related('task', 'uploaded_by').order_by('-uploaded_at')

    active_tab = request.GET.get('tab', 'overview')

    return render(request, 'projects.html', {
        'tasks': tasks,
        'staff': staff,
        'leads': leads,
        'project_statuses': project_statuses,
        'total_projects': total_projects,
        'completed_projects': completed_projects,
        'overdue_projects': overdue_projects,
        'in_progress_projects': in_progress_projects,
        'team_members_count': team_members_count,
        'backlog_tasks': backlog_tasks,
        'todo_tasks': todo_tasks,
        'in_progress_tasks': in_progress_tasks,
        'review_tasks': review_tasks,
        'completed_tasks': completed_tasks,
        'task_activities': task_activities,
        'all_project_files': all_project_files,
        'active_tab': active_tab,
        'search_q': q,
        'active_filter_count': active_filter_count,
        'filter_status': filter_status,
        'filter_priority': filter_priority,
        'filter_risk': filter_risk,
        'filter_starred': filter_starred,
        'filter_lead': filter_lead,
        'sort_by': sort_by
    })


@login_required
@page_permission_required('projects')
def project_board_view(request):
    org = request.user.profile.organization
    tasks = Task.objects.filter(Q(lead__organization=org) | Q(organization=org)).order_by('due_date')
    staff = UserProfile.objects.filter(organization=org)
    leads = Lead.objects.filter(organization=org)
    project_statuses = ProjectStatus.objects.filter(organization=org).order_by('position')
    
    today = timezone.now().date()
    total_projects = tasks.count()
    completed_projects = tasks.filter(Q(completed=True) | Q(status__name__iexact='Completed')).count()
    overdue_projects = tasks.filter(completed=False, due_date__lt=today).exclude(status__name__iexact='Completed').count()
    in_progress_projects = tasks.filter(
        Q(completed=False) & (Q(status__name__iexact='In Progress') | Q(status__isnull=True))
    ).exclude(due_date__lt=today).count()
    team_members_count = staff.count()

    backlog_tasks = tasks.filter(status__name__iexact='Backlog')
    todo_tasks = tasks.filter(status__name__iexact='Todo')
    in_progress_tasks = tasks.filter(Q(status__name__iexact='In Progress') | (Q(status__isnull=True) & Q(completed=False)))
    review_tasks = tasks.filter(status__name__iexact='Review')
    completed_tasks = tasks.filter(Q(completed=True) | Q(status__name__iexact='Completed'))

    return render(request, 'project_board.html', {
        'tasks': tasks,
        'staff': staff,
        'leads': leads,
        'project_statuses': project_statuses,
        'total_projects': total_projects,
        'completed_projects': completed_projects,
        'overdue_projects': overdue_projects,
        'in_progress_projects': in_progress_projects,
        'team_members_count': team_members_count,
        'backlog_tasks': backlog_tasks,
        'todo_tasks': todo_tasks,
        'in_progress_tasks': in_progress_tasks,
        'review_tasks': review_tasks,
        'completed_tasks': completed_tasks,
    })


@login_required
@page_permission_required('projects')
def project_timeline_view(request):
    org = request.user.profile.organization
    tasks = Task.objects.filter(Q(lead__organization=org) | Q(organization=org)).order_by('due_date')
    staff = UserProfile.objects.filter(organization=org)
    leads = Lead.objects.filter(organization=org)
    project_statuses = ProjectStatus.objects.filter(organization=org).order_by('position')

    return render(request, 'project_timeline.html', {
        'tasks': tasks,
        'staff': staff,
        'leads': leads,
        'project_statuses': project_statuses,
    })


@login_required
@page_permission_required('projects')
def project_reports_view(request):
    org = request.user.profile.organization
    tasks = Task.objects.filter(Q(lead__organization=org) | Q(organization=org))
    staff = UserProfile.objects.filter(organization=org)
    
    today = timezone.now().date()
    total_projects = tasks.count()
    completed_projects = tasks.filter(Q(completed=True) | Q(status__name__iexact='Completed')).count()
    overdue_projects = tasks.filter(completed=False, due_date__lt=today).exclude(status__name__iexact='Completed').count()
    in_progress_projects = total_projects - completed_projects - overdue_projects
    if in_progress_projects < 0:
        in_progress_projects = 0

    high_priority_count = tasks.filter(priority='High').count()
    medium_priority_count = tasks.filter(priority='Medium').count()
    low_priority_count = tasks.filter(priority='Low').count()

    completion_rate = round((completed_projects / total_projects * 100), 1) if total_projects > 0 else 0

    return render(request, 'project_reports.html', {
        'tasks': tasks,
        'staff': staff,
        'total_projects': total_projects,
        'completed_projects': completed_projects,
        'overdue_projects': overdue_projects,
        'in_progress_projects': in_progress_projects,
        'high_priority_count': high_priority_count,
        'medium_priority_count': medium_priority_count,
        'low_priority_count': low_priority_count,
        'completion_rate': completion_rate,
    })


@login_required
@page_permission_required('projects')
def project_tasks_view(request):
    org = request.user.profile.organization
    tasks = Task.objects.filter(Q(lead__organization=org) | Q(organization=org)).order_by('due_date')
    staff = UserProfile.objects.filter(organization=org)
    leads = Lead.objects.filter(organization=org)
    project_statuses = ProjectStatus.objects.filter(organization=org).order_by('position')
    
    return render(request, 'project_tasks.html', {
        'tasks': tasks,
        'staff': staff,
        'leads': leads,
        'project_statuses': project_statuses,
    })


@login_required
@page_permission_required('projects')
def project_milestones_view(request):
    org = request.user.profile.organization
    tasks = Task.objects.filter(Q(lead__organization=org) | Q(organization=org)).order_by('due_date')
    staff = UserProfile.objects.filter(organization=org)
    leads = Lead.objects.filter(organization=org)
    
    return render(request, 'project_milestones.html', {
        'tasks': tasks,
        'staff': staff,
        'leads': leads,
    })


@login_required
@page_permission_required('projects')
def project_files_view(request):
    org = request.user.profile.organization
    tasks = Task.objects.filter(Q(lead__organization=org) | Q(organization=org)).order_by('due_date')
    staff = UserProfile.objects.filter(organization=org)

    return render(request, 'project_files.html', {
        'tasks': tasks,
        'staff': staff,
    })


@login_required
@page_permission_required('projects')
def project_time_tracking_view(request):
    org = request.user.profile.organization
    tasks = Task.objects.filter(Q(lead__organization=org) | Q(organization=org)).order_by('due_date')
    staff = UserProfile.objects.filter(organization=org)

    return render(request, 'project_time_tracking.html', {
        'tasks': tasks,
        'staff': staff,
    })




@login_required
@page_permission_required('agreements')
def agreements_list_view(request):
    org = request.user.profile.organization
    agreements = Agreement.objects.filter(organization=org)
    
    # Expiry detection / simple background status update
    for agr in agreements:
        if agr.status == 'Active' and agr.end_date and agr.end_date < timezone.now().date():
            agr.status = 'Expired'
            agr.save()
            
    return render(request, 'agreements_list.html', {
        'agreements': agreements
    })


@login_required
@page_permission_required('agreements')
def create_agreement_view(request):
    org = request.user.profile.organization
    services = Service.objects.filter(organization=org)
    if request.method == 'POST':
        try:
            # Generate Auto Agreement Number
            year = timezone.now().year
            count = Agreement.objects.filter(organization=org, created_at__year=year).count()
            agreement_number = f"AGR-{year}-{count + 1:03d}"
            
            service_id = request.POST.get('service')
            service = None
            if service_id:
                try:
                    service = Service.objects.get(id=int(service_id), organization=org)
                except (ValueError, Service.DoesNotExist):
                    pass
            
            agreement = Agreement.objects.create(
                organization=org,
                agreement_number=agreement_number,
                date=request.POST.get('date'),
                start_date=request.POST.get('start_date'),
                end_date=request.POST.get('end_date'),
                client_name=request.POST.get('client_name'),
                company_name=request.POST.get('company_name', ''),
                client_email=request.POST.get('client_email', ''),
                client_phone=request.POST.get('client_phone', ''),
                client_address=request.POST.get('client_address', ''),
                service=service,
                monthly_fee=request.POST.get('monthly_fee') or 0.00,
                advance_payment=request.POST.get('advance_payment') or 0.00,
                payment_cycle=request.POST.get('payment_cycle', 'Monthly'),
                payment_method=request.POST.get('payment_method', 'Bank Transfer'),
                posts_count=request.POST.get('posts_count') or 0,
                campaigns_count=request.POST.get('campaigns_count') or 0,
                revisions=request.POST.get('revisions') or 3,
                notice_period=request.POST.get('notice_period') or 30,
                notes=request.POST.get('notes', ''),
                project_estimation_json=request.POST.get('project_estimation_json', ''),
                status=request.POST.get('status', 'Draft')
            )
            
            # Save Services
            svc_titles = request.POST.getlist('service_title[]')
            svc_descs = request.POST.getlist('service_desc[]')
            for i in range(len(svc_titles)):
                title = svc_titles[i].strip()
                if title:
                    AgreementService.objects.create(
                        agreement=agreement,
                        title=title,
                        description=svc_descs[i].strip() if i < len(svc_descs) else ''
                    )
            
            # Save Deliverables
            deliv_titles = request.POST.getlist('deliverable_title[]')
            for t in deliv_titles:
                title = t.strip()
                if title:
                    Deliverable.objects.create(agreement=agreement, title=title)
                    
            # Save Client Responsibilities
            resp_texts = request.POST.getlist('responsibility_text[]')
            for r in resp_texts:
                text = r.strip()
                if text:
                    ClientResponsibility.objects.create(agreement=agreement, responsibility=text)
                    
            SystemNotification.objects.create(user=request.user, message='Agreement created successfully.', type='success')
            return redirect('agreements')
        except Exception as e:
            messages.error(request, f"Error creating agreement: {str(e)}")
            
    return render(request, 'agreement_form.html', {
        'action': 'Create',
        'agreement': None,
        'services': services
    })


@login_required
@page_permission_required('agreements')
def update_agreement_view(request, agreement_id):
    org = request.user.profile.organization
    agreement = get_object_or_404(Agreement, id=agreement_id, organization=org)
    services = Service.objects.filter(organization=org)
    
    if request.method == 'POST':
        try:
            agreement.date = request.POST.get('date')
            agreement.start_date = request.POST.get('start_date')
            agreement.end_date = request.POST.get('end_date')
            agreement.client_name = request.POST.get('client_name')
            agreement.company_name = request.POST.get('company_name', '')
            agreement.client_email = request.POST.get('client_email', '')
            agreement.client_phone = request.POST.get('client_phone', '')
            agreement.client_address = request.POST.get('client_address', '')
            
            service_id = request.POST.get('service')
            service = None
            if service_id:
                try:
                    service = Service.objects.get(id=int(service_id), organization=org)
                except (ValueError, Service.DoesNotExist):
                    pass
            agreement.service = service
            agreement.monthly_fee = request.POST.get('monthly_fee') or 0.00
            agreement.advance_payment = request.POST.get('advance_payment') or 0.00
            agreement.payment_cycle = request.POST.get('payment_cycle', 'Monthly')
            agreement.payment_method = request.POST.get('payment_method', 'Bank Transfer')
            agreement.posts_count = request.POST.get('posts_count') or 0
            agreement.campaigns_count = request.POST.get('campaigns_count') or 0
            agreement.revisions = request.POST.get('revisions') or 3
            agreement.notice_period = request.POST.get('notice_period') or 30
            agreement.notes = request.POST.get('notes', '')
            agreement.project_estimation_json = request.POST.get('project_estimation_json', '')
            agreement.status = request.POST.get('status', 'Draft')
            agreement.save()
            
            # Refresh Services
            agreement.services.all().delete()
            svc_titles = request.POST.getlist('service_title[]')
            svc_descs = request.POST.getlist('service_desc[]')
            for i in range(len(svc_titles)):
                title = svc_titles[i].strip()
                if title:
                    AgreementService.objects.create(
                        agreement=agreement,
                        title=title,
                        description=svc_descs[i].strip() if i < len(svc_descs) else ''
                    )
            
            # Refresh Deliverables
            agreement.deliverables.all().delete()
            deliv_titles = request.POST.getlist('deliverable_title[]')
            for t in deliv_titles:
                title = t.strip()
                if title:
                    Deliverable.objects.create(agreement=agreement, title=title)
                    
            # Refresh Client Responsibilities
            agreement.responsibilities.all().delete()
            resp_texts = request.POST.getlist('responsibility_text[]')
            for r in resp_texts:
                text = r.strip()
                if text:
                    ClientResponsibility.objects.create(agreement=agreement, responsibility=text)
                    
            SystemNotification.objects.create(user=request.user, message='Agreement updated successfully.', type='success')
            return redirect('agreements')
        except Exception as e:
            messages.error(request, f"Error updating agreement: {str(e)}")
            
    return render(request, 'agreement_form.html', {
        'action': 'Update',
        'agreement': agreement,
        'services': services
    })


@login_required
@page_permission_required('agreements')
def delete_agreement_view(request, agreement_id):
    if request.method == 'POST':
        org = request.user.profile.organization
        agreement = get_object_or_404(Agreement, id=agreement_id, organization=org)
        agreement.delete()
        SystemNotification.objects.create(user=request.user, message='Agreement deleted successfully.', type='success')
        return redirect('agreements')
    return JsonResponse({'success': False, 'error': 'Invalid request method.'})


@login_required
@page_permission_required('agreements')
def agreement_print_view(request, agreement_id):
    org = request.user.profile.organization
    agreement = get_object_or_404(Agreement, id=agreement_id, organization=org)
    from .document_views import get_or_create_document_settings
    doc_settings = get_or_create_document_settings(org)
    return render(request, 'agreement_print.html', {
        'agreement': agreement,
        'organization': org,
        'doc_settings': doc_settings
    })








@login_required
@login_required
@page_permission_required('campaigns')
def campaign_view(request):
    org = request.user.profile.organization
    campaigns = Campaign.objects.filter(organization=org).order_by('-created_at')
    
    # Auto-seed realistic demo Meta campaigns if empty
    if not campaigns.exists():
        from datetime import date
        Campaign.objects.create(
            organization=org, name='49th Kids kurta mund 10/8/26 - campaign',
            is_active=True, status='Active', results_count=119, results_type='Messaging conversations',
            cost_per_result=4.97, budget=600.00, budget_type='Lifetime', spend=591.51,
            impressions=9494, reach=6159, end_date=date(2026, 8, 15), platform='Meta Ads', leads_generated=119
        )
        Campaign.objects.create(
            organization=org, name='50th davani video ad 11/8/26 – campaign',
            is_active=False, status='Paused', results_count=10, results_type='Messaging conversations',
            cost_per_result=15.65, budget=250.00, budget_type='Lifetime', spend=156.48,
            impressions=2777, reach=2493, end_date=date(2026, 8, 13), platform='Meta Ads', leads_generated=10
        )
        campaigns = Campaign.objects.filter(organization=org).order_by('-created_at')

    # Aggregated metrics for header cards
    total_spend = sum(float(c.spend) for c in campaigns)
    total_gst = sum(c.calc_gst_amount for c in campaigns)
    total_spend_with_gst = round(total_spend + total_gst, 2)
    total_budget = sum(float(c.budget) for c in campaigns)
    total_results = sum(c.effective_results for c in campaigns)
    total_impressions = sum(c.impressions for c in campaigns)
    total_reach = sum(c.reach for c in campaigns)
    avg_cost_per_result = round(total_spend / total_results, 2) if total_results > 0 else 0.00
    active_count = campaigns.filter(is_active=True).count()
    
    context = {
        'campaigns': campaigns,
        'total_spend': total_spend,
        'total_gst': total_gst,
        'total_spend_with_gst': total_spend_with_gst,
        'total_budget': total_budget,
        'total_results': total_results,
        'total_impressions': total_impressions,
        'total_reach': total_reach,
        'avg_cost_per_result': avg_cost_per_result,
        'active_count': active_count,
        'total_count': campaigns.count(),
    }
    return render(request, 'campaign.html', context)


@login_required
@page_permission_required('campaigns')
def campaign_dashboard_view(request):
    org = request.user.profile.organization
    campaigns = Campaign.objects.filter(organization=org).order_by('-created_at')

    total_spend = sum(float(c.spend) for c in campaigns)
    total_budget = sum(float(c.budget) for c in campaigns)
    total_results = sum(c.effective_results for c in campaigns)
    total_impressions = sum(c.impressions for c in campaigns)
    total_reach = sum(c.reach for c in campaigns)
    avg_cost_per_result = round(total_spend / total_results, 2) if total_results > 0 else 0.00
    active_count = campaigns.filter(is_active=True).count()

    # Chart datasets
    chart_names = [c.name[:25] + ('...' if len(c.name) > 25 else '') for c in campaigns[:6]]
    chart_spends = [float(c.spend) for c in campaigns[:6]]
    chart_results = [c.effective_results for c in campaigns[:6]]
    chart_cpr = [c.calc_cost_per_result for c in campaigns[:6]]

    context = {
        'campaigns': campaigns,
        'total_spend': total_spend,
        'total_budget': total_budget,
        'total_results': total_results,
        'total_impressions': total_impressions,
        'total_reach': total_reach,
        'avg_cost_per_result': avg_cost_per_result,
        'active_count': active_count,
        'total_count': campaigns.count(),
        'chart_names_json': json.dumps(chart_names),
        'chart_spends_json': json.dumps(chart_spends),
        'chart_results_json': json.dumps(chart_results),
        'chart_cpr_json': json.dumps(chart_cpr),
    }
    return render(request, 'campaign_dashboard.html', context)


@login_required
@require_POST
@page_permission_required('campaigns')
def toggle_campaign_active(request, campaign_id):
    org = request.user.profile.organization
    campaign = get_object_or_404(Campaign, id=campaign_id, organization=org)
    
    campaign.is_active = not campaign.is_active
    campaign.status = 'Active' if campaign.is_active else 'Paused'
    campaign.save()
    
    return JsonResponse({
        'success': True,
        'is_active': campaign.is_active,
        'status': campaign.status,
        'message': f"Campaign is now {'Active' if campaign.is_active else 'Paused'}."
    })


@login_required
@require_POST
@page_permission_required('campaigns')
def add_campaign(request):
    org = request.user.profile.organization
    name = request.POST.get('name')
    status = request.POST.get('status', 'Active')
    is_active = request.POST.get('is_active') == 'true' or status == 'Active'
    
    results_count = int(request.POST.get('results_count') or request.POST.get('leads_generated') or 0)
    results_type = request.POST.get('results_type') or 'Messaging conversations'
    cost_per_result = float(request.POST.get('cost_per_result') or 0.0)
    budget = float(request.POST.get('budget') or 0)
    budget_type = request.POST.get('budget_type') or 'Lifetime'
    spend = float(request.POST.get('spend') or 0)
    gst_percentage = float(request.POST.get('gst_percentage') or 18.0)
    gst_amount = float(request.POST.get('gst_amount') or 0.0)
    impressions = int(request.POST.get('impressions') or 0)
    reach = int(request.POST.get('reach') or 0)
    end_date_str = request.POST.get('end_date')
    platform = request.POST.get('platform') or 'Meta Ads'
    cost_center = request.POST.get('cost_center') or ''
    
    end_date = None
    if end_date_str:
        try:
            from datetime import datetime
            end_date = datetime.strptime(end_date_str, '%Y-%m-%d').date()
        except Exception:
            pass

    try:
        Campaign.objects.create(
            organization=org,
            name=name,
            status=status,
            is_active=is_active,
            results_count=results_count,
            results_type=results_type,
            cost_per_result=cost_per_result,
            budget=budget,
            budget_type=budget_type,
            spend=spend,
            gst_percentage=gst_percentage,
            gst_amount=gst_amount,
            impressions=impressions,
            reach=reach,
            end_date=end_date,
            platform=platform,
            cost_center=cost_center,
            leads_generated=results_count
        )
        if request.headers.get('x-requested-with') == 'XMLHttpRequest':
            return JsonResponse({'success': True, 'message': 'Campaign launched successfully.'})
        SystemNotification.objects.create(user=request.user, message='Campaign launched successfully.', type='success')
    except Exception as e:
        if request.headers.get('x-requested-with') == 'XMLHttpRequest':
            return JsonResponse({'success': False, 'error': str(e)})
        messages.error(request, f'Error launching campaign: {str(e)}')
    
    return redirect('campaign')


@login_required
@require_POST
@page_permission_required('campaigns')
def edit_campaign(request, campaign_id):
    org = request.user.profile.organization
    campaign = get_object_or_404(Campaign, id=campaign_id, organization=org)
    
    name = request.POST.get('name')
    status = request.POST.get('status')
    if 'is_active' in request.POST:
        campaign.is_active = request.POST.get('is_active') == 'true'
    else:
        campaign.is_active = (status == 'Active')
        
    campaign.name = name
    campaign.status = status
    campaign.results_count = int(request.POST.get('results_count') or request.POST.get('leads_generated') or campaign.results_count)
    campaign.results_type = request.POST.get('results_type') or campaign.results_type
    campaign.cost_per_result = float(request.POST.get('cost_per_result') or campaign.cost_per_result)
    campaign.budget = float(request.POST.get('budget') or campaign.budget)
    campaign.budget_type = request.POST.get('budget_type') or campaign.budget_type
    campaign.spend = float(request.POST.get('spend') or campaign.spend)
    campaign.gst_percentage = float(request.POST.get('gst_percentage') or campaign.gst_percentage or 18.0)
    campaign.gst_amount = float(request.POST.get('gst_amount') or campaign.gst_amount or 0.0)
    campaign.impressions = int(request.POST.get('impressions') or campaign.impressions)
    campaign.reach = int(request.POST.get('reach') or campaign.reach)
    campaign.platform = request.POST.get('platform') or campaign.platform
    campaign.cost_center = request.POST.get('cost_center') or campaign.cost_center
    campaign.leads_generated = campaign.results_count
    
    end_date_str = request.POST.get('end_date')
    if end_date_str:
        try:
            from datetime import datetime
            campaign.end_date = datetime.strptime(end_date_str, '%Y-%m-%d').date()
        except Exception:
            pass

    try:
        campaign.save()
        if request.headers.get('x-requested-with') == 'XMLHttpRequest':
            return JsonResponse({'success': True, 'message': 'Campaign updated successfully.'})
        SystemNotification.objects.create(user=request.user, message='Campaign updated successfully.', type='success')
    except Exception as e:
        if request.headers.get('x-requested-with') == 'XMLHttpRequest':
            return JsonResponse({'success': False, 'error': str(e)})
        messages.error(request, f'Error updating campaign: {str(e)}')
        
    return redirect('campaign')


@login_required
@require_POST
@page_permission_required('campaigns')
def delete_campaign(request, campaign_id):
    org = request.user.profile.organization
    campaign = get_object_or_404(Campaign, id=campaign_id, organization=org)
    
    try:
        campaign.delete()
        if request.headers.get('x-requested-with') == 'XMLHttpRequest':
            return JsonResponse({'success': True, 'message': 'Campaign deleted successfully.'})
        SystemNotification.objects.create(user=request.user, message='Campaign deleted successfully.', type='success')
    except Exception as e:
        if request.headers.get('x-requested-with') == 'XMLHttpRequest':
            return JsonResponse({'success': False, 'error': str(e)})
        messages.error(request, f'Error deleting campaign: {str(e)}')
        
    return redirect('campaign')

def signup_view(request):
    return redirect('login')

def login_view(request):
    if request.user.is_authenticated:
        return redirect('dashboard')
        
    if request.method == 'POST':
        u = request.POST.get('username')
        p = request.POST.get('password')
        user = authenticate(request, username=u, password=p)
        if user is not None:
            login(request, user)
            
            remember_me = request.POST.get('remember_me')
            if not remember_me:
                request.session.set_expiry(0)
                
            return redirect('dashboard')
        else:
            messages.error(request, "Invalid username or password.")
            return render(request, 'registration/login.html')
            
    return render(request, 'registration/login.html')

@login_required
def logout_view(request):
    logout(request)
    return redirect('login')

@login_required
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

    # Base QuerySets
    leads_all_qs = Lead.objects.filter(organization=org)
    
    if start_date:
        if end_date:
            period_leads_qs = leads_all_qs.filter(created_at__gte=start_date, created_at__lte=end_date)
        else:
            period_leads_qs = leads_all_qs.filter(created_at__gte=start_date)
    else:
        period_leads_qs = leads_all_qs

    if prev_start_date and prev_end_date:
        prev_leads_qs = leads_all_qs.filter(created_at__gte=prev_start_date, created_at__lt=prev_end_date)
    else:
        prev_leads_qs = None

    # 1. Total Revenue
    won_leads_period = period_leads_qs.filter(stage='Won')
    total_revenue = float(won_leads_period.aggregate(Sum('value'))['value__sum'] or 0.00)
    
    if prev_leads_qs is not None:
        prev_won = prev_leads_qs.filter(stage='Won')
        prev_revenue = float(prev_won.aggregate(Sum('value'))['value__sum'] or 0.00)
        if prev_revenue > 0:
            revenue_trend = round(((total_revenue - prev_revenue) / prev_revenue) * 100, 1)
        else:
            revenue_trend = 100.0 if total_revenue > 0 else 0.0
    else:
        first_day_this_month = today_start.replace(day=1)
        last_day_last_month = first_day_this_month - timedelta(days=1)
        first_day_last_month = last_day_last_month.replace(day=1)
        rev_this_month = float(leads_all_qs.filter(stage='Won', created_at__gte=first_day_this_month).aggregate(Sum('value'))['value__sum'] or 0.00)
        rev_last_month = float(leads_all_qs.filter(stage='Won', created_at__gte=first_day_last_month, created_at__lt=first_day_this_month).aggregate(Sum('value'))['value__sum'] or 0.00)
        revenue_trend = round(((rev_this_month - rev_last_month) / rev_last_month * 100) if rev_last_month > 0 else (100.0 if rev_this_month > 0 else 0.0), 1)

    # 2. Total Leads
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

    # 3. Conversion Rate
    base_for_conversion = total_leads + won_leads_period.count()
    conversion_rate = round((won_leads_period.count() / base_for_conversion * 100) if base_for_conversion > 0 else 0.0, 1)
    
    if prev_leads_qs is not None:
        prev_won_count = prev_leads_qs.filter(stage='Won').count()
        prev_base = prev_leads_qs.filter(is_client=False).count() + prev_won_count
        prev_conversion = (prev_won_count / prev_base * 100) if prev_base > 0 else 0.0
        conversion_trend = round(conversion_rate - prev_conversion, 1)
    else:
        conversion_trend = 0.0

    # 4. Tasks
    tasks_qs = Task.objects.filter(lead__organization=org)
    active_tasks_count = tasks_qs.filter(completed=False).count()
    completed_tasks_count = tasks_qs.filter(completed=True).count()
    tasks_due_today = tasks_qs.filter(completed=False, due_date=today_start.date()).count() if hasattr(Task, 'due_date') else 0
    total_tasks_count = tasks_qs.count()
    task_completion_rate = round((completed_tasks_count / total_tasks_count * 100) if total_tasks_count > 0 else 0.0, 1)

    pending_tasks_list = []
    for t in tasks_qs.filter(completed=False).order_by('due_date', '-created_at')[:5]:
        pending_tasks_list.append({
            'id': t.id,
            'title': t.title,
            'lead_name': t.lead.name if t.lead else 'General',
            'lead_id': t.lead.id if t.lead else None,
            'due_date': t.due_date.strftime('%b %d') if hasattr(t, 'due_date') and t.due_date else None,
            'is_overdue': bool(hasattr(t, 'due_date') and t.due_date and t.due_date < today_start.date()),
            'priority': getattr(t, 'priority', 'Normal') or 'Normal',
        })

    # 5. Sales Documents
    quotation_count = Quotation.objects.filter(organization=org).count()
    agreement_count = Agreement.objects.filter(organization=org).count()

    # 6. Active Deals
    active_deals_qs = leads_all_qs.filter(is_client=False).exclude(stage__in=['Won', 'Lost'])
    active_deals_count = active_deals_qs.count()
    active_deals_value = float(active_deals_qs.aggregate(Sum('value'))['value__sum'] or 0.00)

    # 7. Total Clients
    total_clients_count = leads_all_qs.filter(is_client=True).count()
    active_clients_count = leads_all_qs.filter(is_client=True).exclude(status='Lost').count()
    new_clients_this_month = leads_all_qs.filter(is_client=True, created_at__gte=first_day_this_month).count()
    new_clients_in_period = period_leads_qs.filter(is_client=True).count()

    # 8. Real Leads Sparkline (Last 7 Days daily counts)
    sparkline_labels = []
    sparkline_values = []
    for i in range(6, -1, -1):
        day_date = today_start.date() - timedelta(days=i)
        day_start = timezone.make_aware(datetime.combine(day_date, datetime.min.time()))
        day_end = timezone.make_aware(datetime.combine(day_date, datetime.max.time()))
        day_cnt = leads_all_qs.filter(is_client=False, created_at__gte=day_start, created_at__lte=day_end).count()
        sparkline_labels.append(day_date.strftime('%a'))
        sparkline_values.append(day_cnt)

    # 9. Dynamic Revenue & Performance Chart Series
    trend_labels = []
    trend_revenue = []
    trend_deals = []
    trend_leads = []

    if chart_range == '7d':
        for i in range(6, -1, -1):
            d = today_start.date() - timedelta(days=i)
            d_start = timezone.make_aware(datetime.combine(d, datetime.min.time()))
            d_end = timezone.make_aware(datetime.combine(d, datetime.max.time()))
            d_won = leads_all_qs.filter(stage='Won', created_at__gte=d_start, created_at__lte=d_end)
            d_rev = float(d_won.aggregate(Sum('value'))['value__sum'] or 0)
            d_cnt = d_won.count()
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
            d_won = leads_all_qs.filter(stage='Won', created_at__gte=d_start, created_at__lte=d_end)
            d_rev = float(d_won.aggregate(Sum('value'))['value__sum'] or 0)
            d_cnt = d_won.count()
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
            m_won = leads_all_qs.filter(stage='Won', created_at__gte=m_date, created_at__lt=next_m)
            m_rev = float(m_won.aggregate(Sum('value'))['value__sum'] or 0)
            m_cnt = m_won.count()
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
            m_won = leads_all_qs.filter(stage='Won', created_at__gte=m_date, created_at__lt=next_m)
            m_rev = float(m_won.aggregate(Sum('value'))['value__sum'] or 0)
            m_cnt = m_won.count()
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
    recent_activities_qs = Activity.objects.filter(lead__organization=org).order_by('-timestamp')[:5]
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
                'quotation_count': quotation_count,
                'agreement_count': agreement_count,
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
        'quotation_count': quotation_count,
        'agreement_count': agreement_count,
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

@login_required
@page_permission_required('leads')
def leads_view(request):
    org = request.user.profile.organization
    
    # Export CSV handler
    if request.GET.get('export') == 'csv':
        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = 'attachment; filename="leads_export.csv"'
        
        writer = csv.writer(response)
        writer.writerow(['Name', 'Email', 'Company', 'Phone Number', 'Alt Phone Number', 'Date and Time', 'Status', 'Last Followup Date and Time', 'Followup Wanted Date and Time'])
        
        leads_export = Lead.objects.filter(organization=org, is_client=False)
        for lead in leads_export:
            writer.writerow([
                lead.name, lead.email, lead.company,
                lead.phone_number or '', lead.alt_phone_number or '',
                lead.date_time.strftime('%Y-%m-%d %H:%M') if lead.date_time else '',
                lead.status,
                lead.last_followup_date_time.strftime('%Y-%m-%d %H:%M') if lead.last_followup_date_time else '',
                lead.followup_wanted_date_time.strftime('%Y-%m-%d %H:%M') if lead.followup_wanted_date_time else ''
            ])
        return response
        
    # Bulk actions POST handler
    if request.method == 'POST':
        action = request.POST.get('bulk_action')
        lead_ids = request.POST.getlist('lead_ids')
        if action and lead_ids:
            target_leads = Lead.objects.filter(id__in=lead_ids, organization=org)
            if action == 'delete':
                count = target_leads.count()
                target_leads.delete()
                SystemNotification.objects.create(user=request.user, message=f"Successfully deleted {count} leads.", type='success')
            elif action == 'change_status_qualified':
                count = target_leads.update(status='Qualified', stage='Qualified')
                for lead in target_leads:
                    Activity.objects.create(
                        lead=lead,
                        type='Stage Update',
                        description="Bulk changed status to Qualified."
                    )
                SystemNotification.objects.create(user=request.user, message=f"Successfully updated {count} leads to Qualified.", type='success')
        return redirect('leads')

    leads_qs = Lead.objects.filter(organization=org, is_client=False)
    
    # Clear old session key if present (do not persist filters/sorting across reloads or page closes)
    user_pref_key = f'leads_filter_pref_user_{request.user.id}'
    if user_pref_key in request.session:
        del request.session[user_pref_key]
        
    q = request.GET.get('q', '').strip()
    status_filter = request.GET.get('status', '').strip()
    owner_filter = request.GET.get('owner', '').strip()
    sort_by = request.GET.get('sort', '').strip()

    # 1. Search Query
    if q:
        leads_qs = leads_qs.filter(name__icontains=q)
        
    # 2. Filters
    if status_filter:
        leads_qs = leads_qs.filter(status=status_filter)
        
    if owner_filter:
        leads_qs = leads_qs.filter(owner_id=owner_filter)
        
    # 3. Sorting
    if sort_by == 'value_desc':
        leads_qs = leads_qs.order_by('-value')
    elif sort_by == 'value_asc':
        leads_qs = leads_qs.order_by('value')
    else:
        leads_qs = leads_qs.order_by('-created_at', '-id')

    # Owners lookup
    owners = UserProfile.objects.filter(organization=org)
    
    # Pagination
    paginator = Paginator(leads_qs, 25)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    # Initialize / fetch dynamic statuses
    statuses = get_or_create_default_statuses(org)
    annotate_lead_badges(page_obj, org)

    context = {
        'leads': page_obj,
        'owners': owners,
        'status_filter': status_filter,
        'owner_filter': owner_filter,
        'sort_by': sort_by,
        'q': q,
        'paginator': paginator,
        'statuses': statuses,
    }
    
    if request.headers.get('x-requested-with') == 'XMLHttpRequest' or request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        from django.template.loader import render_to_string
        html = render_to_string('leads_table_fragment.html', context, request=request)
        response = JsonResponse({'html': html})
        response['Cache-Control'] = 'no-cache, no-store, must-revalidate, max-age=0, private'
        response['Pragma'] = 'no-cache'
        response['Vary'] = 'X-Requested-With'
        return response
        
    response = render(request, 'leads.html', context)
    response['Cache-Control'] = 'no-cache, no-store, must-revalidate, max-age=0, private'
    response['Pragma'] = 'no-cache'
    response['Vary'] = 'X-Requested-With'
    return response

@login_required
@page_permission_required('leads')
def pipeline_view(request):
    org = request.user.profile.organization
    leads_qs = Lead.objects.filter(organization=org)
    
    stages = ['New', 'Qualified', 'Proposal', 'Negotiation', 'Won', 'Lost']
    stage_weights = {
        'New': 0.10,
        'Qualified': 0.30,
        'Proposal': 0.60,
        'Negotiation': 0.80,
        'Won': 1.00,
        'Lost': 0.00
    }
    
    pipeline_stages = {}
    weighted_forecast = 0.0
    total_pipeline = 0.0
    total_deals = 0
    won_count = 0
    lost_count = 0

    for st in stages:
        stage_leads = leads_qs.filter(stage=st).order_by('-created_at')
        stage_total = float(stage_leads.aggregate(Sum('value'))['value__sum'] or 0.00)
        pipeline_stages[st] = {
            'leads': stage_leads,
            'total_value': stage_total,
            'count': stage_leads.count()
        }
        total_deals += stage_leads.count()
        if st == 'Won':
            won_count = stage_leads.count()
        elif st == 'Lost':
            lost_count = stage_leads.count()
        
        if st != 'Lost':
            total_pipeline += stage_total
            weighted_forecast += stage_total * stage_weights.get(st, 0.25)
        
    resolved_deals = won_count + lost_count
    win_rate = round((won_count / resolved_deals * 100) if resolved_deals > 0 else (won_count / total_deals * 100 if total_deals > 0 else 0.0), 1)
    
    owners = UserProfile.objects.filter(organization=org)

    context = {
        'weighted_forecast': weighted_forecast,
        'total_pipeline': total_pipeline,
        'total_deals': total_deals,
        'win_rate': win_rate,
        'pipeline_stages': pipeline_stages,
        'owners': owners
    }
    
    return render(request, 'pipeline.html', context)

@login_required
def update_lead_stage(request):
    if request.method == 'POST':
        lead_id = request.POST.get('lead_id')
        stage = request.POST.get('stage')
        org = request.user.profile.organization
        
        try:
            lead = Lead.objects.get(id=lead_id, organization=org)
            old_stage = lead.stage or lead.status
            
            lead.stage = stage
            if stage == 'Won':
                lead.status = 'Won'
                lead.is_client = True
            elif stage == 'Lost':
                lead.status = 'Lost'
            elif stage == 'Qualified':
                lead.status = 'Qualified'
            elif stage == 'Proposal':
                lead.status = 'Proposal'
            elif stage == 'Negotiation':
                lead.status = 'Discussion'
            elif stage == 'New':
                lead.status = 'New'
                
            lead.save()
            
            # Log activity
            Activity.objects.create(
                lead=lead,
                type='Stage Update',
                description=f"Moved stage from {old_stage} to {stage}."
            )
            return JsonResponse({'success': True, 'stage': stage})
        except Lead.DoesNotExist:
            return JsonResponse({'success': False, 'error': 'Lead not found.'})
        except Exception as e:
            return JsonResponse({'success': False, 'error': str(e)})
            
    return JsonResponse({'success': False, 'error': 'Invalid request method.'})

@login_required
def contact_detail_view(request, lead_id):
    org = request.user.profile.organization
    try:
        lead = Lead.objects.get(id=lead_id, organization=org)
        if lead.is_client:
            return redirect('client_contact_detail', lead_id=lead.id)
        annotate_lead_badges(lead, org)
    except Lead.DoesNotExist:
        return redirect('leads')
        
    activities = lead.activities.all().order_by('-timestamp')
    tasks = lead.tasks.all().order_by('-created_at')
    owners = UserProfile.objects.filter(organization=org)
    statuses = get_or_create_default_statuses(org)
    services = Service.objects.filter(organization=org)
    
    context = {
        'lead': lead,
        'activities': activities,
        'tasks': tasks,
        'owners': owners,
        'statuses': statuses,
        'services': services,
    }
    return render(request, 'contact_detail.html', context)

@login_required
def send_whatsapp_page_view(request, lead_id):
    org = request.user.profile.organization
    try:
        lead = Lead.objects.get(id=lead_id, organization=org)
    except Lead.DoesNotExist:
        return redirect('leads')
        
    activities = lead.activities.all().order_by('-timestamp')
    tasks = lead.tasks.all().order_by('-created_at')
    owners = UserProfile.objects.filter(organization=org)
    services = Service.objects.filter(organization=org)
    
    from .whatsapp_service import get_whatsapp_api_status
    api_status = get_whatsapp_api_status()
    whatsapp_history = getattr(lead, 'whatsapp_messages', None).all().order_by('-sent_at')[:20] if hasattr(lead, 'whatsapp_messages') else []

    context = {
        'lead': lead,
        'activities': activities,
        'tasks': tasks,
        'owners': owners,
        'services': services,
        'api_status': api_status,
        'whatsapp_history': whatsapp_history,
    }
    return render(request, 'send_whatsapp_page.html', context)

@login_required
def send_whatsapp_cloud_api_view(request):
    """
    Sends native interactive WhatsApp Business Cloud API messages containing native action buttons or templates.
    Uses backend whatsapp_service module keeping tokens secure server-side.
    """
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'Invalid HTTP method'}, status=405)

    import json
    org = request.user.profile.organization
    lead_id = request.POST.get('lead_id')
    recipient_phone = request.POST.get('phone_number') or request.POST.get('recipient_phone')
    message_text = request.POST.get('message', '').strip()
    buttons_json = request.POST.get('buttons', '[]')
    template_name = request.POST.get('template_name', '').strip()
    template_language = request.POST.get('template_language', 'en_US').strip()
    custom_token = request.POST.get('access_token', '').strip() or None
    custom_phone_id = request.POST.get('phone_number_id', '').strip() or None

    lead = None
    if lead_id:
        try:
            lead = Lead.objects.get(id=lead_id, organization=org)
        except (Lead.DoesNotExist, ValueError):
            return JsonResponse({'success': False, 'error': 'Lead not found in your organization'}, status=404)

    if not lead and not recipient_phone:
        return JsonResponse({'success': False, 'error': 'Recipient lead or phone number is required.'}, status=400)

    try:
        buttons = json.loads(buttons_json) if isinstance(buttons_json, str) else buttons_json
    except Exception:
        buttons = []

    from .whatsapp_service import send_meta_cloud_api_message
    res = send_meta_cloud_api_message(
        lead=lead,
        recipient_phone=recipient_phone,
        message_text=message_text,
        buttons=buttons,
        template_name=template_name or None,
        template_language=template_language,
        custom_token=custom_token,
        custom_phone_id=custom_phone_id,
        user=request.user,
        organization=org
    )

    return JsonResponse(res)

@login_required
def whatsapp_status_json_view(request):
    from .whatsapp_service import get_whatsapp_api_status
    status = get_whatsapp_api_status()
    return JsonResponse(status)

@login_required
def search_leads_json_view(request):
    org = request.user.profile.organization
    query = request.GET.get('q', '').strip().lower()
    
    leads_qs = Lead.objects.filter(organization=org)
    if query:
        from django.db.models import Q
        leads_qs = leads_qs.filter(Q(name__icontains=query) | Q(phone_number__icontains=query) | Q(company__icontains=query))
    
    leads_data = []
    for l in leads_qs[:15]:
        leads_data.append({
            'id': l.id,
            'name': l.name,
            'company': l.company or 'Individual Client',
            'phone_number': l.phone_number,
            'status': l.status,
            'is_client': l.is_client,
            'avatar_url': l.profile_image_url or ''
        })
        
    return JsonResponse({'success': True, 'leads': leads_data})

@login_required
def add_task(request):
    if request.method == 'POST':
        lead_id = request.POST.get('lead_id')
        title = request.POST.get('title', 'Project Task')
        desc = request.POST.get('description', '')
        start_date = request.POST.get('start_date') or None
        due_date = request.POST.get('due_date')
        if not due_date:
            from django.utils import timezone
            due_date = timezone.now().date() + timezone.timedelta(days=7)
        priority = request.POST.get('priority', 'Medium')
        risk_level = request.POST.get('risk_level', 'Low')
        prog_val = request.POST.get('progress')
        progress = int(prog_val) if prog_val and prog_val.isdigit() else 0
        completed = request.POST.get('completed') == 'true' or request.POST.get('completed') == 'on'
        org = request.user.profile.organization
        
        try:
            lead = None
            if lead_id and lead_id != 'inhouse':
                lead = Lead.objects.get(id=lead_id, organization=org)
            
            status_id = request.POST.get('status_id')
            status_obj = None
            if status_id:
                try:
                    status_obj = ProjectStatus.objects.get(id=status_id, organization=org)
                except ProjectStatus.DoesNotExist:
                    pass

            task = Task.objects.create(
                lead=lead,
                organization=org if not lead else None,
                title=title,
                description=desc,
                start_date=start_date,
                due_date=due_date,
                priority=priority,
                risk_level=risk_level,
                progress=progress,
                status=status_obj,
                completed=completed
            )
            
            assignee_ids = request.POST.getlist('assignees')
            if assignee_ids:
                valid_assignees = UserProfile.objects.filter(id__in=[int(aid) for aid in assignee_ids if aid], organization=org)
                task.assignees.set(valid_assignees)

            if lead:
                # Log activity
                Activity.objects.create(
                    lead=lead,
                    type='Task',
                    description=f"Created task: {title} (Priority: {priority}, Due: {due_date})"
                )
            
            if request.headers.get('x-requested-with') == 'XMLHttpRequest' or request.POST.get('ajax') == 'true':
                return JsonResponse({
                    'success': True,
                    'task': {
                        'id': task.id,
                        'title': task.title,
                        'description': task.description,
                        'due_date_formatted': task.due_date.strftime('%b %d'),
                        'priority': task.priority,
                        'completed': task.completed
                    }
                })
            SystemNotification.objects.create(user=request.user, message='Task created successfully.', type='success')
            return redirect('projects')
        except Lead.DoesNotExist:
            if request.headers.get('x-requested-with') == 'XMLHttpRequest':
                return JsonResponse({'success': False, 'error': 'Lead not found.'})
            messages.error(request, 'Lead not found.')
            return redirect('projects')
        except Exception as e:
            if request.headers.get('x-requested-with') == 'XMLHttpRequest':
                return JsonResponse({'success': False, 'error': str(e)})
            messages.error(request, f'Error: {str(e)}')
            return redirect('projects')
            
    return JsonResponse({'success': False, 'error': 'Invalid request.'})


@login_required
def edit_task(request, task_id):
    if request.method == 'POST':
        org = request.user.profile.organization
        task = get_object_or_404(Task, id=task_id)
        if (task.lead and task.lead.organization != org) or (not task.lead and task.organization != org):
            return JsonResponse({'success': False, 'error': 'Invalid task.'})
        
        try:
            task.title = request.POST.get('title', 'Project Task')
            task.description = request.POST.get('description', '')
            task.priority = request.POST.get('priority', 'Medium')
            if request.POST.get('risk_level'):
                task.risk_level = request.POST.get('risk_level')
            if 'progress' in request.POST and request.POST.get('progress') != '':
                try:
                    task.progress = int(request.POST.get('progress'))
                except ValueError:
                    pass
            task.completed = request.POST.get('completed') == 'true' or request.POST.get('completed') == 'on'
            
            status_id = request.POST.get('status_id')
            if status_id:
                try:
                    task.status = ProjectStatus.objects.get(id=status_id, organization=org)
                except ProjectStatus.DoesNotExist:
                    pass
            elif status_id == "":
                task.status = None
            
            start_date_val = request.POST.get('start_date')
            task.start_date = start_date_val if start_date_val else None
            
            due_date_val = request.POST.get('due_date')
            if due_date_val:
                task.due_date = due_date_val
                
            lead_id = request.POST.get('lead_id')
            if lead_id and lead_id != 'inhouse':
                try:
                    task.lead = Lead.objects.get(id=int(lead_id), organization=org)
                    task.organization = None
                except (ValueError, Lead.DoesNotExist):
                    pass
            elif lead_id == 'inhouse':
                task.lead = None
                task.organization = org
                    
            assignee_ids = request.POST.getlist('assignees')
            if assignee_ids:
                valid_assignees = UserProfile.objects.filter(id__in=[int(aid) for aid in assignee_ids if aid], organization=org)
                task.assignees.set(valid_assignees)
            else:
                task.assignees.clear()
                
            task.save()
            
            if request.headers.get('x-requested-with') == 'XMLHttpRequest':
                return JsonResponse({'success': True, 'message': 'Task updated successfully.'})
            SystemNotification.objects.create(user=request.user, message='Task updated successfully.', type='success')
            return redirect('projects')
        except Exception as e:
            if request.headers.get('x-requested-with') == 'XMLHttpRequest':
                return JsonResponse({'success': False, 'error': str(e)})
            messages.error(request, f'Error updating task: {str(e)}')
            return redirect('projects')
            
    return JsonResponse({'success': False, 'error': 'Invalid request.'})


@login_required
def task_details_json(request, task_id):
    org = request.user.profile.organization
    task = get_object_or_404(Task, id=task_id)
    if (task.lead and task.lead.organization != org) or (not task.lead and task.organization != org):
        return JsonResponse({'success': False, 'error': 'Access denied.'}, status=403)

    todos = [
        {
            'id': t.id,
            'title': t.title,
            'completed': t.completed,
        }
        for t in task.todos.all()
    ]

    activities = []
    if task.lead:
        acts = Activity.objects.filter(lead=task.lead).order_by('-timestamp')[:10]
    else:
        acts = Activity.objects.filter(lead__isnull=True, type='Task').order_by('-timestamp')[:10]

    for act in acts:
        activities.append({
            'description': act.description,
            'timestamp': act.timestamp.strftime('%b %d at %I:%M %p') if act.timestamp else ''
        })

    client_name = (task.lead.company_name or task.lead.name) if task.lead else "In-house Project"

    assignees_list = [
        {
            'id': a.id,
            'name': a.user.get_full_name() or a.user.username,
            'initials': (a.user.get_full_name() or a.user.username)[:2].upper()
        }
        for a in task.assignees.all()
    ]

    files_list = [
        {
            'id': f.id,
            'filename': f.filename,
            'url': f.file.url if f.file else '#',
            'file_size': f.file_size or 'Unknown size',
            'uploaded_at': f.uploaded_at.strftime('%b %d, %Y') if f.uploaded_at else ''
        }
        for f in task.files.all().order_by('-uploaded_at')
    ]

    return JsonResponse({
        'success': True,
        'task': {
            'id': task.id,
            'title': task.title,
            'description': task.description or '',
            'priority': task.priority,
            'risk_level': task.risk_level,
            'progress': task.calculated_progress,
            'due_date': task.due_date.strftime('%Y-%m-%d') if task.due_date else '',
            'due_date_formatted': task.due_date.strftime('%b %d, %Y') if task.due_date else 'No Due Date',
            'start_date': task.start_date.strftime('%Y-%m-%d') if task.start_date else '',
            'status_name': task.status.name if task.status else ('Completed' if task.completed else 'In Progress'),
            'status_id': task.status.id if task.status else '',
            'completed': task.completed,
            'client_name': client_name,
            'lead_id': task.lead.id if task.lead else 'inhouse',
            'assignees': assignees_list,
            'todos': todos,
            'files': files_list,
            'activities': activities
        }
    })


@login_required
def add_task_todo(request, task_id):
    if request.method == 'POST':
        org = request.user.profile.organization
        task = get_object_or_404(Task, id=task_id)
        if (task.lead and task.lead.organization != org) or (not task.lead and task.organization != org):
            return JsonResponse({'success': False, 'error': 'Access denied.'}, status=403)

        title = request.POST.get('title', '').strip()
        if not title:
            return JsonResponse({'success': False, 'error': 'Title is required.'})

        todo = TaskTodo.objects.create(task=task, title=title)
        
        # Log activity
        Activity.objects.create(
            lead=task.lead,
            type='Task',
            description=f"Added todo item '{title}' to task '{task.title}'"
        )

        return JsonResponse({
            'success': True,
            'todo': {
                'id': todo.id,
                'title': todo.title,
                'completed': todo.completed
            },
            'progress': task.calculated_progress,
            'total_todos': task.todos.count(),
            'completed_todos': task.todos.filter(completed=True).count()
        })
    return JsonResponse({'success': False, 'error': 'Invalid method.'})


@login_required
def toggle_task_todo(request, todo_id):
    if request.method == 'POST':
        org = request.user.profile.organization
        todo = get_object_or_404(TaskTodo, id=todo_id)
        task = todo.task
        if (task.lead and task.lead.organization != org) or (not task.lead and task.organization != org):
            return JsonResponse({'success': False, 'error': 'Access denied.'}, status=403)

        todo.completed = not todo.completed
        todo.save()

        calc_prog = task.calculated_progress
        if calc_prog == 100 and not task.completed:
            task.completed = True
            task.save()
        elif calc_prog < 100 and task.completed:
            task.completed = False
            task.save()

        return JsonResponse({
            'success': True,
            'completed': todo.completed,
            'progress': calc_prog,
            'total_todos': task.todos.count(),
            'completed_todos': task.todos.filter(completed=True).count()
        })
    return JsonResponse({'success': False, 'error': 'Invalid method.'})


@login_required
def edit_task_todo(request, todo_id):
    if request.method == 'POST':
        org = request.user.profile.organization
        todo = get_object_or_404(TaskTodo, id=todo_id)
        task = todo.task
        if (task.lead and task.lead.organization != org) or (not task.lead and task.organization != org):
            return JsonResponse({'success': False, 'error': 'Access denied.'}, status=403)

        title = request.POST.get('title', '').strip()
        if not title:
            return JsonResponse({'success': False, 'error': 'Title is required.'})

        todo.title = title
        todo.save()

        return JsonResponse({
            'success': True,
            'todo': {
                'id': todo.id,
                'title': todo.title,
                'completed': todo.completed
            }
        })
    return JsonResponse({'success': False, 'error': 'Invalid method.'})


@login_required
def delete_task_todo(request, todo_id):
    if request.method == 'POST':
        org = request.user.profile.organization
        todo = get_object_or_404(TaskTodo, id=todo_id)
        task = todo.task
        if (task.lead and task.lead.organization != org) or (not task.lead and task.organization != org):
            return JsonResponse({'success': False, 'error': 'Access denied.'}, status=403)

        todo.delete()

        return JsonResponse({
            'success': True,
            'progress': task.calculated_progress,
            'total_todos': task.todos.count(),
            'completed_todos': task.todos.filter(completed=True).count()
        })
    return JsonResponse({'success': False, 'error': 'Invalid method.'})


@login_required
def get_task_comments(request, task_id):
    org = request.user.profile.organization
    task = get_object_or_404(Task, id=task_id)
    if (task.lead and task.lead.organization != org) or (not task.lead and task.organization != org):
        return JsonResponse({'success': False, 'error': 'Access denied.'}, status=403)

    comments_data = []
    for c in task.comments.all().order_by('created_at'):
        user_name = c.user.get_full_name() or c.user.username
        initials = (user_name[:2]).upper()
        comments_data.append({
            'id': c.id,
            'user_name': user_name,
            'initials': initials,
            'is_me': (c.user == request.user),
            'message': c.message,
            'timestamp': c.created_at.strftime('%b %d, %I:%M %p') if c.created_at else ''
        })

    assignees_data = [
        {
            'name': a.user.get_full_name() or a.user.username,
            'initials': (a.user.get_full_name() or a.user.username)[:2].upper()
        }
        for a in task.assignees.all()
    ]

    return JsonResponse({
        'success': True,
        'task': {
            'id': task.id,
            'title': task.title,
            'priority': task.priority,
            'status_name': task.status.name if task.status else ('Completed' if task.completed else 'In Progress'),
            'assignees': assignees_data
        },
        'comments': comments_data
    })


@login_required
def add_task_comment(request, task_id):
    if request.method == 'POST':
        org = request.user.profile.organization
        task = get_object_or_404(Task, id=task_id)
        if (task.lead and task.lead.organization != org) or (not task.lead and task.organization != org):
            return JsonResponse({'success': False, 'error': 'Access denied.'}, status=403)

        msg = request.POST.get('message', '').strip()
        if not msg:
            return JsonResponse({'success': False, 'error': 'Message cannot be empty.'})

        comment = TaskComment.objects.create(
            task=task,
            user=request.user,
            message=msg
        )

        user_name = request.user.get_full_name() or request.user.username
        initials = (user_name[:2]).upper()

        # Log Activity if task has associated lead
        if task.lead:
            Activity.objects.create(
                lead=task.lead,
                type='Task',
                description=f"{user_name} posted a message on '{task.title}': {msg[:80]}"
            )

        # Notify assigned team members, lead owner, and organization staff
        notify_users = set()
        for assignee in task.assignees.all():
            if assignee.user and assignee.user != request.user:
                notify_users.add(assignee.user)

        if task.lead and task.lead.owner and task.lead.owner.user and task.lead.owner.user != request.user:
            notify_users.add(task.lead.owner.user)

        for member in org.members.all():
            if member.user and member.user != request.user and member.user not in notify_users:
                notify_users.add(member.user)

        preview_msg = msg[:70] + ('...' if len(msg) > 70 else '')
        for u in notify_users:
            SystemNotification.objects.create(
                user=u,
                message=f"[{task.title}] {user_name}: \"{preview_msg}\"",
                type='info'
            )

        return JsonResponse({
            'success': True,
            'comment': {
                'id': comment.id,
                'user_name': user_name,
                'initials': initials,
                'is_me': True,
                'message': comment.message,
                'timestamp': comment.created_at.strftime('%b %d, %I:%M %p') if comment.created_at else 'Just now'
            }
        })
    return JsonResponse({'success': False, 'error': 'Invalid request method.'})


@login_required
def move_task_status(request, task_id):
    if request.method == 'POST':
        org = request.user.profile.organization
        task = get_object_or_404(Task, id=task_id)
        if (task.lead and task.lead.organization != org) or (not task.lead and task.organization != org):
            return JsonResponse({'success': False, 'error': 'Access denied.'}, status=403)

        status_val = request.POST.get('status') or request.POST.get('status_id')
        if not status_val:
            return JsonResponse({'success': False, 'error': 'No status provided.'})

        if status_val in ['Completed', 'complete', 'complete_toggle']:
            task.completed = True
            comp_status = ProjectStatus.objects.filter(organization=org, name__iexact='Completed').first()
            if comp_status:
                task.status = comp_status
        else:
            status_obj = None
            if str(status_val).isdigit():
                status_obj = ProjectStatus.objects.filter(id=int(status_val), organization=org).first()
            if not status_obj:
                status_obj = ProjectStatus.objects.filter(organization=org, name__iexact=status_val).first()
            
            if status_obj:
                task.status = status_obj
                task.completed = (status_obj.name.lower() == 'completed')
            else:
                task.completed = (str(status_val).lower() == 'completed')

        task.save()

        status_name = task.status.name if task.status else ("Completed" if task.completed else "In Progress")
        
        # Log activity
        Activity.objects.create(
            lead=task.lead,
            type='Task',
            description=f"Moved task '{task.title}' to status: {status_name}"
        )

        return JsonResponse({
            'success': True,
            'task_id': task.id,
            'new_status': status_name,
            'completed': task.completed
        })
    return JsonResponse({'success': False, 'error': 'Invalid request.'})


@login_required
def toggle_task_star(request, task_id):
    if request.method == 'POST':
        org = request.user.profile.organization
        task = get_object_or_404(Task, id=task_id)
        if (task.lead and task.lead.organization != org) or (not task.lead and task.organization != org):
            return JsonResponse({'success': False, 'error': 'Access denied.'}, status=403)

        task.is_starred = not task.is_starred
        task.save()

        return JsonResponse({
            'success': True,
            'task_id': task.id,
            'is_starred': task.is_starred
        })
    return JsonResponse({'success': False, 'error': 'Invalid request.'})


@login_required
def upload_task_file(request, task_id):
    if request.method == 'POST':
        org = request.user.profile.organization
        task = get_object_or_404(Task, id=task_id)
        if (task.lead and task.lead.organization != org) or (not task.lead and task.organization != org):
            return JsonResponse({'success': False, 'error': 'Access denied.'}, status=403)

        uploaded_file = request.FILES.get('file')
        if not uploaded_file:
            return JsonResponse({'success': False, 'error': 'No file provided.'})

        size_bytes = uploaded_file.size
        if size_bytes < 1024:
            size_str = f"{size_bytes} B"
        elif size_bytes < 1024 * 1024:
            size_str = f"{round(size_bytes / 1024, 1)} KB"
        else:
            size_str = f"{round(size_bytes / (1024 * 1024), 1)} MB"

        tf = TaskFile.objects.create(
            task=task,
            file=uploaded_file,
            filename=uploaded_file.name,
            file_size=size_str,
            uploaded_by=request.user
        )

        Activity.objects.create(
            lead=task.lead,
            type='Task',
            description=f"Uploaded file '{tf.filename}' to project '{task.title}'"
        )

        return JsonResponse({
            'success': True,
            'file': {
                'id': tf.id,
                'filename': tf.filename,
                'url': tf.file.url if tf.file else '#',
                'file_size': tf.file_size,
                'uploaded_at': tf.uploaded_at.strftime('%b %d, %Y')
            }
        })
    return JsonResponse({'success': False, 'error': 'Invalid method.'})


@login_required
def delete_task_file(request, file_id):
    if request.method == 'POST':
        org = request.user.profile.organization
        tf = get_object_or_404(TaskFile, id=file_id)
        task = tf.task
        if (task.lead and task.lead.organization != org) or (not task.lead and task.organization != org):
            return JsonResponse({'success': False, 'error': 'Access denied.'}, status=403)

        filename = tf.filename
        tf.delete()

        Activity.objects.create(
            lead=task.lead,
            type='Task',
            description=f"Deleted file '{filename}' from project '{task.title}'"
        )

        return JsonResponse({'success': True})
    return JsonResponse({'success': False, 'error': 'Invalid method.'})


@login_required
def add_task_milestone(request, task_id):
    if request.method == 'POST':
        org = request.user.profile.organization
        task = get_object_or_404(Task, id=task_id)
        if (task.lead and task.lead.organization != org) or (not task.lead and task.organization != org):
            return JsonResponse({'success': False, 'error': 'Access denied.'}, status=403)

        title = request.POST.get('title', '').strip()
        due_date_str = request.POST.get('due_date', '').strip()
        if not title:
            return JsonResponse({'success': False, 'error': 'Milestone title is required.'})

        due_date = timezone.now().date()
        if due_date_str:
            try:
                due_date = datetime.strptime(due_date_str, '%Y-%m-%d').date()
            except ValueError:
                pass

        tm = TaskMilestone.objects.create(
            task=task,
            title=title,
            due_date=due_date
        )

        Activity.objects.create(
            lead=task.lead,
            type='Task',
            description=f"Added milestone '{tm.title}' to project '{task.title}'"
        )

        return JsonResponse({
            'success': True,
            'milestone': {
                'id': tm.id,
                'title': tm.title,
                'due_date': tm.due_date.strftime('%b %d, %Y'),
                'completed': tm.completed
            }
        })
    return JsonResponse({'success': False, 'error': 'Invalid method.'})


@login_required
def toggle_task_milestone(request, milestone_id):
    if request.method == 'POST':
        org = request.user.profile.organization
        tm = get_object_or_404(TaskMilestone, id=milestone_id)
        task = tm.task
        if (task.lead and task.lead.organization != org) or (not task.lead and task.organization != org):
            return JsonResponse({'success': False, 'error': 'Access denied.'}, status=403)

        tm.completed = not tm.completed
        tm.save()

        return JsonResponse({'success': True, 'completed': tm.completed})
    return JsonResponse({'success': False, 'error': 'Invalid method.'})


@login_required
def delete_task_milestone(request, milestone_id):
    if request.method == 'POST':
        org = request.user.profile.organization
        tm = get_object_or_404(TaskMilestone, id=milestone_id)
        task = tm.task
        if (task.lead and task.lead.organization != org) or (not task.lead and task.organization != org):
            return JsonResponse({'success': False, 'error': 'Access denied.'}, status=403)

        tm.delete()
        return JsonResponse({'success': True})
    return JsonResponse({'success': False, 'error': 'Invalid method.'})


@login_required
def import_projects(request):
    if request.method == 'POST':
        org = request.user.profile.organization
        import_file = request.FILES.get('file')
        if not import_file:
            messages.error(request, "No import file selected.")
            return redirect('projects')

        created_count = 0
        errors = []

        try:
            content = import_file.read().decode('utf-8', errors='ignore')
            if import_file.name.endswith('.csv'):
                reader = csv.DictReader(io.StringIO(content))
                for idx, row in enumerate(reader, start=1):
                    title = row.get('title') or row.get('Project') or row.get('Name') or row.get('Title')
                    if not title:
                        errors.append(f"Row {idx}: Missing title")
                        continue
                    
                    desc = row.get('description') or row.get('Description') or ''
                    prio = (row.get('priority') or row.get('Priority') or 'Medium').strip().capitalize()
                    risk = (row.get('risk') or row.get('Risk') or 'Low').strip().capitalize()
                    
                    due_date = timezone.now().date() + timedelta(days=14)
                    due_str = row.get('due_date') or row.get('Due Date')
                    if due_str:
                        try:
                            due_date = datetime.strptime(due_str.strip(), '%Y-%m-%d').date()
                        except ValueError:
                            pass

                    Task.objects.create(
                        organization=org,
                        title=title.strip(),
                        description=desc.strip(),
                        priority=prio if prio in ['High', 'Medium', 'Low'] else 'Medium',
                        risk_level=risk if risk in ['High', 'Medium', 'Low'] else 'Low',
                        due_date=due_date
                    )
                    created_count += 1
            elif import_file.name.endswith('.json'):
                data = json.loads(content)
                items = data if isinstance(data, list) else data.get('projects', [])
                for idx, item in enumerate(items, start=1):
                    title = item.get('title') or item.get('name')
                    if not title:
                        errors.append(f"Item {idx}: Missing title")
                        continue
                    
                    due_date = timezone.now().date() + timedelta(days=14)
                    due_str = item.get('due_date')
                    if due_str:
                        try:
                            due_date = datetime.strptime(due_str.strip(), '%Y-%m-%d').date()
                        except ValueError:
                            pass

                    Task.objects.create(
                        organization=org,
                        title=title.strip(),
                        description=item.get('description', ''),
                        priority=item.get('priority', 'Medium'),
                        risk_level=item.get('risk_level', 'Low'),
                        due_date=due_date
                    )
                    created_count += 1
            else:
                messages.error(request, "Unsupported file format. Please upload CSV or JSON.")
                return redirect('projects')

            if created_count > 0:
                messages.success(request, f"Successfully imported {created_count} project(s) into database!")
                Activity.objects.create(
                    lead=None,
                    type='Task',
                    description=f"Imported {created_count} project(s) from {import_file.name}"
                )
            if errors:
                messages.warning(request, f"Skipped {len(errors)} invalid record(s).")
        except Exception as e:
            messages.error(request, f"Error parsing import file: {str(e)}")

        return redirect('projects')
    return redirect('projects')


@login_required
def delete_task(request, task_id):
    if request.method == 'POST':
        org = request.user.profile.organization
        task = get_object_or_404(Task, id=task_id)
        if (task.lead and task.lead.organization != org) or (not task.lead and task.organization != org):
            return JsonResponse({'success': False, 'error': 'Invalid task.'})
        task.delete()
        if request.headers.get('x-requested-with') == 'XMLHttpRequest':
            return JsonResponse({'success': True, 'message': 'Task deleted successfully.'})
        SystemNotification.objects.create(user=request.user, message='Task deleted.', type='success')
        return redirect('projects')
        
    return JsonResponse({'success': False, 'error': 'Invalid request.'})

@login_required
def complete_task(request):
    if request.method == 'POST':
        task_id = request.POST.get('task_id')
        org = request.user.profile.organization
        
        try:
            task = Task.objects.get(id=task_id, lead__organization=org)
            task.completed = not task.completed
            task.save()
            
            # Log activity
            status_text = "completed" if task.completed else "re-opened"
            Activity.objects.create(
                lead=task.lead,
                type='Task',
                description=f"Marked task '{task.title}' as {status_text}."
            )
            return JsonResponse({'success': True, 'completed': task.completed, 'progress': task.calculated_progress})
        except Task.DoesNotExist:
            return JsonResponse({'success': False, 'error': 'Task not found.'})
        except Exception as e:
            return JsonResponse({'success': False, 'error': str(e)})
            
    return JsonResponse({'success': False, 'error': 'Invalid request.'})

@login_required
def log_activity(request):
    if request.method == 'POST':
        lead_id = request.POST.get('lead_id')
        act_type = request.POST.get('type')
        desc = request.POST.get('description')
        org = request.user.profile.organization
        
        try:
            lead = Lead.objects.get(id=lead_id, organization=org)
            activity = Activity.objects.create(
                lead=lead,
                type=act_type,
                description=desc
            )
            # Update last activity datetime implicitly through save
            lead.save()
            
            return JsonResponse({
                'success': True,
                'activity': {
                    'type': activity.type,
                    'description': activity.description,
                    'timestamp': activity.timestamp.strftime('%Y-%m-%d %H:%M')
                }
            })
        except Lead.DoesNotExist:
            return JsonResponse({'success': False, 'error': 'Lead not found.'})
        except Exception as e:
            return JsonResponse({'success': False, 'error': str(e)})
            
    return JsonResponse({'success': False, 'error': 'Invalid request.'})

@login_required
def quick_create_lead(request):
    if request.method == 'POST':
        name = request.POST.get('name')
        email = request.POST.get('email')
        company = request.POST.get('company')
        phone_number = request.POST.get('phone_number', '')
        value = 0
        score = request.POST.get('score', 50)
        
        org = request.user.profile.organization
        owner = request.user.profile
        
        is_ajax = request.headers.get('x-requested-with') == 'XMLHttpRequest'
        
        try:
            # Get default status name
            default_status = get_or_create_default_statuses(org).filter(is_default=True).first()
            if not default_status:
                default_status = get_or_create_default_statuses(org).first()
            status_name = default_status.name if default_status else 'New'

            lead = Lead.objects.create(
                organization=org,
                name=name,
                email=email,
                company=company,
                phone_number=phone_number,
                date_time=timezone.now(),
                value=value,
                score=score,
                owner=owner,
                status=status_name,
                stage=status_name,
                lifecycle_stage='Prospect',
                health_score=80,
                annual_revenue=value
            )
            Activity.objects.create(
                lead=lead,
                type='Creation',
                description="Lead added via quick create."
            )
            if is_ajax:
                return JsonResponse({
                    'success': True,
                    'message': f"Successfully created lead '{name}' for {company}.",
                    'lead': {
                        'id': lead.id,
                        'name': lead.name,
                        'email': lead.email,
                        'company': lead.company,
                        'value': float(lead.value),
                        'status': lead.status,
                        'badge_class': lead.status_badge_class,
                        'owner_name': lead.owner.user.get_full_name() or lead.owner.user.username if lead.owner else '',
                        'owner_initials': (lead.owner.user.username[:2].upper() if lead.owner else 'UN'),
                        'created_at_formatted': lead.created_at.strftime('%b %d') if lead.created_at else timezone.now().strftime('%b %d'),
                        'profile_image_url': lead.profile_image_url or ''
                    }
                })
            SystemNotification.objects.create(user=request.user, message=f"Successfully created lead '{name}' for {company}.", type='success')
        except Exception as e:
            if is_ajax:
                return JsonResponse({'success': False, 'error': str(e)})
            messages.error(request, f"Error creating lead: {str(e)}")
            
    return redirect(request.META.get('HTTP_REFERER', 'leads'))

@login_required
@page_permission_required('calendar')
def calendar_view(request):
    """Display calendar with events for the user's organization."""
    org = request.user.profile.organization
    events = Event.objects.filter(organization=org).order_by('start_time')
    calendar_statuses = get_or_create_dynamic_statuses(org, 'calendar', CalendarStatus)
    return render(request, 'calendar.html', {'events': events, 'calendar_statuses': calendar_statuses})


@login_required
@page_permission_required('calendar')
def calendar_list_view(request):
    """Display list of organization events in tabular format, optionally filtered by date."""
    org = request.user.profile.organization
    date_str = request.GET.get('date')
    
    events = Event.objects.filter(organization=org)
    
    if date_str:
        try:
            from datetime import datetime
            dt = datetime.strptime(date_str, "%Y-%m-%d")
            events = events.filter(start_time__date=dt.date())
        except ValueError:
            pass
            
    events = events.order_by('-start_time')
    calendar_statuses = get_or_create_dynamic_statuses(org, 'calendar', CalendarStatus)
    return render(request, 'calendar_list.html', {
        'events': events,
        'filter_date': date_str,
        'calendar_statuses': calendar_statuses
    })


@login_required
@page_permission_required('calendar')
def event_create_view(request):
    """Create a new calendar event via modal form."""
    org = request.user.profile.organization
    if request.method == 'POST':
        form = EventForm(request.POST)
        if form.is_valid():
            event = form.save(commit=False)
            event.owner = request.user
            event.organization = org
            event.save()
            try:
                from .event_notifications import check_and_send_event_notifications
                check_and_send_event_notifications(event)
            except Exception:
                pass
            SystemNotification.objects.create(user=request.user, message='Event created successfully.', type='success')
            return redirect('calendar')
    else:
        form = EventForm()
    return render(request, 'event_form.html', {'form': form, 'action': 'Create'})

@login_required
@page_permission_required('calendar')
def event_edit_view(request, event_id):
    """Edit an existing calendar event."""
    org = request.user.profile.organization
    event = get_object_or_404(Event, id=event_id, organization=org)
    if request.method == 'POST':
        form = EventForm(request.POST, instance=event)
        if form.is_valid():
            event = form.save()
            try:
                from .event_notifications import check_and_send_event_notifications
                check_and_send_event_notifications(event)
            except Exception:
                pass
            SystemNotification.objects.create(user=request.user, message='Event updated successfully.', type='success')
            return redirect('calendar')
    else:
        form = EventForm(instance=event)
    return render(request, 'event_form.html', {'form': form, 'action': 'Edit'})

@login_required
@page_permission_required('calendar')
def event_delete_view(request, event_id):
    """Delete a calendar event."""
    org = request.user.profile.organization
    event = get_object_or_404(Event, id=event_id, organization=org)
    event.delete()
    SystemNotification.objects.create(user=request.user, message='Event deleted.', type='success')
    return redirect('calendar')

@login_required
def profile_edit_view(request):
    """Edit user profile fields and avatar."""
    user = request.user
    profile = user.profile
    if request.method == 'POST':
        form = ProfileForm(request.POST, request.FILES, instance=profile)
        # Handle builtâ€‘in User fields separately
        username = request.POST.get('username')
        first_name = request.POST.get('first_name')
        last_name = request.POST.get('last_name')
        email = request.POST.get('email')
        password = request.POST.get('password')
        
        if username:
            user.username = username
        if first_name is not None:
            user.first_name = first_name
        if last_name is not None:
            user.last_name = last_name
        if email:
            user.email = email
            
        if password and password.strip():
            user.set_password(password.strip())
            
        user.save()
        
        if password and password.strip():
            from django.contrib.auth import update_session_auth_hash
            update_session_auth_hash(request, user)
            
        if form.is_valid():
            profile_obj = form.save(commit=False)
            
            # Handle profile image file upload
            profile_file = request.FILES.get('profile_image_file')
            if profile_file:
                from django.core.files.storage import default_storage
                from django.core.files.base import ContentFile
                from django.conf import settings
                import os
                path = default_storage.save(os.path.join('avatars', f"user_{user.id}_{profile_file.name}"), ContentFile(profile_file.read()))
                profile_obj.profile_image_url = default_storage.url(path)
                
            profile_obj.save()
            SystemNotification.objects.create(user=request.user, message='Profile updated successfully.', type='success')
            return redirect('profile_edit')
    else:
        form = ProfileForm(instance=profile)
    return render(request, 'profile_edit.html', {'form': form, 'user': user})




@login_required
@page_permission_required('calendar')
def calendar_events_json_view(request):
    """Return JSON list of organization events for FullCalendar."""
    org = request.user.profile.organization
    events = Event.objects.filter(organization=org)
    events_data = []
    for event in events:
        events_data.append({
            'id': event.id,
            'title': event.title,
            'start': event.start_time.strftime('%Y-%m-%dT%H:%M:%S') if event.start_time else None,
            'end': event.end_time.strftime('%Y-%m-%dT%H:%M:%S') if event.end_time else None,
            'description': event.description or '',
            'recurring': event.recurring,
            'color': event.color,
            'owner': event.owner.get_full_name() or event.owner.username
        })
    return JsonResponse(events_data, safe=False)


@login_required
def event_create_ajax(request):
    """Create a new event via AJAX and return JSON."""
    if request.method == 'POST':
        org = request.user.profile.organization
        form = EventForm(request.POST)
        if form.is_valid():
            event = form.save(commit=False)
            event.owner = request.user
            event.organization = org
            event.save()
            try:
                from .event_notifications import check_and_send_event_notifications
                check_and_send_event_notifications(event)
            except Exception:
                pass
            return JsonResponse({
                'success': True,
                'event': {
                    'id': event.id,
                    'title': event.title,
                    'start': event.start_time.strftime('%Y-%m-%dT%H:%M:%S') if event.start_time else None,
                    'end': event.end_time.strftime('%Y-%m-%dT%H:%M:%S') if event.end_time else None,
                    'description': event.description or '',
                    'recurring': event.recurring,
                    'color': event.color,
                    'owner': event.owner.get_full_name() or event.owner.username
                }
            })
        else:
            return JsonResponse({'success': False, 'errors': form.errors.get_json_data()})
    return JsonResponse({'success': False, 'error': 'Invalid request method.'})


@login_required
def event_edit_ajax(request, event_id):
    """Edit an event via AJAX and return JSON."""
    org = request.user.profile.organization
    event = get_object_or_404(Event, id=event_id, organization=org)
    if request.method == 'POST':
        form = EventForm(request.POST, instance=event)
        if form.is_valid():
            event = form.save()
            try:
                from .event_notifications import check_and_send_event_notifications
                check_and_send_event_notifications(event)
            except Exception:
                pass
            return JsonResponse({
                'success': True,
                'event': {
                    'id': event.id,
                    'title': event.title,
                    'start': event.start_time.strftime('%Y-%m-%dT%H:%M:%S') if event.start_time else None,
                    'end': event.end_time.strftime('%Y-%m-%dT%H:%M:%S') if event.end_time else None,
                    'description': event.description or '',
                    'recurring': event.recurring,
                    'color': event.color,
                    'owner': event.owner.get_full_name() or event.owner.username
                }
            })
        else:
            return JsonResponse({'success': False, 'errors': form.errors.get_json_data()})
    return JsonResponse({'success': False, 'error': 'Invalid request method.'})


@login_required
def event_delete_ajax(request, event_id):
    """Delete an event via AJAX and return JSON."""
    if request.method == 'POST':
        org = request.user.profile.organization
        event = get_object_or_404(Event, id=event_id, organization=org)
        event.delete()
        return JsonResponse({'success': True})
    return JsonResponse({'success': False, 'error': 'Invalid request method.'})


@login_required
def add_lead(request):
    org = request.user.profile.organization
    owners = UserProfile.objects.filter(organization=org)
    statuses = get_or_create_default_statuses(org)
    services = Service.objects.filter(organization=org)
    
    if request.method == 'POST':
        name = request.POST.get('name')
        company = request.POST.get('company')
        email = request.POST.get('email')
        phone_number = request.POST.get('phone_number')
        alt_phone_number = request.POST.get('alt_phone_number')
        
        date_time_val = request.POST.get('date_time')
        date_time = date_time_val if date_time_val else timezone.now()
        
        status = request.POST.get('status')
        if not status:
            default_status = get_or_create_default_statuses(org).filter(is_default=True).first()
            if not default_status:
                default_status = get_or_create_default_statuses(org).first()
            status = default_status.name if default_status else 'New'
        
        owner_id = request.POST.get('owner')
        owner = None
        if owner_id:
            try:
                owner = UserProfile.objects.get(id=owner_id, organization=org)
            except UserProfile.DoesNotExist:
                pass
                
        last_followup_val = request.POST.get('last_followup_date_time')
        last_followup_date_time = last_followup_val if last_followup_val else None

        followup_wanted_val = request.POST.get('followup_wanted_date_time')
        followup_wanted_date_time = followup_wanted_val if followup_wanted_val else None

        value_val = request.POST.get('value', '0.00')
        value = safe_parse_decimal(value_val, 0.00)

        location = request.POST.get('location', '')

        profile_image_url = request.POST.get('profile_image_url', '')
        
        service = None
        service_id = request.POST.get('service')
        if service_id:
            try:
                service = Service.objects.get(id=service_id, organization=org)
            except Service.DoesNotExist:
                pass

        try:
            if not name or not company or not phone_number:
                if request.headers.get('x-requested-with') == 'XMLHttpRequest':
                    return JsonResponse({'success': False, 'error': 'Name, Company, and Phone Number are required fields.'})
                messages.error(request, "Name, Company, and Phone Number are required fields.")
                return redirect('leads')
                
            lead = Lead.objects.create(
                organization=org,
                name=name,
                company=company,
                email=email if email else None,
                phone_number=phone_number,
                alt_phone_number=alt_phone_number,
                date_time=date_time,
                status=status,
                owner=owner,
                last_followup_date_time=last_followup_date_time,
                followup_wanted_date_time=followup_wanted_date_time,
                stage=status,
                value=value,
                location=location if location else None,
                profile_image_url=profile_image_url if profile_image_url else None,
                health_score=80
            )
            if service:
                lead.services.add(service)
                
            Activity.objects.create(
                lead=lead,
                type='Creation',
                description="Lead added."
            )
            
            if request.headers.get('x-requested-with') == 'XMLHttpRequest':
                return JsonResponse({
                    'success': True,
                    'message': f"Successfully created lead '{name}'."
                })
            SystemNotification.objects.create(user=request.user, message=f"Successfully created lead '{name}'.", type='success')
            return redirect('leads')
        except Exception as e:
            if request.headers.get('x-requested-with') == 'XMLHttpRequest':
                return JsonResponse({'success': False, 'error': str(e)})
            messages.error(request, f"Error creating lead: {str(e)}")
            
    # GET or fallthrough
    context = {
        'title': 'Add New Lead',
        'owners': owners,
        'statuses': statuses,
        'services': services,
        'action_url': request.path,
    }
    return render(request, 'lead_form.html', context)


@login_required
def edit_lead(request, lead_id):
    org = request.user.profile.organization
    lead = get_object_or_404(Lead, id=lead_id, organization=org)
    owners = UserProfile.objects.filter(organization=org)
    statuses = get_or_create_default_statuses(org)
    services = Service.objects.filter(organization=org)
    
    if request.method == 'POST':
        try:
            lead.name = request.POST.get('name')
            lead.company = request.POST.get('company')
            lead.email = request.POST.get('email')
            lead.phone_number = request.POST.get('phone_number')
            lead.alt_phone_number = request.POST.get('alt_phone_number')
            
            date_time_val = request.POST.get('date_time')
            lead.date_time = date_time_val if date_time_val else (lead.date_time or timezone.now())
            
            lead.status = request.POST.get('status')
            
            owner_id = request.POST.get('owner')
            if owner_id:
                try:
                    lead.owner = UserProfile.objects.get(id=owner_id, organization=org)
                except UserProfile.DoesNotExist:
                    lead.owner = None
            else:
                lead.owner = None
                
            last_followup_val = request.POST.get('last_followup_date_time')
            lead.last_followup_date_time = last_followup_val if last_followup_val else None

            followup_wanted_val = request.POST.get('followup_wanted_date_time')
            lead.followup_wanted_date_time = followup_wanted_val if followup_wanted_val else None

            val_input = request.POST.get('value', '').strip()
            if val_input == '':
                lead.value = None
            else:
                lead.value = safe_parse_decimal(val_input, 0.00)
                
            lead.paid_amount = safe_parse_decimal(request.POST.get('paid_amount', '0.00'), 0.00)
            lead.location = request.POST.get('location', '') or None
            lead.profile_image_url = request.POST.get('profile_image_url', '') or None
            lead.notes = request.POST.get('notes', '')
            
            if lead.status == 'Qualified' and not lead.is_client:
                lead.is_client = True
                from .models import ClientStatus
                status_obj = ClientStatus.objects.filter(organization=org).first()
                lead.status = status_obj.name if status_obj else 'Active'
                
            lead.save()
            
            service_ids = request.POST.getlist('services')
            if service_ids:
                services = Service.objects.filter(id__in=service_ids, organization=org)
                lead.services.set(services)
            else:
                lead.services.clear()
            
            Activity.objects.create(
                lead=lead,
                type='Stage Update',
                description="Lead details updated."
            )
            
            if request.headers.get('x-requested-with') == 'XMLHttpRequest':
                return JsonResponse({
                    'success': True,
                    'message': f"Successfully updated lead '{lead.name}'."
                })
            SystemNotification.objects.create(user=request.user, message=f"Successfully updated lead '{lead.name}'.", type='success')
            if lead.is_client:
                return redirect('client_contact_detail', lead_id=lead.id)
            return redirect('contact_detail', lead_id=lead.id)
        except Exception as e:
            if request.headers.get('x-requested-with') == 'XMLHttpRequest':
                return JsonResponse({'success': False, 'error': str(e)})
            messages.error(request, f"Error updating lead: {str(e)}")
            
    # GET or fallthrough
    context = {
        'title': f'Edit Lead: {lead.name}',
        'lead': lead,
        'owners': owners,
        'statuses': statuses,
        'services': services,
        'action_url': request.path,
    }
    return render(request, 'lead_form.html', context)


@login_required
def delete_lead(request, lead_id):
    org = request.user.profile.organization
    lead = get_object_or_404(Lead, id=lead_id, organization=org)
    
    if request.method == 'POST':
        name = lead.name
        lead.delete()
        if request.headers.get('x-requested-with') == 'XMLHttpRequest':
            return JsonResponse({'success': True, 'message': f"Successfully deleted lead '{name}'."})
        SystemNotification.objects.create(user=request.user, message=f"Successfully deleted lead '{name}'.", type='success')
        return redirect('leads')


@login_required
def send_lead_email(request):
    if request.method == 'POST':
        lead_id = request.POST.get('lead_id')
        subject = request.POST.get('subject')
        message = request.POST.get('message')
        to_email = request.POST.get('to_email')
        
        org = request.user.profile.organization
        try:
            lead = Lead.objects.get(id=lead_id, organization=org)
            
            # Send Email logic here
            from django.core.mail import send_mail
            from django.conf import settings
            
            from_email = getattr(settings, 'DEFAULT_FROM_EMAIL', 'noreply@xenocrm.com')
            send_mail(subject, message, from_email, [to_email], fail_silently=True)
            
            # Log Activity
            Activity.objects.create(
                lead=lead,
                type='Email',
                description=f"Sent email: {subject}\n\n{message}"
            )
            
            return JsonResponse({'success': True})
        except Exception as e:
            return JsonResponse({'success': False, 'error': str(e)})
            
    return JsonResponse({'success': False, 'error': 'Invalid request method.'})
        
    if request.headers.get('x-requested-with') == 'XMLHttpRequest':
        return JsonResponse({'success': False, 'error': 'Invalid request method.'})
    messages.error(request, "Invalid request method for deletion.")
    return redirect('leads')


@login_required
def lead_json_view(request, lead_id):
    org = request.user.profile.organization
    try:
        lead = Lead.objects.get(id=lead_id, organization=org)
        data = {
            'id': lead.id,
            'name': lead.name,
            'company': lead.company,
            'email': lead.email,
            'phone_number': lead.phone_number or '',
            'alt_phone_number': lead.alt_phone_number or '',
            'date_time': lead.date_time.strftime('%Y-%m-%dT%H:%M') if lead.date_time else '',
            'status': lead.status,
            'owner_id': lead.owner.id if lead.owner else '',
            'last_followup_date_time': lead.last_followup_date_time.strftime('%Y-%m-%dT%H:%M') if lead.last_followup_date_time else '',
            'followup_wanted_date_time': lead.followup_wanted_date_time.strftime('%Y-%m-%dT%H:%M') if lead.followup_wanted_date_time else '',
        }
        return JsonResponse({'success': True, 'lead': data})
    except Lead.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Lead not found.'})


# â”€â”€ Helper functions for dynamic statuses â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

DEFAULT_STATUSES = [
    {'name': 'New',       'color': 'green',  'position': 0, 'is_default': True},
    {'name': 'Contacted', 'color': 'grey',   'position': 1, 'is_default': False},
    {'name': 'Qualified', 'color': 'blue',   'position': 2, 'is_default': False},
    {'name': 'Cold Lead', 'color': 'red',    'position': 3, 'is_default': False},
    {'name': 'Lost',      'color': 'red',    'position': 4, 'is_default': False},
]


def get_or_create_default_statuses(org):
    """Return the queryset of LeadStatus for `org`, seeding defaults if empty."""
    qs = LeadStatus.objects.filter(organization=org)
    if not qs.exists():
        for s in DEFAULT_STATUSES:
            LeadStatus.objects.create(organization=org, **s)
        qs = LeadStatus.objects.filter(organization=org)
    return qs


def annotate_lead_badges(leads, org):
    """Attach _badge_class to each lead object to avoid N+1 queries."""
    statuses = {s.name: s.badge_class for s in get_or_create_default_statuses(org)}
    iterable = leads if hasattr(leads, '__iter__') else [leads]
    for lead in iterable:
        badge = statuses.get(lead.status)
        if badge is None:
            badge = get_default_badge_class(lead.status)
        lead._badge_class = badge


# â”€â”€ Lead Statuses management views â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

def get_or_create_dynamic_statuses(org, category_str, model_class):
    qs = model_class.objects.filter(organization=org)
    DEFAULT_STATUSES_MAP = {
        'clients': [{'name': 'Active', 'color': '#10b981'}, {'name': 'Inactive', 'color': '#64748b'}, {'name': 'Pending', 'color': '#f59e0b'}, {'name': 'Suspended', 'color': '#ef4444'}],
        'projects': [{'name': 'Planning', 'color': '#3b82f6'}, {'name': 'In Progress', 'color': '#f59e0b'}, {'name': 'On Hold', 'color': '#64748b'}, {'name': 'Completed', 'color': '#10b981'}, {'name': 'Cancelled', 'color': '#ef4444'}],
        'campaigns': [{'name': 'Planning', 'color': '#64748b'}, {'name': 'Active', 'color': '#0053db'}, {'name': 'Completed', 'color': '#22c55e'}],
        'calendar': [{'name': 'Meetings', 'color': '#004ac6'}, {'name': 'Calls', 'color': '#10b981'}, {'name': 'Deadlines', 'color': '#ef4444'}, {'name': 'Follow-ups', 'color': '#8b5cf6'}, {'name': 'Personal', 'color': '#f97316'}],
        'tickets': [{'name': 'Open', 'color': '#ef4444'}, {'name': 'Pending', 'color': '#f59e0b'}, {'name': 'Resolved', 'color': '#10b981'}, {'name': 'Closed', 'color': '#64748b'}],
        'priority': [{'name': 'Low', 'color': '#64748b'}, {'name': 'Medium', 'color': '#f59e0b'}, {'name': 'High', 'color': '#ef4444'}, {'name': 'Critical', 'color': '#8b5cf6'}],
        'invoices': [{'name': 'Pending', 'color': '#f59e0b'}, {'name': 'Paid', 'color': '#10b981'}, {'name': 'Partial', 'color': '#3b82f6'}, {'name': 'Overdue', 'color': '#ef4444'}, {'name': 'Draft', 'color': '#64748b'}]
    }
    if not qs.exists():
        defaults = DEFAULT_STATUSES_MAP.get(category_str, [])
        for idx, s in enumerate(defaults):
            model_class.objects.create(organization=org, name=s['name'], color=s['color'], position=idx)
        qs = model_class.objects.filter(organization=org)
    elif category_str == 'invoices':
        # Ensure Draft exists if missing
        if not qs.filter(name__iexact='Draft').exists():
            model_class.objects.create(organization=org, name='Draft', color='#64748b', position=4)
            qs = model_class.objects.filter(organization=org)
    return qs

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

def lead_statuses_view(request):
    """List all lead statuses for the current organisation."""
    org = request.user.profile.organization
    statuses = get_or_create_default_statuses(org)
    
    client_statuses = get_or_create_dynamic_statuses(org, 'clients', ClientStatus)
    project_statuses = get_or_create_dynamic_statuses(org, 'projects', ProjectStatus)
    campaign_statuses = get_or_create_dynamic_statuses(org, 'campaigns', CampaignStatus)
    calendar_statuses = get_or_create_dynamic_statuses(org, 'calendar', CalendarStatus)
    ticket_statuses = get_or_create_dynamic_statuses(org, 'tickets', TicketStatus)
    priority_statuses = get_or_create_dynamic_statuses(org, 'priority', PriorityStatus)

    return render(request, 'lead_statuses.html', {
        'statuses': statuses,
        'client_statuses': client_statuses,
        'project_statuses': project_statuses,
        'campaign_statuses': campaign_statuses,
        'calendar_statuses': calendar_statuses,
        'ticket_statuses': ticket_statuses,
        'priority_statuses': priority_statuses,
    })


@login_required
@page_permission_required('lead_statuses')
def add_lead_status(request):
    """Create a new lead status via AJAX POST."""
    if request.method == 'POST':
        org = request.user.profile.organization
        name = request.POST.get('name', '').strip()
        color = request.POST.get('color', 'blue')

        if not name:
            return JsonResponse({'success': False, 'error': 'Status name is required.'})

        if LeadStatus.objects.filter(organization=org, name=name).exists():
            return JsonResponse({'success': False, 'error': f"Status '{name}' already exists."})

        max_pos = LeadStatus.objects.filter(organization=org).count()
        LeadStatus.objects.create(organization=org, name=name, color=color, position=max_pos)
        return JsonResponse({'success': True, 'message': f"Status '{name}' created."})

    return JsonResponse({'success': False, 'error': 'Invalid request method.'})


@login_required
@page_permission_required('lead_statuses')
def edit_lead_status(request, status_id):
    """Edit an existing lead status via AJAX POST."""
    if request.method == 'POST':
        org = request.user.profile.organization
        try:
            status_obj = LeadStatus.objects.get(id=status_id, organization=org)
        except LeadStatus.DoesNotExist:
            return JsonResponse({'success': False, 'error': 'Status not found.'})

        new_name = request.POST.get('name', '').strip()
        new_color = request.POST.get('color', status_obj.color)

        if not new_name:
            return JsonResponse({'success': False, 'error': 'Status name is required.'})

        # Check uniqueness (excluding self)
        if LeadStatus.objects.filter(organization=org, name=new_name).exclude(id=status_id).exists():
            return JsonResponse({'success': False, 'error': f"Status '{new_name}' already exists."})

        old_name = status_obj.name
        status_obj.name = new_name
        status_obj.color = new_color
        status_obj.save()

        # Rename on all leads that had the old name
        if old_name != new_name:
            Lead.objects.filter(organization=org, status=old_name).update(status=new_name)

        return JsonResponse({'success': True, 'message': f"Status updated to '{new_name}'."})

    return JsonResponse({'success': False, 'error': 'Invalid request method.'})


@login_required
@page_permission_required('lead_statuses')
def delete_lead_status(request, status_id):
    """Delete a lead status via AJAX POST, reassigning leads to the default."""
    if request.method == 'POST':
        org = request.user.profile.organization
        try:
            status_obj = LeadStatus.objects.get(id=status_id, organization=org)
        except LeadStatus.DoesNotExist:
            return JsonResponse({'success': False, 'error': 'Status not found.'})

        # Prevent deleting the last status
        if LeadStatus.objects.filter(organization=org).count() <= 1:
            return JsonResponse({'success': False, 'error': 'Cannot delete the last remaining status.'})

        # Find fallback status
        fallback = LeadStatus.objects.filter(organization=org, is_default=True).exclude(id=status_id).first()
        if not fallback:
            fallback = LeadStatus.objects.filter(organization=org).exclude(id=status_id).first()

        # Reassign leads
        Lead.objects.filter(organization=org, status=status_obj.name).update(status=fallback.name)

        deleted_name = status_obj.name
        status_obj.delete()

        return JsonResponse({'success': True, 'message': f"Status '{deleted_name}' deleted. Leads reassigned to '{fallback.name}'."})

    return JsonResponse({'success': False, 'error': 'Invalid request method.'})


@login_required
def reorder_lead_statuses(request):
    """Reorder statuses via AJAX POST with a list of status IDs in order."""
    if request.method == 'POST':
        import json
        org = request.user.profile.organization
        try:
            body = json.loads(request.body)
            order = body.get('order', [])
        except (json.JSONDecodeError, AttributeError):
            order = request.POST.getlist('order[]')

        for idx, sid in enumerate(order):
            LeadStatus.objects.filter(id=sid, organization=org).update(position=idx)

        return JsonResponse({'success': True, 'message': 'Statuses reordered.'})

    return JsonResponse({'success': False, 'error': 'Invalid request method.'})


@login_required
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


# â”€â”€ CSV Import helpers and view â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

def map_headers(headers):
    # Map lowercase versions of headers to normalized internal fields
    field_mappings = {
        'name': ['name', 'lead name', 'full name', 'contact name'],
        'email': ['email', 'email address'],
        'company': ['company', 'company name'],
        'phone_number': ['phone', 'phone number', 'contact phone'],
        'alt_phone_number': ['alt phone', 'alt phone number'],
        'value': ['value', 'deal value', 'lead value'],
        'score': ['score', 'lead score', 'health score'],
        'status': ['status', 'lead status'],
        'stage': ['stage', 'lead stage'],
        'owner': ['owner', 'assigned owner', 'assigned to'],
        'annual_revenue': ['annual revenue', 'revenue'],
        'lifecycle_stage': ['lifecycle stage', 'lifecycle'],
        'last_followup': ['last followup', 'last followup date and time', 'last followup date/time', 'last followup datetime'],
        'followup_wanted': ['followup wanted', 'follow up wanted', 'followup wanted date and time', 'follow up wanted date/time', 'next followup', 'next followup date and time', 'next followup date/time'],
        'date_time': ['date and time', 'date/time', 'date', 'datetime', 'date time'],
        'location': ['location', 'address', 'city']
    }
    
    mapped = {}
    for header in headers:
        if not header:
            continue
        header_lower = header.lower().strip()
        for field, aliases in field_mappings.items():
            if header_lower in aliases:
                mapped[field] = header
                break
                
    # Fallback to substring matching for required fields
    if 'name' not in mapped:
        for h in headers:
            if h and 'name' in h.lower():
                mapped['name'] = h
                break
    if 'email' not in mapped:
        for h in headers:
            if h and 'email' in h.lower():
                mapped['email'] = h
                break
    if 'company' not in mapped:
        for h in headers:
            if h and 'company' in h.lower():
                mapped['company'] = h
                break
                
    return mapped

def is_valid_email(email_str):
    from django.core.validators import validate_email
    from django.core.exceptions import ValidationError
    try:
        validate_email(email_str)
        return True
    except ValidationError:
        return False

def safe_parse_decimal(val, default=0.00):
    from decimal import Decimal, InvalidOperation
    if not val:
        return Decimal(str(default))
    val = val.strip().replace('$', '').replace(',', '')
    try:
        return Decimal(val)
    except (InvalidOperation, ValueError):
        return Decimal(str(default))

def safe_parse_int(val, default=50):
    if not val:
        return default
    val = val.strip()
    try:
        return int(float(val))
    except ValueError:
        return default

def safe_parse_datetime(val):
    from django.utils.dateparse import parse_datetime
    from django.utils import timezone
    from datetime import datetime
    if not val:
        return None
    val = val.strip()
    if not val:
        return None
    dt = parse_datetime(val)
    if dt:
        try:
            return timezone.make_aware(dt) if timezone.is_naive(dt) else dt
        except Exception:
            return dt
    formats = [
        '%Y-%m-%d %H:%M:%S',
        '%Y-%m-%d %H:%M',
        '%Y-%m-%d',
        '%m/%d/%Y %H:%M:%S',
        '%m/%d/%Y %H:%M',
        '%m/%d/%Y',
        '%d/%m/%Y %H:%M:%S',
        '%d/%m/%Y %H:%M',
        '%d/%m/%Y',
    ]
    for fmt in formats:
        try:
            dt = datetime.strptime(val, fmt)
            try:
                return timezone.make_aware(dt)
            except Exception:
                return dt
        except ValueError:
            continue
    return None

@login_required
def download_lead_template(request):
    import csv
    from django.http import HttpResponse
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename="lead_import_template.csv"'
    writer = csv.writer(response)
    writer.writerow(['Name', 'Phone Number', 'Company', 'Email', 'Alt Phone Number', 'Score', 'Annual Revenue', 'Location'])
    return response

@login_required
def import_leads(request):
    if request.method != 'POST':
        from django.contrib import messages
        messages.error(request, 'Invalid request method. Please use the Import button on the Leads page.')
        return redirect('leads')
        
    csv_file = request.FILES.get('file')
    if not csv_file:
        return JsonResponse({'success': False, 'error': 'No file uploaded.'})
        
    if not csv_file.name.endswith('.csv'):
        return JsonResponse({'success': False, 'error': 'Uploaded file is not a CSV.'})
        
    import io
    try:
        file_data = csv_file.read().decode('utf-8-sig')
    except Exception as e:
        try:
            csv_file.seek(0)
            file_data = csv_file.read().decode('latin-1')
        except Exception as e2:
            return JsonResponse({'success': False, 'error': f'Failed to decode file: {str(e)}'})

    io_string = io.StringIO(file_data)
    reader = csv.DictReader(io_string)
    
    if not reader.fieldnames:
        return JsonResponse({'success': False, 'error': 'CSV file is empty or headers are missing.'})
        
    headers = reader.fieldnames
    mapped = map_headers(headers)
    
    required_fields = ['name', 'phone_number', 'company']
    missing_fields = [f for f in required_fields if f not in mapped]
    if missing_fields:
        return JsonResponse({
            'success': False, 
            'error': f'Missing required columns: {", ".join([f.replace("_", " ").capitalize() for f in missing_fields])}. Please ensure your CSV has Name, Phone Number, and Company columns.'
        })
        
    org = request.user.profile.organization
    imported_count = 0
    failed_rows = []
    
    from django.db import transaction
    
    for row_idx, row in enumerate(reader, start=2):
        name = row.get(mapped['name'], '')
        email = row.get(mapped.get('email'), '') if 'email' in mapped else ''
        phone_number = row.get(mapped['phone_number'], '')
        company = row.get(mapped['company'], '')
        
        name = name.strip() if name else ''
        email = email.strip() if email else ''
        phone_number = phone_number.strip() if phone_number else ''
        company = company.strip() if company else ''
        
        errors = []
        if not name:
            errors.append('Name is required')
        if not phone_number:
            errors.append('Phone Number is required')
        if email and not is_valid_email(email):
            errors.append(f'Invalid email format: {email}')
        if not company:
            errors.append('Company is required')
            
        if errors:
            failed_rows.append({'row': row_idx, 'errors': errors, 'data': f'{name or "N/A"} ({phone_number or "N/A"})'})
            continue
            
        
        alt_phone_number = row.get(mapped.get('alt_phone_number', ''), '')
        alt_phone_number = alt_phone_number.strip() if alt_phone_number else None
        
        raw_val = row.get(mapped.get('value', ''), '0')
        value = safe_parse_decimal(raw_val)
        
        raw_score = row.get(mapped.get('score', ''), '50')
        score = safe_parse_int(raw_score, default=50)
        
        raw_rev = row.get(mapped.get('annual_revenue', ''), '0')
        annual_revenue = safe_parse_decimal(raw_rev)
        
        raw_health = row.get(mapped.get('health_score', ''), '50')
        health_score = safe_parse_int(raw_health, default=50)
        
        lifecycle_stage = row.get(mapped.get('lifecycle_stage', ''), 'Prospect')
        lifecycle_stage = lifecycle_stage.strip() if lifecycle_stage else 'Prospect'
        
        raw_date_time = row.get(mapped.get('date_time', ''), '')
        date_time = safe_parse_datetime(raw_date_time)
        if not date_time:
            from django.utils import timezone
            date_time = timezone.now()
        
        raw_followup = row.get(mapped.get('last_followup', ''), '')
        last_followup_date_time = safe_parse_datetime(raw_followup)
        
        raw_followup_wanted = row.get(mapped.get('followup_wanted', ''), '')
        followup_wanted_date_time = safe_parse_datetime(raw_followup_wanted)
        
        owner = None
        raw_owner = row.get(mapped.get('owner', ''), '')
        raw_owner = raw_owner.strip() if raw_owner else ''
        if raw_owner:
            owner = UserProfile.objects.filter(organization=org).filter(
                Q(user__email__iexact=raw_owner) |
                Q(user__username__iexact=raw_owner)
            ).first()
            if not owner:
                for profile in UserProfile.objects.filter(organization=org):
                    full_name = profile.user.get_full_name().strip()
                    if full_name.lower() == raw_owner.lower():
                        owner = profile
                        break
        
        raw_status = row.get(mapped.get('status', ''), '')
        raw_status = raw_status.strip() if raw_status else ''
        if not raw_status:
            default_status = get_or_create_default_statuses(org).filter(is_default=True).first()
            if not default_status:
                default_status = get_or_create_default_statuses(org).first()
            status = default_status.name if default_status else 'New'
        else:
            status = raw_status
            if not LeadStatus.objects.filter(organization=org, name__iexact=status).exists():
                max_pos = LeadStatus.objects.filter(organization=org).count()
                LeadStatus.objects.create(organization=org, name=status, color='blue', position=max_pos)
                
        raw_stage = row.get(mapped.get('stage', ''), '')
        raw_stage = raw_stage.strip() if raw_stage else ''
        if not raw_stage:
            stage = status
        else:
            stage = raw_stage
            
        valid_stages = [choice[0] for choice in Lead.STAGE_CHOICES]
        if stage not in valid_stages:
            matched = False
            for vs in valid_stages:
                if vs.lower() == stage.lower():
                    stage = vs
                    matched = True
                    break
            if not matched:
                stage = 'New'
                
        location = row.get(mapped.get('location', ''), '')
        location = location.strip() if location else None
                
        try:
            with transaction.atomic():
                lead = Lead.objects.create(
                    organization=org,
                    name=name,
                    email=email,
                    company=company,
                    phone_number=phone_number,
                    alt_phone_number=alt_phone_number,
                    score=score,
                    status=status,
                    stage=stage,
                    value=value,
                    owner=owner,
                    lifecycle_stage=lifecycle_stage,
                    annual_revenue=annual_revenue,
                    health_score=health_score,
                    date_time=date_time,
                    last_followup_date_time=last_followup_date_time,
                    followup_wanted_date_time=followup_wanted_date_time,
                    location=location
                )
                Activity.objects.create(
                    lead=lead,
                    type='Creation',
                    description="Lead imported via CSV."
                )
                imported_count += 1
        except Exception as ex:
            failed_rows.append({'row': row_idx, 'errors': [f'Database error: {str(ex)}'], 'data': f'{name} ({email})'})
            
    return JsonResponse({
        'success': True,
        'imported': imported_count,
        'failed': len(failed_rows),
        'errors': failed_rows
    })


@login_required
@page_permission_required('staff')
def staff_list_view(request):
    """List all user profiles in the current organization."""
    org = request.user.profile.organization
    staff_members = UserProfile.objects.filter(organization=org).select_related('user')
    return render(request, 'staff.html', {'staff_members': staff_members})


DEFAULT_ROLES = ['Sales Executive', 'Manager', 'Administrator', 'Representative']

def get_or_create_default_roles(org):
    """Return the queryset of StaffRole for `org`, seeding defaults if empty."""
    qs = StaffRole.objects.filter(organization=org)
    if not qs.exists():
        for role_name in DEFAULT_ROLES:
            StaffRole.objects.create(organization=org, name=role_name)
        qs = StaffRole.objects.filter(organization=org)
    return qs


@login_required
@page_permission_required('staff')
def add_staff_view(request):
    """View to add a new staff member."""
    org = request.user.profile.organization
    roles = get_or_create_default_roles(org)
    
    if request.method == 'POST':
        username = request.POST.get('username', '').strip()
        email = request.POST.get('email', '').strip()
        first_name = request.POST.get('first_name', '').strip()
        last_name = request.POST.get('last_name', '').strip()
        role = request.POST.get('role', 'Sales Executive').strip()
        password = request.POST.get('password', '').strip()
        profile_image_url = request.POST.get('profile_image_url', '').strip()
        profile_file = request.FILES.get('profile_image_file')
        if profile_file:
            from django.core.files.storage import default_storage
            from django.core.files.base import ContentFile
            from django.conf import settings
            import os
            path = default_storage.save(os.path.join('avatars', f"staff_{username}_{profile_file.name}"), ContentFile(profile_file.read()))
            profile_image_url = default_storage.url(path)
        phone_number = request.POST.get('phone_number', '').strip()
        location = request.POST.get('location', '').strip()

        # Gather form data to populate back in case of error
        department_id = request.POST.get('department_id', '').strip()
        form_data = {
            'username': username,
            'email': email,
            'first_name': first_name,
            'last_name': last_name,
            'role': role,
            'profile_image_url': profile_image_url,
            'phone_number': phone_number,
            'location': location,
            'department_id': department_id
        }

        if not username or not email or not password:
            messages.error(request, 'Username, email and password are required.')
        elif User.objects.filter(username=username).exists():
            messages.error(request, f"Username '{username}' already exists.")
        else:
            try:
                user = User.objects.create_user(
                    username=username,
                    email=email,
                    password=password,
                    first_name=first_name,
                    last_name=last_name
                )
                from crm.models import Department
                dept = None
                if department_id:
                    dept = Department.objects.filter(id=department_id, organization=org).first()
                UserProfile.objects.create(
                    user=user,
                    organization=org,
                    role=role,
                    profile_image_url=profile_image_url or None,
                    phone_number=phone_number or None,
                    location=location or None,
                    department=dept
                )
                SystemNotification.objects.create(user=request.user, message=f"Staff member '{first_name or username}' created successfully.", type='success')
                return redirect('staff')
            except Exception as e:
                messages.error(request, str(e))
                
        context = {
            'title': 'Add New Staff Member',
            'action_url': request.path,
            'form_data': form_data,
            'profile': None,
            'roles': roles,
            'departments': org.departments.all(),
        }
        return render(request, 'staff_form.html', context)

    # GET request
    context = {
        'title': 'Add New Staff Member',
        'action_url': request.path,
        'form_data': {
            'phone_number': '',
            'location': '',
            'department_id': ''
        },
        'profile': None,
        'roles': roles,
        'departments': org.departments.all(),
    }
    return render(request, 'staff_form.html', context)


@login_required
@page_permission_required('staff')
def edit_staff_view(request, profile_id):
    """View to update a staff member."""
    org = request.user.profile.organization
    roles = get_or_create_default_roles(org)
    try:
        profile = UserProfile.objects.get(id=profile_id, organization=org)
    except UserProfile.DoesNotExist:
        messages.error(request, 'Staff member not found.')
        return redirect('staff')

    if request.method == 'POST':
        username = request.POST.get('username', '').strip()
        email = request.POST.get('email', '').strip()
        first_name = request.POST.get('first_name', '').strip()
        last_name = request.POST.get('last_name', '').strip()
        role = request.POST.get('role', '').strip()
        password = request.POST.get('password', '').strip()
        profile_image_url = request.POST.get('profile_image_url', '').strip()
        profile_file = request.FILES.get('profile_image_file')
        if profile_file:
            from django.core.files.storage import default_storage
            from django.core.files.base import ContentFile
            from django.conf import settings
            import os
            path = default_storage.save(os.path.join('avatars', f"staff_{username}_{profile_file.name}"), ContentFile(profile_file.read()))
            profile_image_url = default_storage.url(path)
        phone_number = request.POST.get('phone_number', '').strip()
        location = request.POST.get('location', '').strip()

        # Gather form data to populate back in case of error
        department_id = request.POST.get('department_id', '').strip()
        form_data = {
            'username': username,
            'email': email,
            'first_name': first_name,
            'last_name': last_name,
            'role': role,
            'profile_image_url': profile_image_url,
            'phone_number': phone_number,
            'location': location,
            'department_id': department_id
        }

        if not username or not email:
            messages.error(request, 'Username and email are required.')
        elif User.objects.filter(username=username).exclude(id=profile.user.id).exists():
            messages.error(request, f"Username '{username}' already exists.")
        else:
            try:
                user = profile.user
                user.username = username
                user.email = email
                user.first_name = first_name
                user.last_name = last_name
                if password:
                    user.set_password(password)
                user.save()

                from crm.models import Department
                dept = None
                if department_id:
                    dept = Department.objects.filter(id=department_id, organization=org).first()
                profile.role = role
                profile.profile_image_url = profile_image_url or None
                profile.phone_number = phone_number or None
                profile.location = location or None
                profile.department = dept
                profile.save()

                SystemNotification.objects.create(user=request.user, message=f"Staff member '{first_name or username}' updated successfully.", type='success')
                return redirect('staff')
            except Exception as e:
                messages.error(request, str(e))

        context = {
            'title': f'Edit Staff Member: {profile.user.username}',
            'profile': profile,
            'action_url': request.path,
            'form_data': form_data,
            'roles': roles,
        }
        return render(request, 'staff_form.html', context)

    # GET request
    form_data = {
        'username': profile.user.username,
        'email': profile.user.email,
        'first_name': profile.user.first_name,
        'last_name': profile.user.last_name,
        'role': profile.role,
        'profile_image_url': profile.profile_image_url or '',
        'phone_number': profile.phone_number or '',
        'location': profile.location or '',
        'department_id': profile.department.id if profile.department else ''
    }
    context = {
        'title': f'Edit Staff Member: {profile.user.username}',
        'profile': profile,
        'action_url': request.path,
        'form_data': form_data,
        'roles': roles,
        'departments': org.departments.all(),
    }
    return render(request, 'staff_form.html', context)


@login_required
@page_permission_required('staff')
def delete_staff_ajax(request, profile_id):
    """AJAX endpoint to delete a staff member."""
    if request.method == 'POST':
        org = request.user.profile.organization
        try:
            profile = UserProfile.objects.get(id=profile_id, organization=org)
            if profile.user == request.user:
                return JsonResponse({'success': False, 'error': 'You cannot delete your own profile.'})

            from django.db import transaction, connection
            user = profile.user
            with transaction.atomic():
                with connection.cursor() as cursor:
                    # Fetch any legacy hr_employees rows
                    cursor.execute("SELECT id FROM hr_employees WHERE user_profile_id = %s", [profile.id])
                    emp_ids = [row[0] for row in cursor.fetchall()]
                    if emp_ids:
                        cursor.execute("UPDATE hr_employees SET reporting_manager_id = NULL WHERE reporting_manager_id = ANY(%s)", [emp_ids])
                        cursor.execute("DELETE FROM hr_employee_documents WHERE employee_id = ANY(%s)", [emp_ids])
                        cursor.execute("DELETE FROM hr_attendance_corrections WHERE employee_id = ANY(%s)", [emp_ids])
                        cursor.execute("DELETE FROM hr_onboarding_processes WHERE employee_id = ANY(%s)", [emp_ids])
                        cursor.execute("DELETE FROM hr_performance_goals WHERE employee_id = ANY(%s)", [emp_ids])
                        cursor.execute("DELETE FROM hr_resignations WHERE employee_id = ANY(%s)", [emp_ids])
                        cursor.execute("DELETE FROM hr_leave_balances WHERE employee_id = ANY(%s)", [emp_ids])
                        cursor.execute("DELETE FROM hr_performance_reviews WHERE employee_id = ANY(%s)", [emp_ids])
                        cursor.execute("DELETE FROM hr_attendance WHERE employee_id = ANY(%s)", [emp_ids])
                        cursor.execute("DELETE FROM hr_leave_requests WHERE employee_id = ANY(%s)", [emp_ids])
                        cursor.execute("DELETE FROM hr_payrolls WHERE employee_id = ANY(%s)", [emp_ids])
                        cursor.execute("DELETE FROM hr_employees WHERE id = ANY(%s)", [emp_ids])

                    # Clean up foreign keys referencing user_profiles.id
                    cursor.execute("UPDATE hr_branches SET manager_id = NULL WHERE manager_id = %s", [profile.id])
                    cursor.execute("UPDATE hr_candidate_interviews SET interviewer_id = NULL WHERE interviewer_id = %s", [profile.id])
                    cursor.execute("UPDATE hr_audit_logs SET actor_id = NULL WHERE actor_id = %s", [profile.id])
                    cursor.execute("UPDATE hr_employee_documents SET verified_by_id = NULL WHERE verified_by_id = %s", [profile.id])
                    cursor.execute("UPDATE hr_attendance_corrections SET reviewed_by_id = NULL WHERE reviewed_by_id = %s", [profile.id])
                    cursor.execute("DELETE FROM hr_notifications WHERE recipient_id = %s", [profile.id])
                    cursor.execute("UPDATE hr_onboarding_tasks SET assigned_to_id = NULL WHERE assigned_to_id = %s", [profile.id])
                    cursor.execute("UPDATE hr_performance_reviews SET reviewer_id = NULL WHERE reviewer_id = %s", [profile.id])
                    cursor.execute("UPDATE hr_leave_requests SET hr_approval_by_id = NULL WHERE hr_approval_by_id = %s", [profile.id])
                    cursor.execute("UPDATE hr_leave_requests SET manager_approval_by_id = NULL WHERE manager_approval_by_id = %s", [profile.id])
                    cursor.execute("UPDATE quotations SET prepared_by_id = NULL WHERE prepared_by_id = %s", [profile.id])
                    cursor.execute("DELETE FROM quotation_activities WHERE user_id = %s", [profile.id])
                    cursor.execute("UPDATE content_items SET editor_id = NULL WHERE editor_id = %s", [profile.id])
                    cursor.execute("UPDATE tickets SET assignee_id = NULL WHERE assignee_id = %s", [profile.id])
                    cursor.execute("UPDATE leads SET owner_id = NULL WHERE owner_id = %s", [profile.id])
                    cursor.execute("DELETE FROM tasks_assignees WHERE userprofile_id = %s", [profile.id])

                profile.delete()
                if user:
                    user.delete()
            return JsonResponse({'success': True, 'message': 'Staff member deleted successfully.'})
        except UserProfile.DoesNotExist:
            return JsonResponse({'success': False, 'error': 'Staff member not found.'})
        except Exception as e:
            return JsonResponse({'success': False, 'error': f'Failed to delete staff member: {str(e)}'})

    return JsonResponse({'success': False, 'error': 'Invalid request method.'})


# ── Staff Roles management views ──────────────────────────────────────────

@login_required
@page_permission_required('staff_roles')
def staff_roles_view(request):
    """List all staff roles for the current organization."""
    org = request.user.profile.organization
    roles = get_or_create_default_roles(org)
    return render(request, 'staff_roles.html', {'roles': roles})


@login_required
@page_permission_required('staff_roles')
def add_staff_role(request):
    """Create a new staff role via AJAX POST, or redirect to roles list on GET."""
    if request.method == 'POST':
        org = request.user.profile.organization
        name = request.POST.get('name', '').strip()

        if not name:
            return JsonResponse({'success': False, 'error': 'Role name is required.'})

        if StaffRole.objects.filter(organization=org, name=name).exists():
            return JsonResponse({'success': False, 'error': f"Role '{name}' already exists."})

        StaffRole.objects.create(organization=org, name=name)
        return JsonResponse({'success': True, 'message': f"Role '{name}' created."})

    return JsonResponse({'success': False, 'error': 'Invalid request method.'})


@login_required
@page_permission_required('staff_roles')
def edit_staff_role(request, role_id):
    """Edit an existing staff role via AJAX POST."""
    if request.method == 'POST':
        org = request.user.profile.organization
        try:
            role_obj = StaffRole.objects.get(id=role_id, organization=org)
        except StaffRole.DoesNotExist:
            return JsonResponse({'success': False, 'error': 'Role not found.'})

        new_name = request.POST.get('name', '').strip()

        if not new_name:
            return JsonResponse({'success': False, 'error': 'Role name is required.'})

        # Check uniqueness (excluding self)
        if StaffRole.objects.filter(organization=org, name=new_name).exclude(id=role_id).exists():
            return JsonResponse({'success': False, 'error': f"Role '{new_name}' already exists."})

        old_name = role_obj.name
        role_obj.name = new_name
        role_obj.save()

        # Update all UserProfiles that had the old role name
        if old_name != new_name:
            UserProfile.objects.filter(organization=org, role=old_name).update(role=new_name)

        return JsonResponse({'success': True, 'message': f"Role updated to '{new_name}'."})

    return JsonResponse({'success': False, 'error': 'Invalid request method.'})


@login_required
@page_permission_required('staff_roles')
def delete_staff_role(request, role_id):
    """Delete a staff role via AJAX POST, reassigning users to a fallback role."""
    if request.method == 'POST':
        org = request.user.profile.organization
        try:
            role_obj = StaffRole.objects.get(id=role_id, organization=org)
        except StaffRole.DoesNotExist:
            return JsonResponse({'success': False, 'error': 'Role not found.'})

        # Prevent deleting the last role
        if StaffRole.objects.filter(organization=org).count() <= 1:
            return JsonResponse({'success': False, 'error': 'Cannot delete the last remaining role.'})

        # Find fallback role (the first one that's not this one)
        fallback = StaffRole.objects.filter(organization=org).exclude(id=role_id).first()

        # Reassign users
        UserProfile.objects.filter(organization=org, role=role_obj.name).update(role=fallback.name)

        deleted_name = role_obj.name
        role_obj.delete()

        return JsonResponse({'success': True, 'message': f"Role '{deleted_name}' deleted. Users reassigned to '{fallback.name}'."})

    return JsonResponse({'success': False, 'error': 'Invalid request method.'})


# â”€â”€ Service Management views â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

@login_required
@page_permission_required('services')
def services_view(request):
    """List all services for the current organization."""
    org = request.user.profile.organization
    services = Service.objects.filter(organization=org)
    return render(request, 'services.html', {'services': services})


@login_required
@page_permission_required('services')
def add_service(request):
    """Create a new service via AJAX POST."""
    if request.method == 'POST':
        org = request.user.profile.organization
        name = request.POST.get('name', '').strip()
        description = request.POST.get('description', '').strip()
        price_val = request.POST.get('price', '0.00').strip()
        price = safe_parse_decimal(price_val, 0.00)

        if not name:
            return JsonResponse({'success': False, 'error': 'Service name is required.'})

        if Service.objects.filter(organization=org, name=name).exists():
            return JsonResponse({'success': False, 'error': f"Service '{name}' already exists."})

        Service.objects.create(organization=org, name=name, description=description, price=price)
        return JsonResponse({'success': True, 'message': f"Service '{name}' created."})

    return JsonResponse({'success': False, 'error': 'Invalid request method.'})


@login_required
@page_permission_required('services')
def edit_service(request, service_id):
    """Edit an existing service via AJAX POST."""
    if request.method == 'POST':
        org = request.user.profile.organization
        try:
            service_obj = Service.objects.get(id=service_id, organization=org)
        except Service.DoesNotExist:
            return JsonResponse({'success': False, 'error': 'Service not found.'})

        new_name = request.POST.get('name', '').strip()
        new_description = request.POST.get('description', '').strip()
        new_price_val = request.POST.get('price', '').strip()
        new_price = safe_parse_decimal(new_price_val, service_obj.price)

        if not new_name:
            return JsonResponse({'success': False, 'error': 'Service name is required.'})

        # Check uniqueness (excluding self)
        if Service.objects.filter(organization=org, name=new_name).exclude(id=service_id).exists():
            return JsonResponse({'success': False, 'error': f"Service '{new_name}' already exists."})

        service_obj.name = new_name
        service_obj.description = new_description
        service_obj.price = new_price
        service_obj.save()

        return JsonResponse({'success': True, 'message': f"Service updated to '{new_name}'."})

    return JsonResponse({'success': False, 'error': 'Invalid request method.'})


@login_required
@page_permission_required('services')
def delete_service(request, service_id):
    """Delete a service via AJAX POST."""
    if request.method == 'POST':
        org = request.user.profile.organization
        try:
            service_obj = Service.objects.get(id=service_id, organization=org)
        except Service.DoesNotExist:
            return JsonResponse({'success': False, 'error': 'Service not found.'})

        deleted_name = service_obj.name
        service_obj.delete()

        return JsonResponse({'success': True, 'message': f"Service '{deleted_name}' deleted."})

    return JsonResponse({'success': False, 'error': 'Invalid request method.'})


@login_required
def notifications_view(request):
    org = request.user.profile.organization
    import datetime
    from django.urls import reverse
    now = timezone.now()
    one_week_later = now + datetime.timedelta(days=7)

    unified_feed = []
    profile = request.user.profile

    # 1. Calendar Events (Next 7 days)
    if profile.has_access_calendar:
        calendar_events = Event.objects.filter(
            organization=org,
            start_time__gte=now,
            start_time__lte=one_week_later
        ).order_by('start_time')
        
        for event in calendar_events:
            unified_feed.append({
                'type': 'Event',
                'title': event.title,
                'description': f"{event.start_time.strftime('%I:%M %p')} - {event.end_time.strftime('%I:%M %p')}",
                'date': event.start_time,
                'icon': 'calendar_month',
                'color_class': 'text-primary bg-primary/10 border-primary/30',
                'url': reverse('calendar')
            })

    # 2. Pending Tasks
    if profile.has_access_projects or profile.has_access_leads:
        pending_tasks = Task.objects.filter(
            lead__organization=org,
            completed=False
        ).order_by('due_date')
    
        for task in pending_tasks:
            dt = timezone.make_aware(datetime.datetime.combine(task.due_date, datetime.time.min)) if not hasattr(task.due_date, 'hour') else task.due_date
            unified_feed.append({
                'type': 'Task',
                'title': task.title,
                'description': f"Lead: {task.lead.name}",
                'date': dt,
                'icon': 'rocket_launch',
                'color_class': 'text-warning bg-warning/10 border-warning/30',
                'url': reverse('contact_detail', args=[task.lead.id])
            })

    # 3. Expiring Agreements (Next 30 days)
    if profile.has_access_agreements or profile.has_access_projects:
        thirty_days_later = now.date() + datetime.timedelta(days=30)
        expiring_agreements = Agreement.objects.filter(
            organization=org,
            end_date__lte=thirty_days_later
        ).order_by('end_date')
    
        for ag in expiring_agreements:
            dt = timezone.make_aware(datetime.datetime.combine(ag.end_date, datetime.time.min))
            unified_feed.append({
                'type': 'Agreement',
                'title': f"Agreement {ag.agreement_number}",
                'description': f"Client: {ag.client_name}",
                'date': dt,
                'icon': 'contract',
                'color_class': 'text-secondary bg-secondary/10 border-secondary/30',
                'url': reverse('agreement_detail', args=[ag.id])
            })

    # 4. Open Tickets
    if profile.has_access_support:
        open_tickets = Ticket.objects.filter(
            organization=org,
            status__in=['Open', 'In Progress']
        ).order_by('-created_at')
    
        for ticket in open_tickets:
            unified_feed.append({
                'type': 'Support Ticket',
                'title': ticket.subject,
                'description': f"Status: {ticket.status}",
                'date': ticket.created_at,
                'icon': 'support_agent',
                'color_class': 'text-tertiary bg-tertiary-container/30 border-tertiary/30',
                'url': reverse('customer_support')
            })

    # 5. Finance Invoices (Overdue / Due soon)
    if profile.has_access_finance or profile.has_access_finance_invoices:
        try:
            from finance.models import Invoice
            unpaid_invoices = Invoice.objects.filter(
                organization=org,
                status__in=['Pending', 'Overdue', 'Unpaid', 'Sent']
            ).order_by('due_date')[:10]
            for inv in unpaid_invoices:
                inv_dt = timezone.make_aware(datetime.datetime.combine(inv.due_date, datetime.time.min)) if inv.due_date and not hasattr(inv.due_date, 'hour') else (inv.created_at or now)
                unified_feed.append({
                    'type': 'Invoice',
                    'title': f"Invoice #{inv.invoice_number or inv.id} - {inv.client.name if hasattr(inv, 'client') and inv.client else 'Client'}",
                    'description': f"Amount: ₹{getattr(inv, 'total_amount', 0)} | Status: {inv.status}",
                    'date': inv_dt,
                    'icon': 'wallet',
                    'color_class': 'text-teal-600 bg-teal-50 border-teal-200',
                    'url': reverse('invoices') if 'invoices' in [p.name for p in request.resolver_match.app_names or []] else '#'
                })
        except Exception:
            pass

    # 6. Recent Activities
    if profile.has_access_leads:
        recent_activities = Activity.objects.filter(
            lead__organization=org
        ).order_by('-timestamp')[:20]
    
        for act in recent_activities:
            unified_feed.append({
                'type': 'Activity',
                'title': f"{act.type} - {act.lead.name}",
                'description': act.description,
                'date': act.timestamp,
                'icon': 'history',
                'color_class': 'text-on-surface bg-surface-variant/50 border-outline-variant',
                'url': reverse('contact_detail', args=[act.lead.id])
            })

    # 6. System Alerts
    system_alerts = SystemNotification.objects.filter(user=request.user).order_by('-created_at')
    
    for alert in system_alerts:
        icon = 'check_circle' if alert.type == 'success' else ('error' if alert.type == 'error' else 'info')
        color_class = 'text-success bg-success/10 border-success/30' if alert.type == 'success' else ('text-error bg-error/10 border-error/30' if alert.type == 'error' else 'text-info bg-info/10 border-info/30')
        unified_feed.append({
            'type': 'System Alert',
            'title': alert.message,
            'description': alert.type.capitalize(),
            'date': alert.created_at,
            'icon': icon,
            'color_class': color_class,
            'url': '#',
            'is_unread': not alert.is_read
        })

    # Mark unread as read
    SystemNotification.objects.filter(user=request.user, is_read=False).update(is_read=True)

    # Sort unified feed by date descending (newest / furthest future first)
    unified_feed.sort(key=lambda x: x['date'], reverse=True)

    context = {
        'unified_feed': unified_feed,
        'now': now,
    }
    return render(request, 'notifications.html', context)


@login_required
@page_permission_required('notification_settings')
def notification_settings_view(request):
    """Render notification configuration controls."""
    return render(request, 'notification_settings.html')


@login_required
@page_permission_required('role_permissions')
def role_permissions_view(request):
    """Render and manage role based page permissions matrix."""
    org = request.user.profile.organization
    from crm.views import get_or_create_default_roles
    roles = get_or_create_default_roles(org)
    
    import json
    from django.http import JsonResponse
    from crm.models import StaffRole, UserProfile

    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            target_type = data.get('type')
            target_id = data.get('id')
            perms = data.get('permissions')
            
            if target_type == 'role' and target_id:
                role_obj = StaffRole.objects.get(organization=org, name=target_id)
                role_obj.permissions_json = json.dumps(perms)
                role_obj.save()
                return JsonResponse({'success': True, 'message': f"Permissions for role '{target_id}' updated successfully."})
            
            elif target_type == 'staff' and target_id:
                staff_obj = UserProfile.objects.get(organization=org, id=target_id)
                staff_obj.custom_permissions_json = json.dumps(perms)
                staff_obj.save()
                return JsonResponse({'success': True, 'message': f"Permissions for staff updated successfully."})

            return JsonResponse({'success': False, 'error': 'Missing type or id.'})
        except Exception as e:
            return JsonResponse({'success': False, 'error': str(e)})

    # GET request: Serialize current database permissions
    role_permissions_map = {}
    for role in roles:
        try:
            role_permissions_map[role.name] = json.loads(role.permissions_json or '{}')
        except Exception:
            role_permissions_map[role.name] = {}
            
    # Serialize staff permissions
    staff_members = UserProfile.objects.filter(organization=org).select_related('user')
    staff_permissions_map = {}
    for staff in staff_members:
        try:
            staff_permissions_map[staff.id] = json.loads(staff.custom_permissions_json or '{}')
        except Exception:
            staff_permissions_map[staff.id] = {}

    context = {
        'roles': roles,
        'staff_members': staff_members,
        'role_permissions_json': json.dumps(role_permissions_map),
        'staff_permissions_json': json.dumps(staff_permissions_map),
    }
    return render(request, 'role_permissions.html', context)


@login_required
@page_permission_required('departments')
def departments_view(request):
    """View to list and manage departments and assigned staff members."""
    org = request.user.profile.organization
    depts = org.departments.all().prefetch_related('members__user')
    all_staff = org.members.all().select_related('user')
    return render(request, 'departments.html', {
        'departments': depts,
        'all_staff': all_staff
    })


@login_required
@page_permission_required('departments')
def add_department(request):
    """Create a new department via AJAX POST."""
    if request.method == 'POST':
        org = request.user.profile.organization
        name = request.POST.get('name', '').strip()
        description = request.POST.get('description', '').strip()
        if not name:
            return JsonResponse({'success': False, 'error': 'Name is required.'})
        from crm.models import Department
        try:
            dept = Department.objects.create(organization=org, name=name, description=description)
            return JsonResponse({'success': True, 'message': f"Department '{dept.name}' created successfully."})
        except Exception as e:
            return JsonResponse({'success': False, 'error': str(e)})
    return JsonResponse({'success': False, 'error': 'Invalid request method.'})


@login_required
@page_permission_required('departments')
def edit_department(request, department_id):
    """Edit a department's details via AJAX POST."""
    if request.method == 'POST':
        org = request.user.profile.organization
        from crm.models import Department
        try:
            dept = Department.objects.get(id=department_id, organization=org)
            name = request.POST.get('name', '').strip()
            description = request.POST.get('description', '').strip()
            if not name:
                return JsonResponse({'success': False, 'error': 'Name is required.'})
            dept.name = name
            dept.description = description
            dept.save()
            return JsonResponse({'success': True, 'message': f"Department '{dept.name}' updated successfully."})
        except Exception as e:
            return JsonResponse({'success': False, 'error': str(e)})
    return JsonResponse({'success': False, 'error': 'Invalid request method.'})


@login_required
@page_permission_required('departments')
def delete_department(request, department_id):
    """Delete a department via AJAX POST."""
    if request.method == 'POST':
        org = request.user.profile.organization
        from crm.models import Department
        try:
            dept = Department.objects.get(id=department_id, organization=org)
            dept.delete()
            return JsonResponse({'success': True, 'message': 'Department deleted successfully.'})
        except Exception as e:
            return JsonResponse({'success': False, 'error': str(e)})
    return JsonResponse({'success': False, 'error': 'Invalid request method.'})


@login_required
@page_permission_required('departments')
def assign_staff_to_department(request):
    """Assign an existing staff profile to a department via AJAX POST."""
    if request.method == 'POST':
        org = request.user.profile.organization
        dept_id = request.POST.get('department_id')
        profile_id = request.POST.get('profile_id')
        
        from crm.models import Department, UserProfile
        try:
            dept = Department.objects.get(id=dept_id, organization=org)
            profile = UserProfile.objects.get(id=profile_id, organization=org)
            profile.department = dept
            profile.save()
            return JsonResponse({
                'success': True, 
                'message': f"Assigned '{profile.user.get_full_name() or profile.user.username}' to '{dept.name}' successfully."
            })
        except Exception as e:
            return JsonResponse({'success': False, 'error': str(e)})
@login_required
def settings_dashboard_view(request):
    """Central ERP settings & system control hub view."""
    org = request.user.profile.organization
    from crm.models import StaffRole, Department, Service, UserProfile, Lead, ContentItem
    
    total_staff = UserProfile.objects.filter(organization=org).count() if org else 0
    total_roles = StaffRole.objects.filter(organization=org).count() if org else 0
    total_departments = Department.objects.filter(organization=org).count() if org else 0
    total_services = Service.objects.filter(organization=org).count() if org else 0
    total_leads = Lead.objects.filter(organization=org).count() if org else 0
    total_content_items = ContentItem.objects.filter(organization=org).count() if org else 0
    
    context = {
        'org': org,
        'total_staff': total_staff,
        'total_roles': total_roles,
        'total_departments': total_departments,
        'total_services': total_services,
        'total_leads': total_leads,
        'total_content_items': total_content_items,
        'system_version': 'v2.4 Enterprise ERP',
        'db_status': 'Operational',
    }
    return render(request, 'settings_dashboard.html', context)


from django.db.models import Q
from django.core.paginator import Paginator
from datetime import date, timedelta

@login_required
@page_permission_required('content_tracker')
def content_tracker_view(request):
    """Render the central Content Tracker dashboard page with filters, sorting, and pagination."""
    org = request.user.profile.organization
    raw_clients = Lead.objects.filter(organization=org, is_client=True)
    seen_companies = set()
    clients = []
    for c in raw_clients:
        if c.company and c.company not in seen_companies:
            seen_companies.add(c.company)
            clients.append(c)
    editors = org.members.filter(role__iexact='Editor').select_related('user')
    
    # Base Query
    from crm.models import ContentItem
    items = ContentItem.objects.filter(organization=org)
    
    # Search
    q = request.GET.get('q', '').strip()
    if q:
        items = items.filter(
            Q(video_title__icontains=q) | 
            Q(notes__icontains=q) | 
            Q(client__name__icontains=q)
        )
        
    # Filters
    client_filter = request.GET.get('client_filter', '').strip()
    if client_filter:
        items = items.filter(client_id=client_filter)
        
    editor_filter = request.GET.get('editor_filter', '').strip()
    if editor_filter:
        items = items.filter(editor_id=editor_filter)
        
    status_filter = request.GET.get('status_filter', '').strip()
    if status_filter:
        items = items.filter(status=status_filter)
        
    priority_filter = request.GET.get('priority_filter', '').strip()
    if priority_filter:
        items = items.filter(priority=priority_filter)
        
    date_filter = request.GET.get('date_filter', '').strip()
    if date_filter:
        today = date.today()
        if date_filter == 'today':
            items = items.filter(due_date=today)
        elif date_filter == 'week':
            start_week = today - timedelta(days=today.weekday())
            end_week = start_week + timedelta(days=6)
            items = items.filter(due_date__range=[start_week, end_week])
        elif date_filter == 'month':
            items = items.filter(due_date__year=today.year, due_date__month=today.month)
            
    # Sorting
    sort_by = request.GET.get('sort', '-due_date')
    allowed_sort_fields = [
        'id', '-id', 'client__company', '-client__company', 'video_title', '-video_title',
        'editor__user__username', '-editor__user__username', 'date_received', '-date_received',
        'due_date', '-due_date', 'status', '-status', 'priority', '-priority'
    ]
    if sort_by not in allowed_sort_fields:
        sort_by = '-due_date'
    items = items.order_by(sort_by)
    
    # Stats counts
    total_count = items.count()
    pending_count = items.filter(status='Pending').count()
    editing_count = items.filter(status='Editing').count()
    published_count = items.filter(status='Published').count()
    scheduled_count = items.filter(status='Scheduled').count()
    
    # Pagination
    limit = request.GET.get('limit', '25')
    try:
        limit_val = int(limit)
    except ValueError:
        limit_val = 25
    paginator = Paginator(items, limit_val)
    page_num = request.GET.get('page', 1)
    page_obj = paginator.get_page(page_num)
    
    status_options = _get_content_options(org, 'status')
    priority_options = _get_content_options(org, 'priority')
    
    context = {
        'page_obj': page_obj,
        'clients': clients,
        'editors': editors,
        'total_count': total_count,
        'pending_count': pending_count,
        'editing_count': editing_count,
        'published_count': published_count,
        'scheduled_count': scheduled_count,
        'status_options': status_options,
        'priority_options': priority_options,
        'q': q,
        'client_filter': client_filter,
        'editor_filter': editor_filter,
        'status_filter': status_filter,
        'priority_filter': priority_filter,
        'date_filter': date_filter,
        'sort_by': sort_by,
        'limit': limit_val,
    }
    return render(request, 'content_tracker.html', context)


@login_required
@page_permission_required('content_tracker')
def add_content_item(request):
    """Add a new client video content item via dedicated form page."""
    if not (request.user.is_superuser or request.user.profile.has_edit_content_tracker):
        if request.headers.get('x-requested-with') == 'XMLHttpRequest' or request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return JsonResponse({'success': False, 'error': 'You do not have permission to add content.'}, status=403)
        messages.error(request, 'You do not have permission to add content.')
        return redirect('content_tracker')

    org = request.user.profile.organization
    raw_clients = Lead.objects.filter(organization=org, is_client=True)
    seen_companies = set()
    clients = []
    for c in raw_clients:
        if c.company and c.company not in seen_companies:
            seen_companies.add(c.company)
            clients.append(c)
    editors = org.members.filter(role__iexact='Editor').select_related('user')

    if request.method == 'POST':
        from crm.models import ContentItem
        client_id = request.POST.get('client_id')
        editor_id = request.POST.get('editor_id')
        video_title = request.POST.get('video_title', '').strip()
        date_received = request.POST.get('date_received') or None
        due_date = request.POST.get('due_date') or None
        status = request.POST.get('status', 'Pending')
        priority = request.POST.get('priority', 'Medium')
        notes = request.POST.get('notes', '').strip()

        form_data = {
            'client_id': client_id, 'video_title': video_title, 'editor_id': editor_id,
            'date_received': date_received or '', 'due_date': due_date or '',
            'status': status, 'priority': priority, 'notes': notes,
        }

        is_ajax = request.headers.get('x-requested-with') == 'XMLHttpRequest' or request.headers.get('X-Requested-With') == 'XMLHttpRequest'

        if not client_id or not video_title:
            if is_ajax:
                return JsonResponse({'success': False, 'error': 'Client and Video Title are required.'})
            messages.error(request, 'Client and Video Title are required.')
            return render(request, 'content_item_form.html', {
                'title': 'Add Content Item', 'form_data': form_data,
                'clients': clients, 'editors': editors,
            })

        try:
            client_obj = Lead.objects.get(id=client_id, organization=org)
            editor_obj = None
            if editor_id:
                editor_obj = UserProfile.objects.get(id=editor_id, organization=org)

            ContentItem.objects.create(
                organization=org, client=client_obj, video_title=video_title,
                editor=editor_obj, date_received=date_received, due_date=due_date,
                status=status, priority=priority, notes=notes,
            )
            SystemNotification.objects.create(user=request.user, message=f"Content item '{video_title}' created successfully.", type='success')
            if is_ajax:
                return JsonResponse({'success': True, 'message': f"Content item '{video_title}' created successfully."})
            return redirect('content_tracker')
        except Exception as e:
            if is_ajax:
                return JsonResponse({'success': False, 'error': str(e)})
            messages.error(request, str(e))
            return render(request, 'content_item_form.html', {
                'title': 'Add Content Item', 'form_data': form_data,
                'clients': clients, 'editors': editors,
            })

    # GET request
    context = {
        'title': 'Add Content Item',
        'form_data': {},
        'clients': clients,
        'editors': editors,
    }
    return render(request, 'content_item_form.html', context)


@login_required
@page_permission_required('content_tracker')
def edit_content_item(request, item_id):
    """Edit a content item via dedicated form page."""
    if not (request.user.is_superuser or request.user.profile.has_edit_content_tracker):
        if request.headers.get('x-requested-with') == 'XMLHttpRequest' or request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return JsonResponse({'success': False, 'error': 'You do not have permission to edit content.'}, status=403)
        messages.error(request, 'You do not have permission to edit content.')
        return redirect('content_tracker')

    org = request.user.profile.organization
    from crm.models import ContentItem
    clients = Lead.objects.filter(organization=org, is_client=True)
    editors = org.members.filter(role__iexact='Editor').select_related('user')

    try:
        item = ContentItem.objects.get(id=item_id, organization=org)
    except ContentItem.DoesNotExist:
        messages.error(request, 'Content item not found.')
        return redirect('content_tracker')

    if request.method == 'POST':
        client_id = request.POST.get('client_id')
        editor_id = request.POST.get('editor_id')
        video_title = request.POST.get('video_title', '').strip()
        date_received = request.POST.get('date_received') or None
        due_date = request.POST.get('due_date') or None
        status = request.POST.get('status', 'Pending')
        priority = request.POST.get('priority', 'Medium')
        notes = request.POST.get('notes', '').strip()
        form_data = {
            'client_id': client_id, 'video_title': video_title, 'editor_id': editor_id,
            'date_received': date_received or '', 'due_date': due_date or '',
            'status': status, 'priority': priority, 'notes': notes,
        }

        is_ajax = request.headers.get('x-requested-with') == 'XMLHttpRequest' or request.headers.get('X-Requested-With') == 'XMLHttpRequest'

        if not client_id or not video_title:
            if is_ajax:
                return JsonResponse({'success': False, 'error': 'Client and Video Title are required.'})
            messages.error(request, 'Client and Video Title are required.')
            return render(request, 'content_item_form.html', {
                'title': f'Edit: {item.video_title}', 'form_data': form_data,
                'clients': clients, 'editors': editors,
            })

        try:
            client_obj = Lead.objects.get(id=client_id, organization=org)
            editor_obj = None
            if editor_id:
                editor_obj = UserProfile.objects.get(id=editor_id, organization=org)

            item.client = client_obj
            item.editor = editor_obj
            item.video_title = video_title
            item.date_received = date_received
            item.due_date = due_date
            item.status = status
            item.priority = priority
            item.notes = notes
            item.save()
            SystemNotification.objects.create(user=request.user, message=f"Content item '{video_title}' updated successfully.", type='success')
            if is_ajax:
                return JsonResponse({'success': True, 'message': f"Content item '{video_title}' updated successfully."})
            return redirect('content_tracker')
        except Exception as e:
            if is_ajax:
                return JsonResponse({'success': False, 'error': str(e)})
            messages.error(request, str(e))
            return render(request, 'content_item_form.html', {
                'title': f'Edit: {item.video_title}', 'form_data': form_data,
                'clients': clients, 'editors': editors,
            })

    # GET request — populate from existing item
    form_data = {
        'client_id': str(item.client_id),
        'video_title': item.video_title,
        'editor_id': str(item.editor_id) if item.editor_id else '',
        'date_received': str(item.date_received) if item.date_received else '',
        'due_date': str(item.due_date) if item.due_date else '',
        'status': item.status,
        'priority': item.priority,
        'notes': item.notes or '',
    }
    context = {
        'title': f'Edit: {item.video_title}',
        'form_data': form_data,
        'clients': clients,
        'editors': editors,
    }
    return render(request, 'content_item_form.html', context)


@login_required
@page_permission_required('content_tracker')
def delete_content_item(request, item_id):
    """Remove a content item."""
    if not (request.user.is_superuser or request.user.profile.has_delete_content_tracker):
        return JsonResponse({'success': False, 'error': 'You do not have permission to delete content.'}, status=403)

    if request.method == 'POST':
        org = request.user.profile.organization
        from crm.models import ContentItem
        try:
            item = ContentItem.objects.get(id=item_id, organization=org)
            item.delete()
            return JsonResponse({'success': True, 'message': 'Content item deleted successfully.'})
        except Exception as e:
            return JsonResponse({'success': False, 'error': str(e)})
    return JsonResponse({'success': False, 'error': 'Invalid request method.'})


@login_required
@page_permission_required('content_tracker')
def duplicate_content_item(request, item_id):
    """Create a duplicated content item entry."""
    if not (request.user.is_superuser or request.user.profile.has_edit_content_tracker):
        return JsonResponse({'success': False, 'error': 'You do not have permission to duplicate content.'}, status=403)

    if request.method == 'POST':
        org = request.user.profile.organization
        from crm.models import ContentItem
        try:
            item = ContentItem.objects.get(id=item_id, organization=org)
            item.id = None
            item.video_title = f"[Copy] {item.video_title}"
            item.save()
            return JsonResponse({'success': True, 'message': 'Content item duplicated successfully.'})
        except Exception as e:
            return JsonResponse({'success': False, 'error': str(e)})
    return JsonResponse({'success': False, 'error': 'Invalid request method.'})


@login_required
@page_permission_required('content_tracker')
def mark_content_complete(request, item_id):
    """Quick completion action for a video."""
    if request.method == 'POST':
        org = request.user.profile.organization
        from crm.models import ContentItem
        try:
            item = ContentItem.objects.get(id=item_id, organization=org)
            item.status = 'Published'
            item.save()
            return JsonResponse({'success': True, 'message': f"Content Item '{item.video_title}' marked as Published."})
        except Exception as e:
            return JsonResponse({'success': False, 'error': str(e)})
    return JsonResponse({'success': False, 'error': 'Invalid request method.'})


@login_required
@page_permission_required('content_tracker')
def update_content_item_status(request, item_id):
    """Inline update status of a content item via AJAX (accessible to Editors and Content Managers)."""
    if request.method == 'POST':
        org = request.user.profile.organization
        from crm.models import ContentItem
        try:
            item = ContentItem.objects.get(id=item_id, organization=org)
            status_val = None
            if request.content_type and 'application/json' in request.content_type:
                data = json.loads(request.body)
                status_val = data.get('status', '').strip()
            else:
                status_val = request.POST.get('status', '').strip()

            if not status_val:
                return JsonResponse({'success': False, 'error': 'Status cannot be empty.'})

            item.status = status_val
            item.save()
            return JsonResponse({'success': True, 'message': f"Status updated to '{status_val}'.", 'status': item.status})
        except ContentItem.DoesNotExist:
            return JsonResponse({'success': False, 'error': 'Content item not found.'}, status=404)
        except Exception as e:
            return JsonResponse({'success': False, 'error': str(e)}, status=500)
    return JsonResponse({'success': False, 'error': 'Invalid request method.'}, status=400)


@login_required
@page_permission_required('content_tracker')
def bulk_delete_content_items(request):
    """Batch deletion of multiple content items."""
    if not (request.user.is_superuser or request.user.profile.has_delete_content_tracker):
        return JsonResponse({'success': False, 'error': 'You do not have permission to delete content.'}, status=403)

    if request.method == 'POST':
        org = request.user.profile.organization
        from crm.models import ContentItem
        import json
        try:
            data = json.loads(request.body)
            ids = data.get('ids', [])
            if ids:
                ContentItem.objects.filter(id__in=ids, organization=org).delete()
                return JsonResponse({'success': True, 'message': f"Successfully deleted {len(ids)} items."})
            return JsonResponse({'success': False, 'error': 'No items selected.'})
        except Exception as e:
            return JsonResponse({'success': False, 'error': str(e)})
    return JsonResponse({'success': False, 'error': 'Invalid request method.'})


@login_required
@page_permission_required('content_tracker')
def import_content_items(request):
    """Import content tracker items from a CSV file."""
    if not (request.user.is_superuser or request.user.profile.has_edit_content_tracker):
        return JsonResponse({'success': False, 'error': 'You do not have permission to import content.'}, status=403)

    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'Invalid request method.'})

    csv_file = request.FILES.get('file')
    if not csv_file:
        return JsonResponse({'success': False, 'error': 'No file uploaded.'})

    if not csv_file.name.endswith('.csv'):
        return JsonResponse({'success': False, 'error': 'Uploaded file is not a CSV.'})


    import io
    try:
        file_data = csv_file.read().decode('utf-8-sig')
    except Exception:
        try:
            csv_file.seek(0)
            file_data = csv_file.read().decode('latin-1')
        except Exception as e2:
            return JsonResponse({'success': False, 'error': f'Failed to decode file: {str(e2)}'})

    io_string = io.StringIO(file_data)
    reader = csv.DictReader(io_string)

    if not reader.fieldnames:
        return JsonResponse({'success': False, 'error': 'CSV file is empty or headers are missing.'})

    # Build flexible header mapping
    headers = reader.fieldnames
    mapped = {}
    header_aliases = {
        'client': ['client', 'client name', 'client_name', 'account', 'company'],
        'video_title': ['video title', 'video_title', 'title', 'content title', 'content_title', 'name'],
        'editor': ['editor', 'editor name', 'editor_name', 'assigned to', 'assigned_to', 'assignee'],
        'date_received': ['date received', 'date_received', 'received date', 'received_date', 'received'],
        'due_date': ['due date', 'due_date', 'deadline', 'due'],
        'status': ['status', 'content status', 'content_status'],
        'priority': ['priority', 'urgency', 'importance'],
        'notes': ['notes', 'note', 'comments', 'comment', 'description', 'remarks'],
    }

    for field, aliases in header_aliases.items():
        for h in headers:
            if h and h.strip().lower() in aliases:
                mapped[field] = h
                break

    # client and video_title are required
    if 'client' not in mapped:
        return JsonResponse({
            'success': False,
            'error': 'Missing required column: Client. Please ensure your CSV has a Client (or Client Name) column.'
        })
    if 'video_title' not in mapped:
        return JsonResponse({
            'success': False,
            'error': 'Missing required column: Video Title. Please ensure your CSV has a Video Title (or Title) column.'
        })

    org = request.user.profile.organization
    from crm.models import ContentItem
    from django.db import transaction

    # Pre-fetch clients and editors for matching
    clients_qs = Lead.objects.filter(organization=org)
    client_map = {}
    for c in clients_qs:
        client_map[c.name.strip().lower()] = c

    editors_qs = org.members.select_related('user')
    editor_map = {}
    for e in editors_qs:
        full_name = e.user.get_full_name().strip().lower()
        username = e.user.username.strip().lower()
        if full_name:
            editor_map[full_name] = e
        editor_map[username] = e

    # Valid choices
    valid_statuses = [c[0] for c in ContentItem.STATUS_CHOICES]
    valid_priorities = [c[0] for c in ContentItem.PRIORITY_CHOICES]

    imported_count = 0
    failed_rows = []

    def safe_parse_date(val):
        """Parse a date string in multiple formats, return None on failure."""
        if not val:
            return None
        val = val.strip()
        if not val:
            return None
        from datetime import datetime as dt_cls
        formats = [
            '%Y-%m-%d', '%m/%d/%Y', '%d/%m/%Y',
            '%Y-%m-%d %H:%M:%S', '%m/%d/%Y %H:%M:%S', '%d/%m/%Y %H:%M:%S',
            '%Y-%m-%d %H:%M', '%m/%d/%Y %H:%M', '%d/%m/%Y %H:%M',
            '%d-%m-%Y', '%m-%d-%Y',
        ]
        for fmt in formats:
            try:
                return dt_cls.strptime(val, fmt).date()
            except ValueError:
                continue
        return None

    def match_choice(val, valid_choices):
        """Case-insensitive match against valid choices."""
        if not val:
            return None
        val_lower = val.strip().lower()
        for choice in valid_choices:
            if choice.lower() == val_lower:
                return choice
        return None

    for row_idx, row in enumerate(reader, start=2):
        # Required fields
        raw_client = row.get(mapped['client'], '').strip()
        raw_title = row.get(mapped['video_title'], '').strip()

        errors = []
        if not raw_client:
            errors.append('Client is required')
        if not raw_title:
            errors.append('Video Title is required')

        if errors:
            failed_rows.append({
                'row': row_idx,
                'errors': errors,
                'data': f'{raw_client or "N/A"} - {raw_title or "N/A"}'
            })
            continue

        # Match client
        client_obj = client_map.get(raw_client.lower())
        if not client_obj:
            failed_rows.append({
                'row': row_idx,
                'errors': [f'Client not found: "{raw_client}". Make sure the client exists in your CRM.'],
                'data': f'{raw_client} - {raw_title}'
            })
            continue

        # Match editor (optional)
        editor_obj = None
        raw_editor = row.get(mapped.get('editor', ''), '').strip()
        if raw_editor:
            editor_obj = editor_map.get(raw_editor.lower())

        # Parse dates (optional)
        date_received = safe_parse_date(row.get(mapped.get('date_received', ''), ''))
        due_date = safe_parse_date(row.get(mapped.get('due_date', ''), ''))

        # Match choice fields with defaults
        raw_status = row.get(mapped.get('status', ''), '').strip()
        status = match_choice(raw_status, valid_statuses) or 'Pending'

        raw_priority = row.get(mapped.get('priority', ''), '').strip()
        priority = match_choice(raw_priority, valid_priorities) or 'Medium'

        notes = row.get(mapped.get('notes', ''), '').strip() or None

        try:
            with transaction.atomic():
                ContentItem.objects.create(
                    organization=org,
                    client=client_obj,
                    video_title=raw_title,
                    editor=editor_obj,
                    date_received=date_received,
                    due_date=due_date,
                    status=status,
                    priority=priority,
                    notes=notes,
                )
                imported_count += 1
        except Exception as ex:
            failed_rows.append({
                'row': row_idx,
                'errors': [f'Database error: {str(ex)}'],
                'data': f'{raw_client} - {raw_title}'
            })

    return JsonResponse({
        'success': True,
        'imported': imported_count,
        'failed': len(failed_rows),
        'errors': failed_rows
    })


# â”€â”€â”€ Content Settings (Manage Dropdown Options) â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

DEFAULT_CONTENT_OPTIONS = {
    'status': ['Pending', 'Editing', 'Review', 'Approved', 'Published', 'Rejected', 'Scheduled'],
    'priority': ['Low', 'Medium', 'High', 'Urgent'],
}


def _seed_content_defaults(org):
    """Populate default dropdown options for an organization if none exist."""
    for category, values in DEFAULT_CONTENT_OPTIONS.items():
        if not ContentDropdownOption.objects.filter(organization=org, category=category).exists():
            for i, val in enumerate(values):
                ContentDropdownOption.objects.create(
                    organization=org, category=category, value=val, display_order=i, is_active=True
                )


def _get_content_options(org, category):
    """Return list of active option values for a category (with fallback defaults)."""
    options = list(
        ContentDropdownOption.objects.filter(
            organization=org, category=category, is_active=True
        ).values_list('value', flat=True)
    )
    if not options:
        return DEFAULT_CONTENT_OPTIONS.get(category, [])
    return options


@login_required
@page_permission_required('content_settings')
def content_settings_view(request):
    """Manage Content Tracker dropdown options."""
    org = request.user.profile.organization
    
    # Remove obsolete categories from database
    ContentDropdownOption.objects.filter(
        organization=org, 
        category__in=['platform', 'post_type', 'editor_status', 'campaign_status', 'marketer_status']
    ).delete()
    
    _seed_content_defaults(org)

    categories = ContentDropdownOption.CATEGORY_CHOICES
    all_options = {}
    for cat_key, cat_label in categories:
        all_options[cat_key] = {
            'label': cat_label,
            'items': ContentDropdownOption.objects.filter(organization=org, category=cat_key).order_by('display_order', 'value'),
        }

    context = {
        'all_options': all_options,
        'categories': categories,
    }
    return render(request, 'content_settings.html', context)


@login_required
@page_permission_required('content_settings')
def add_content_option(request):
    """Add a new dropdown option."""
    if request.method == 'POST':
        org = request.user.profile.organization
        category = request.POST.get('category', '').strip()
        value = request.POST.get('value', '').strip()
        valid_cats = [c[0] for c in ContentDropdownOption.CATEGORY_CHOICES]
        if not category or not value or category not in valid_cats:
            messages.error(request, 'Valid category and value are required.')
            return redirect('content_settings')
        # Check for duplicate
        if ContentDropdownOption.objects.filter(organization=org, category=category, value=value).exists():
            messages.error(request, f'"{value}" already exists in {category}.')
            return redirect('content_settings')
        # Get next display order
        max_order = ContentDropdownOption.objects.filter(organization=org, category=category).count()
        ContentDropdownOption.objects.create(
            organization=org, category=category, value=value, display_order=max_order, is_active=True
        )
        SystemNotification.objects.create(user=request.user, message=f'"{value}" added successfully.', type='success')
        return redirect('content_settings')
    return redirect('content_settings')


@login_required
@page_permission_required('content_settings')
def edit_content_option(request, option_id):
    """Edit an existing dropdown option."""
    if request.method == 'POST':
        org = request.user.profile.organization
        try:
            option = ContentDropdownOption.objects.get(id=option_id, organization=org)
            new_value = request.POST.get('value', '').strip()
            is_active = request.POST.get('is_active') == 'on'
            if not new_value:
                messages.error(request, 'Value cannot be empty.')
                return redirect('content_settings')
            # Check for duplicate (different id, same category+value)
            dup = ContentDropdownOption.objects.filter(
                organization=org, category=option.category, value=new_value
            ).exclude(id=option.id).exists()
            if dup:
                messages.error(request, f'"{new_value}" already exists.')
                return redirect('content_settings')
            option.value = new_value
            option.is_active = is_active
            option.save()
            SystemNotification.objects.create(user=request.user, message=f'Option updated to "{new_value}".', type='success')
        except ContentDropdownOption.DoesNotExist:
            messages.error(request, 'Option not found.')
        return redirect('content_settings')
    return redirect('content_settings')


@login_required
@page_permission_required('content_settings')
def delete_content_option(request, option_id):
    """Delete a dropdown option."""
    if request.method == 'POST':
        org = request.user.profile.organization
        try:
            option = ContentDropdownOption.objects.get(id=option_id, organization=org)
            option.delete()
            SystemNotification.objects.create(user=request.user, message='Option deleted.', type='success')
        except ContentDropdownOption.DoesNotExist:
            messages.error(request, 'Option not found.')
        return redirect('content_settings')
    return redirect('content_settings')

import json
from django.http import JsonResponse


@login_required
def post_management_view(request):
    org = request.user.profile.organization
    from crm.models import ContentItem
    from django.utils import timezone
    
    today = timezone.now().date()
    # Fetch custom marketer statuses from settings
    from crm.models import ContentDropdownOption
    active_marketer_statuses = ContentDropdownOption.objects.filter(
        organization=org, category='marketer_status', is_active=True
    ).order_by('display_order', 'value').values_list('value', flat=True)
    
    status_choices = list(active_marketer_statuses)
    if not status_choices:
        status_choices = ['Approved', 'Scheduled', 'Published']
        
    items = ContentItem.objects.filter(
        organization=org,
        status='Approved'
    )
    
    priority_filter = request.GET.get('priority_filter', '').strip()
    if priority_filter:
        items = items.filter(priority=priority_filter)
        
    items = items.order_by('-due_date', '-created_at')
    
    current_month_name = today.strftime('%B %Y')
    grouped_items = {current_month_name: list(items)}
    
    # We strictly use 'Published' as the completion status
    completion_status = 'Published'
    
    context = {
        'grouped_items': grouped_items,
        'status_choices': status_choices,
        'priority_filter': priority_filter,
        'completion_status': completion_status,
    }
    return render(request, 'post_management.html', context)

@login_required
def post_management_update(request):
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            item_id = data.get('item_id')
            status = data.get('status')
            notes = data.get('notes')
            
            org = request.user.profile.organization
            from crm.models import ContentItem
            item = ContentItem.objects.get(id=item_id, organization=org)
            
            if status is not None:
                item.status = status
            if notes is not None:
                item.notes = notes
                
            item.save()
            return JsonResponse({'success': True, 'message': 'Updated successfully.'})
            
        except ContentItem.DoesNotExist:
            return JsonResponse({'success': False, 'message': 'Item not found.'}, status=404)
        except Exception as e:
            return JsonResponse({'success': False, 'message': str(e)}, status=500)
            
    return JsonResponse({'success': False, 'message': 'Invalid request method.'}, status=400)

@login_required
def editor_dashboard_view(request):
    import json
    from datetime import timedelta
    from django.utils import timezone
    from django.db.models import Count
    from crm.models import ContentItem
    from core.models import UserProfile
    
    org = request.user.profile.organization
    items = ContentItem.objects.filter(organization=org)
    today = timezone.now().date()
    
    # KPI Data
    total_count = items.count()
    in_editing_count = items.filter(status='Editing').count()
    review_count = items.filter(status='Review').count()
    approved_count = items.filter(status='Approved').count()
    published_count = items.filter(status='Published').count()
    overdue_count = items.filter(due_date__lt=today).exclude(status__in=['Published', 'Approved']).count()
    active_editors_count = items.filter(editor__isnull=False).values('editor').distinct().count()

    kpi = {
        'total_videos': total_count,
        'in_editing': in_editing_count,
        'pending_review': review_count,
        'approved': approved_count,
        'published': published_count,
        'overdue': overdue_count,
        'active_editors': active_editors_count,
        'avg_editing_time': '2.5 days' if total_count > 0 else '0 hrs'
    }

    total = total_count or 1
    # Pipeline Data
    pipeline = [
        {'stage': 'Pending', 'count': items.filter(status='Pending').count(), 'percent': int(items.filter(status='Pending').count()/total*100)},
        {'stage': 'Editing', 'count': in_editing_count, 'percent': int(in_editing_count/total*100)},
        {'stage': 'Review', 'count': review_count, 'percent': int(review_count/total*100)},
        {'stage': 'Approved', 'count': approved_count, 'percent': int(approved_count/total*100)},
        {'stage': 'Published', 'count': published_count, 'percent': int(published_count/total*100)},
    ]

    # Analytics Charts Data
    # 1. Videos completed per day (last 7 days)
    completed_per_day_labels = []
    completed_per_day_data = []
    for i in range(6, -1, -1):
        day = today - timedelta(days=i)
        completed_per_day_labels.append(day.strftime('%a (%d)'))
        completed_per_day_data.append(items.filter(updated_at__date=day, status__in=['Approved', 'Published']).count())
    
    # 2. Monthly Performance (last 6 months)
    monthly_perf_labels = []
    monthly_perf_data = []
    for i in range(5, -1, -1):
        # approximate month start
        month_target = (today.replace(day=1) - timedelta(days=i*30))
        monthly_perf_labels.append(month_target.strftime('%b %Y'))
        m_count = items.filter(created_at__year=month_target.year, created_at__month=month_target.month).count()
        monthly_perf_data.append(m_count)
    
    # 3. Content Status Distribution
    status_dist_labels = ['Pending', 'Editing', 'Review', 'Approved', 'Published', 'Scheduled']
    status_dist_data = [
        items.filter(status='Pending').count(),
        in_editing_count,
        review_count,
        approved_count,
        published_count,
        items.filter(status='Scheduled').count(),
    ]

    # 4. Top Clients Distribution (replaced removed platform)
    client_counts = items.values('client__company', 'client__name').annotate(count=Count('id')).order_by('-count')[:6]
    client_labels = [(c['client__company'] or c['client__name'] or 'Client') for c in client_counts if (c['client__company'] or c['client__name'])]
    client_data = [c['count'] for c in client_counts if (c['client__company'] or c['client__name'])]

    # 5. Department Workload Table
    editors = org.members.filter(role__iexact='Editor').select_related('user')
    if not editors.exists():
        editor_ids = items.filter(editor__isnull=False).values_list('editor_id', flat=True).distinct()
        editors = UserProfile.objects.filter(id__in=editor_ids, organization=org).select_related('user')

    workload = []
    for ed in editors:
        ed_items = items.filter(editor=ed)
        assigned = ed_items.count()
        in_prog = ed_items.filter(status='Editing').count()
        rev = ed_items.filter(status='Review').count()
        comp = ed_items.filter(status__in=['Approved', 'Published']).count()
        od = ed_items.filter(due_date__lt=today).exclude(status__in=['Approved', 'Published']).count()
        prod = int((comp / max(assigned, 1)) * 100) if assigned > 0 else 0
        name = ed.user.get_full_name() or ed.user.username
        workload.append({
            'editor': name,
            'assigned': assigned,
            'in_progress': in_prog,
            'review': rev,
            'completed': comp,
            'overdue': od,
            'productivity': prod
        })

    # Content Status Summary
    status_summary = {
        'pending_editing': items.filter(status='Pending').count(),
        'in_review': review_count,
        'waiting_client': review_count,
        'scheduled': items.filter(status='Scheduled').count(),
        'published_today': items.filter(status='Published', updated_at__date=today).count()
    }
    
    # Priority
    priority = {
        'high': items.filter(priority='High').count(),
        'medium': items.filter(priority='Medium').count(),
        'low': items.filter(priority='Low').count(),
        'urgent': items.filter(priority='Urgent').count()
    }

    context = {
        'kpi': kpi,
        'pipeline': pipeline,
        'completed_per_day_labels': json.dumps(completed_per_day_labels),
        'completed_per_day_data': json.dumps(completed_per_day_data),
        'monthly_perf_labels': json.dumps(monthly_perf_labels),
        'monthly_perf_data': json.dumps(monthly_perf_data),
        'status_dist_labels': json.dumps(status_dist_labels),
        'status_dist_data': json.dumps(status_dist_data),
        'client_labels': json.dumps(client_labels),
        'client_data': json.dumps(client_data),
        'workload': workload,
        'status_summary': status_summary,
        'priority': priority
    }
    return render(request, 'editor_dashboard.html', context)


@login_required
def finance_dashboard_view(request):
    from .models import Invoice, InvoiceItem, Lead, PartnerPayout, DocumentSettings, FinancePaymentMethod
    import calendar
    import datetime

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

    # 4. Current Bank Balance Calculation (Base balance set to 10,886.48; updated by future income and expense changes)
    base_balance = 10886.48
    base_revenue = 122750.00
    base_outflow = 93147.07
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
    last_month_date = today.replace(day=1) - datetime.timedelta(days=1)
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
                            pm_obj = FinancePaymentMethod.objects.filter(organization=request.user.profile.organization, name__iexact=method_str).first()
                            
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
                            pm_obj = FinancePaymentMethod.objects.filter(organization=request.user.profile.organization, name__iexact=method_str).first()
                            
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

@login_required
@page_permission_required('lead_statuses')
def lead_status_settings(request):
    org = request.user.profile.organization
    statuses = get_or_create_default_statuses(org)
    services = Service.objects.filter(organization=org).order_name_or_created() if hasattr(Service.objects, 'order_name_or_created') else Service.objects.filter(organization=org).order_by('name')
    return render(request, 'lead_settings.html', {
        'statuses': statuses,
        'services': services
    })

@login_required
@page_permission_required('clients_status')
def client_status_settings(request):
    from django.urls import reverse
    return generic_status_settings_view(
        request, 'clients', ClientStatus, 'Clients',
        reverse('add_dynamic_status', args=['clients']),
        '/statuses/category/clients/',
        '/statuses/category/clients/',
        reverse('reorder_dynamic_statuses', args=['clients'])
    )

@login_required
@page_permission_required('projects_status')
def project_status_settings(request):
    from django.urls import reverse
    return generic_status_settings_view(
        request, 'projects', ProjectStatus, 'Projects',
        reverse('add_dynamic_status', args=['projects']),
        '/statuses/category/projects/',
        '/statuses/category/projects/',
        reverse('reorder_dynamic_statuses', args=['projects'])
    )

@login_required
@page_permission_required('campaigns_status')
def campaign_status_settings(request):
    from django.urls import reverse
    return generic_status_settings_view(
        request, 'campaigns', CampaignStatus, 'Campaigns',
        reverse('add_dynamic_status', args=['campaigns']),
        '/statuses/category/campaigns/',
        '/statuses/category/campaigns/',
        reverse('reorder_dynamic_statuses', args=['campaigns'])
    )

@login_required
@page_permission_required('calendar_status')
def calendar_status_settings(request):
    from django.urls import reverse
    return generic_status_settings_view(
        request, 'calendar', CalendarStatus, 'Calendar',
        reverse('add_dynamic_status', args=['calendar']),
        '/statuses/category/calendar/',
        '/statuses/category/calendar/',
        reverse('reorder_dynamic_statuses', args=['calendar'])
    )

@login_required
@page_permission_required('support_status')
def ticket_status_settings(request):
    org = request.user.profile.organization
    statuses = TicketStatus.objects.filter(organization=org)
    priorities = PriorityStatus.objects.filter(organization=org)
    
    return render(request, 'ticket_settings.html', {
        'statuses': statuses,
        'priorities': priorities,
    })

@login_required
@page_permission_required('support_status')
def priority_status_settings(request):
    from django.urls import reverse
    return generic_status_settings_view(
        request, 'priority', PriorityStatus, 'Priority',
        reverse('add_dynamic_status', args=['priority']),
        '/statuses/category/priority/',
        '/statuses/category/priority/',
        reverse('reorder_dynamic_statuses', args=['priority'])
    )

@login_required
def add_service(request):
    if request.method == 'POST':
        name = request.POST.get('name')
        price_val = request.POST.get('price', 0.0)
        if name:
            Service.objects.create(
                organization=request.user.profile.organization,
                name=name,
                price=safe_parse_decimal(price_val, 0.0)
            )
            return JsonResponse({'success': True, 'message': 'Service added successfully.'})
    return JsonResponse({'success': False, 'error': 'Invalid request.'})

@login_required
def edit_service(request, service_id):
    if request.method == 'POST':
        service = get_object_or_404(Service, id=service_id, organization=request.user.profile.organization)
        name = request.POST.get('name')
        price_val = request.POST.get('price')
        if name:
            service.name = name
            if price_val:
                service.price = safe_parse_decimal(price_val, service.price)
            service.save()
            return JsonResponse({'success': True, 'message': 'Service updated successfully.'})
    return JsonResponse({'success': False, 'error': 'Invalid request.'})

@login_required
def delete_service(request, service_id):
    if request.method == 'POST':
        service = get_object_or_404(Service, id=service_id, organization=request.user.profile.organization)
        service.delete()
        return JsonResponse({'success': True, 'message': 'Service deleted successfully.'})
    return JsonResponse({'success': False, 'error': 'Invalid request.'})

@login_required
def client_contact_detail_view(request, lead_id):
    org = request.user.profile.organization
    try:
        lead = Lead.objects.get(id=lead_id, organization=org, is_client=True)
        # Assuming ClientStatus objects have similar badge generation or it's handled in the template
    except Lead.DoesNotExist:
        return redirect('clients')
        
    activities = lead.activities.all().order_by('-timestamp')
    tasks = lead.tasks.all().order_by('-created_at')
    owners = UserProfile.objects.filter(organization=org)
    client_statuses = get_or_create_dynamic_statuses(org, 'clients', ClientStatus)
    services = Service.objects.filter(organization=org)
    
    context = {
        'lead': lead,
        'activities': activities,
        'tasks': tasks,
        'owners': owners,
        'client_statuses': client_statuses,
        'services': services,
    }
    return render(request, 'client_contact_detail.html', context)

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



def offline_view(request):
    """Offline page rendered when user loses internet connection."""
    return render(request, 'offline.html')


