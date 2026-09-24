import io

import openpyxl
from django.contrib.auth.models import User
from django.db import IntegrityError, transaction
from django.test import TestCase
from django.urls import reverse

from dnevnik import constants
from dnevnik.models import Attendance, Lesson, SchoolClass, SchoolYear, Student, Subject


def make_user(username):
    user = User.objects.create_user(username=username, password="x")
    user.profile.must_change_password = False
    user.profile.save()
    return user


class BlockLessonTests(TestCase):
    """A block of several hours is entered as one lesson per school hour, so
    a student can be present for hour 1-2 and absent for hour 3."""

    def setUp(self):
        self.teacher = make_user("nastavnik1")
        school_year = SchoolYear.objects.create(name="2025./2026.", is_active=True)
        self.school_class = SchoolClass.objects.create(name="1.a", school_year=school_year)
        self.subject = Subject.objects.create(name="Praktikum")
        self.ana = Student.objects.create(
            first_name="Ana", last_name="Anić", school_class=self.school_class
        )
        self.ivan = Student.objects.create(
            first_name="Ivan", last_name="Ivić", school_class=self.school_class
        )
        self.client.login(username="nastavnik1", password="x")

    def _params(self, period, **extra):
        params = {
            "razred": self.school_class.id,
            "predmet": self.subject.id,
            "datum": "2026-01-15",
            "sat": period,
        }
        params.update(extra)
        return params

    def _save_hour(self, period, **statuses):
        data = self._params(period)
        for student, status in statuses.items():
            data[f"status_{getattr(self, student).id}"] = status
        return self.client.post(reverse("otvori_sat"), data)

    def test_each_hour_of_a_block_is_a_separate_lesson(self):
        self._save_hour(1)
        self._save_hour(2)
        self._save_hour(3)
        self.assertEqual(Lesson.objects.count(), 3)
        self.assertEqual(
            sorted(Lesson.objects.values_list("period", flat=True)), [1, 2, 3]
        )

    def test_student_can_be_absent_only_for_one_hour_of_the_block(self):
        self._save_hour(1, ana=constants.ATTENDANCE_PRESENT)
        self._save_hour(2, ana=constants.ATTENDANCE_PRESENT)
        self._save_hour(3, ana=constants.ATTENDANCE_ABSENT)
        statuses = {
            a.lesson.period: a.status
            for a in Attendance.objects.filter(student=self.ana).select_related("lesson")
        }
        self.assertEqual(
            statuses,
            {
                1: constants.ATTENDANCE_PRESENT,
                2: constants.ATTENDANCE_PRESENT,
                3: constants.ATTENDANCE_ABSENT,
            },
        )

    def test_reopening_the_same_hour_reuses_the_lesson(self):
        self._save_hour(2)
        lesson = Lesson.objects.get()
        response = self.client.get(reverse("otvori_sat"), self._params(2))
        self.assertRedirects(response, reverse("sat", kwargs={"pk": lesson.id}))
        self._save_hour(2)
        self.assertEqual(Lesson.objects.count(), 1)

    def test_model_allows_different_periods_but_not_the_same_one_twice(self):
        Lesson.objects.create(
            school_class=self.school_class,
            subject=self.subject,
            teacher=self.teacher,
            date="2026-01-15",
            period=1,
        )
        Lesson.objects.create(
            school_class=self.school_class,
            subject=self.subject,
            teacher=self.teacher,
            date="2026-01-15",
            period=2,
        )
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Lesson.objects.create(
                    school_class=self.school_class,
                    subject=self.subject,
                    teacher=self.teacher,
                    date="2026-01-15",
                    period=2,
                )

    def test_period_defaults_to_first_hour_when_not_given(self):
        data = self._params(1)
        del data["sat"]
        self.client.post(reverse("otvori_sat"), data)
        self.assertEqual(Lesson.objects.get().period, 1)


class CopyAttendanceTests(TestCase):
    def setUp(self):
        self.teacher = make_user("nastavnik1")
        self.other_teacher = make_user("nastavnik2")
        school_year = SchoolYear.objects.create(name="2025./2026.", is_active=True)
        self.school_class = SchoolClass.objects.create(name="1.a", school_year=school_year)
        self.subject = Subject.objects.create(name="Praktikum")
        self.ana = Student.objects.create(
            first_name="Ana", last_name="Anić", school_class=self.school_class
        )
        self.ivan = Student.objects.create(
            first_name="Ivan", last_name="Ivić", school_class=self.school_class
        )
        self.hour1 = Lesson.objects.create(
            school_class=self.school_class,
            subject=self.subject,
            teacher=self.teacher,
            date="2026-01-15",
            period=1,
        )
        Attendance.objects.create(
            lesson=self.hour1, student=self.ana, status=constants.ATTENDANCE_ABSENT
        )
        Attendance.objects.create(
            lesson=self.hour1, student=self.ivan, status=constants.ATTENDANCE_LATE
        )
        self.client.login(username="nastavnik1", password="x")

    def _open_hour2(self, **extra):
        params = {
            "razred": self.school_class.id,
            "predmet": self.subject.id,
            "datum": "2026-01-15",
            "sat": 2,
        }
        params.update(extra)
        return self.client.get(reverse("otvori_sat"), params)

    def _statuses(self, response):
        return {row["student"].id: row["status"] for row in response.context["rows"]}

    def test_second_hour_offers_copy_from_previous_hour(self):
        response = self._open_hour2()
        self.assertEqual(response.context["previous_lesson"], self.hour1)

    def test_first_hour_has_nothing_to_copy_from(self):
        response = self.client.get(
            reverse("otvori_sat"),
            {
                "razred": self.school_class.id,
                "predmet": self.subject.id,
                "datum": "2026-01-16",
                "sat": 1,
            },
        )
        self.assertIsNone(response.context["previous_lesson"])

    def test_without_copy_everyone_starts_present(self):
        statuses = self._statuses(self._open_hour2())
        self.assertEqual(set(statuses.values()), {constants.ATTENDANCE_PRESENT})

    def test_copy_prefills_statuses_from_previous_hour(self):
        statuses = self._statuses(self._open_hour2(kopiraj=self.hour1.id))
        self.assertEqual(statuses[self.ana.id], constants.ATTENDANCE_ABSENT)
        self.assertEqual(statuses[self.ivan.id], constants.ATTENDANCE_LATE)

    def test_copy_saves_nothing_until_the_teacher_clicks_save(self):
        self._open_hour2(kopiraj=self.hour1.id)
        self.assertEqual(Lesson.objects.filter(period=2).count(), 0)
        self.assertEqual(Attendance.objects.count(), 2)  # only hour 1's rows

    def test_copied_statuses_can_be_adjusted_before_saving(self):
        self.client.post(
            reverse("otvori_sat"),
            {
                "razred": self.school_class.id,
                "predmet": self.subject.id,
                "datum": "2026-01-15",
                "sat": 2,
                f"status_{self.ana.id}": constants.ATTENDANCE_PRESENT,  # came back
                f"status_{self.ivan.id}": constants.ATTENDANCE_LATE,
            },
        )
        hour2 = Lesson.objects.get(period=2)
        ana_h2 = Attendance.objects.get(lesson=hour2, student=self.ana)
        self.assertEqual(ana_h2.status, constants.ATTENDANCE_PRESENT)
        # hour 1 is untouched
        self.assertEqual(
            Attendance.objects.get(lesson=self.hour1, student=self.ana).status,
            constants.ATTENDANCE_ABSENT,
        )

    def test_cannot_copy_from_a_lesson_on_another_day(self):
        other_day = Lesson.objects.create(
            school_class=self.school_class,
            subject=self.subject,
            teacher=self.teacher,
            date="2026-01-14",
            period=1,
        )
        Attendance.objects.create(
            lesson=other_day, student=self.ana, status=constants.ATTENDANCE_ABSENT
        )
        statuses = self._statuses(self._open_hour2(kopiraj=other_day.id))
        self.assertEqual(set(statuses.values()), {constants.ATTENDANCE_PRESENT})

    def test_other_teachers_earlier_hour_is_not_offered_as_copy_source(self):
        self.client.logout()
        self.client.login(username="nastavnik2", password="x")
        response = self._open_hour2()
        self.assertIsNone(response.context["previous_lesson"])


class BlockExportTests(TestCase):
    def test_matrix_has_one_column_per_hour_with_its_own_status(self):
        teacher = make_user("nastavnik1")
        school_year = SchoolYear.objects.create(name="2025./2026.", is_active=True)
        school_class = SchoolClass.objects.create(name="1.a", school_year=school_year)
        subject = Subject.objects.create(name="Praktikum")
        ana = Student.objects.create(first_name="Ana", last_name="Anić", school_class=school_class)
        for period, status in [
            (1, constants.ATTENDANCE_PRESENT),
            (2, constants.ATTENDANCE_PRESENT),
            (3, constants.ATTENDANCE_ABSENT),
        ]:
            lesson = Lesson.objects.create(
                school_class=school_class,
                subject=subject,
                teacher=teacher,
                date="2026-01-15",
                period=period,
            )
            Attendance.objects.create(lesson=lesson, student=ana, status=status)

        self.client.login(username="nastavnik1", password="x")
        response = self.client.get(
            reverse("izvoz_prisutnost"),
            {"razred": school_class.id, "predmet": subject.id, "format": "xlsx"},
        )
        sheet = openpyxl.load_workbook(io.BytesIO(response.content))["Prisutnost"]
        rows = list(sheet.iter_rows(values_only=True))
        header, ana_row = rows[4], rows[5]
        self.assertEqual(
            [h.split("\n")[1] for h in header[1:]], ["1. sat", "2. sat", "3. sat"]
        )
        self.assertEqual(list(ana_row[1:]), ["Prisutan", "Prisutan", "Odsutan"])
