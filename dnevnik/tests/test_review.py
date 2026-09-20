from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from dnevnik import constants
from dnevnik.models import Attendance, Lesson, SchoolClass, SchoolYear, Student, Subject


def make_user(username, **kwargs):
    user = User.objects.create_user(username=username, password="x", **kwargs)
    user.profile.must_change_password = False
    user.profile.save()
    return user


class ReviewScreensTests(TestCase):
    def setUp(self):
        self.teacher = make_user("nastavnik1")
        self.other_teacher = make_user("nastavnik2")

        self.school_year = SchoolYear.objects.create(name="2025./2026.", is_active=True)
        self.school_class = SchoolClass.objects.create(
            name="1.a", school_year=self.school_year, homeroom_teacher=self.teacher
        )
        self.subject_math = Subject.objects.create(name="Matematika")
        self.subject_croatian = Subject.objects.create(name="Hrvatski jezik")
        self.student = Student.objects.create(
            first_name="Ana", last_name="Anić", school_class=self.school_class, is_ip=True
        )

        # Lesson 1: Matematika, 2026-01-10, student absent+justified
        lesson1 = Lesson.objects.create(
            school_class=self.school_class,
            subject=self.subject_math,
            teacher=self.teacher,
            date="2026-01-10",
        )
        Attendance.objects.create(
            lesson=lesson1,
            student=self.student,
            status=constants.ATTENDANCE_ABSENT,
            justified=True,
        )

        # Lesson 2: Hrvatski, 2026-02-05, student absent+unjustified
        lesson2 = Lesson.objects.create(
            school_class=self.school_class,
            subject=self.subject_croatian,
            teacher=self.teacher,
            date="2026-02-05",
        )
        Attendance.objects.create(
            lesson=lesson2,
            student=self.student,
            status=constants.ATTENDANCE_ABSENT,
            justified=False,
        )

        # Lesson 3: Matematika, 2026-03-01, student late
        lesson3 = Lesson.objects.create(
            school_class=self.school_class,
            subject=self.subject_math,
            teacher=self.teacher,
            date="2026-03-01",
        )
        Attendance.objects.create(
            lesson=lesson3, student=self.student, status=constants.ATTENDANCE_LATE
        )

    def test_any_logged_in_teacher_can_view_any_class(self):
        self.client.login(username="nastavnik2", password="x")
        response = self.client.get(reverse("razred_detalj", kwargs={"pk": self.school_class.id}))
        self.assertEqual(response.status_code, 200)

    def test_any_logged_in_teacher_can_view_any_student_profile(self):
        self.client.login(username="nastavnik2", password="x")
        response = self.client.get(reverse("ucenik_profil", kwargs={"pk": self.student.id}))
        self.assertEqual(response.status_code, 200)

    def test_class_overview_totals_all_subjects(self):
        self.client.login(username="nastavnik1", password="x")
        response = self.client.get(reverse("razred_detalj", kwargs={"pk": self.school_class.id}))
        row = response.context["rows"][0]
        self.assertEqual(row["odsutan"], 2)
        self.assertEqual(row["opravdano"], 1)
        self.assertEqual(row["neopravdano"], 1)
        self.assertEqual(row["kasni"], 1)

    def test_student_profile_summary_matches_totals(self):
        self.client.login(username="nastavnik1", password="x")
        response = self.client.get(reverse("ucenik_profil", kwargs={"pk": self.student.id}))
        summary = response.context["summary"]
        self.assertEqual(summary["odsutan"], 2)
        self.assertEqual(summary["opravdano"], 1)
        self.assertEqual(summary["neopravdano"], 1)
        self.assertEqual(summary["kasni"], 1)

    def test_filter_by_subject_restricts_summary(self):
        self.client.login(username="nastavnik1", password="x")
        response = self.client.get(
            reverse("ucenik_profil", kwargs={"pk": self.student.id}),
            {"predmet": self.subject_math.id},
        )
        summary = response.context["summary"]
        # Only lesson1 (absent+justified) and lesson3 (late) are Matematika.
        self.assertEqual(summary["odsutan"], 1)
        self.assertEqual(summary["opravdano"], 1)
        self.assertEqual(summary["neopravdano"], 0)
        self.assertEqual(summary["kasni"], 1)

    def test_filter_by_date_range_restricts_summary(self):
        self.client.login(username="nastavnik1", password="x")
        response = self.client.get(
            reverse("ucenik_profil", kwargs={"pk": self.student.id}),
            {"datum_od": "2026-02-01", "datum_do": "2026-02-28"},
        )
        summary = response.context["summary"]
        # Only lesson2 (Hrvatski, absent+unjustified) falls in February.
        self.assertEqual(summary["odsutan"], 1)
        self.assertEqual(summary["opravdano"], 0)
        self.assertEqual(summary["neopravdano"], 1)
        self.assertEqual(summary["kasni"], 0)

    def test_ip_badge_flag_visible_on_class_overview(self):
        self.client.login(username="nastavnik1", password="x")
        response = self.client.get(reverse("razred_detalj", kwargs={"pk": self.school_class.id}))
        self.assertContains(response, "IP")

    def test_class_list_shows_class(self):
        self.client.login(username="nastavnik1", password="x")
        response = self.client.get(reverse("razredi"))
        self.assertContains(response, "1.a")
