from django.contrib.auth.models import AbstractUser
from django.db import models


class User(AbstractUser):
    """A person on a software team. What they can do depends on their role in each project (see Membership)."""

    email = models.EmailField(unique=True)

    REQUIRED_FIELDS = ['email']

    @property
    def display_name(self):
        return self.get_full_name() or self.username
