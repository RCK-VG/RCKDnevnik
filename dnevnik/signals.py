from django.conf import settings
from django.db.backends.signals import connection_created
from django.db.models.signals import post_save
from django.dispatch import receiver

from .collation import compare as _cro_compare
from .models import Profile


@receiver(post_save, sender=settings.AUTH_USER_MODEL)
def create_profile_for_new_user(sender, instance, created, **kwargs):
    if created:
        Profile.objects.get_or_create(user=instance)


@receiver(connection_created)
def register_croatian_collation(sender, connection, **kwargs):
    """Make the "cro" collation (Croatian alphabet) available on every SQLite
    connection, so columns declared with db_collation="cro" sort correctly."""
    if connection.vendor == "sqlite":
        connection.connection.create_collation("cro", _cro_compare)
