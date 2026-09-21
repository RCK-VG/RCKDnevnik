import datetime

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from dnevnik.models import Lesson, SchoolClass, SchoolYear, Subject


def make_user(username, **kwargs):
    user = User.objects.create_user(username=username, password="x", **kwargs)
    user.profile.must_change_password = False
    user.profile.save()
    return user


class AllLessonsListTests(TestCase):
    def setUp(self):
        self.teacher1 = make_user("nastavnik1")
        self.teacher2 = make_user("nastavnik2")
        school_year = SchoolYear.objects.create(name="2025./2026.", is_active=True)
        self.school_class = SchoolClass.objects.create(name="1.a", school_year=school_year)
        self.other_class = SchoolClass.objects.create(name="1.b", school_year=school_year)
        self.subject = Subject.objects.create(name="Matematika")
        self.other_subject = Subject.objects.create(name="Hrvatski jezik")

        self.lesson1 = Lesson.objects.create(
            school_class=self.school_class,
            subject=self.subject,
            teacher=self.teacher1,
            date="2026-01-10",
            topic="Razlomci",
        )
        self.lesson2 = Lesson.objects.create(
            school_class=self.other_class,
            subject=self.other_subject,
            teacher=self.teacher2,
            date="2026-02-05",
            topic="Padezi",
        )

    def test_any_teacher_sees_lessons_by_other_teachers(self):
        self.client.login(username="nastavnik1", password="x")
        response = self.client.get(reverse("svi_satovi"))
        self.assertEqual(response.status_code, 200)
        lessons_shown = list(response.context["page_obj"])
        self.assertIn(self.lesson2, lessons_shown)  # not their own lesson

    def test_filter_by_teacher(self):
        self.client.login(username="nastavnik1", password="x")
        response = self.client.get(reverse("svi_satovi"), {"nastavnik": self.teacher2.id})
        lessons_shown = list(response.context["page_obj"])
        self.assertEqual(lessons_shown, [self.lesson2])

    def test_filter_by_razred(self):
        self.client.login(username="nastavnik1", password="x")
        response = self.client.get(reverse("svi_satovi"), {"razred": self.school_class.id})
        lessons_shown = list(response.context["page_obj"])
        self.assertEqual(lessons_shown, [self.lesson1])

    def test_filter_by_date_range(self):
        self.client.login(username="nastavnik1", password="x")
        response = self.client.get(
            reverse("svi_satovi"), {"datum_od": "2026-02-01", "datum_do": "2026-02-28"}
        )
        lessons_shown = list(response.context["page_obj"])
        self.assertEqual(lessons_shown, [self.lesson2])

    def test_pagination_second_page(self):
        start = datetime.date(2026, 3, 1)
        for i in range(60):
            Lesson.objects.create(
                school_class=self.school_class,
                subject=self.subject,
                teacher=self.teacher1,
                date=start + datetime.timedelta(days=i),
                topic=f"Extra {i}",
            )
        self.client.login(username="nastavnik1", password="x")
        response = self.client.get(reverse("svi_satovi"), {"page": 2})
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context["page_obj"].has_previous())
