from django.shortcuts import render, redirect, get_object_or_404
from django.http import JsonResponse
from django.contrib.auth.decorators import login_required
from .models import Ticket, TicketStatus, PriorityStatus
from core.models import UserProfile, SystemNotification
from core.permissions import page_permission_required

@login_required
@page_permission_required('support')
def customer_support_view(request):
    org = request.user.profile.organization
    tickets = Ticket.objects.filter(organization=org)
    staff = UserProfile.objects.filter(organization=org)
    projects = []
    try:
        from activities.models import Task
        projects = Task.objects.filter(lead__organization=org)
    except Exception:
        pass

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
                from activities.models import Task
                project = Task.objects.get(id=int(project_id), lead__organization=org)
            except Exception:
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
                from activities.models import Task
                project = Task.objects.get(id=int(project_id), lead__organization=org)
                ticket.project = project
            except Exception:
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
@page_permission_required('ticket_statuses')
def ticket_status_settings(request):
    org = request.user.profile.organization
    statuses = TicketStatus.objects.filter(organization=org)
    return render(request, 'generic_status_settings.html', {
        'category': 'tickets',
        'title': 'Ticket Statuses',
        'statuses': statuses
    })

@login_required
@page_permission_required('ticket_statuses')
def priority_status_settings(request):
    org = request.user.profile.organization
    statuses = PriorityStatus.objects.filter(organization=org)
    return render(request, 'generic_status_settings.html', {
        'category': 'priority',
        'title': 'Priority Levels',
        'statuses': statuses
    })
