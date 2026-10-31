"""Events other apps react to (notifications) without the releases app knowing about them."""
from django.dispatch import Signal

release_event_recorded = Signal()
