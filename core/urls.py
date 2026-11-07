from django.urls import path
from django.contrib.auth import views as auth_views
from . import views

urlpatterns = [
    # Auth
    path('login/', views.login_view, name='login'),
    path('signup/', views.signup_view, name='signup'),
    path('logout/', views.logout_view, name='logout'),
    path('profile/edit/', views.profile_edit_view, name='profile_edit'),

    # Password Reset
    path('password_reset/', auth_views.PasswordResetView.as_view(), name='password_reset'),
    path('password_reset/done/', auth_views.PasswordResetDoneView.as_view(), name='password_reset_done'),
    path('reset/<uidb64>/<token>/', auth_views.PasswordResetConfirmView.as_view(), name='password_reset_confirm'),
    path('reset/done/', auth_views.PasswordResetCompleteView.as_view(), name='password_reset_complete'),

    # Staff Management
    path('staff/', views.staff_list_view, name='staff'),
    path('staff/add/', views.add_staff_view, name='add_staff'),
    path('staff/<int:profile_id>/edit/', views.edit_staff_view, name='edit_staff'),
    path('staff/<int:profile_id>/delete/', views.delete_staff_ajax, name='delete_staff'),

    # Staff Roles
    path('staff/roles/', views.staff_roles_view, name='staff_roles'),
    path('staff/roles/add/', views.add_staff_role, name='add_staff_role'),
    path('staff/roles/<int:role_id>/edit/', views.edit_staff_role, name='edit_staff_role'),
    path('staff/roles/<int:role_id>/delete/', views.delete_staff_role, name='delete_staff_role'),

    # Settings & Departments
    path('settings/', views.settings_dashboard_view, name='settings_dashboard'),
    path('settings/notifications/', views.notification_settings_view, name='notification_settings'),
    path('settings/permissions/', views.role_permissions_view, name='role_permissions'),
    path('settings/departments/', views.departments_view, name='departments'),
    path('settings/departments/add/', views.add_department, name='add_department'),
    path('settings/departments/<int:department_id>/edit/', views.edit_department, name='edit_department'),
    path('settings/departments/<int:department_id>/delete/', views.delete_department, name='delete_department'),
    path('settings/departments/assign-staff/', views.assign_staff_to_department, name='assign_staff_to_department'),

    # Notifications
    path('notifications/', views.notifications_view, name='notifications'),
]

