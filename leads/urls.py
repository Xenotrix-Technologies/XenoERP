from django.urls import path
from . import views

urlpatterns = [
    path('leads/', views.leads_view, name='leads'),
    path('leads/add/', views.add_lead, name='add_lead'),
    path('leads/import/', views.import_leads, name='import_leads'),
    path('leads/import/template/', views.download_lead_template, name='download_lead_template'),
    path('leads/<int:lead_id>/edit/', views.edit_lead, name='edit_lead'),
    path('leads/<int:lead_id>/delete/', views.delete_lead, name='delete_lead'),
    path('leads/<int:lead_id>/json/', views.lead_json_view, name='lead_json'),
    path('leads/send-email/', views.send_lead_email, name='send_lead_email'),
    path('pipeline/', views.pipeline_view, name='pipeline'),
    path('pipeline/update-stage/', views.update_lead_stage, name='update_lead_stage'),
    path('leads/<int:lead_id>/', views.contact_detail_view, name='contact_detail'),
    path('api/leads/search/', views.search_leads_json_view, name='search_leads_json'),
    path('lead/quick-create/', views.quick_create_lead, name='quick_create_lead'),

    # Lead Statuses
    path('statuses/lead-statuses/', views.lead_statuses_view, name='lead_statuses'),
    path('statuses/leads/', views.lead_status_settings, name='lead_status_settings'),
    path('statuses/add/', views.add_lead_status, name='add_lead_status'),
    path('statuses/<int:status_id>/edit/', views.edit_lead_status, name='edit_lead_status'),
    path('statuses/<int:status_id>/delete/', views.delete_lead_status, name='delete_lead_status'),
    path('statuses/reorder/', views.reorder_lead_statuses, name='reorder_lead_statuses'),
]

