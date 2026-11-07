import csv
import io
import json
from datetime import date, timedelta, datetime
from django.db import transaction
from django.db.models import Q, Count
from django.core.paginator import Paginator
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.contrib import messages
from django.utils import timezone

from core.permissions import page_permission_required
from core.models import UserProfile, SystemNotification
from leads.models import Lead
from .models import ContentItem, ContentDropdownOption


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
        formats = [
            '%Y-%m-%d', '%m/%d/%Y', '%d/%m/%Y',
            '%Y-%m-%d %H:%M:%S', '%m/%d/%Y %H:%M:%S', '%d/%m/%Y %H:%M:%S',
            '%Y-%m-%d %H:%M', '%m/%d/%Y %H:%M', '%d/%m/%Y %H:%M',
            '%d-%m-%Y', '%m-%d-%Y',
        ]
        for fmt in formats:
            try:
                return datetime.strptime(val, fmt).date()
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

        client_obj = client_map.get(raw_client.lower())
        if not client_obj:
            failed_rows.append({
                'row': row_idx,
                'errors': [f'Client not found: "{raw_client}". Make sure the client exists in your CRM.'],
                'data': f'{raw_client} - {raw_title}'
            })
            continue

        editor_obj = None
        raw_editor = row.get(mapped.get('editor', ''), '').strip()
        if raw_editor:
            editor_obj = editor_map.get(raw_editor.lower())

        date_received = safe_parse_date(row.get(mapped.get('date_received', ''), ''))
        due_date = safe_parse_date(row.get(mapped.get('due_date', ''), ''))

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
        if ContentDropdownOption.objects.filter(organization=org, category=category, value=value).exists():
            messages.error(request, f'"{value}" already exists in {category}.')
            return redirect('content_settings')
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


@login_required
def post_management_view(request):
    org = request.user.profile.organization
    today = timezone.now().date()
    
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
    pipeline = [
        {'stage': 'Pending', 'count': items.filter(status='Pending').count(), 'percent': int(items.filter(status='Pending').count()/total*100)},
        {'stage': 'Editing', 'count': in_editing_count, 'percent': int(in_editing_count/total*100)},
        {'stage': 'Review', 'count': review_count, 'percent': int(review_count/total*100)},
        {'stage': 'Approved', 'count': approved_count, 'percent': int(approved_count/total*100)},
        {'stage': 'Published', 'count': published_count, 'percent': int(published_count/total*100)},
    ]

    # Analytics Charts Data
    completed_per_day_labels = []
    completed_per_day_data = []
    for i in range(6, -1, -1):
        day = today - timedelta(days=i)
        completed_per_day_labels.append(day.strftime('%a (%d)'))
        completed_per_day_data.append(items.filter(updated_at__date=day, status__in=['Approved', 'Published']).count())
    
    monthly_perf_labels = []
    monthly_perf_data = []
    for i in range(5, -1, -1):
        month_target = (today.replace(day=1) - timedelta(days=i*30))
        monthly_perf_labels.append(month_target.strftime('%b %Y'))
        m_count = items.filter(created_at__year=month_target.year, created_at__month=month_target.month).count()
        monthly_perf_data.append(m_count)
    
    status_dist_labels = ['Pending', 'Editing', 'Review', 'Approved', 'Published', 'Scheduled']
    status_dist_data = [
        items.filter(status='Pending').count(),
        in_editing_count,
        review_count,
        approved_count,
        published_count,
        items.filter(status='Scheduled').count(),
    ]

    client_counts = items.values('client__company', 'client__name').annotate(count=Count('id')).order_by('-count')[:6]
    client_labels = [(c['client__company'] or c['client__name'] or 'Client') for c in client_counts if (c['client__company'] or c['client__name'])]
    client_data = [c['count'] for c in client_counts if (c['client__company'] or c['client__name'])]

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

    status_summary = {
        'pending_editing': items.filter(status='Pending').count(),
        'in_review': review_count,
        'waiting_client': review_count,
        'scheduled': items.filter(status='Scheduled').count(),
        'published_today': items.filter(status='Published', updated_at__date=today).count()
    }
    
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
