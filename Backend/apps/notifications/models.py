from django.conf import settings
from django.db import models


class Notification(models.Model):
    recipient  = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='+')
    release    = models.ForeignKey('releases.Release', on_delete=models.CASCADE, related_name='+')
    event      = models.ForeignKey('releases.ReleaseEvent', null=True, blank=True, on_delete=models.CASCADE,
                                   related_name='+')
    message    = models.CharField(max_length=300)
    created_at = models.DateTimeField(auto_now_add=True)
    read_at    = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-created_at', '-pk']
        indexes = [models.Index(fields=['recipient', 'read_at'])]

    def __str__(self):
        return f'To {self.recipient}: {self.message}'
