import logging
from datetime import timedelta
from django.utils import timezone
from django.core.mail import send_mail
from django.conf import settings

logger = logging.getLogger(__name__)

NOTIFICATION_EMAIL = "xenotrixtech@gmail.com"


def check_and_send_event_notifications(event=None):
    """
    Check events and send 10-hour and 1-hour email notifications to xenotrixtech@gmail.com.
    If event is passed, check that specific event; otherwise check all upcoming events.
    """
    from crm.models import Event

    now = timezone.now()

    if event:
        events_to_check = [event]
    else:
        # Check all upcoming events within window
        events_to_check = Event.objects.filter(
            start_time__gte=now - timedelta(hours=1),
            start_time__lte=now + timedelta(hours=12)
        )

    for ev in events_to_check:
        if not ev.start_time:
            continue

        time_until_start = ev.start_time - now
        hours_until_start = time_until_start.total_seconds() / 3600.0

        # 10 Hours Notification (triggers if event is 10 hours away or created within 10h)
        if hours_until_start <= 10.0 and hours_until_start > 0 and not ev.notified_10h:
            send_event_email_reminder(ev, time_label="10 Hours")
            ev.notified_10h = True
            ev.save(update_fields=['notified_10h'])

        # 1 Hour Notification (triggers if event is 1 hour away or created within 1h)
        if hours_until_start <= 1.0 and hours_until_start > -0.5 and not ev.notified_1h:
            send_event_email_reminder(ev, time_label="1 Hour")
            ev.notified_1h = True
            ev.save(update_fields=['notified_1h'])


def send_event_email_reminder(event, time_label):
    """Send email notification to xenotrixtech@gmail.com about an event."""
    start_str = event.start_time.strftime('%B %d, %Y at %I:%M %p') if event.start_time else 'Scheduled Time'
    end_str = event.end_time.strftime('%I:%M %p') if event.end_time else ''
    owner_name = (event.owner.get_full_name() or event.owner.username) if event.owner else 'Unknown'
    org_name = event.organization.name if event.organization else 'XenoCRM'

    subject = f"⏰ [{time_label} Reminder] Calendar Event: {event.title}"

    body = f"""Hello,

This is an automated reminder that a calendar event is starting in {time_label}:

📌 Event Title: {event.title}
📅 Date & Time: {start_str} {'- ' + end_str if end_str else ''}
👤 Organizer: {owner_name}
🏢 Organization: {org_name}
📝 Description: {event.description or 'No description provided.'}

--
XenoCRM Calendar Notification System
"""

    html_message = f"""
    <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto; border: 1px solid #e2e8f0; border-radius: 12px; padding: 24px; background-color: #ffffff;">
        <div style="background-color: #2563eb; color: #ffffff; padding: 16px 20px; border-radius: 8px 8px 0 0; text-align: center;">
            <h2 style="margin: 0; font-size: 20px; color: #ffffff;">⏰ Event Reminder ({time_label} Before)</h2>
        </div>
        <div style="padding: 20px; color: #1e293b; line-height: 1.6;">
            <p style="font-size: 18px; font-weight: bold; margin-top: 0; color: #0f172a;">{event.title}</p>
            <table style="width: 100%; border-collapse: collapse; margin-bottom: 20px;">
                <tr>
                    <td style="padding: 8px 0; color: #64748b; font-weight: bold; width: 140px;">📅 Date & Time:</td>
                    <td style="padding: 8px 0; color: #0f172a; font-weight: bold;">{start_str} {('- ' + end_str) if end_str else ''}</td>
                </tr>
                <tr>
                    <td style="padding: 8px 0; color: #64748b; font-weight: bold;">👤 Organizer:</td>
                    <td style="padding: 8px 0; color: #0f172a;">{owner_name}</td>
                </tr>
                <tr>
                    <td style="padding: 8px 0; color: #64748b; font-weight: bold;">🏢 Organization:</td>
                    <td style="padding: 8px 0; color: #0f172a;">{org_name}</td>
                </tr>
            </table>
            {"<div style='background-color: #f8fafc; border-left: 4px solid #2563eb; padding: 12px 16px; border-radius: 4px; margin-bottom: 20px;'><p style='margin: 0; color: #475569; font-size: 14px;'><strong>Description:</strong> " + event.description + "</p></div>" if event.description else ""}
        </div>
        <div style="border-top: 1px solid #e2e8f0; padding-top: 16px; text-align: center; color: #94a3b8; font-size: 12px;">
            Sent automatically to {NOTIFICATION_EMAIL} by XenoCRM Calendar System.
        </div>
    </div>
    """

    try:
        from_email = getattr(settings, 'DEFAULT_FROM_EMAIL', 'XenoCRM Notifications <xenotrixtech@gmail.com>')
        send_mail(
            subject=subject,
            message=body,
            from_email=from_email,
            recipient_list=[NOTIFICATION_EMAIL],
            html_message=html_message,
            fail_silently=False
        )
        logger.info(f"Sent {time_label} email reminder for event '{event.title}' to {NOTIFICATION_EMAIL}")
        print(f"[Email Notification Sent] {time_label} reminder for event '{event.title}' sent to {NOTIFICATION_EMAIL}")
    except Exception as e:
        logger.error(f"Failed to send {time_label} email reminder for event '{event.title}': {e}")
        print(f"[Email Notification Error] Failed to send {time_label} reminder for '{event.title}': {e}")
