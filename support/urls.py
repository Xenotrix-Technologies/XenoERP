from django.urls import path
from . import views

urlpatterns = [
    path('customer-support/', views.customer_support_view, name='customer_support'),
    path('customer-support/ticket/create/', views.create_ticket, name='create_ticket'),
    path('customer-support/ticket/<int:ticket_id>/edit/', views.edit_ticket, name='edit_ticket'),
    path('customer-support/ticket/<int:ticket_id>/delete/', views.delete_ticket, name='delete_ticket'),
    path('statuses/tickets/', views.ticket_status_settings, name='ticket_status_settings'),
    path('statuses/priority/', views.priority_status_settings, name='priority_status_settings'),
]

