from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from dnevnik.models import Attendance, Lesson, SchoolClass, SchoolYear, Student, Subject


def make_user(username):
    user = User.objects.create_user(username=username, password="x")
    user.profile.must_change_password = False
    user.profile.save()
    return user


class OpenLessonNoDuplicateTests(TestCase):
    def setUp(self):
        self.teacher = make_user("nastavnik1")
        school_year = SchoolYear.objects.create(name="2025./2026.", is_active=True)
        self.school_class = SchoolClass.objects.create(name="1.a", school_year=school_year)
        self.subject = Subject.objects.create(name="Matematika")
        Student.objects.create(first_name="Ana", last_name="Anić", school_class=self.school_class)
        self.client.login(username="nastavnik1", password="x")

    def _open_url_get(self):
        return (
            reverse("otvori_sat")
            + f"?razred={self.school_class.id}&predmet={self.subject.id}&datum=2026-01-15"
        )

    def _post_data(self, **extra):
        data = {
            "razred": self.school_class.id,
            "predmet": self.subject.id,
            "datum": "2026-01-15",
        }
        data.update(extra)
        return data

    def test_first_save_creates_exactly_one_lesson(self):
        self.client.post(reverse("otvori_sat"), self._post_data(tema="Uvod"))
        self.assertEqual(Lesson.objects.count(), 1)

    def test_reopening_and_saving_again_does_not_duplicate(self):
        self.client.post(reverse("otvori_sat"), self._post_data(tema="Uvod"))
        lesson = Lesson.objects.get()
        # Re-open the same slot: should redirect straight to the existing lesson.
        response = self.client.get(self._open_url_get())
        self.assertRedirects(response, reverse("sat", kwargs={"pk": lesson.id}))

        self.client.post(reverse("sat", kwargs={"pk": lesson.id}), {"tema": "Uvod - izmjena"})
        self.assertEqual(Lesson.objects.count(), 1)
        lesson.refresh_from_db()
        self.assertEqual(lesson.topic, "Uvod - izmjena")

    def test_save_populates_attendance_for_all_active_students(self):
        Student.objects.create(first_name="Ivan", last_name="Ivić", school_class=self.school_class)
        self.client.post(reverse("otvori_sat"), self._post_data(tema="Uvod"))
        lesson = Lesson.objects.get()
        self.assertEqual(Attendance.objects.filter(lesson=lesson).count(), 2)


class LessonEditPermissionTests(TestCase):
    def setUp(self):
        self.owner = make_user("nastavnik1")
        self.other_teacher = make_user("nastavnik2")
        self.admin = make_user("admin1")
        self.admin.is_staff = True
        self.admin.save()

        school_year = SchoolYear.objects.create(name="2025./2026.", is_active=True)
        school_class = SchoolClass.objects.create(name="1.a", school_year=school_year)
        subject = Subject.objects.create(name="Matematika")
        self.lesson = Lesson.objects.create(
            school_class=school_class, subject=subject, teacher=self.owner, date="2026-01-15"
        )

    def test_owner_can_open_edit_screen(self):
        self.client.login(username="nastavnik1", password="x")
        response = self.client.get(reverse("sat", kwargs={"pk": self.lesson.id}))
        self.assertEqual(response.status_code, 200)

    def test_other_teacher_can_view_but_not_edit_someone_elses_lesson(self):
        # Per spec, every teacher can VIEW every lesson; only the owner/admin
        # can edit it. The view should render read-only (no Spremi button).
        self.client.login(username="nastavnik2", password="x")
        response = self.client.get(reverse("sat", kwargs={"pk": self.lesson.id}))
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.context["can_edit"])
        self.assertNotContains(response, "Spremi")

    def test_other_teacher_cannot_post_changes_either(self):
        self.client.login(username="nastavnik2", password="x")
        response = self.client.post(
            reverse("sat", kwargs={"pk": self.lesson.id}), {"tema": "Neovlasteni pokusaj"}
        )
        self.assertEqual(response.status_code, 403)
        self.lesson.refresh_from_db()
        self.assertNotEqual(self.lesson.topic, "Neovlasteni pokusaj")

    def test_admin_can_edit_any_lesson(self):
        self.client.login(username="admin1", password="x")
        response = self.client.post(
            reverse("sat", kwargs={"pk": self.lesson.id}), {"tema": "Admin izmjena"}
        )
        self.assertEqual(response.status_code, 302)
        self.lesson.refresh_from_db()
        self.assertEqual(self.lesson.topic, "Admin izmjena")
