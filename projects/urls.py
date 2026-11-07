from django.urls import path
from . import views

urlpatterns = [
    # Clients
    path('clients/', views.clients_view, name='clients'),
    path('clients/quick-create-ajax/', views.quick_create_client_ajax, name='quick_create_client_ajax'),
    path('clients/edit-ajax/<int:client_id>/', views.edit_client_ajax, name='edit_client_ajax'),
    path('clients/profile/<path:company_name>/', views.client_profile_view, name='client_profile'),
    path('clients/service/<str:service_id>/', views.service_clients_view, name='service_clients'),
    path('clients/edit-company/', views.edit_client_company, name='edit_client_company'),
    path('clients/delete-company/', views.delete_client_company, name='delete_client_company'),
    path('clients/contact/<int:lead_id>/', views.client_contact_detail_view, name='client_contact_detail'),
    path('statuses/clients/', views.client_status_settings, name='client_status_settings'),

    # Projects
    path('projects/', views.projects_view, name='projects'),
    path('projects/tasks/', views.project_tasks_view, name='project_tasks'),
    path('projects/board/', views.project_board_view, name='project_board'),
    path('projects/timeline/', views.project_timeline_view, name='project_timeline'),
    path('projects/milestones/', views.project_milestones_view, name='project_milestones'),
    path('projects/files/', views.project_files_view, name='project_files'),
    path('projects/time-tracking/', views.project_time_tracking_view, name='project_time_tracking'),
    path('projects/reports/', views.project_reports_view, name='project_reports'),
    path('projects/import/', views.import_projects, name='import_projects'),
    path('statuses/projects/', views.project_status_settings, name='project_status_settings'),

    # Agreements
    path('agreements/', views.agreements_list_view, name='agreements'),
    path('agreements/create/', views.create_agreement_view, name='create_agreement'),
    path('agreements/<int:agreement_id>/', views.agreement_print_view, name='agreement_detail'),
    path('agreements/<int:agreement_id>/edit/', views.update_agreement_view, name='edit_agreement'),
    path('agreements/<int:agreement_id>/delete/', views.delete_agreement_view, name='delete_agreement'),
    path('agreements/<int:agreement_id>/print/', views.agreement_print_view, name='print_agreement'),
    path('agreement/view/<str:public_token>/', views.public_agreement_view, name='public_agreement_view'),
    path('agreement/view/<str:public_token>/sign/', views.public_agreement_sign, name='public_agreement_sign'),
]

