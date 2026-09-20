from django.contrib.auth.models import User
from django.test import TestCase

from dnevnik.models import Lesson, Note, SchoolClass, SchoolYear, Student, Subject
from dnevnik.permissions import can_edit_lesson, can_edit_note, can_set_justified, is_admin


class PermissionHelperTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user(username="admin1", password="x", is_staff=True)
        self.teacher_a = User.objects.create_user(username="nastavnik_a", password="x")
        self.teacher_b = User.objects.create_user(username="nastavnik_b", password="x")

        self.school_year = SchoolYear.objects.create(name="2025./2026.", is_active=True)
        self.school_class = SchoolClass.objects.create(
            name="1.a", school_year=self.school_year, homeroom_teacher=self.teacher_a
        )
        self.subject = Subject.objects.create(name="Matematika")
        self.student = Student.objects.create(
            first_name="Ana", last_name="Anić", school_class=self.school_class
        )
        self.lesson = Lesson.objects.create(
            school_class=self.school_class,
            subject=self.subject,
            teacher=self.teacher_b,
            date="2026-01-15",
        )
        self.note = Note.objects.create(lesson=self.lesson, author=self.teacher_b, text="Bilješka")

    def test_is_admin(self):
        self.assertTrue(is_admin(self.admin))
        self.assertFalse(is_admin(self.teacher_a))

    def test_teacher_can_edit_own_lesson_only(self):
        self.assertTrue(can_edit_lesson(self.teacher_b, self.lesson))
        self.assertFalse(can_edit_lesson(self.teacher_a, self.lesson))

    def test_admin_can_edit_any_lesson(self):
        self.assertTrue(can_edit_lesson(self.admin, self.lesson))

    def test_teacher_can_edit_own_note_only(self):
        self.assertTrue(can_edit_note(self.teacher_b, self.note))
        self.assertFalse(can_edit_note(self.teacher_a, self.note))

    def test_only_homeroom_teacher_or_admin_can_set_justified(self):
        # teacher_a is the homeroom teacher of 1.a
        self.assertTrue(can_set_justified(self.teacher_a, self.school_class))
        self.assertTrue(can_set_justified(self.admin, self.school_class))
        # teacher_b merely teaches a lesson there, but is not the homeroom teacher
        self.assertFalse(can_set_justified(self.teacher_b, self.school_class))
