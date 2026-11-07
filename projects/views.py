import csv
import io
import json
from datetime import timedelta, datetime
from urllib.parse import unquote
from django.shortcuts import render, redirect, get_object_or_404
from django.http import JsonResponse, HttpResponse
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.db.models import Q

from .models import (
    ClientStatus, ProjectStatus, Agreement, AgreementVersion,
    AgreementService, ClientResponsibility, Deliverable
)
from core.models import UserProfile, SystemNotification
from core.permissions import page_permission_required
from leads.models import Lead
from services.models import Service
from activities.models import Task, TaskFile, Activity, Event

# ── Clients Views ────────────────────────────────────────────────────────────

@login_required
@page_permission_required('clients')
def clients_view(request):
    org = request.user.profile.organization
    services_qs = Service.objects.filter(organization=org)
    leads = Lead.objects.filter(organization=org, is_client=True).order_by('-created_at')

    clients_list = []
    total_mrr = 0.0
    total_contract_value = 0.0
    active_count = 0
    onboarding_count = 0
    paused_count = 0
    completed_count = 0

    for lead in leads:
        company_name = lead.company or lead.name
        total_val = float(lead.value or 0.0)
        paid_val = float(lead.paid_amount or 0.0)
        total_contract_value += total_val

        agreement = Agreement.objects.filter(
            Q(lead=lead) | (Q(company_name__iexact=company_name) if company_name else Q(id=0)),
            organization=org
        ).first()

        monthly_retainer = float(agreement.monthly_fee) if agreement and agreement.monthly_fee else (
            round(total_val / 12, 2) if total_val > 50000 else total_val
        )
        if monthly_retainer == 0 and total_val > 0:
            monthly_retainer = total_val

        st = (lead.status or '').strip().lower()
        if st in ['completed']:
            status_tab = 'completed'
            completed_count += 1
        elif st in ['active', 'contracted', 'won']:
            status_tab = 'active'
            active_count += 1
            total_mrr += monthly_retainer
        elif st in ['qualified', 'new', 'onboarding', 'proposal']:
            status_tab = 'onboarding'
            onboarding_count += 1
        else:
            status_tab = 'paused'
            paused_count += 1

        if lead.lifecycle_stage in ['Enterprise', 'Growth', 'Pro', 'Starter']:
            tier = lead.lifecycle_stage
        elif total_val >= 100000 or monthly_retainer >= 50000:
            tier = 'Enterprise'
        elif total_val >= 30000 or monthly_retainer >= 15000:
            tier = 'Growth'
        elif total_val >= 15000:
            tier = 'Pro'
        else:
            tier = 'Starter'

        services_list = [s.name for s in lead.services.all()]
        if not services_list:
            if agreement and agreement.service:
                services_list.append(agreement.service.name)
            elif agreement and agreement.agreement_type:
                services_list.append(agreement.agreement_type.replace(' Agreement', ''))
            else:
                services_list.append('Digital Marketing')

        linked_tasks = Task.objects.filter(
            Q(lead=lead) | (Q(title__icontains=company_name) if company_name else Q(id=0))
        ).filter(
            Q(organization=org) | Q(organization__isnull=True)
        ).order_by('-created_at')

        projects_data = []
        active_tasks_count = 0
        total_deliverables = 0
        completed_deliverables = 0

        for t in linked_tasks:
            if not t.completed:
                active_tasks_count += 1
            m_total = t.milestones.count()
            m_done = t.milestones.filter(completed=True).count()
            todos_total = t.todos.count()
            todos_done = t.todos.filter(completed=True).count()

            deliv_count = m_total + todos_total
            deliv_done = m_done + todos_done
            total_deliverables += deliv_count
            completed_deliverables += deliv_done

            projects_data.append({
                'id': t.id,
                'name': t.title,
                'description': t.description or '',
                'progress': t.progress or (int((deliv_done / deliv_count * 100)) if deliv_count > 0 else (100 if t.completed else 0)),
                'target_end_date': t.due_date.strftime('%Y-%m-%d') if t.due_date else '',
                'priority': t.priority,
                'status': t.status.name if t.status else ('Completed' if t.completed else 'In Progress'),
                'deliverables_done': deliv_done,
                'deliverables_total': deliv_count
            })

        overall_progress = int((completed_deliverables / total_deliverables * 100)) if total_deliverables > 0 else (100 if status_tab == 'completed' else (75 if status_tab == 'active' else 25))

        client_events = []
        for e in Event.objects.filter(
            Q(title__icontains=company_name) | Q(description__icontains=company_name) | Q(title__icontains=lead.name),
            organization=org
        ).order_by('start_time')[:6]:
            client_events.append({
                'id': e.id,
                'title': e.title,
                'start_time': e.start_time.strftime('%b %d, %Y • %I:%M %p') if e.start_time else '',
                'color': e.color or '#00BAFF',
                'description': e.description or ''
            })

        clients_list.append({
            'id': lead.id,
            'name': lead.name,
            'company': company_name,
            'email': lead.email or '',
            'phone': lead.phone_number or '',
            'status': lead.status,
            'status_tab': status_tab,
            'tier': tier,
            'monthly_retainer': monthly_retainer,
            'contract_value': total_val,
            'paid_amount': paid_val,
            'services': services_list,
            'agreement_start_date': agreement.start_date.strftime('%b %d, %Y') if agreement and agreement.start_date else (lead.created_at.strftime('%b %d, %Y') if lead.created_at else ''),
            'agreement_end_date': agreement.end_date.strftime('%b %d, %Y') if agreement and agreement.end_date else 'Perpetual Retainer',
            'projects': projects_data,
            'projects_count': len(projects_data),
            'active_tasks_count': active_tasks_count,
            'deliverables_progress': overall_progress,
            'upcoming_events': client_events,
            'notes': lead.notes or ''
        })

    all_service_names = list(services_qs.values_list('name', flat=True))
    if not all_service_names:
        all_service_names = ['Digital Marketing', 'SEO Retainer', 'Website Development', 'Content Strategy', 'Social Media', 'E-Commerce']

    avg_retainer = round(total_mrr / active_count, 2) if active_count > 0 else 0.0

    context = {
        'clients': clients_list,
        'clients_json': json.dumps(clients_list, default=str),
        'services': all_service_names,
        'metrics': {
            'total_clients': len(clients_list),
            'active_clients': active_count,
            'onboarding_clients': onboarding_count,
            'paused_clients': paused_count,
            'completed_clients': completed_count,
            'total_mrr': total_mrr,
            'total_contract_value': total_contract_value,
            'avg_retainer': avg_retainer
        }
    }
    return render(request, 'clients.html', context)

@login_required
def quick_create_client_ajax(request):
    if request.method == 'POST':
        org = request.user.profile.organization
        name = request.POST.get('name', '').strip()
        company = request.POST.get('company', '').strip() or name
        email = request.POST.get('email', '').strip()
        phone = request.POST.get('phone', '').strip()
        status = request.POST.get('status', 'Active').strip()
        tier = request.POST.get('tier', 'Growth').strip()
        notes = request.POST.get('notes', '').strip()

        try:
            monthly_retainer = float(request.POST.get('monthly_retainer', 0.0))
        except (ValueError, TypeError):
            monthly_retainer = 0.0

        if not name:
            return JsonResponse({'success': False, 'error': 'Client contact name is required.'})

        lead = Lead.objects.create(
            organization=org,
            name=name,
            company=company,
            email=email,
            phone_number=phone,
            status=status,
            stage='Won' if status.lower() in ['active', 'contracted'] else 'New',
            value=monthly_retainer * 12 if monthly_retainer > 0 else 50000.0,
            is_client=True,
            lifecycle_stage=tier if tier in ['Enterprise', 'Growth', 'Pro', 'Starter'] else 'Growth',
            notes=notes
        )

        selected_services = request.POST.getlist('services[]') or request.POST.getlist('services')
        if selected_services:
            for s_name in selected_services:
                service_obj, _ = Service.objects.get_or_create(organization=org, name=s_name.strip())
                lead.services.add(service_obj)

        return JsonResponse({
            'success': True,
            'message': f"Client '{company}' onboarded successfully.",
            'client_id': lead.id
        })

    return JsonResponse({'success': False, 'error': 'Invalid request method.'})

@login_required
def edit_client_ajax(request, client_id):
    if request.method == 'POST':
        org = request.user.profile.organization
        lead = get_object_or_404(Lead, id=client_id, organization=org, is_client=True)

        name = request.POST.get('name', '').strip()
        company = request.POST.get('company', '').strip()
        email = request.POST.get('email', '').strip()
        phone = request.POST.get('phone', '').strip()
        status = request.POST.get('status', '').strip()
        tier = request.POST.get('tier', '').strip()
        notes = request.POST.get('notes', '').strip()

        if name:
            lead.name = name
        if company:
            lead.company = company
        if email:
            lead.email = email
        if phone:
            lead.phone_number = phone
        if status:
            lead.status = status
            if status.lower() in ['active', 'contracted']:
                lead.stage = 'Won'
        if tier in ['Enterprise', 'Growth', 'Pro', 'Starter']:
            lead.lifecycle_stage = tier
        if notes is not None:
            lead.notes = notes

        retainer_val = request.POST.get('monthly_retainer')
        if retainer_val is not None and retainer_val != '':
            try:
                monthly_fee = float(retainer_val)
                lead.value = monthly_fee * 12
                agreements = Agreement.objects.filter(
                    Q(lead=lead) | (Q(company_name__iexact=lead.company) if lead.company else Q(id=0)),
                    organization=org
                )
                for agr in agreements:
                    agr.monthly_fee = monthly_fee
                    agr.total_value = monthly_fee * 12
                    agr.save()
            except (ValueError, TypeError):
                pass

        lead.save()

        selected_services = request.POST.getlist('services[]') or request.POST.getlist('services')
        lead.services.clear()
        if selected_services:
            for s_name in selected_services:
                s_name = s_name.strip()
                if s_name:
                    service_obj, _ = Service.objects.get_or_create(organization=org, name=s_name)
                    lead.services.add(service_obj)

        return JsonResponse({
            'success': True,
            'message': f"Client '{lead.company}' updated successfully."
        })

    return JsonResponse({'success': False, 'error': 'Invalid request method.'})

@login_required
@page_permission_required('clients')
def service_clients_view(request, service_id):
    org = request.user.profile.organization
    leads = Lead.objects.filter(organization=org, is_client=True)

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

    client_statuses = ClientStatus.objects.filter(organization=org)

    context = {
        'service_name': service_name,
        'clients': clients_list,
        'client_statuses': client_statuses,
    }
    return render(request, 'service_clients.html', context)

@login_required
@page_permission_required('clients')
def client_profile_view(request, company_name):
    company_name = unquote(company_name)
    org = request.user.profile.organization
    leads = Lead.objects.filter(organization=org, company=company_name).order_by('-created_at')

    if not leads.exists():
        messages.error(request, "Client not found.")
        return redirect('clients')

    total_value = max((lead.value or 0) for lead in leads) if leads.exists() else 0
    total_paid = max((lead.paid_amount or 0) for lead in leads) if leads.exists() else 0

    agreements = Agreement.objects.filter(
        Q(organization=org) & (Q(company_name=company_name) | Q(client_name=company_name))
    ).order_by('-created_at')

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
    if request.method == 'POST':
        org = request.user.profile.organization
        old_name = request.POST.get('old_company_name', '').strip()
        new_name = request.POST.get('new_company_name', '').strip()

        if not old_name or not new_name:
            return JsonResponse({'success': False, 'error': 'Company names are required.'})

        leads_updated = Lead.objects.filter(organization=org, company=old_name).update(company=new_name)
        return JsonResponse({'success': True, 'message': f"Updated {leads_updated} records to '{new_name}'."})

    return JsonResponse({'success': False, 'error': 'Invalid request method.'})

@login_required
def delete_client_company(request):
    if request.method == 'POST':
        org = request.user.profile.organization
        company_name = request.POST.get('company_name', '').strip()

        if not company_name:
            return JsonResponse({'success': False, 'error': 'Company name is required.'})

        leads_deleted, _ = Lead.objects.filter(organization=org, company=company_name).delete()
        return JsonResponse({'success': True, 'message': f"Deleted company '{company_name}' and all its {leads_deleted} leads."})

    return JsonResponse({'success': False, 'error': 'Invalid request method.'})

@login_required
def client_contact_detail_view(request, lead_id):
    org = request.user.profile.organization
    try:
        lead = Lead.objects.get(id=lead_id, organization=org)
    except Lead.DoesNotExist:
        return redirect('clients')

    activities = lead.activities.all().order_by('-timestamp') if hasattr(lead, 'activities') else []
    tasks = lead.tasks.all().order_by('-created_at') if hasattr(lead, 'tasks') else []
    owners = UserProfile.objects.filter(organization=org)
    statuses = ClientStatus.objects.filter(organization=org)
    services = Service.objects.filter(organization=org)

    context = {
        'lead': lead,
        'activities': activities,
        'tasks': tasks,
        'owners': owners,
        'statuses': statuses,
        'services': services,
    }
    return render(request, 'client_contact_detail.html', context)

@login_required
@page_permission_required('client_statuses')
def client_status_settings(request):
    org = request.user.profile.organization
    statuses = ClientStatus.objects.filter(organization=org)
    return render(request, 'generic_status_settings.html', {
        'category': 'clients',
        'title': 'Client Statuses',
        'statuses': statuses
    })

# ── Projects Views ───────────────────────────────────────────────────────────

@login_required
@page_permission_required('projects')
def projects_view(request):
    org = request.user.profile.organization
    tasks = Task.objects.filter(Q(lead__organization=org) | Q(organization=org)).order_by('due_date')
    staff = UserProfile.objects.filter(organization=org)
    leads = Lead.objects.filter(organization=org)
    clients = Lead.objects.filter(organization=org, is_client=True).order_by('company')
    project_statuses = ProjectStatus.objects.filter(organization=org).order_by('position')

    today = timezone.now().date()
    total_projects = tasks.count()
    completed_projects = tasks.filter(Q(completed=True) | Q(status__name__iexact='Completed')).count()
    overdue_projects = tasks.filter(completed=False, due_date__lt=today).exclude(status__name__iexact='Completed').count()
    in_progress_projects = tasks.filter(Q(completed=False) & ~Q(status__name__iexact='Completed')).count()
    team_members_count = staff.count()

    q = request.GET.get('q', '').strip() or request.GET.get('search', '').strip()
    if q:
        tasks = tasks.filter(
            Q(title__icontains=q) |
            Q(description__icontains=q) |
            Q(lead__name__icontains=q) |
            Q(status__name__icontains=q)
        )

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
        'clients': clients,
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
    in_progress_projects = tasks.filter(Q(completed=False) & ~Q(status__name__iexact='Completed')).count()
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
                try:
                    Activity.objects.create(
                        lead=None,
                        type='Task',
                        description=f"Imported {created_count} project(s) from {import_file.name}"
                    )
                except Exception:
                    pass
            if errors:
                messages.warning(request, f"Skipped {len(errors)} invalid record(s).")
        except Exception as e:
            messages.error(request, f"Error parsing import file: {str(e)}")

        return redirect('projects')
    return redirect('projects')

@login_required
@page_permission_required('project_statuses')
def project_status_settings(request):
    org = request.user.profile.organization
    statuses = ProjectStatus.objects.filter(organization=org)
    return render(request, 'generic_status_settings.html', {
        'category': 'projects',
        'title': 'Project Statuses',
        'statuses': statuses
    })

# ── Agreements Views ─────────────────────────────────────────────────────────

@login_required
@page_permission_required('agreements')
def agreements_list_view(request):
    org = request.user.profile.organization
    agreements = Agreement.objects.filter(organization=org)

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
    clients = Lead.objects.filter(organization=org).order_by('company', 'name')

    lead_id = request.GET.get('lead_id')
    selected_lead = None
    if lead_id:
        try:
            selected_lead = Lead.objects.get(id=int(lead_id), organization=org)
        except (ValueError, Lead.DoesNotExist):
            pass

    if request.method == 'POST':
        try:
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

            client_lead_id = request.POST.get('client_lead_id')
            lead = None
            if client_lead_id:
                try:
                    lead = Lead.objects.get(id=int(client_lead_id), organization=org)
                except (ValueError, Lead.DoesNotExist):
                    pass
            elif selected_lead:
                lead = selected_lead

            agreement = Agreement.objects.create(
                organization=org,
                agreement_number=agreement_number,
                lead=lead,
                date=request.POST.get('date') or timezone.now().date(),
                start_date=request.POST.get('start_date') or timezone.now().date(),
                end_date=request.POST.get('end_date') or (timezone.now().date() + timedelta(days=365)),
                client_name=request.POST.get('client_name', ''),
                company_name=request.POST.get('company_name', ''),
                client_email=request.POST.get('client_email', ''),
                client_phone=request.POST.get('client_phone', ''),
                client_address=request.POST.get('client_address', ''),
                gstin=request.POST.get('gstin', ''),
                service=service,
                agreement_type=request.POST.get('agreement_type', 'Universal Service Agreement'),
                project_name=request.POST.get('project_name', ''),
                monthly_fee=request.POST.get('monthly_fee') or 0.00,
                advance_payment=request.POST.get('advance_payment') or 0.00,
                total_value=request.POST.get('total_value') or 0.00,
                payment_cycle=request.POST.get('payment_cycle', 'Monthly'),
                payment_method=request.POST.get('payment_method', 'Bank Transfer'),
                scope_of_work=request.POST.get('scope_of_work', ''),
                deliverables_text=request.POST.get('deliverables_text', ''),
                payment_terms_text=request.POST.get('payment_terms_text', ''),
                governing_law=request.POST.get('governing_law', 'Laws of Telangana, India'),
                confidentiality_clause=request.POST.get('confidentiality_clause', ''),
                ip_clause=request.POST.get('ip_clause', ''),
                termination_clause=request.POST.get('termination_clause', ''),
                refund_policy=request.POST.get('refund_policy', ''),
                limitation_liability=request.POST.get('limitation_liability', ''),
                dispute_resolution=request.POST.get('dispute_resolution', ''),
                posts_count=request.POST.get('posts_count') or 0,
                campaigns_count=request.POST.get('campaigns_count') or 0,
                revisions=request.POST.get('revisions') or 3,
                notice_period=request.POST.get('notice_period') or 30,
                notes=request.POST.get('notes', ''),
                project_estimation_json=request.POST.get('project_estimation_json', ''),
                status=request.POST.get('status', 'Draft')
            )

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

            deliv_titles = request.POST.getlist('deliverable_title[]')
            for t in deliv_titles:
                title = t.strip()
                if title:
                    Deliverable.objects.create(agreement=agreement, title=title)

            resp_texts = request.POST.getlist('responsibility_text[]')
            for r in resp_texts:
                text = r.strip()
                if text:
                    ClientResponsibility.objects.create(agreement=agreement, responsibility=text)

            SystemNotification.objects.create(user=request.user, message='Agreement created successfully.', type='success')
            return redirect('agreements')
        except Exception as e:
            messages.error(request, f"Error creating agreement: {str(e)}")

    current_lead_id = selected_lead.id if selected_lead else ''
    return render(request, 'agreement_form.html', {
        'action': 'Create',
        'agreement': None,
        'services': services,
        'clients': clients,
        'selected_lead': selected_lead,
        'current_lead_id': current_lead_id
    })

@login_required
@page_permission_required('agreements')
def update_agreement_view(request, agreement_id):
    org = request.user.profile.organization
    agreement = get_object_or_404(Agreement, id=agreement_id, organization=org)
    services = Service.objects.filter(organization=org)
    clients = Lead.objects.filter(organization=org).order_by('company', 'name')

    if request.method == 'POST':
        try:
            agreement.date = request.POST.get('date') or timezone.now().date()
            agreement.start_date = request.POST.get('start_date') or timezone.now().date()
            agreement.end_date = request.POST.get('end_date') or (timezone.now().date() + timedelta(days=365))
            agreement.client_name = request.POST.get('client_name', '')
            agreement.company_name = request.POST.get('company_name', '')
            agreement.client_email = request.POST.get('client_email', '')
            agreement.client_phone = request.POST.get('client_phone', '')
            agreement.client_address = request.POST.get('client_address', '')
            agreement.gstin = request.POST.get('gstin', '')

            client_lead_id = request.POST.get('client_lead_id')
            if client_lead_id:
                try:
                    agreement.lead = Lead.objects.get(id=int(client_lead_id), organization=org)
                except (ValueError, Lead.DoesNotExist):
                    pass

            service_id = request.POST.get('service')
            service = None
            if service_id:
                try:
                    service = Service.objects.get(id=int(service_id), organization=org)
                except (ValueError, Service.DoesNotExist):
                    pass
            agreement.service = service
            agreement.agreement_type = request.POST.get('agreement_type', agreement.agreement_type or 'Universal Service Agreement')
            agreement.project_name = request.POST.get('project_name', agreement.project_name)
            agreement.monthly_fee = request.POST.get('monthly_fee') or 0.00
            agreement.advance_payment = request.POST.get('advance_payment') or 0.00
            agreement.total_value = request.POST.get('total_value') or agreement.total_value or 0.00
            agreement.payment_cycle = request.POST.get('payment_cycle', 'Monthly')
            agreement.payment_method = request.POST.get('payment_method', 'Bank Transfer')
            agreement.scope_of_work = request.POST.get('scope_of_work', agreement.scope_of_work)
            agreement.deliverables_text = request.POST.get('deliverables_text', agreement.deliverables_text)
            agreement.payment_terms_text = request.POST.get('payment_terms_text', agreement.payment_terms_text)
            agreement.governing_law = request.POST.get('governing_law', agreement.governing_law or 'Laws of Telangana, India')
            agreement.confidentiality_clause = request.POST.get('confidentiality_clause', agreement.confidentiality_clause)
            agreement.ip_clause = request.POST.get('ip_clause', agreement.ip_clause)
            agreement.termination_clause = request.POST.get('termination_clause', agreement.termination_clause)
            agreement.refund_policy = request.POST.get('refund_policy', agreement.refund_policy)
            agreement.limitation_liability = request.POST.get('limitation_liability', agreement.limitation_liability)
            agreement.dispute_resolution = request.POST.get('dispute_resolution', agreement.dispute_resolution)
            agreement.posts_count = request.POST.get('posts_count') or 0
            agreement.campaigns_count = request.POST.get('campaigns_count') or 0
            agreement.revisions = request.POST.get('revisions') or 3
            agreement.notice_period = request.POST.get('notice_period') or 30
            agreement.notes = request.POST.get('notes', '')
            agreement.project_estimation_json = request.POST.get('project_estimation_json', '')
            agreement.status = request.POST.get('status', 'Draft')
            agreement.save()

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

            agreement.deliverables.all().delete()
            deliv_titles = request.POST.getlist('deliverable_title[]')
            for t in deliv_titles:
                title = t.strip()
                if title:
                    Deliverable.objects.create(agreement=agreement, title=title)

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

    current_lead_id = agreement.lead_id if agreement.lead_id else ''
    return render(request, 'agreement_form.html', {
        'action': 'Update',
        'agreement': agreement,
        'services': services,
        'clients': clients,
        'current_lead_id': current_lead_id
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
    doc_settings = None
    try:
        from finance.models import DocumentSettings
        doc_settings = DocumentSettings.objects.filter(organization=org).first()
    except Exception:
        pass
    return render(request, 'agreement_print.html', {
        'agreement': agreement,
        'organization': org,
        'doc_settings': doc_settings
    })

def public_agreement_view(request, public_token):
    agreement = get_object_or_404(Agreement, public_token=public_token)
    doc_settings = None
    try:
        from finance.models import DocumentSettings
        doc_settings = DocumentSettings.objects.filter(organization=agreement.organization).first()
    except Exception:
        pass

    if agreement.status in ['Draft', 'Sent']:
        agreement.status = 'Viewed'
        agreement.save()

    context = {
        'agreement': agreement,
        'doc_settings': doc_settings,
    }
    return render(request, 'agreements/agreement_public.html', context)

@csrf_exempt
def public_agreement_sign(request, public_token):
    agreement = get_object_or_404(Agreement, public_token=public_token)

    if agreement.status == 'Signed':
        return JsonResponse({'success': False, 'error': 'Agreement is already signed.'}, status=400)

    if request.method == 'POST':
        data = json.loads(request.body) if request.content_type == 'application/json' else request.POST

        signer_name = data.get('signer_name', agreement.client_name)
        signer_email = data.get('signer_email', agreement.client_email)
        sig_type = data.get('signature_type', 'draw')
        sig_data = data.get('signature_data')

        if not sig_data:
            return JsonResponse({'success': False, 'error': 'Signature data is required.'}, status=400)

        x_forwarded = request.META.get('HTTP_X_FORWARDED_FOR')
        client_ip = x_forwarded.split(',')[0].strip() if x_forwarded else request.META.get('REMOTE_ADDR')

        agreement.status = 'Signed'
        agreement.signature_type = sig_type
        agreement.signature_data = sig_data
        agreement.signed_at = timezone.now()
        agreement.signed_by_name = signer_name
        agreement.signed_by_email = signer_email
        agreement.signed_ip = client_ip
        agreement.save()

        try:
            AgreementVersion.objects.create(
                agreement=agreement,
                version_number=1,
                created_by=None,
                snapshot_data={'signed': True, 'signed_at': str(agreement.signed_at)},
                change_summary='Signed via Public Client Portal'
            )
        except Exception:
            pass

        return JsonResponse({
            'success': True,
            'message': 'Agreement successfully signed!',
            'signed_at': agreement.signed_at.strftime('%b %d, %Y %I:%M %p')
        })

    return JsonResponse({'success': False, 'error': 'Invalid request method.'}, status=405)
