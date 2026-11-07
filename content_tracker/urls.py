from django.urls import path
from . import views

urlpatterns = [
    # Content Tracker
    path('settings/content-tracker/', views.content_tracker_view, name='content_tracker'),
    path('settings/content-tracker/add/', views.add_content_item, name='add_content_item'),
    path('settings/content-tracker/<int:item_id>/edit/', views.edit_content_item, name='edit_content_item'),
    path('settings/content-tracker/<int:item_id>/delete/', views.delete_content_item, name='delete_content_item'),
    path('settings/content-tracker/<int:item_id>/duplicate/', views.duplicate_content_item, name='duplicate_content_item'),
    path('settings/content-tracker/<int:item_id>/mark-complete/', views.mark_content_complete, name='mark_content_complete'),
    path('settings/content-tracker/<int:item_id>/update-status/', views.update_content_item_status, name='update_content_item_status'),
    path('settings/content-tracker/bulk-delete/', views.bulk_delete_content_items, name='bulk_delete_content_items'),
    path('settings/content-tracker/import/', views.import_content_items, name='import_content_items'),

    # Editor Dashboard & Post Management
    path('editor-dashboard/', views.editor_dashboard_view, name='editor_dashboard'),
    path('post-management/', views.post_management_view, name='post_management'),
    path('post-management/update/', views.post_management_update, name='post_management_update'),

    # Content Settings (Dropdown Options)
    path('settings/content-settings/', views.content_settings_view, name='content_settings'),
    path('settings/content-settings/add/', views.add_content_option, name='add_content_option'),
    path('settings/content-settings/<int:option_id>/edit/', views.edit_content_option, name='edit_content_option'),
    path('settings/content-settings/<int:option_id>/delete/', views.delete_content_option, name='delete_content_option'),
]

