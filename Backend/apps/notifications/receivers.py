from django.dispatch import receiver

from apps.releases.signals import release_event_recorded

from .services import notify_about


@receiver(release_event_recorded)
def on_release_event(sender, event, **kwargs):
    notify_about(event)
