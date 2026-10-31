from django.db.models.signals import post_delete
from django.dispatch import receiver

from .models import Screenshot


@receiver(post_delete, sender=Screenshot)
def delete_screenshot_files(sender, instance, **kwargs):
    """Remove the stored image and thumbnail along with the row."""
    for field in (instance.image, instance.thumbnail):
        if field.name:
            field.storage.delete(field.name)
