from django.contrib import admin

from .models import ActivityLog, BlockedSite, ComputerSession


class ReadOnlyAdmin(admin.ModelAdmin):
    """Logs are written only by student computers. Admins can view and, by
    hand, delete them - nothing is ever deleted automatically."""

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False


@admin.register(ActivityLog)
class ActivityLogAdmin(ReadOnlyAdmin):
    list_display = (
        "received_at",
        "client_time",
        "class_name",
        "last_name",
        "first_name",
        "computer_name",
        "event_type",
        "details",
    )
    list_filter = ("event_type", "class_name", "computer_name", "received_at")
    search_fields = ("last_name", "first_name", "computer_name", "details")
    date_hierarchy = "received_at"


@admin.register(BlockedSite)
class BlockedSiteAdmin(admin.ModelAdmin):
    list_display = ("pattern", "category", "is_active", "created_at")
    list_filter = ("is_active", "category")
    search_fields = ("pattern", "category")
    list_editable = ("is_active",)


@admin.register(ComputerSession)
class ComputerSessionAdmin(ReadOnlyAdmin):
    list_display = ("created_at", "class_name", "last_name", "first_name", "computer_name", "last_seen_at")
    list_filter = ("class_name", "computer_name")
    search_fields = ("last_name", "first_name", "computer_name")
    exclude = ("token_hash",)
