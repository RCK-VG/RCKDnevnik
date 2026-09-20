from datetime import timedelta

from django.conf import settings
from django.utils import timezone

from .models import LoginAttempt


def is_locked_out(username):
    window_start = timezone.now() - timedelta(minutes=settings.LOGIN_LOCKOUT_MINUTES)
    recent = LoginAttempt.objects.filter(username__iexact=username, created_at__gte=window_start)
    last_success = recent.filter(successful=True).order_by("-created_at").first()
    failed_qs = recent.filter(successful=False)
    if last_success:
        failed_qs = failed_qs.filter(created_at__gt=last_success.created_at)
    return failed_qs.count() >= settings.LOGIN_MAX_ATTEMPTS


def record_attempt(username, successful):
    LoginAttempt.objects.create(username=username, successful=successful)


def cleanup_old_attempts(days=7):
    cutoff = timezone.now() - timedelta(days=days)
    LoginAttempt.objects.filter(created_at__lt=cutoff).delete()
