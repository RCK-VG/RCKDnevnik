from django.apps import AppConfig


class DnevnikConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "dnevnik"
    verbose_name = "Mali e-Dnevnik"

    def ready(self):
        from . import signals  # noqa: F401
