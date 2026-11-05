from datetime import datetime
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.utils import timezone
from django.contrib import messages
from django.http import JsonResponse
from django.db.models import Q, Sum, Count

from crm.views import page_permission_required
from crm.models import Department, UserProfile
from activities.models import Task
from .models import EmployeeProfile, Attendance, LeaveRequest, Payroll, LeaveType, AttendanceStatus, PayrollRule, LeaveRequestStatus
from .forms import EmployeeProfileForm, AttendanceForm, LeaveRequestForm, PayrollForm, LeaveTypeForm, AttendanceStatusForm, PayrollRuleForm, LeaveRequestStatusForm, DepartmentForm


@login_required
@page_permission_required('hr')
def hr_dashboard(request):
    """
    Executive Command Center for Human Resources operations:
    Workforce directory, attendance live status, leave approvals,
    workload capacity meters, and payroll summaries.
    """
    org = request.user.profile.organization
    today = timezone.now().date()
    
    # 1. Staff Members & Headcount
    staff_members = UserProfile.objects.filter(organization=org).select_related('user', 'department').order_by('user__first_name', 'user__username')
    employees_count = staff_members.count()
    
    # 2. Departments
    departments = Department.objects.filter(organization=org).order_by('name')
    dept_stats = []
    for d in departments:
        count = staff_members.filter(department=d).count()
        pct = int((count / (employees_count or 1)) * 100) if employees_count > 0 else 0
        dept_stats.append({
            'department': d,
            'count': count,
            'percent': pct
        })
    unassigned_count = staff_members.filter(department__isnull=True).count()
    if unassigned_count > 0:
        dept_stats.append({
            'department': {'id': 0, 'name': 'General / Unassigned'},
            'count': unassigned_count,
            'percent': int((unassigned_count / (employees_count or 1)) * 100) if employees_count > 0 else 0
        })

    # 3. Attendance Today
    today_attendances = Attendance.objects.filter(organization=org, date=today).select_related('user_profile__user', 'status')
    today_att_map = {att.user_profile_id: att for att in today_attendances}
    
    present_staff_ids = set()
    for att in today_attendances:
        if att.clock_in or (att.status and 'absent' not in att.status.name.lower()):
            present_staff_ids.add(att.user_profile_id)
            
    present_today = len(present_staff_ids)
    attendance_rate = int((present_today / (employees_count or 1)) * 100) if employees_count > 0 else 0
    
    recent_attendances = Attendance.objects.filter(organization=org).select_related('user_profile__user', 'status').order_by('-date', '-clock_in')[:20]
    
    # 4. Leaves
    on_leave_today_qs = LeaveRequest.objects.filter(
        organization=org,
        start_date__lte=today,
        end_date__gte=today,
        status__name__iexact='Approved'
    ).select_related('user_profile__user', 'leave_type')
    on_leave = on_leave_today_qs.count()
    on_leave_today_staff_ids = set(on_leave_today_qs.values_list('user_profile_id', flat=True))
    
    pending_leaves = LeaveRequest.objects.filter(
        organization=org,
        status__name__iexact='Pending'
    ).select_related('user_profile__user', 'leave_type', 'status').order_by('-applied_on')
    pending_leaves_count = pending_leaves.count()
    
    all_leaves = LeaveRequest.objects.filter(organization=org).select_related('user_profile__user', 'leave_type', 'status').order_by('-applied_on')[:20]
    
    # 5. Live Today Staff Status Roster
    staff_today_roster = []
    for staff in staff_members:
        att = today_att_map.get(staff.id)
        is_on_leave = staff.id in on_leave_today_staff_ids
        
        if is_on_leave:
            status_label = 'On Leave'
            status_badge = 'bg-rose-50 text-rose-700 border border-rose-200'
            status_color = 'rose'
        elif att:
            if att.clock_out:
                status_label = 'Clocked Out'
                status_badge = 'bg-slate-100 text-slate-700 border border-slate-200'
                status_color = 'slate'
            elif att.clock_in:
                status_label = 'Clocked In'
                status_badge = 'bg-emerald-50 text-emerald-700 border border-emerald-200'
                status_color = 'emerald'
            elif att.status:
                status_label = att.status.name
                status_badge = 'bg-blue-50 text-blue-700 border border-blue-200'
                status_color = 'blue'
            else:
                status_label = 'Present'
                status_badge = 'bg-emerald-50 text-emerald-700 border border-emerald-200'
                status_color = 'emerald'
        else:
            status_label = 'Not Marked'
            status_badge = 'bg-amber-50 text-amber-700 border border-amber-200'
            status_color = 'amber'
            
        staff_today_roster.append({
            'profile': staff,
            'attendance': att,
            'is_on_leave': is_on_leave,
            'status_label': status_label,
            'status_badge': status_badge,
            'status_color': status_color,
        })
        
    # 6. Team Workload & Active Tasks Capacity (XenoPlan Architecture)
    active_tasks = Task.objects.filter(
        Q(lead__organization=org) | Q(organization=org),
        completed=False
    ).exclude(status__name__iexact='Completed').prefetch_related('assignees')
    
    active_task_assignments_count = 0
    staff_workload_cards = []
    for staff in staff_members:
        staff_tasks = [t for t in active_tasks if staff in t.assignees.all()]
        task_count = len(staff_tasks)
        active_task_assignments_count += task_count
        
        allocated_hours = task_count * 4
        max_capacity = 40
        load_percent = min(100, int((allocated_hours / max_capacity) * 100))
        
        if load_percent >= 90:
            load_color = 'rose'
            load_badge = 'bg-rose-50 text-rose-700 border border-rose-200'
            load_label = 'Overloaded'
        elif load_percent >= 60:
            load_color = 'amber'
            load_badge = 'bg-amber-50 text-amber-700 border border-amber-200'
            load_label = 'Moderate'
        else:
            load_color = 'emerald'
            load_badge = 'bg-emerald-50 text-emerald-700 border border-emerald-200'
            load_label = 'Optimal'
            
        staff_workload_cards.append({
            'profile': staff,
            'active_tasks_count': task_count,
            'active_tasks': staff_tasks[:3],
            'allocated_hours': allocated_hours,
            'max_capacity': max_capacity,
            'load_percent': load_percent,
            'load_color': load_color,
            'load_badge': load_badge,
            'load_label': load_label,
        })

    # 7. Payroll metrics
    all_payrolls = Payroll.objects.filter(organization=org).select_related('user_profile__user').order_by('-cycle_end_date', '-processed_on')
    pending_payroll = all_payrolls.filter(status='Draft').count()
    paid_payroll = all_payrolls.filter(status='Paid').count()
    
    total_payroll_paid = all_payrolls.filter(status='Paid').aggregate(Sum('net_pay'))['net_pay__sum'] or 0
    total_payroll_pending = all_payrolls.filter(status='Draft').aggregate(Sum('net_pay'))['net_pay__sum'] or 0
    recent_payrolls = all_payrolls[:8]
    
    # 8. Modals / Form selects
    leave_types = LeaveType.objects.filter(organization=org, is_active=True)
    attendance_statuses = AttendanceStatus.objects.filter(organization=org, is_active=True)
    leave_statuses = LeaveRequestStatus.objects.filter(organization=org, is_active=True)

    return render(request, 'hr_dashboard.html', {
        'page_title': 'Human Resources Command Center',
        'today': today,
        'staff_members': staff_members,
        'employees_count': employees_count,
        'departments': departments,
        'dept_stats': dept_stats,
        'present_today': present_today,
        'attendance_rate': attendance_rate,
        'recent_attendances': recent_attendances,
        'on_leave': on_leave,
        'on_leave_today_qs': on_leave_today_qs,
        'pending_leaves': pending_leaves,
        'pending_leaves_count': pending_leaves_count,
        'all_leaves': all_leaves,
        'staff_today_roster': staff_today_roster,
        'staff_workload_cards': staff_workload_cards,
        'active_task_assignments_count': active_task_assignments_count,
        'pending_payroll': pending_payroll,
        'paid_payroll': paid_payroll,
        'total_payroll_paid': total_payroll_paid,
        'total_payroll_pending': total_payroll_pending,
        'recent_payrolls': recent_payrolls,
        'leave_types': leave_types,
        'attendance_statuses': attendance_statuses,
        'leave_statuses': leave_statuses,
    })


@login_required
@page_permission_required('hr')
def leave_action(request, leave_id):
    """
    Quick 1-click approval or rejection of a leave request.
    """
    org = request.user.profile.organization
    leave = get_object_or_404(LeaveRequest, id=leave_id, organization=org)
    
    if request.method == 'POST':
        action = request.POST.get('action') # 'approve' or 'reject'
        status_name = 'Approved' if action == 'approve' else 'Rejected'
        status_obj, _ = LeaveRequestStatus.objects.get_or_create(
            organization=org,
            name=status_name,
            defaults={'is_active': True}
        )
        leave.status = status_obj
        leave.save()
        
        emp_name = leave.user_profile.user.get_full_name() or leave.user_profile.user.username
        msg = f"Leave request for {emp_name} has been {status_name.lower()}."
        if request.headers.get('x-requested-with') == 'XMLHttpRequest':
            return JsonResponse({'success': True, 'message': msg, 'status': status_name})
            
        messages.success(request, msg)
        return redirect(request.META.get('HTTP_REFERER', 'hr_dashboard'))
        
    return JsonResponse({'success': False, 'error': 'Invalid request method.'})


@login_required
@page_permission_required('hr')
def quick_log_attendance(request):
    """
    Quickly record or update attendance directly from the HR Dashboard.
    """
    org = request.user.profile.organization
    if request.method == 'POST':
        user_profile_id = request.POST.get('user_profile')
        date_str = request.POST.get('date')
        clock_in = request.POST.get('clock_in') or None
        clock_out = request.POST.get('clock_out') or None
        status_id = request.POST.get('status') or None
        notes = request.POST.get('notes', '')
        
        if not user_profile_id:
            if request.headers.get('x-requested-with') == 'XMLHttpRequest':
                return JsonResponse({'success': False, 'error': 'Employee profile is required.'})
            messages.error(request, 'Employee profile is required.')
            return redirect('hr_dashboard')
            
        profile = get_object_or_404(UserProfile, id=int(user_profile_id), organization=org)
        log_date = datetime.strptime(date_str, '%Y-%m-%d').date() if date_str else timezone.now().date()
        
        status_obj = None
        if status_id:
            try:
                status_obj = AttendanceStatus.objects.get(id=int(status_id), organization=org)
            except (AttendanceStatus.DoesNotExist, ValueError):
                pass
                
        att, created = Attendance.objects.update_or_create(
            user_profile=profile,
            date=log_date,
            organization=org,
            defaults={
                'clock_in': clock_in,
                'clock_out': clock_out,
                'status': status_obj,
                'notes': notes
            }
        )
        
        emp_name = profile.user.get_full_name() or profile.user.username
        msg = f"Attendance logged for {emp_name} on {log_date}."
        if request.headers.get('x-requested-with') == 'XMLHttpRequest':
            return JsonResponse({'success': True, 'message': msg})
        messages.success(request, msg)
        return redirect(request.META.get('HTTP_REFERER', 'hr_dashboard'))
        
    return JsonResponse({'success': False, 'error': 'Invalid method.'})


@login_required
@page_permission_required('hr')
def hr_attendance(request):
    org = request.user.profile.organization
    
    if request.method == 'POST':
        form = AttendanceForm(request.POST, organization=org)
        if form.is_valid():
            attendance = form.save(commit=False)
            attendance.organization = org
            attendance.save()
            messages.success(request, 'Attendance logged successfully.')
            return redirect('hr_attendance')
    else:
        form = AttendanceForm(organization=org)
        
    attendances = Attendance.objects.filter(organization=org).order_by('-date')
    
    return render(request, 'hr_attendance.html', {
        'page_title': 'Attendance Tracking',
        'attendances': attendances,
        'form': form
    })


@login_required
@page_permission_required('hr')
def hr_leaves(request):
    org = request.user.profile.organization
    
    if request.method == 'POST':
        form = LeaveRequestForm(request.POST, organization=org)
        if form.is_valid():
            leave = form.save(commit=False)
            leave.organization = org
            leave.save()
            messages.success(request, 'Leave request added successfully.')
            return redirect('hr_leaves')
    else:
        form = LeaveRequestForm(organization=org)
        
    leaves = LeaveRequest.objects.filter(organization=org)
    
    return render(request, 'hr_leaves.html', {
        'page_title': 'Leave Management',
        'leaves': leaves,
        'form': form
    })


@login_required
@page_permission_required('hr')
def hr_payroll(request):
    org = request.user.profile.organization
    
    if request.method == 'POST':
        form = PayrollForm(request.POST, organization=org)
        if form.is_valid():
            payroll = form.save(commit=False)
            payroll.organization = org
            payroll.save()
            messages.success(request, 'Payroll processed successfully.')
            return redirect('hr_payroll')
    else:
        form = PayrollForm(organization=org)
        
    payrolls = Payroll.objects.filter(organization=org)
    
    return render(request, 'hr_payroll.html', {
        'page_title': 'Payroll Processing',
        'payrolls': payrolls,
        'form': form
    })


@login_required
@page_permission_required('hr')
def edit_payroll(request, payroll_id):
    org = request.user.profile.organization
    payroll = get_object_or_404(Payroll, id=payroll_id, organization=org)
    
    if request.method == 'POST':
        form = PayrollForm(request.POST, instance=payroll, organization=org)
        if form.is_valid():
            form.save()
            messages.success(request, 'Salary slip updated successfully.')
        else:
            messages.error(request, 'Error updating salary slip. Please check the values entered.')
    return redirect('hr_payroll')


@login_required
@page_permission_required('hr')
def delete_payroll(request, payroll_id):
    org = request.user.profile.organization
    payroll = get_object_or_404(Payroll, id=payroll_id, organization=org)
    if request.method == 'POST':
        payroll.delete()
        messages.success(request, 'Salary slip deleted successfully.')
    return redirect('hr_payroll')


@login_required
@page_permission_required('hr')
def hr_settings(request):
    """
    Settings page for HR module to manage statuses and configurations.
    """
    org = request.user.profile.organization
    
    # Forms
    leave_form = LeaveTypeForm()
    attendance_form = AttendanceStatusForm()
    payroll_rule_form = PayrollRuleForm()
    leave_request_status_form = LeaveRequestStatusForm()
    department_form = DepartmentForm()
    
    # Handle POST
    if request.method == 'POST':
        action = request.POST.get('action')
        
        if action == 'add_leave_type':
            leave_form = LeaveTypeForm(request.POST)
            if leave_form.is_valid():
                obj = leave_form.save(commit=False)
                obj.organization = org
                obj.save()
                messages.success(request, 'Leave Type added successfully.')
                return redirect('hr_settings')
                
        elif action == 'add_leave_request_status':
            leave_request_status_form = LeaveRequestStatusForm(request.POST)
            if leave_request_status_form.is_valid():
                obj = leave_request_status_form.save(commit=False)
                obj.organization = org
                obj.save()
                messages.success(request, 'Leave Request Status added successfully.')
                return redirect('hr_settings')
                
        elif action == 'add_attendance_status':
            attendance_form = AttendanceStatusForm(request.POST)
            if attendance_form.is_valid():
                obj = attendance_form.save(commit=False)
                obj.organization = org
                obj.save()
                messages.success(request, 'Attendance Status added successfully.')
                return redirect('hr_settings')
                
        elif action == 'add_payroll_rule':
            payroll_rule_form = PayrollRuleForm(request.POST)
            if payroll_rule_form.is_valid():
                obj = payroll_rule_form.save(commit=False)
                obj.organization = org
                obj.save()
                messages.success(request, 'Payroll Rule added successfully.')
                return redirect('hr_settings')
                
        elif action == 'delete_leave_type':
            item_id = request.POST.get('item_id')
            LeaveType.objects.filter(id=item_id, organization=org).delete()
            messages.success(request, 'Leave Type deleted.')
            return redirect('hr_settings')
            
        elif action == 'delete_leave_request_status':
            item_id = request.POST.get('item_id')
            LeaveRequestStatus.objects.filter(id=item_id, organization=org).delete()
            messages.success(request, 'Leave Request Status deleted.')
            return redirect('hr_settings')
            
        elif action == 'delete_attendance_status':
            item_id = request.POST.get('item_id')
            AttendanceStatus.objects.filter(id=item_id, organization=org).delete()
            messages.success(request, 'Attendance Status deleted.')
            return redirect('hr_settings')
            
        elif action == 'delete_payroll_rule':
            item_id = request.POST.get('item_id')
            PayrollRule.objects.filter(id=item_id, organization=org).delete()
            messages.success(request, 'Payroll Rule deleted.')
            return redirect('hr_settings')
            
        elif action == 'add_department':
            department_form = DepartmentForm(request.POST)
            if department_form.is_valid():
                obj = department_form.save(commit=False)
                obj.organization = org
                obj.save()
                messages.success(request, 'Department added successfully.')
                return redirect('hr_settings')
                
        elif action == 'delete_department':
            item_id = request.POST.get('item_id')
            Department.objects.filter(id=item_id, organization=org).delete()
            messages.success(request, 'Department deleted.')
            return redirect('hr_settings')

    # Querysets
    leave_types = LeaveType.objects.filter(organization=org)
    attendance_statuses = AttendanceStatus.objects.filter(organization=org)
    payroll_rules = PayrollRule.objects.filter(organization=org)
    leave_request_statuses = LeaveRequestStatus.objects.filter(organization=org)
    departments = Department.objects.filter(organization=org)

    return render(request, 'hr_settings.html', {
        'page_title': 'HR Settings',
        'leave_types': leave_types,
        'attendance_statuses': attendance_statuses,
        'payroll_rules': payroll_rules,
        'leave_request_statuses': leave_request_statuses,
        'departments': departments,
        'leave_form': leave_form,
        'attendance_form': attendance_form,
        'payroll_rule_form': payroll_rule_form,
        'leave_request_status_form': leave_request_status_form,
        'department_form': department_form,
    })
