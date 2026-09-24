from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from django.contrib.auth.models import User

from . import constants
from .models import (
    Attendance,
    AttendanceHistory,
    ClassSubject,
    ExportLog,
    Lesson,
    Note,
    NoteHistory,
    Profile,
    SchoolClass,
    SchoolYear,
    Student,
    Subject,
)


class ProfileInline(admin.StackedInline):
    model = Profile
    can_delete = False
    extra = 0


class CustomUserAdmin(UserAdmin):
    inlines = [ProfileInline]
    list_display = ("username", "first_name", "last_name", "is_staff", "is_active")


admin.site.unregister(User)
admin.site.register(User, CustomUserAdmin)


@admin.register(SchoolYear)
class SchoolYearAdmin(admin.ModelAdmin):
    list_display = ("name", "is_active", "is_archived")
    list_filter = ("is_active", "is_archived")


class ClassSubjectInline(admin.TabularInline):
    model = ClassSubject
    extra = 1
    autocomplete_fields = ("subject",)


@admin.register(SchoolClass)
class SchoolClassAdmin(admin.ModelAdmin):
    list_display = ("name", "school_year", "homeroom_teacher")
    list_filter = ("school_year",)
    search_fields = ("name",)
    autocomplete_fields = ("homeroom_teacher",)
    inlines = [ClassSubjectInline]


@admin.register(Subject)
class SubjectAdmin(admin.ModelAdmin):
    list_display = ("name", "is_archived")
    search_fields = ("name",)
    list_filter = ("is_archived",)


@admin.register(Student)
class StudentAdmin(admin.ModelAdmin):
    list_display = (
        "last_name",
        "first_name",
        "school_class",
        "group_label",
        "is_ip",
        "is_pp",
        "is_archived",
    )
    list_display_links = ("last_name", "first_name")
    list_editable = ("group_label",)
    list_filter = (
        "school_class__school_year",
        "school_class",
        "group_label",
        "is_ip",
        "is_pp",
        "is_archived",
    )
    search_fields = ("first_name", "last_name")
    actions = ["postavi_grupu_a", "postavi_grupu_b", "ukloni_iz_grupe"]

    @admin.display(description=constants.IP_LABEL, boolean=True)
    def is_ip(self, obj):
        return obj.is_ip

    @admin.display(description=constants.PP_LABEL, boolean=True)
    def is_pp(self, obj):
        return obj.is_pp

    @admin.action(description="Postavi odabrane u grupu A")
    def postavi_grupu_a(self, request, queryset):
        queryset.update(group_label="A")

    @admin.action(description="Postavi odabrane u grupu B")
    def postavi_grupu_b(self, request, queryset):
        queryset.update(group_label="B")

    @admin.action(description="Ukloni odabrane iz grupe (cijeli razred)")
    def ukloni_iz_grupe(self, request, queryset):
        queryset.update(group_label="")


class AttendanceInline(admin.TabularInline):
    model = Attendance
    extra = 0


@admin.register(Lesson)
class LessonAdmin(admin.ModelAdmin):
    list_display = ("date", "period", "school_class", "subject", "teacher", "topic")
    list_filter = ("school_class__school_year", "school_class", "subject", "teacher")
    search_fields = ("topic",)
    date_hierarchy = "date"
    inlines = [AttendanceInline]


@admin.register(Attendance)
class AttendanceAdmin(admin.ModelAdmin):
    list_display = ("lesson", "student", "status", "justified", "updated_by", "updated_at")
    list_filter = ("status", "justified")
    search_fields = ("student__first_name", "student__last_name")


@admin.register(AttendanceHistory)
class AttendanceHistoryAdmin(admin.ModelAdmin):
    list_display = ("attendance", "status", "justified", "changed_by", "changed_at")
    readonly_fields = [f.name for f in AttendanceHistory._meta.fields]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False


@admin.register(Note)
class NoteAdmin(admin.ModelAdmin):
    list_display = ("lesson", "student", "author", "created_at", "is_archived")
    list_filter = ("is_archived", "lesson__subject")
    search_fields = ("text",)


@admin.register(NoteHistory)
class NoteHistoryAdmin(admin.ModelAdmin):
    list_display = ("note", "edited_by", "edited_at")
    readonly_fields = [f.name for f in NoteHistory._meta.fields]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False


@admin.register(ExportLog)
class ExportLogAdmin(admin.ModelAdmin):
    list_display = ("report_type", "user", "created_at")
    readonly_fields = [f.name for f in ExportLog._meta.fields]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False
