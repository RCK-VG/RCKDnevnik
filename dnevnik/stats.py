from django.db.models import Count, Q

from . import constants

EMPTY_STATS = {"odsutan": 0, "opravdano": 0, "neopravdano": 0, "kasni": 0, "prisutan": 0}


def stats_aggregate_kwargs():
    """Count() expressions to use with .values(...).annotate(...) or .aggregate(...)
    on an Attendance queryset. Count() never returns None, even for an empty
    queryset, so callers don't need to guard against missing keys."""
    return dict(
        odsutan=Count("id", filter=Q(status=constants.ATTENDANCE_ABSENT)),
        opravdano=Count("id", filter=Q(status=constants.ATTENDANCE_ABSENT, justified=True)),
        neopravdano=Count("id", filter=Q(status=constants.ATTENDANCE_ABSENT, justified=False)),
        kasni=Count("id", filter=Q(status=constants.ATTENDANCE_LATE)),
        prisutan=Count("id", filter=Q(status=constants.ATTENDANCE_PRESENT)),
    )
