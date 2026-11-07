import json
from datetime import datetime
from django.shortcuts import render, redirect, get_object_or_404
from django.http import JsonResponse
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.utils import timezone
from django.db.models import Q

from .models import (
    CalendarStatus, Activity, WhatsAppMessage, Task, TaskTodo,
    TaskFile, TaskMilestone, TaskComment, Meeting, Event
)
from .forms import EventForm
from core.models import UserProfile, SystemNotification
from core.permissions import page_permission_required
from leads.models import Lead
from services.models import Service

# ── Task Views ───────────────────────────────────────────────────────────────

@login_required
def add_task(request):
    if request.method == 'POST':
        lead_id = request.POST.get('lead_id')
        title = request.POST.get('title', 'Project Task')
        desc = request.POST.get('description', '')
        start_date = request.POST.get('start_date') or None
        due_date = request.POST.get('due_date')
        if not due_date:
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

            status_obj = None
            status_id = request.POST.get('status_id')
            if status_id:
                try:
                    from projects.models import ProjectStatus
                    status_obj = ProjectStatus.objects.get(id=status_id, organization=org)
                except Exception:
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
                        'due_date_formatted': task.due_date.strftime('%b %d') if task.due_date else '',
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
                    from projects.models import ProjectStatus
                    task.status = ProjectStatus.objects.get(id=status_id, organization=org)
                except Exception:
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

    client_name = (task.lead.company or task.lead.name) if task.lead else "In-house Project"

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

        if task.lead:
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
        task.progress = calc_prog
        if calc_prog == 100 and not task.completed:
            task.completed = True
        elif calc_prog < 100 and task.completed:
            task.completed = False
        task.save()

        return JsonResponse({
            'success': True,
            'completed': todo.completed,
            'progress': calc_prog,
            'deliverables_done': task.deliverables_done,
            'deliverables_total': task.deliverables_total
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
        calc_prog = task.calculated_progress
        task.progress = calc_prog
        if calc_prog == 100 and not task.completed:
            task.completed = True
        elif calc_prog < 100 and task.completed:
            task.completed = False
        task.save()

        return JsonResponse({
            'success': True,
            'progress': calc_prog,
            'deliverables_done': task.deliverables_done,
            'deliverables_total': task.deliverables_total
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

        if task.lead:
            Activity.objects.create(
                lead=task.lead,
                type='Task',
                description=f"{user_name} posted a message on '{task.title}': {msg[:80]}"
            )

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
            try:
                from projects.models import ProjectStatus
                comp_status = ProjectStatus.objects.filter(organization=org, name__iexact='Completed').first()
                if comp_status:
                    task.status = comp_status
            except Exception:
                pass
        else:
            status_obj = None
            try:
                from projects.models import ProjectStatus
                if str(status_val).isdigit():
                    status_obj = ProjectStatus.objects.filter(id=int(status_val), organization=org).first()
                if not status_obj:
                    status_obj = ProjectStatus.objects.filter(organization=org, name__iexact=status_val).first()
            except Exception:
                pass

            if status_obj:
                task.status = status_obj
                task.completed = (status_obj.name.lower() == 'completed')
            else:
                task.completed = (str(status_val).lower() == 'completed')

        task.save()
        status_name = task.status.name if task.status else ("Completed" if task.completed else "In Progress")

        if task.lead:
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

        if task.lead:
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

        if task.lead:
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

        calc_prog = task.calculated_progress
        task.progress = calc_prog
        task.save()

        if task.lead:
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
                'due_date': tm.due_date.strftime('%b %d'),
                'completed': tm.completed,
                'kind': 'milestone'
            },
            'progress': calc_prog,
            'deliverables_done': task.deliverables_done,
            'deliverables_total': task.deliverables_total
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

        calc_prog = task.calculated_progress
        task.progress = calc_prog
        if calc_prog == 100 and not task.completed:
            task.completed = True
        elif calc_prog < 100 and task.completed:
            task.completed = False
        task.save()

        return JsonResponse({
            'success': True,
            'completed': tm.completed,
            'progress': calc_prog,
            'deliverables_done': task.deliverables_done,
            'deliverables_total': task.deliverables_total
        })
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
        calc_prog = task.calculated_progress
        task.progress = calc_prog
        if calc_prog == 100 and not task.completed:
            task.completed = True
        elif calc_prog < 100 and task.completed:
            task.completed = False
        task.save()

        return JsonResponse({
            'success': True,
            'progress': calc_prog,
            'deliverables_done': task.deliverables_done,
            'deliverables_total': task.deliverables_total
        })
    return JsonResponse({'success': False, 'error': 'Invalid method.'})

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
            task = Task.objects.filter(id=task_id).filter(Q(lead__organization=org) | Q(organization=org)).first()
            if not task:
                return JsonResponse({'success': False, 'error': 'Task not found.'})
            task.completed = not task.completed
            task.save()

            status_text = "completed" if task.completed else "re-opened"
            if task.lead:
                Activity.objects.create(
                    lead=task.lead,
                    type='Task',
                    description=f"Marked task '{task.title}' as {status_text}."
                )
            return JsonResponse({'success': True, 'completed': task.completed, 'progress': task.calculated_progress})
        except Exception as e:
            return JsonResponse({'success': False, 'error': str(e)})

    return JsonResponse({'success': False, 'error': 'Invalid request.'})

# ── Activity Log View ────────────────────────────────────────────────────────

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

# ── Calendar & Events Views ──────────────────────────────────────────────────

@login_required
@page_permission_required('calendar')
def calendar_view(request):
    org = request.user.profile.organization
    events = Event.objects.filter(organization=org).order_by('start_time')
    calendar_statuses = CalendarStatus.objects.filter(organization=org)
    clients = Lead.objects.filter(organization=org, is_client=True).order_by('company')

    milestone_count = Task.objects.filter(Q(lead__organization=org) | Q(organization=org), due_date__isnull=False).count()
    events_count = events.count()
    total_scheduled = events_count + milestone_count

    meetings_count = events.filter(Q(color__in=['#00BAFF', '#004ac6', '#2563EB']) | Q(title__icontains='Meeting')).count()
    campaigns_count = events.filter(color__in=['#06B6D4', '#00D0C6']).count()
    followups_count = events.filter(color__in=['#FB923C', '#8b5cf6', '#FBBF24']).count()

    categories_list = [
        {'id': 'client_meeting', 'label': 'Client Meetings', 'color': '#00BAFF', 'badge': 'bg-sky-50 text-sky-700 border-sky-200'},
        {'id': 'milestone_deliverable', 'label': 'Milestone Deliverables', 'color': '#10B981', 'badge': 'bg-emerald-50 text-emerald-700 border-emerald-200'},
        {'id': 'social_post', 'label': 'Social Posts', 'color': '#00D0C6', 'badge': 'bg-teal-50 text-teal-700 border-teal-200'},
        {'id': 'ad_campaign', 'label': 'Ad Campaigns', 'color': '#06B6D4', 'badge': 'bg-cyan-50 text-cyan-700 border-cyan-200'},
        {'id': 'website_milestone', 'label': 'Website Milestones', 'color': '#34D399', 'badge': 'bg-emerald-50 text-emerald-700 border-emerald-200'},
        {'id': 'seo_task', 'label': 'SEO Deliverables', 'color': '#FBBF24', 'badge': 'bg-amber-50 text-amber-700 border-amber-200'},
        {'id': 'payment_followup', 'label': 'Payment Follow-ups', 'color': '#FB923C', 'badge': 'bg-orange-50 text-orange-700 border-orange-200'},
        {'id': 'internal_meeting', 'label': 'Internal Syncs', 'color': '#94A3B8', 'badge': 'bg-slate-100 text-slate-700 border-slate-200'},
    ]

    context = {
        'events': events,
        'calendar_statuses': calendar_statuses,
        'clients': clients,
        'categories': categories_list,
        'analytics': {
            'total_scheduled': total_scheduled,
            'meetings_count': meetings_count,
            'deliverables_count': milestone_count,
            'campaigns_count': campaigns_count,
            'followups_count': followups_count
        }
    }
    return render(request, 'calendar.html', context)

@login_required
@page_permission_required('calendar')
def calendar_list_view(request):
    org = request.user.profile.organization
    date_str = request.GET.get('date')
    events = Event.objects.filter(organization=org)

    if date_str:
        try:
            dt = datetime.strptime(date_str, "%Y-%m-%d")
            events = events.filter(start_time__date=dt.date())
        except ValueError:
            pass

    events = events.order_by('-start_time')
    calendar_statuses = CalendarStatus.objects.filter(organization=org)
    return render(request, 'calendar_list.html', {
        'events': events,
        'filter_date': date_str,
        'calendar_statuses': calendar_statuses
    })

@login_required
@page_permission_required('calendar')
def event_create_view(request):
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
    org = request.user.profile.organization
    event = get_object_or_404(Event, id=event_id, organization=org)
    event.delete()
    SystemNotification.objects.create(user=request.user, message='Event deleted.', type='success')
    return redirect('calendar')

@login_required
def calendar_events_json_view(request):
    org = request.user.profile.organization
    client_id_filter = request.GET.get('client_id', '').strip()
    category_filter = request.GET.get('category', '').strip()

    events = Event.objects.filter(organization=org)
    events_data = []

    def get_category_info(evt_color, desc):
        color_map = {
            '#00baff': ('client_meeting', 'Client Meeting'),
            '#004ac6': ('client_meeting', 'Client Meeting'),
            '#2563eb': ('client_meeting', 'Client Meeting'),
            '#10b981': ('milestone_deliverable', 'Milestone Deliverable'),
            '#c6f24e': ('milestone_deliverable', 'Milestone Deliverable'),
            '#00d0c6': ('social_post', 'Social Post'),
            '#06b6d4': ('ad_campaign', 'Ad Campaign'),
            '#34d399': ('website_milestone', 'Website Milestone'),
            '#fbbf24': ('seo_task', 'SEO Deliverable'),
            '#fb7185': ('content_review', 'Content Review'),
            '#fb923c': ('payment_followup', 'Payment Follow-up'),
            '#8b5cf6': ('payment_followup', 'Payment Follow-up'),
            '#94a3b8': ('internal_meeting', 'Internal Meeting'),
        }
        c = (evt_color or '#00baff').lower()
        return color_map.get(c, ('client_meeting', 'Client Meeting'))

    clients_map = {c.id: c.company for c in Lead.objects.filter(organization=org, is_client=True)}

    for event in events:
        desc = event.description or ''
        cat_slug, cat_label = get_category_info(event.color, desc)

        event_client_id = None
        event_client_name = 'Internal Sync'
        for cid, cname in clients_map.items():
            if cname and (cname.lower() in event.title.lower() or cname.lower() in desc.lower()):
                event_client_id = cid
                event_client_name = cname
                break

        if client_id_filter and client_id_filter != 'all':
            if str(event_client_id) != str(client_id_filter) and (str(client_id_filter) not in desc):
                continue

        if category_filter and category_filter != 'all':
            if cat_slug != category_filter:
                continue

        events_data.append({
            'id': f"event-{event.id}",
            'raw_id': event.id,
            'title': event.title,
            'start': event.start_time.strftime('%Y-%m-%dT%H:%M:%S') if event.start_time else None,
            'end': event.end_time.strftime('%Y-%m-%dT%H:%M:%S') if event.end_time else None,
            'description': desc,
            'recurring': event.recurring,
            'color': event.color or '#00BAFF',
            'is_milestone': False,
            'category': cat_slug,
            'category_label': cat_label,
            'client_id': event_client_id,
            'client_name': event_client_name,
            'owner': event.owner.get_full_name() or event.owner.username if event.owner else 'System'
        })

    # Include tasks when requested or from calendar UI
    include_tasks = 't' in request.GET or request.GET.get('include_tasks') == 'true' or category_filter in ['milestone_deliverable']
    if include_tasks:
        tasks = Task.objects.filter(
            Q(lead__organization=org) | Q(organization=org),
            due_date__isnull=False
        ).select_related('lead', 'status')

        for task in tasks:
            task_client_id = task.lead.id if task.lead else None
            task_client_name = task.lead.company if task.lead else 'Internal Project'

            if client_id_filter and client_id_filter != 'all':
                if str(task_client_id) != str(client_id_filter):
                    continue

            status_name = task.status.name if task.status else ('Completed' if task.completed else 'In Progress')
            events_data.append({
                'id': f"milestone-{task.id}",
                'raw_id': task.id,
                'title': f"[Deliverable] {task.title}",
                'start': task.due_date.strftime('%Y-%m-%d'),
                'end': task.due_date.strftime('%Y-%m-%d'),
                'description': f"Deliverable Deadline for {task_client_name}. Status: {status_name}. Progress: {task.progress}%.",
                'color': '#10B981',
                'is_milestone': True,
                'allDay': True,
                'category': 'milestone_deliverable',
                'category_label': 'Milestone Deliverable',
                'client_id': task_client_id,
                'client_name': task_client_name,
                'priority': task.priority,
                'status': status_name,
                'progress': task.progress
            })

    return JsonResponse(events_data, safe=False)

@login_required
def event_create_ajax(request):
    if request.method == 'POST':
        org = request.user.profile.organization
        title = request.POST.get('title', '').strip()
        start_time_str = request.POST.get('start_time', '').strip()
        end_time_str = request.POST.get('end_time', '').strip()
        color = request.POST.get('color', '#00BAFF').strip()
        description = request.POST.get('description', '').strip()
        client_name = request.POST.get('client_name', '').strip()
        meeting_link = request.POST.get('meeting_link', '').strip()

        if not title:
            return JsonResponse({'success': False, 'error': 'Event title is required.'})

        extra_lines = []
        if client_name:
            extra_lines.append(f"Client: {client_name}")
        if meeting_link:
            extra_lines.append(f"Meeting Link: {meeting_link}")
        if extra_lines:
            description = (description + "\n\n" + "\n".join(extra_lines)).strip()

        try:
            clean_start = start_time_str.replace('Z', '+00:00')
            if 'T' in clean_start:
                start_dt = datetime.fromisoformat(clean_start)
            else:
                start_dt = datetime.strptime(clean_start, '%Y-%m-%d %H:%M')
        except Exception:
            start_dt = timezone.now()

        try:
            clean_end = end_time_str.replace('Z', '+00:00') if end_time_str else ''
            if clean_end and 'T' in clean_end:
                end_dt = datetime.fromisoformat(clean_end)
            elif clean_end:
                end_dt = datetime.strptime(clean_end, '%Y-%m-%d %H:%M')
            else:
                end_dt = start_dt + timezone.timedelta(hours=1)
        except Exception:
            end_dt = start_dt + timezone.timedelta(hours=1)

        event = Event.objects.create(
            organization=org,
            owner=request.user,
            title=title,
            start_time=start_dt,
            end_time=end_dt,
            color=color,
            description=description
        )

        try:
            from .event_notifications import check_and_send_event_notifications
            check_and_send_event_notifications(event)
        except Exception:
            pass

        return JsonResponse({
            'success': True,
            'event': {
                'id': f"event-{event.id}",
                'raw_id': event.id,
                'title': event.title,
                'start': event.start_time.strftime('%Y-%m-%dT%H:%M:%S'),
                'end': event.end_time.strftime('%Y-%m-%dT%H:%M:%S'),
                'color': event.color,
                'description': event.description
            }
        })
    return JsonResponse({'success': False, 'error': 'Invalid request method.'})

@login_required
def event_edit_ajax(request, event_id):
    org = request.user.profile.organization
    event = get_object_or_404(Event, id=event_id, organization=org)

    if request.method == 'POST':
        title = request.POST.get('title')
        if title:
            event.title = title.strip()

        start_time_str = request.POST.get('start_time')
        if start_time_str:
            try:
                clean_start = start_time_str.replace('Z', '+00:00')
                if 'T' in clean_start:
                    event.start_time = datetime.fromisoformat(clean_start)
                else:
                    event.start_time = datetime.strptime(clean_start, '%Y-%m-%d %H:%M')
            except Exception:
                pass

        end_time_str = request.POST.get('end_time')
        if end_time_str:
            try:
                clean_end = end_time_str.replace('Z', '+00:00')
                if 'T' in clean_end:
                    event.end_time = datetime.fromisoformat(clean_end)
                else:
                    event.end_time = datetime.strptime(clean_end, '%Y-%m-%d %H:%M')
            except Exception:
                pass

        color = request.POST.get('color')
        if color:
            event.color = color.strip()

        description = request.POST.get('description')
        if description is not None:
            event.description = description.strip()

        recurring_val = request.POST.get('recurring')
        if recurring_val is not None:
            event.recurring = (recurring_val.lower() in ['true', '1', 'on', 'yes'])

        event.save()

        return JsonResponse({
            'success': True,
            'event': {
                'id': f"event-{event.id}",
                'raw_id': event.id,
                'title': event.title,
                'start': event.start_time.strftime('%Y-%m-%dT%H:%M:%S') if event.start_time else None,
                'end': event.end_time.strftime('%Y-%m-%dT%H:%M:%S') if event.end_time else None,
                'color': event.color,
                'description': event.description,
                'recurring': event.recurring
            }
        })

    return JsonResponse({'success': False, 'error': 'Invalid request method.'})

@login_required
def event_delete_ajax(request, event_id):
    if request.method == 'POST':
        org = request.user.profile.organization
        event = get_object_or_404(Event, id=event_id, organization=org)
        event.delete()
        return JsonResponse({'success': True})
    return JsonResponse({'success': False, 'error': 'Invalid request method.'})

@login_required
@page_permission_required('calendar_statuses')
def calendar_status_settings(request):
    org = request.user.profile.organization
    statuses = CalendarStatus.objects.filter(organization=org)
    return render(request, 'generic_status_settings.html', {
        'category': 'calendar',
        'title': 'Calendar Statuses',
        'statuses': statuses
    })

# ── WhatsApp Views ───────────────────────────────────────────────────────────

@login_required
def send_whatsapp_page_view(request, lead_id):
    org = request.user.profile.organization
    try:
        lead = Lead.objects.get(id=lead_id, organization=org)
    except Lead.DoesNotExist:
        return redirect('leads')

    activities = lead.activities.all().order_by('-timestamp') if hasattr(lead, 'activities') else []
    tasks = lead.tasks.all().order_by('-created_at') if hasattr(lead, 'tasks') else []
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
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'Invalid HTTP method'}, status=405)

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
