from django.contrib.auth.models import User
from django.db import IntegrityError, transaction
from django.test import TestCase

from dnevnik.models import Attendance, Lesson, SchoolClass, SchoolYear, Student, Subject


class LessonUniquenessTests(TestCase):
    def setUp(self):
        self.teacher = User.objects.create_user(username="nastavnik1", password="x")
        self.school_year = SchoolYear.objects.create(name="2025./2026.", is_active=True)
        self.school_class = SchoolClass.objects.create(name="1.a", school_year=self.school_year)
        self.subject = Subject.objects.create(name="Matematika")

    def test_same_class_subject_date_teacher_cannot_repeat(self):
        Lesson.objects.create(
            school_class=self.school_class,
            subject=self.subject,
            teacher=self.teacher,
            date="2026-01-15",
        )
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Lesson.objects.create(
                    school_class=self.school_class,
                    subject=self.subject,
                    teacher=self.teacher,
                    date="2026-01-15",
                )

    def test_different_teacher_same_slot_is_allowed(self):
        other_teacher = User.objects.create_user(username="nastavnik2", password="x")
        Lesson.objects.create(
            school_class=self.school_class,
            subject=self.subject,
            teacher=self.teacher,
            date="2026-01-15",
        )
        # Two teachers covering the same class/subject/date (e.g. a substitution)
        # are two distinct lessons, not a duplicate.
        Lesson.objects.create(
            school_class=self.school_class,
            subject=self.subject,
            teacher=other_teacher,
            date="2026-01-15",
        )
        self.assertEqual(Lesson.objects.count(), 2)


class AttendanceUniquenessTests(TestCase):
    def setUp(self):
        teacher = User.objects.create_user(username="nastavnik1", password="x")
        school_year = SchoolYear.objects.create(name="2025./2026.", is_active=True)
        school_class = SchoolClass.objects.create(name="1.a", school_year=school_year)
        subject = Subject.objects.create(name="Matematika")
        self.student = Student.objects.create(
            first_name="Ana", last_name="Anić", school_class=school_class
        )
        self.lesson = Lesson.objects.create(
            school_class=school_class, subject=subject, teacher=teacher, date="2026-01-15"
        )

    def test_one_attendance_record_per_student_per_lesson(self):
        Attendance.objects.create(lesson=self.lesson, student=self.student)
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Attendance.objects.create(lesson=self.lesson, student=self.student)
