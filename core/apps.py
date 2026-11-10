from django.apps import AppConfig
from django.db.models.signals import post_migrate


def auto_resync_sequences(sender, **kwargs):
    if sender.name == 'core':
        from django.core.management import call_command
        try:
            call_command('resync_sequences')
        except Exception:
            pass


class CoreConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'core'

    def ready(self):
        post_migrate.connect(auto_resync_sequences, sender=self)
