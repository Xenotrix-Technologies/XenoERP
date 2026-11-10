import json
import os
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.models import User
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import JsonResponse
from django.utils import timezone
from django.urls import reverse
from django.db import transaction, connection
from django.core.files.storage import default_storage
from django.core.files.base import ContentFile

from .models import Organization, Department, StaffRole, UserProfile, SystemNotification
from .forms import ProfileForm
from .permissions import page_permission_required

DEFAULT_ROLES = ['Sales Executive', 'Manager', 'Administrator', 'Representative']

def get_or_create_default_roles(org):
    """Return the queryset of StaffRole for `org`, seeding defaults if empty."""
    qs = StaffRole.objects.filter(organization=org)
    if not qs.exists():
        for role_name in DEFAULT_ROLES:
            StaffRole.objects.create(organization=org, name=role_name)
        qs = StaffRole.objects.filter(organization=org)
    return qs

def _get_landing_page_for_user(user):
    """Determine the first permitted landing page for an employee based on permissions."""
    if not user or not user.is_authenticated:
        return 'login'
    if user.is_superuser:
        return 'dashboard'
    profile = getattr(user, 'profile', None)
    if profile:
        from .permissions import PERM_REDIRECT_ORDER
        if profile.check_page_permission('dashboard'):
            return 'dashboard'
        for perm, target_name in PERM_REDIRECT_ORDER:
            if profile.check_page_permission(perm):
                return target_name
    return 'dashboard'

def signup_view(request):
    return redirect('login')

def login_view(request):
    if request.user.is_authenticated:
        return redirect(_get_landing_page_for_user(request.user))

    if request.method == 'POST':
        u = request.POST.get('username')
        p = request.POST.get('password')
        user = authenticate(request, username=u, password=p)
        if user is not None:
            login(request, user)

            remember_me = request.POST.get('remember_me')
            if not remember_me:
                request.session.set_expiry(0)

            next_url = request.POST.get('next') or request.GET.get('next')
            if next_url and next_url.startswith('/') and not next_url.startswith('//'):
                return redirect(next_url)
            return redirect(_get_landing_page_for_user(user))
        else:
            messages.error(request, "Invalid username or password.")
            return render(request, 'registration/login.html')

    return render(request, 'registration/login.html')

@login_required
def logout_view(request):
    logout(request)
    return redirect('login')

@login_required
def profile_edit_view(request):
    """Edit user profile fields and avatar."""
    user = request.user
    profile = user.profile
    if request.method == 'POST':
        form = ProfileForm(request.POST, request.FILES, instance=profile)
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

            profile_file = request.FILES.get('profile_image_file')
            if profile_file:
                path = default_storage.save(os.path.join('avatars', f"user_{user.id}_{profile_file.name}"), ContentFile(profile_file.read()))
                profile_obj.profile_image_url = default_storage.url(path)

            profile_obj.save()
            SystemNotification.objects.create(user=request.user, message='Profile updated successfully.', type='success')
            return redirect('profile_edit')
    else:
        form = ProfileForm(instance=profile)
    return render(request, 'profile_edit.html', {'form': form, 'user': user})

@login_required
@page_permission_required('staff')
def staff_list_view(request):
    """List all user profiles in the current organization."""
    org = request.user.profile.organization
    staff_members = UserProfile.objects.filter(organization=org).select_related('user')
    return render(request, 'staff.html', {'staff_members': staff_members})

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
            path = default_storage.save(os.path.join('avatars', f"staff_{username}_{profile_file.name}"), ContentFile(profile_file.read()))
            profile_image_url = default_storage.url(path)
        phone_number = request.POST.get('phone_number', '').strip()
        location = request.POST.get('location', '').strip()
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
                try:
                    SystemNotification.objects.create(user=request.user, message=f"Staff member '{first_name or username}' created successfully.", type='success')
                except Exception:
                    pass
                messages.success(request, f"Staff member '{first_name or username}' created successfully.")
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
            path = default_storage.save(os.path.join('avatars', f"staff_{username}_{profile_file.name}"), ContentFile(profile_file.read()))
            profile_image_url = default_storage.url(path)
        phone_number = request.POST.get('phone_number', '').strip()
        location = request.POST.get('location', '').strip()
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

                dept = None
                if department_id:
                    dept = Department.objects.filter(id=department_id, organization=org).first()
                profile.role = role
                profile.profile_image_url = profile_image_url or None
                profile.phone_number = phone_number or None
                profile.location = location or None
                profile.department = dept
                profile.save()

                try:
                    SystemNotification.objects.create(user=request.user, message=f"Staff member '{first_name or username}' updated successfully.", type='success')
                except Exception:
                    pass
                messages.success(request, f"Staff member '{first_name or username}' updated successfully.")
                return redirect('staff')
            except Exception as e:
                messages.error(request, str(e))

        context = {
            'title': f'Edit Staff Member: {profile.user.username}',
            'profile': profile,
            'action_url': request.path,
            'form_data': form_data,
            'roles': roles,
            'departments': org.departments.all(),
        }
        return render(request, 'staff_form.html', context)

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

            user = profile.user
            with transaction.atomic():
                with connection.cursor() as cursor:
                    try:
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
                    except Exception:
                        pass

                    for table_cleanup in [
                        ("hr_branches", "manager_id"),
                        ("hr_candidate_interviews", "interviewer_id"),
                        ("hr_audit_logs", "actor_id"),
                        ("hr_employee_documents", "verified_by_id"),
                        ("hr_attendance_corrections", "reviewed_by_id"),
                        ("hr_onboarding_tasks", "assigned_to_id"),
                        ("hr_performance_reviews", "reviewer_id"),
                        ("hr_leave_requests", "hr_approval_by_id"),
                        ("hr_leave_requests", "manager_approval_by_id"),
                        ("quotations", "prepared_by_id"),
                        ("content_items", "editor_id"),
                        ("tickets", "assignee_id"),
                        ("leads", "owner_id"),
                    ]:
                        try:
                            cursor.execute(f"UPDATE {table_cleanup[0]} SET {table_cleanup[1]} = NULL WHERE {table_cleanup[1]} = %s", [profile.id])
                        except Exception:
                            pass

                    for delete_table in ["hr_notifications", "quotation_activities", "tasks_assignees"]:
                        try:
                            col = "recipient_id" if delete_table == "hr_notifications" else ("user_id" if delete_table == "quotation_activities" else "userprofile_id")
                            cursor.execute(f"DELETE FROM {delete_table} WHERE {col} = %s", [profile.id])
                        except Exception:
                            pass

                profile.delete()
                if user:
                    user.delete()
            return JsonResponse({'success': True, 'message': 'Staff member deleted successfully.'})
        except UserProfile.DoesNotExist:
            return JsonResponse({'success': False, 'error': 'Staff member not found.'})
        except Exception as e:
            return JsonResponse({'success': False, 'error': f'Failed to delete staff member: {str(e)}'})

    return JsonResponse({'success': False, 'error': 'Invalid request method.'})

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
    """Create a new staff role via AJAX POST."""
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

        if StaffRole.objects.filter(organization=org, name=new_name).exclude(id=role_id).exists():
            return JsonResponse({'success': False, 'error': f"Role '{new_name}' already exists."})

        old_name = role_obj.name
        role_obj.name = new_name
        role_obj.save()

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

        if StaffRole.objects.filter(organization=org).count() <= 1:
            return JsonResponse({'success': False, 'error': 'Cannot delete the last remaining role.'})

        fallback = StaffRole.objects.filter(organization=org).exclude(id=role_id).first()
        UserProfile.objects.filter(organization=org, role=role_obj.name).update(role=fallback.name)

        deleted_name = role_obj.name
        role_obj.delete()

        return JsonResponse({'success': True, 'message': f"Role '{deleted_name}' deleted. Users reassigned to '{fallback.name}'."})

    return JsonResponse({'success': False, 'error': 'Invalid request method.'})

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
    return JsonResponse({'success': False, 'error': 'Invalid request method.'})

@login_required
def settings_dashboard_view(request):
    """Central ERP settings & system control hub view."""
    org = request.user.profile.organization if hasattr(request.user, 'profile') else None
    
    total_staff = UserProfile.objects.filter(organization=org).count() if org else 0
    total_roles = StaffRole.objects.filter(organization=org).count() if org else 0
    total_departments = Department.objects.filter(organization=org).count() if org else 0

    total_services = 0
    total_leads = 0
    total_content_items = 0
    try:
        from services.models import Service
        total_services = Service.objects.filter(organization=org).count() if org else 0
    except Exception:
        pass
    try:
        from leads.models import Lead
        total_leads = Lead.objects.filter(organization=org).count() if org else 0
    except Exception:
        pass
    try:
        from content_tracker.models import ContentItem
        total_content_items = ContentItem.objects.filter(organization=org).count() if org else 0
    except Exception:
        pass

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
    roles = get_or_create_default_roles(org)

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
                return JsonResponse({'success': True, 'message': "Permissions for staff updated successfully."})

            return JsonResponse({'success': False, 'error': 'Missing type or id.'})
        except Exception as e:
            return JsonResponse({'success': False, 'error': str(e)})

    role_permissions_map = {}
    for role in roles:
        try:
            role_permissions_map[role.name] = json.loads(role.permissions_json or '{}')
        except Exception:
            role_permissions_map[role.name] = {}
            
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
def notifications_view(request):
    """Unified notification feed view."""
    org = request.user.profile.organization
    import datetime
    now = timezone.now()
    one_week_later = now + datetime.timedelta(days=7)
    unified_feed = []
    profile = request.user.profile

    # 1. Calendar Events
    try:
        from activities.models import Event
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
    except Exception:
        pass

    # 2. Pending Tasks
    try:
        from activities.models import Task
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
                    'description': f"Lead: {task.lead.name}" if task.lead else "Task",
                    'date': dt,
                    'icon': 'rocket_launch',
                    'color_class': 'text-warning bg-warning/10 border-warning/30',
                    'url': reverse('contact_detail', args=[task.lead.id]) if task.lead else '#'
                })
    except Exception:
        pass

    # 3. Expiring Agreements
    try:
        from projects.models import Agreement
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
    except Exception:
        pass

    # 4. Open Tickets
    try:
        from support.models import Ticket
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
    except Exception:
        pass

    # 5. Finance Invoices
    try:
        from finance.models import Invoice
        if profile.has_access_finance or profile.has_access_finance_invoices:
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
                    'url': reverse('invoice_dashboard')
                })
    except Exception:
        pass

    # 6. Recent Activities
    try:
        from activities.models import Activity
        if profile.has_access_leads:
            recent_activities = Activity.objects.filter(
                lead__organization=org
            ).order_by('-timestamp')[:20]
            for act in recent_activities:
                unified_feed.append({
                    'type': 'Activity',
                    'title': f"{act.type} - {act.lead.name}" if act.lead else act.type,
                    'description': act.description,
                    'date': act.timestamp,
                    'icon': 'history',
                    'color_class': 'text-on-surface bg-surface-variant/50 border-outline-variant',
                    'url': reverse('contact_detail', args=[act.lead.id]) if act.lead else '#'
                })
    except Exception:
        pass

    # 7. System Alerts
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

    SystemNotification.objects.filter(user=request.user, is_read=False).update(is_read=True)
    unified_feed.sort(key=lambda x: x['date'], reverse=True)

    context = {
        'unified_feed': unified_feed,
        'now': now,
    }
    return render(request, 'notifications.html', context)
