import io

import openpyxl
from django.contrib.auth.models import User
from django.db import IntegrityError, transaction
from django.test import TestCase
from django.urls import reverse

from dnevnik.models import (
    ClassSubject,
    Lesson,
    SchoolClass,
    SchoolYear,
    Subject,
    theory_teacher_for,
)


def make_user(username, **kwargs):
    user = User.objects.create_user(username=username, password="x", **kwargs)
    user.profile.must_change_password = False
    user.profile.save()
    return user


class TheoryTeacherTests(TestCase):
    def setUp(self):
        self.teacher = make_user("nastavnik1")
        school_year = SchoolYear.objects.create(name="2025./2026.", is_active=True)
        self.class_a = SchoolClass.objects.create(name="1.a", school_year=school_year)
        self.class_b = SchoolClass.objects.create(name="1.b", school_year=school_year)
        self.subject = Subject.objects.create(name="Informatika")
        ClassSubject.objects.create(
            school_class=self.class_a,
            subject=self.subject,
            theory_teacher_name="Marko Marić",
            theory_teacher_email="marko@skola.hr",
        )
        self.client.login(username="nastavnik1", password="x")

    def _open(self, school_class):
        return self.client.get(
            reverse("otvori_sat"),
            {"razred": school_class.id, "predmet": self.subject.id, "datum": "2026-01-15"},
        )

    def test_lookup_is_per_class_and_subject(self):
        self.assertEqual(theory_teacher_for(self.class_a, self.subject).theory_teacher_name, "Marko Marić")
        self.assertIsNone(theory_teacher_for(self.class_b, self.subject))

    def test_lesson_screen_shows_theory_teacher_with_email(self):
        response = self._open(self.class_a)
        self.assertContains(response, "Teoriju drži")
        self.assertContains(response, "Marko Marić (marko@skola.hr)")

    def test_lesson_screen_shows_nothing_when_no_theory_teacher_set(self):
        response = self._open(self.class_b)
        self.assertNotContains(response, "Teoriju drži")

    def test_theory_teacher_also_shown_on_existing_lesson(self):
        lesson = Lesson.objects.create(
            school_class=self.class_a, subject=self.subject, teacher=self.teacher, date="2026-01-15"
        )
        response = self.client.get(reverse("sat", kwargs={"pk": lesson.id}))
        self.assertContains(response, "Marko Marić")

    def test_only_one_row_per_class_and_subject(self):
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                ClassSubject.objects.create(school_class=self.class_a, subject=self.subject)

    def test_row_without_name_or_email_counts_as_not_set(self):
        ClassSubject.objects.create(school_class=self.class_b, subject=self.subject)
        self.assertIsNone(theory_teacher_for(self.class_b, self.subject))

    def test_export_for_one_subject_names_the_theory_teacher(self):
        response = self.client.get(
            reverse("izvoz_prisutnost"),
            {"razred": self.class_a.id, "predmet": self.subject.id, "format": "csv"},
        )
        self.assertIn("Učitelj teorije: Marko Marić (marko@skola.hr)", response.content.decode("utf-8-sig"))

    def test_excel_lessons_sheet_lists_theory_teacher_per_subject(self):
        Lesson.objects.create(
            school_class=self.class_a, subject=self.subject, teacher=self.teacher, date="2026-01-15"
        )
        response = self.client.get(
            reverse("izvoz_prisutnost"), {"razred": self.class_a.id, "format": "xlsx"}
        )
        sheet = openpyxl.load_workbook(io.BytesIO(response.content))["Satovi"]
        rows = list(sheet.iter_rows(values_only=True))
        self.assertEqual(rows[2][:2], ("Predmet", "Učitelj teorije"))
        self.assertEqual(rows[3][:2], ("Informatika", "Marko Marić (marko@skola.hr)"))


class TheoryTeacherAdminTests(TestCase):
    def test_class_admin_page_has_theory_teacher_inline(self):
        admin = User.objects.create_superuser(username="admin1", password="x", email="a@a.hr")
        admin.profile.must_change_password = False
        admin.profile.save()
        school_year = SchoolYear.objects.create(name="2025./2026.", is_active=True)
        school_class = SchoolClass.objects.create(name="1.a", school_year=school_year)
        self.client.login(username="admin1", password="x")
        response = self.client.get(f"/admin/dnevnik/schoolclass/{school_class.id}/change/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Učitelj teorije")
