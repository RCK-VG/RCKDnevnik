import io
import json
from datetime import datetime

from django.contrib.auth.models import User
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from dnevnik.models import ExportLog
from nadzor.models import ActivityLog
from nadzor.services import normalize_name


def make_user(username, **kwargs):
    user = User.objects.create_user(username=username, password="x", **kwargs)
    user.profile.must_change_password = False
    user.profile.save()
    return user


def make_log(first, last, klasa, computer, event, when=None, details=""):
    log = ActivityLog.objects.create(
        first_name=first,
        last_name=last,
        class_name=klasa,
        computer_name=computer,
        event_type=event,
        details=details,
        search_name=normalize_name(f"{last} {first}"),
    )
    if when:
        ActivityLog.objects.filter(pk=log.pk).update(received_at=when)
    return log


class AccessTests(TestCase):
    def setUp(self):
        self.admin = make_user("admin1", is_staff=True)
        self.teacher = make_user("nastavnik1")
        self.allowed = make_user("nastavnik2")
        self.allowed.profile.can_view_monitoring = True
        self.allowed.profile.save()

    def test_anonymous_is_sent_to_login(self):
        response = self.client.get(reverse("nadzor_zapisi"))
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("prijava"), response["Location"])

    def test_ordinary_teacher_is_forbidden_and_has_no_menu_link(self):
        self.client.login(username="nastavnik1", password="x")
        self.assertEqual(self.client.get(reverse("nadzor_zapisi")).status_code, 403)
        self.assertNotContains(self.client.get(reverse("pocetna")), reverse("nadzor_zapisi"))

    def test_teacher_with_checkbox_can_view(self):
        self.client.login(username="nastavnik2", password="x")
        self.assertEqual(self.client.get(reverse("nadzor_zapisi")).status_code, 200)
        self.assertContains(self.client.get(reverse("pocetna")), reverse("nadzor_zapisi"))

    def test_admin_can_view(self):
        self.client.login(username="admin1", password="x")
        self.assertEqual(self.client.get(reverse("nadzor_zapisi")).status_code, 200)

    def test_checkbox_is_on_user_admin_page(self):
        superuser = User.objects.create_superuser(username="su", password="x", email="s@s.hr")
        superuser.profile.must_change_password = False
        superuser.profile.save()
        self.client.login(username="su", password="x")
        response = self.client.get(f"/admin/auth/user/{self.teacher.id}/change/")
        self.assertContains(response, "Smije vidjeti nadzor računala")


class FilterTests(TestCase):
    def setUp(self):
        make_user("admin1", is_staff=True)
        self.client.login(username="admin1", password="x")
        tz = timezone.get_current_timezone()
        make_log("Luka", "Čolić", "1.C", "ROBOTIKA5", "POKRENUTA APLIKACIJA",
                 datetime(2026, 9, 28, 10, 0, tzinfo=tz), "RobloxPlayerBeta")
        make_log("Ana", "Anić", "2.F", "CADCAM12", "INSTALIRAN PROGRAM",
                 datetime(2026, 9, 29, 23, 30, tzinfo=tz), "Steam")
        make_log("Ivan", "Ivić", "1.C", "PiH2", "PRIJAVA", datetime(2026, 9, 30, 8, 0, tzinfo=tz))

    def shown(self, **params):
        response = self.client.get(reverse("nadzor_zapisi"), params)
        return sorted(log.last_name for log in response.context["page_obj"])

    def test_no_filter_shows_all(self):
        self.assertEqual(self.shown(), ["Anić", "Ivić", "Čolić"])

    def test_filter_by_class(self):
        self.assertEqual(self.shown(razred="1.C"), ["Ivić", "Čolić"])

    def test_filter_by_computer_and_type(self):
        self.assertEqual(self.shown(racunalo="CADCAM12"), ["Anić"])
        self.assertEqual(self.shown(vrsta="PRIJAVA"), ["Ivić"])

    def test_name_search_is_case_insensitive_for_croatian_letters(self):
        self.assertEqual(self.shown(ucenik="čolić"), ["Čolić"])
        self.assertEqual(self.shown(ucenik="LUKA ČOLIĆ"), ["Čolić"])

    def test_date_range_uses_local_days(self):
        # 29.9. 23:30 local must count as the 29th, not the 30th (UTC).
        self.assertEqual(self.shown(datum_od="2026-09-29", datum_do="2026-09-29"), ["Anić"])
        self.assertEqual(self.shown(datum_od="2026-09-29"), ["Anić", "Ivić"])

    def test_csv_export_respects_filters_and_is_logged(self):
        response = self.client.get(reverse("nadzor_zapisi"), {"razred": "1.C", "izvoz": "csv"})
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.content.startswith("﻿".encode("utf-8")))
        text = response.content.decode("utf-8-sig")
        self.assertIn("Čolić;Luka;ROBOTIKA5;POKRENUTA APLIKACIJA;RobloxPlayerBeta", text)
        self.assertNotIn("Anić", text)
        log = ExportLog.objects.get()
        self.assertEqual(log.report_type, "nadzor_racunala")
        self.assertIn("razred=1.C", log.filters_summary)


class ClientConfigCommandTests(TestCase):
    @override_settings(NADZOR_API_KEY="tajni-kljuc")
    def test_prints_config_with_key_from_settings(self):
        out = io.StringIO()
        call_command("nadzor_klijent_config", "--url", "https://192.168.1.50:8443/", stdout=out)
        config = json.loads(out.getvalue())
        self.assertEqual(config["serverUrl"], "https://192.168.1.50:8443")
        self.assertEqual(config["apiKey"], "tajni-kljuc")

    @override_settings(NADZOR_API_KEY="")
    def test_refuses_without_key(self):
        with self.assertRaises(CommandError):
            call_command("nadzor_klijent_config", "--url", "https://x:8443")
