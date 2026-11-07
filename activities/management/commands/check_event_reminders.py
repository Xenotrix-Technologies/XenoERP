from django.core.management.base import BaseCommand
from crm.event_notifications import check_and_send_event_notifications


class Command(BaseCommand):
    help = 'Check upcoming calendar events and send 10h and 1h email reminders to xenotrixtech@gmail.com'

    def handle(self, *args, **options):
        self.stdout.write('Checking upcoming calendar events for 10h and 1h email reminders...')
        check_and_send_event_notifications()
        self.stdout.write(self.style.SUCCESS('Successfully processed calendar event reminders.'))
