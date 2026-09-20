from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from dnevnik import constants
from dnevnik.models import Attendance, Lesson, SchoolClass, SchoolYear, Student, Subject


def make_user(username):
    user = User.objects.create_user(username=username, password="x")
    user.profile.must_change_password = False
    user.profile.save()
    return user


class GroupFilterTests(TestCase):
    def setUp(self):
        self.teacher = make_user("nastavnik1")
        school_year = SchoolYear.objects.create(name="2025./2026.", is_active=True)
        self.school_class = SchoolClass.objects.create(name="1.a", school_year=school_year)
        self.subject = Subject.objects.create(name="Praktikum")

        self.student_a = Student.objects.create(
            first_name="Ana", last_name="Anić", school_class=self.school_class, group_label="A"
        )
        self.student_b = Student.objects.create(
            first_name="Bruno", last_name="Barić", school_class=self.school_class, group_label="B"
        )
        self.student_none = Student.objects.create(
            first_name="Ivan", last_name="Ivić", school_class=self.school_class
        )
        self.client.login(username="nastavnik1", password="x")

    def _open_url(self, **extra):
        params = {
            "razred": self.school_class.id,
            "predmet": self.subject.id,
            "datum": "2026-01-15",
        }
        params.update(extra)
        return params

    def test_opening_with_group_shows_only_that_groups_students(self):
        response = self.client.get(reverse("otvori_sat"), self._open_url(grupa="A"))
        names = [row["student"].last_name for row in response.context["rows"]]
        self.assertEqual(names, ["Anić"])

    def test_opening_without_group_shows_whole_class(self):
        response = self.client.get(reverse("otvori_sat"), self._open_url())
        names = {row["student"].last_name for row in response.context["rows"]}
        self.assertEqual(names, {"Anić", "Barić", "Ivić"})

    def test_saving_group_a_only_creates_attendance_for_group_a(self):
        self.client.post(reverse("otvori_sat"), self._open_url(grupa="A", tema="Uvod"))
        lesson = Lesson.objects.get()
        recorded_students = set(Attendance.objects.filter(lesson=lesson).values_list("student_id", flat=True))
        self.assertEqual(recorded_students, {self.student_a.id})

    def test_saving_group_b_after_group_a_does_not_touch_group_a_attendance(self):
        # Group A: mark Ana absent.
        self.client.post(
            reverse("otvori_sat"),
            {
                **self._open_url(grupa="A"),
                f"status_{self.student_a.id}": constants.ATTENDANCE_ABSENT,
            },
        )
        lesson = Lesson.objects.get()
        ana_attendance = Attendance.objects.get(lesson=lesson, student=self.student_a)
        self.assertEqual(ana_attendance.status, constants.ATTENDANCE_ABSENT)

        # Now open and save Group B for the SAME lesson (reused, not duplicated).
        response = self.client.get(reverse("otvori_sat"), self._open_url(grupa="B"))
        self.assertRedirects(response, reverse("sat", kwargs={"pk": lesson.id}) + "?grupa=B")

        self.client.post(
            reverse("sat", kwargs={"pk": lesson.id}),
            {
                "grupa": "B",
                "tema": "Uvod",
                f"status_{self.student_b.id}": constants.ATTENDANCE_LATE,
            },
        )

        self.assertEqual(Lesson.objects.count(), 1)
        ana_attendance.refresh_from_db()
        self.assertEqual(ana_attendance.status, constants.ATTENDANCE_ABSENT)  # untouched
        bruno_attendance = Attendance.objects.get(lesson=lesson, student=self.student_b)
        self.assertEqual(bruno_attendance.status, constants.ATTENDANCE_LATE)
        # Ivan (no group) was never touched by either group-scoped save.
        self.assertFalse(Attendance.objects.filter(lesson=lesson, student=self.student_none).exists())

    def test_has_groups_true_when_any_student_has_a_group(self):
        response = self.client.get(reverse("otvori_sat"), self._open_url())
        self.assertTrue(response.context["has_groups"])

    def test_has_groups_false_for_class_without_groups(self):
        ungrouped_class = SchoolClass.objects.create(
            name="2.a", school_year=self.school_class.school_year
        )
        Student.objects.create(first_name="Pero", last_name="Perić", school_class=ungrouped_class)
        response = self.client.get(
            reverse("otvori_sat"),
            {"razred": ungrouped_class.id, "predmet": self.subject.id, "datum": "2026-01-15"},
        )
        self.assertFalse(response.context["has_groups"])


class StudentAdminGroupActionTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_superuser(username="admin1", password="x", email="a@a.com")
        self.admin.profile.must_change_password = False
        self.admin.profile.save()
        school_year = SchoolYear.objects.create(name="2025./2026.", is_active=True)
        school_class = SchoolClass.objects.create(name="1.a", school_year=school_year)
        self.s1 = Student.objects.create(first_name="Ana", last_name="Anić", school_class=school_class)
        self.s2 = Student.objects.create(first_name="Bruno", last_name="Barić", school_class=school_class)
        self.client.login(username="admin1", password="x")

    def test_bulk_action_sets_group_a(self):
        from django.contrib.admin.sites import site
        from dnevnik.models import Student

        model_admin = site._registry[Student]
        model_admin.postavi_grupu_a(None, Student.objects.filter(id__in=[self.s1.id, self.s2.id]))
        self.s1.refresh_from_db()
        self.s2.refresh_from_db()
        self.assertEqual(self.s1.group_label, "A")
        self.assertEqual(self.s2.group_label, "A")
