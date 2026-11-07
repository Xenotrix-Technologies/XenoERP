from .models import SystemNotification

def unread_notifications_count(request):
    """Context processor exposing count of unread system notifications for the current user."""
    if request.user.is_authenticated:
        count = SystemNotification.objects.filter(user=request.user, is_read=False).count()
        return {'unread_notifications_count': count}
    return {'unread_notifications_count': 0}

