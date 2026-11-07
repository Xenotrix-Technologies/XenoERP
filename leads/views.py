import csv
import io
from decimal import Decimal
from django.shortcuts import render, redirect, get_object_or_404
from django.http import HttpResponse, JsonResponse
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.utils import timezone
from django.db.models import Sum, Q
from django.core.paginator import Paginator
from django.db import transaction

from .models import Lead, LeadStatus
from .utils import (
    get_or_create_default_statuses, annotate_lead_badges,
    map_headers, is_valid_email, safe_parse_decimal, safe_parse_int, safe_parse_datetime
)
from core.models import UserProfile, SystemNotification
from core.permissions import page_permission_required

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
                try:
                    from activities.models import Activity
                    for lead in target_leads:
                        Activity.objects.create(
                            lead=lead,
                            type='Stage Update',
                            description="Bulk changed status to Qualified."
                        )
                except Exception:
                    pass
                SystemNotification.objects.create(user=request.user, message=f"Successfully updated {count} leads to Qualified.", type='success')
        return redirect('leads')

    leads_qs = Lead.objects.filter(organization=org, is_client=False)

    user_pref_key = f'leads_filter_pref_user_{request.user.id}'
    if user_pref_key in request.session:
        del request.session[user_pref_key]

    q = request.GET.get('q', '').strip()
    status_filter = request.GET.get('status', '').strip()
    owner_filter = request.GET.get('owner', '').strip()
    sort_by = request.GET.get('sort', '').strip()

    if q:
        leads_qs = leads_qs.filter(Q(name__icontains=q) | Q(company__icontains=q))

    if status_filter:
        leads_qs = leads_qs.filter(status=status_filter)

    if owner_filter:
        leads_qs = leads_qs.filter(owner_id=owner_filter)

    if sort_by == 'value_desc':
        leads_qs = leads_qs.order_by('-value')
    elif sort_by == 'value_asc':
        leads_qs = leads_qs.order_by('value')
    else:
        leads_qs = leads_qs.order_by('-created_at', '-id')

    owners = UserProfile.objects.filter(organization=org)

    paginator = Paginator(leads_qs, 25)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

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
@page_permission_required('pipeline')
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

            try:
                from activities.models import Activity
                Activity.objects.create(
                    lead=lead,
                    type='Stage Update',
                    description=f"Moved stage from {old_stage} to {stage}."
                )
            except Exception:
                pass
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

    activities = lead.activities.all().order_by('-timestamp') if hasattr(lead, 'activities') else []
    tasks = lead.tasks.all().order_by('-created_at') if hasattr(lead, 'tasks') else []
    owners = UserProfile.objects.filter(organization=org)
    statuses = get_or_create_default_statuses(org)
    
    services = []
    try:
        from services.models import Service
        services = Service.objects.filter(organization=org)
    except Exception:
        pass

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
            try:
                from activities.models import Activity
                Activity.objects.create(
                    lead=lead,
                    type='Creation',
                    description="Lead added via quick create."
                )
            except Exception:
                pass

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
def add_lead(request):
    org = request.user.profile.organization
    owners = UserProfile.objects.filter(organization=org)
    statuses = get_or_create_default_statuses(org)
    services = []
    try:
        from services.models import Service
        services = Service.objects.filter(organization=org)
    except Exception:
        pass

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
        if status in ['Qualified', 'Active'] and service_id:
            try:
                from services.models import Service
                service = Service.objects.get(id=service_id, organization=org)
            except Exception:
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

            try:
                from activities.models import Activity
                Activity.objects.create(
                    lead=lead,
                    type='Creation',
                    description="Lead added."
                )
            except Exception:
                pass

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
    services = []
    try:
        from services.models import Service
        services = Service.objects.filter(organization=org)
    except Exception:
        pass

    if request.method == 'POST':
        try:
            if request.POST.get('name'):
                lead.name = request.POST.get('name')
            if request.POST.get('company'):
                lead.company = request.POST.get('company')
            if 'email' in request.POST:
                lead.email = request.POST.get('email')
            if request.POST.get('phone_number'):
                lead.phone_number = request.POST.get('phone_number')
            elif not lead.phone_number:
                lead.phone_number = ''
            if 'alt_phone_number' in request.POST:
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
                try:
                    from projects.models import ClientStatus
                    status_obj = ClientStatus.objects.filter(organization=org).first()
                    lead.status = status_obj.name if status_obj else 'Active'
                except Exception:
                    pass

            lead.save()

            service_ids = request.POST.getlist('services')
            single_service = request.POST.get('service')
            if single_service and not service_ids:
                service_ids = [single_service]

            if lead.status in ['Qualified', 'Active'] and service_ids:
                try:
                    from services.models import Service
                    matched_services = Service.objects.filter(id__in=service_ids, organization=org)
                    lead.services.set(matched_services)
                except Exception:
                    pass
            else:
                lead.services.clear()

            try:
                from activities.models import Activity
                Activity.objects.create(
                    lead=lead,
                    type='Stage Update',
                    description="Lead details updated."
                )
            except Exception:
                pass

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
            from django.core.mail import send_mail
            from django.conf import settings

            from_email = getattr(settings, 'DEFAULT_FROM_EMAIL', 'noreply@xenocrm.com')
            send_mail(subject, message, from_email, [to_email], fail_silently=True)

            try:
                from activities.models import Activity
                Activity.objects.create(
                    lead=lead,
                    type='Email',
                    description=f"Sent email: {subject}\n\n{message}"
                )
            except Exception:
                pass

            return JsonResponse({'success': True})
        except Exception as e:
            return JsonResponse({'success': False, 'error': str(e)})

    return JsonResponse({'success': False, 'error': 'Invalid request method.'})

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

@login_required
def search_leads_json_view(request):
    org = request.user.profile.organization
    query = request.GET.get('q', '').strip().lower()

    leads_qs = Lead.objects.filter(organization=org)
    if query:
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
@page_permission_required('lead_statuses')
def lead_statuses_view(request):
    """List all statuses across modules for the current organisation."""
    org = request.user.profile.organization
    statuses = get_or_create_default_statuses(org)

    client_statuses = []
    project_statuses = []
    campaign_statuses = []
    calendar_statuses = []
    ticket_statuses = []
    priority_statuses = []

    try:
        from projects.models import ClientStatus, ProjectStatus
        client_statuses = ClientStatus.objects.filter(organization=org)
        project_statuses = ProjectStatus.objects.filter(organization=org)
    except Exception:
        pass

    try:
        from campaigns.models import CampaignStatus
        campaign_statuses = CampaignStatus.objects.filter(organization=org)
    except Exception:
        pass

    try:
        from activities.models import CalendarStatus
        calendar_statuses = CalendarStatus.objects.filter(organization=org)
    except Exception:
        pass

    try:
        from support.models import TicketStatus, PriorityStatus
        ticket_statuses = TicketStatus.objects.filter(organization=org)
        priority_statuses = PriorityStatus.objects.filter(organization=org)
    except Exception:
        pass

    return render(request, 'lead_statuses_new.html', {
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
def lead_status_settings(request):
    org = request.user.profile.organization
    statuses = get_or_create_default_statuses(org)
    return render(request, 'lead_settings.html', {'statuses': statuses})

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

        if LeadStatus.objects.filter(organization=org, name=new_name).exclude(id=status_id).exists():
            return JsonResponse({'success': False, 'error': f"Status '{new_name}' already exists."})

        old_name = status_obj.name
        status_obj.name = new_name
        status_obj.color = new_color
        status_obj.save()

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

        if LeadStatus.objects.filter(organization=org).count() <= 1:
            return JsonResponse({'success': False, 'error': 'Cannot delete the last remaining status.'})

        fallback = LeadStatus.objects.filter(organization=org, is_default=True).exclude(id=status_id).first()
        if not fallback:
            fallback = LeadStatus.objects.filter(organization=org).exclude(id=status_id).first()

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

def download_lead_template(request):
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename="lead_import_template.csv"'
    writer = csv.writer(response)
    writer.writerow(['Name', 'Phone Number', 'Company', 'Email', 'Alt Phone Number', 'Score', 'Annual Revenue', 'Location'])
    return response

@login_required
def import_leads(request):
    if request.method != 'POST':
        messages.error(request, 'Invalid request method. Please use the Import button on the Leads page.')
        return redirect('leads')

    csv_file = request.FILES.get('file')
    if not csv_file:
        return JsonResponse({'success': False, 'error': 'No file uploaded.'})

    if not csv_file.name.endswith('.csv'):
        return JsonResponse({'success': False, 'error': 'Uploaded file is not a CSV.'})

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
                try:
                    from activities.models import Activity
                    Activity.objects.create(
                        lead=lead,
                        type='Creation',
                        description="Lead imported via CSV."
                    )
                except Exception:
                    pass
                imported_count += 1
        except Exception as ex:
            failed_rows.append({'row': row_idx, 'errors': [f'Database error: {str(ex)}'], 'data': f'{name} ({email})'})

    return JsonResponse({
        'success': True,
        'imported': imported_count,
        'failed': len(failed_rows),
        'errors': failed_rows
    })
