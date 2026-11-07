from django.urls import path
from . import views

urlpatterns = [
    path('campaign/', views.campaign_view, name='campaign'),
    path('campaign/dashboard/', views.campaign_dashboard_view, name='campaign_dashboard'),
    path('campaign/add/', views.add_campaign, name='add_campaign'),
    path('campaign/<int:campaign_id>/edit/', views.edit_campaign, name='edit_campaign'),
    path('campaign/<int:campaign_id>/delete/', views.delete_campaign, name='delete_campaign'),
    path('campaign/<int:campaign_id>/toggle-active/', views.toggle_campaign_active, name='toggle_campaign_active'),
    path('statuses/campaigns/', views.campaign_status_settings, name='campaign_status_settings'),
]

