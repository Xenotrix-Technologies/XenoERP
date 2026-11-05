from django.urls import path
from . import views

urlpatterns = [
    path('', views.hr_dashboard, name='hr_dashboard'),
    path('attendance/', views.hr_attendance, name='hr_attendance'),
    path('attendance/quick-log/', views.quick_log_attendance, name='hr_quick_log_attendance'),
    path('leaves/', views.hr_leaves, name='hr_leaves'),
    path('leaves/<int:leave_id>/action/', views.leave_action, name='hr_leave_action'),
    path('payroll/', views.hr_payroll, name='hr_payroll'),
    path('payroll/<int:payroll_id>/edit/', views.edit_payroll, name='edit_payroll'),
    path('payroll/<int:payroll_id>/delete/', views.delete_payroll, name='delete_payroll'),
    path('settings/', views.hr_settings, name='hr_settings'),
]
