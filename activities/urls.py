from django.urls import path
from . import views

urlpatterns = [
    # Task endpoints
    path('task/add/', views.add_task, name='add_task'),
    path('task/complete/', views.complete_task, name='complete_task'),
    path('task/<int:task_id>/edit/', views.edit_task, name='edit_task'),
    path('task/<int:task_id>/delete/', views.delete_task, name='delete_task'),
    path('task/<int:task_id>/details/', views.task_details_json, name='task_details_json'),
    path('task/<int:task_id>/move-status/', views.move_task_status, name='move_task_status'),
    path('task/<int:task_id>/toggle-star/', views.toggle_task_star, name='toggle_task_star'),
    path('task/<int:task_id>/todo/add/', views.add_task_todo, name='add_task_todo'),
    path('task/todo/<int:todo_id>/toggle/', views.toggle_task_todo, name='toggle_task_todo'),
    path('task/todo/<int:todo_id>/edit/', views.edit_task_todo, name='edit_task_todo'),
    path('task/todo/<int:todo_id>/delete/', views.delete_task_todo, name='delete_task_todo'),
    path('task/<int:task_id>/comments/', views.get_task_comments, name='get_task_comments'),
    path('task/<int:task_id>/comment/add/', views.add_task_comment, name='add_task_comment'),
    path('task/<int:task_id>/file/upload/', views.upload_task_file, name='upload_task_file'),
    path('task/file/<int:file_id>/delete/', views.delete_task_file, name='delete_task_file'),
    path('task/<int:task_id>/milestone/add/', views.add_task_milestone, name='add_task_milestone'),
    path('task/milestone/<int:milestone_id>/toggle/', views.toggle_task_milestone, name='toggle_task_milestone'),
    path('task/milestone/<int:milestone_id>/reschedule/', views.reschedule_task_milestone, name='reschedule_task_milestone'),
    path('task/milestone/<int:milestone_id>/edit/', views.edit_task_milestone, name='edit_task_milestone'),
    path('task/milestone/<int:milestone_id>/delete/', views.delete_task_milestone, name='delete_task_milestone'),

    # Activity Log
    path('activity/log/', views.log_activity, name='log_activity'),

    # Calendar
    path('calendar/', views.calendar_view, name='calendar'),
    path('calendar/list/', views.calendar_list_view, name='calendar_list'),
    path('calendar/create/', views.event_create_view, name='event_create'),
    path('calendar/edit/<int:event_id>/', views.event_edit_view, name='event_edit'),
    path('calendar/delete/<int:event_id>/', views.event_delete_view, name='event_delete'),
    path('calendar/events-json/', views.calendar_events_json_view, name='calendar_events_json'),
    path('calendar/create-ajax/', views.event_create_ajax, name='event_create_ajax'),
    path('calendar/edit-ajax/<int:event_id>/', views.event_edit_ajax, name='event_edit_ajax'),
    path('calendar/delete-ajax/<int:event_id>/', views.event_delete_ajax, name='event_delete_ajax'),
    path('statuses/calendar/', views.calendar_status_settings, name='calendar_status_settings'),

    # WhatsApp API & messaging
    path('leads/<int:lead_id>/send-whatsapp/', views.send_whatsapp_page_view, name='send_whatsapp_page'),
    path('api/whatsapp/send-cloud-api/', views.send_whatsapp_cloud_api_view, name='send_whatsapp_cloud_api'),
    path('api/whatsapp/status/', views.whatsapp_status_json_view, name='whatsapp_status_json'),
]

