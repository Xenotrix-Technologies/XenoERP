from django.urls import path
from . import views

urlpatterns = [
    path('services/', views.services_view, name='services'),
    path('services/add/', views.add_service, name='add_service'),
    path('services/<int:service_id>/edit/', views.edit_service, name='edit_service'),
    path('services/<int:service_id>/delete/', views.delete_service, name='delete_service'),
]

