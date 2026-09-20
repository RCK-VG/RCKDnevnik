from django.contrib.auth.models import User
from django.test import TestCase, override_settings
from django.urls import reverse

from dnevnik import auth_throttle


class ForcePasswordChangeTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="nastavnik1", password="Pocetna123!")
        # profile is auto-created with must_change_password=True by the signal

    def test_new_user_is_redirected_to_password_change(self):
        self.client.login(username="nastavnik1", password="Pocetna123!")
        response = self.client.get(reverse("pocetna"))
        self.assertRedirects(response, reverse("promjena_lozinke"))

    def test_password_change_screen_itself_is_reachable(self):
        self.client.login(username="nastavnik1", password="Pocetna123!")
        response = self.client.get(reverse("promjena_lozinke"))
        self.assertEqual(response.status_code, 200)

    def test_after_changing_password_user_can_reach_home(self):
        self.client.login(username="nastavnik1", password="Pocetna123!")
        response = self.client.post(
            reverse("promjena_lozinke"),
            {
                "old_password": "Pocetna123!",
                "new_password1": "NovaSigurnaLozinka9!",
                "new_password2": "NovaSigurnaLozinka9!",
            },
        )
        self.assertRedirects(response, reverse("pocetna"))
        self.user.refresh_from_db()
        self.assertFalse(self.user.profile.must_change_password)

    def test_no_redirect_loop_for_odjava_while_password_change_pending(self):
        self.client.login(username="nastavnik1", password="Pocetna123!")
        response = self.client.post(reverse("odjava"))
        self.assertNotEqual(response.status_code, 500)


@override_settings(LOGIN_MAX_ATTEMPTS=3, LOGIN_LOCKOUT_MINUTES=15)
class LoginThrottleTests(TestCase):
    def setUp(self):
        User.objects.create_user(username="nastavnik2", password="TocnaLozinka123!")

    def test_locks_out_after_max_failed_attempts(self):
        for _ in range(3):
            self.client.post(
                reverse("prijava"), {"username": "nastavnik2", "password": "kriva-lozinka"}
            )
        self.assertTrue(auth_throttle.is_locked_out("nastavnik2"))

        response = self.client.post(
            reverse("prijava"), {"username": "nastavnik2", "password": "TocnaLozinka123!"}
        )
        # Locked out even with the correct password.
        self.assertContains(response, "Previše neuspjelih pokušaja")

    def test_successful_login_resets_lockout_window(self):
        self.client.post(reverse("prijava"), {"username": "nastavnik2", "password": "TocnaLozinka123!"})
        self.assertFalse(auth_throttle.is_locked_out("nastavnik2"))
