from django.contrib.auth.models import User
from django.test import TestCase

from dnevnik import constants, lesson_service
from dnevnik.models import AttendanceHistory, Note, NoteHistory, SchoolClass, SchoolYear, Student


class SaveAttendanceTests(TestCase):
    def setUp(self):
        self.teacher = User.objects.create_user(username="nastavnik1", password="x")
        self.homeroom = User.objects.create_user(username="razrednik1", password="x")
        school_year = SchoolYear.objects.create(name="2025./2026.", is_active=True)
        self.school_class = SchoolClass.objects.create(
            name="1.a", school_year=school_year, homeroom_teacher=self.homeroom
        )
        self.student = Student.objects.create(
            first_name="Ana", last_name="Anić", school_class=self.school_class
        )
        from dnevnik.models import Lesson, Subject

        self.lesson = Lesson.objects.create(
            school_class=self.school_class,
            subject=Subject.objects.create(name="Matematika"),
            teacher=self.teacher,
            date="2026-01-15",
        )

    def test_default_present_can_be_marked_absent(self):
        attendance = lesson_service.save_attendance(
            self.lesson, self.student, constants.ATTENDANCE_ABSENT, "", self.teacher
        )
        self.assertEqual(attendance.status, constants.ATTENDANCE_ABSENT)
        self.assertIsNone(attendance.justified)

    def test_non_homeroom_teacher_cannot_set_justified(self):
        attendance = lesson_service.save_attendance(
            self.lesson, self.student, constants.ATTENDANCE_ABSENT, "true", self.teacher
        )
        self.assertIsNone(attendance.justified)

    def test_homeroom_teacher_can_set_justified(self):
        attendance = lesson_service.save_attendance(
            self.lesson, self.student, constants.ATTENDANCE_ABSENT, "true", self.homeroom
        )
        self.assertTrue(attendance.justified)

    def test_changing_status_writes_history_of_previous_value(self):
        lesson_service.save_attendance(
            self.lesson, self.student, constants.ATTENDANCE_PRESENT, "", self.teacher
        )
        lesson_service.save_attendance(
            self.lesson, self.student, constants.ATTENDANCE_ABSENT, "", self.teacher
        )
        history = AttendanceHistory.objects.all()
        self.assertEqual(history.count(), 1)
        self.assertEqual(history.first().status, constants.ATTENDANCE_PRESENT)

    def test_saving_same_status_twice_does_not_duplicate_or_log_history(self):
        lesson_service.save_attendance(
            self.lesson, self.student, constants.ATTENDANCE_PRESENT, "", self.teacher
        )
        lesson_service.save_attendance(
            self.lesson, self.student, constants.ATTENDANCE_PRESENT, "", self.teacher
        )
        from dnevnik.models import Attendance

        self.assertEqual(Attendance.objects.filter(lesson=self.lesson, student=self.student).count(), 1)
        self.assertEqual(AttendanceHistory.objects.count(), 0)

    def test_marking_present_again_clears_justified(self):
        lesson_service.save_attendance(
            self.lesson, self.student, constants.ATTENDANCE_ABSENT, "true", self.homeroom
        )
        attendance = lesson_service.save_attendance(
            self.lesson, self.student, constants.ATTENDANCE_PRESENT, "", self.homeroom
        )
        self.assertIsNone(attendance.justified)


class SaveNoteTests(TestCase):
    def setUp(self):
        self.author = User.objects.create_user(username="nastavnik1", password="x")
        self.other = User.objects.create_user(username="nastavnik2", password="x")
        self.admin = User.objects.create_user(username="admin1", password="x", is_staff=True)
        school_year = SchoolYear.objects.create(name="2025./2026.", is_active=True)
        school_class = SchoolClass.objects.create(name="1.a", school_year=school_year)
        self.student = Student.objects.create(
            first_name="Ana", last_name="Anić", school_class=school_class
        )
        from dnevnik.models import Lesson, Subject

        self.lesson = Lesson.objects.create(
            school_class=school_class,
            subject=Subject.objects.create(name="Matematika"),
            teacher=self.author,
            date="2026-01-15",
        )

    def test_creates_note_with_author(self):
        note = lesson_service.save_note(self.lesson, self.student, "Kasnio na sat", self.author)
        self.assertEqual(note.author, self.author)
        self.assertEqual(Note.objects.count(), 1)

    def test_editing_own_note_logs_history(self):
        note = lesson_service.save_note(self.lesson, self.student, "Prvi tekst", self.author)
        lesson_service.save_note(self.lesson, self.student, "Izmijenjeni tekst", self.author)
        note.refresh_from_db()
        self.assertEqual(note.text, "Izmijenjeni tekst")
        history = NoteHistory.objects.get(note=note)
        self.assertEqual(history.text, "Prvi tekst")

    def test_other_user_cannot_edit_someone_elses_note(self):
        note = lesson_service.save_note(self.lesson, self.student, "Original", self.author)
        lesson_service.save_note(self.lesson, self.student, "Pokusaj izmjene", self.other)
        note.refresh_from_db()
        self.assertEqual(note.text, "Original")

    def test_admin_can_edit_others_note(self):
        note = lesson_service.save_note(self.lesson, self.student, "Original", self.author)
        lesson_service.save_note(self.lesson, self.student, "Admin izmjena", self.admin)
        note.refresh_from_db()
        self.assertEqual(note.text, "Admin izmjena")

    def test_clearing_text_archives_note_instead_of_deleting(self):
        note = lesson_service.save_note(self.lesson, self.student, "Tekst", self.author)
        lesson_service.save_note(self.lesson, self.student, "", self.author)
        note.refresh_from_db()
        self.assertTrue(note.is_archived)
        self.assertEqual(Note.objects.count(), 1)  # archived, not deleted

    def test_general_note_uses_null_student(self):
        note = lesson_service.save_note(self.lesson, None, "Opća napomena", self.author)
        self.assertIsNone(note.student)
