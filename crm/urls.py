from django.urls import path, include
from . import views

urlpatterns = [
    # Top-level Dashboard & Offline
    path('', views.dashboard_view, name='root'),
    path('dashboard/', views.dashboard_view, name='dashboard'),
    path('offline/', views.offline_view, name='offline'),

    # Dynamic status management endpoints
    path('statuses/category/<str:category>/add/', views.add_dynamic_status, name='add_dynamic_status'),
    path('statuses/category/<str:category>/<int:status_id>/edit/', views.edit_dynamic_status, name='edit_dynamic_status'),
    path('statuses/category/<str:category>/<int:status_id>/delete/', views.delete_dynamic_status, name='delete_dynamic_status'),
    path('statuses/category/<str:category>/reorder/', views.reorder_dynamic_statuses, name='reorder_dynamic_statuses'),

    # Modular Domain Apps
    path('', include('core.urls')),
    path('', include('leads.urls')),
    path('', include('services.urls')),
    path('', include('support.urls')),
    path('', include('projects.urls')),
    path('', include('activities.urls')),
    path('', include('campaigns.urls')),
    path('', include('content_tracker.urls')),
    path('', include('finance.urls')),
]
