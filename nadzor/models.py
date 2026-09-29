from datetime import timedelta

from django.conf import settings
from django.db import models
from django.utils import timezone


class ComputerSession(models.Model):
    """One student login on one computer. The client gets a random token;
    only its SHA-256 hash is stored.

    Identity is just "class + first + last name" typed by the student, so it
    is a record of who SAID they sat there - not proof of identity."""

    token_hash = models.CharField(max_length=64, unique=True)
    student = models.ForeignKey(
        "dnevnik.Student",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="computer_sessions",
    )
    # Snapshot at login time, copied into every log of this session, so old
    # logs stay accurate if the student is later renamed or moved.
    first_name = models.CharField(max_length=100)
    last_name = models.CharField(max_length=100)
    class_name = models.CharField(max_length=20)
    computer_name = models.CharField(max_length=64)
    created_at = models.DateTimeField(auto_now_add=True)
    last_seen_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Prijava na računalo"
        verbose_name_plural = "Prijave na računala"

    def __str__(self):
        return f"{self.last_name} {self.first_name} ({self.class_name}) @ {self.computer_name}"

    def is_valid(self, now=None):
        now = now or timezone.now()
        return now < self.created_at + timedelta(days=settings.NADZOR_TOKEN_DAYS)


class ActivityLog(models.Model):
    """One event reported by a student computer.

    Retention: on purpose there is NO automatic deletion - logs are kept
    until an admin deletes them by hand (Django admin). If a retention period
    is ever wanted, add a management command that deletes
    ActivityLog.objects.filter(received_at__lt=timezone.now() - <period>)
    and schedule it next to the daily backup in docker-compose.yml."""

    session = models.ForeignKey(
        ComputerSession,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="logs",
    )
    student = models.ForeignKey(
        "dnevnik.Student",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="activity_logs",
    )
    first_name = models.CharField(max_length=100, verbose_name="Ime")
    last_name = models.CharField(max_length=100, verbose_name="Prezime")
    class_name = models.CharField(max_length=20, db_index=True, verbose_name="Razred")
    computer_name = models.CharField(max_length=64, db_index=True, verbose_name="Računalo")
    event_type = models.CharField(max_length=100, db_index=True, verbose_name="Vrsta")
    details = models.TextField(blank=True, verbose_name="Detalji")
    received_at = models.DateTimeField(
        auto_now_add=True, db_index=True, verbose_name="Vrijeme (server)"
    )
    # Reported by the computer; differs from received_at when the event
    # waited in the offline queue. Not trustworthy (PC clock), informational.
    client_time = models.DateTimeField(null=True, blank=True, verbose_name="Vrijeme (računalo)")
    # Casefolded "prezime ime": SQLite only compares ASCII letters
    # case-insensitively, so searching "čolić" must use this column.
    search_name = models.CharField(max_length=210, db_index=True, editable=False)

    class Meta:
        ordering = ["-received_at", "-id"]
        verbose_name = "Zapis aktivnosti"
        verbose_name_plural = "Zapisi aktivnosti"

    def __str__(self):
        return f"{self.received_at:%d.%m.%Y. %H:%M} {self.computer_name} {self.event_type}"
