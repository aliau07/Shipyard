from django.apps import AppConfig


class ReleasesConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.releases'

    def ready(self):
        from . import receivers  # noqa: F401
