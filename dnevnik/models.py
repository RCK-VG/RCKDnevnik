from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models

from . import constants


class SchoolYear(models.Model):
    name = models.CharField(max_length=20, unique=True, help_text="npr. 2025./2026.")
    is_active = models.BooleanField(default=False)
    is_archived = models.BooleanField(default=False)

    class Meta:
        ordering = ["-name"]
        verbose_name = "Školska godina"
        verbose_name_plural = "Školske godine"

    def __str__(self):
        return self.name


class SchoolClass(models.Model):
    name = models.CharField(max_length=20, help_text="npr. 1.a")
    school_year = models.ForeignKey(
        SchoolYear, on_delete=models.PROTECT, related_name="classes"
    )
    homeroom_teacher = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="homeroom_classes",
        verbose_name="Razrednik",
    )

    class Meta:
        unique_together = ("name", "school_year")
        ordering = ["school_year", "name"]
        verbose_name = "Razred"
        verbose_name_plural = "Razredi"

    def __str__(self):
        return f"{self.name} ({self.school_year})"


class Subject(models.Model):
    name = models.CharField(max_length=100, unique=True)
    is_archived = models.BooleanField(default=False)

    class Meta:
        ordering = ["name"]
        verbose_name = "Predmet"
        verbose_name_plural = "Predmeti"

    def __str__(self):
        return self.name


class Student(models.Model):
    first_name = models.CharField(max_length=100, verbose_name="Ime")
    last_name = models.CharField(max_length=100, verbose_name="Prezime")
    school_class = models.ForeignKey(
        SchoolClass, on_delete=models.PROTECT, related_name="students"
    )
    is_ip = models.BooleanField(default=False, verbose_name=constants.IP_LABEL)
    is_pp = models.BooleanField(default=False, verbose_name=constants.PP_LABEL)
    is_archived = models.BooleanField(default=False)
    group_label = models.CharField(
        max_length=1,
        choices=constants.GROUP_CHOICES,
        blank=True,
        default="",
        verbose_name="Grupa",
        help_text="Za satove koji se dijele u grupe (npr. praktikum).",
    )

    class Meta:
        ordering = ["last_name", "first_name"]
        verbose_name = "Učenik"
        verbose_name_plural = "Učenici"

    def __str__(self):
        return f"{self.last_name} {self.first_name}"

    @property
    def full_name(self):
        return f"{self.last_name} {self.first_name}"


class Lesson(models.Model):
    school_class = models.ForeignKey(
        SchoolClass, on_delete=models.PROTECT, related_name="lessons"
    )
    subject = models.ForeignKey(Subject, on_delete=models.PROTECT, related_name="lessons")
    teacher = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="lessons"
    )
    date = models.DateField()
    topic = models.CharField(max_length=255, blank=True, verbose_name="Tema sata")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ("school_class", "subject", "date", "teacher")
        ordering = ["-date", "-created_at"]
        verbose_name = "Nastavni sat"
        verbose_name_plural = "Nastavni satovi"

    def __str__(self):
        return f"{self.school_class} - {self.subject} - {self.date}"


class Attendance(models.Model):
    STATUS_CHOICES = constants.ATTENDANCE_STATUS_CHOICES

    lesson = models.ForeignKey(
        Lesson, on_delete=models.CASCADE, related_name="attendance_records"
    )
    student = models.ForeignKey(
        Student, on_delete=models.PROTECT, related_name="attendance_records"
    )
    status = models.CharField(
        max_length=10, choices=STATUS_CHOICES, default=constants.ATTENDANCE_PRESENT
    )
    # Only meaningful when status == odsutan. None = not (yet) marked.
    justified = models.BooleanField(null=True, blank=True)
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="+"
    )
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ("lesson", "student")
        verbose_name = "Prisutnost"
        verbose_name_plural = "Prisutnost"

    def __str__(self):
        return f"{self.student} - {self.lesson} - {self.status}"

    def clean(self):
        if self.justified is not None and self.status != constants.ATTENDANCE_ABSENT:
            raise ValidationError(
                "Opravdano/neopravdano se može postaviti samo za odsutne učenike."
            )


class AttendanceHistory(models.Model):
    attendance = models.ForeignKey(Attendance, on_delete=models.CASCADE, related_name="history")
    status = models.CharField(max_length=10, choices=constants.ATTENDANCE_STATUS_CHOICES)
    justified = models.BooleanField(null=True, blank=True)
    changed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="+"
    )
    changed_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-changed_at"]
        verbose_name = "Povijest prisutnosti"
        verbose_name_plural = "Povijest prisutnosti"


class Note(models.Model):
    lesson = models.ForeignKey(Lesson, on_delete=models.CASCADE, related_name="notes")
    # null student = general note about the whole lesson
    student = models.ForeignKey(
        Student, on_delete=models.PROTECT, related_name="notes", null=True, blank=True
    )
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="notes"
    )
    text = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    is_archived = models.BooleanField(default=False)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Bilješka"
        verbose_name_plural = "Bilješke"

    def __str__(self):
        target = self.student or self.lesson.school_class
        return f"Bilješka ({target}) - {self.author}"


class NoteHistory(models.Model):
    note = models.ForeignKey(Note, on_delete=models.CASCADE, related_name="history")
    text = models.TextField()
    edited_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="+"
    )
    edited_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-edited_at"]
        verbose_name = "Povijest bilješke"
        verbose_name_plural = "Povijest bilješki"


class ExportLog(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="+"
    )
    report_type = models.CharField(max_length=50)
    filters_summary = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Zapis o izvozu"
        verbose_name_plural = "Zapisi o izvozu"


class Profile(models.Model):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="profile"
    )
    must_change_password = models.BooleanField(default=True)

    def __str__(self):
        return f"Profil ({self.user})"


class LoginAttempt(models.Model):
    username = models.CharField(max_length=150)
    successful = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
