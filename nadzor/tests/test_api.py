import json
from datetime import timedelta

from django.core.cache import cache
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from dnevnik.models import SchoolClass, SchoolYear, Student
from nadzor.models import ActivityLog, ComputerSession
from nadzor.services import hash_token

KEY = "test-kljuc-123"


@override_settings(NADZOR_API_KEY=KEY, NADZOR_TOKEN_DAYS=7, NADZOR_PRIJAVA_MAX_POKUSAJA=5)
class ApiTestCase(TestCase):
    def setUp(self):
        cache.clear()
        self.year = SchoolYear.objects.create(name="2026./2027.", is_active=True)
        old_year = SchoolYear.objects.create(name="2025./2026.", is_archived=True)
        self.klasa = SchoolClass.objects.create(name="1.C", school_year=self.year)
        self.other = SchoolClass.objects.create(name="2.F", school_year=self.year)
        self.old_class = SchoolClass.objects.create(name="1.C", school_year=old_year)
        self.colic = Student.objects.create(first_name="Luka", last_name="Čolić", school_class=self.klasa)
        self.anamarija = Student.objects.create(
            first_name="Ana Marija", last_name="Đurašin", school_class=self.klasa
        )
        Student.objects.create(first_name="Stari", last_name="Učenik", school_class=self.old_class)
        Student.objects.create(
            first_name="Arhiviran", last_name="Učenik", school_class=self.klasa, is_archived=True
        )

    def get(self, name, key=KEY):
        headers = {"HTTP_X_API_KEY": key} if key is not None else {}
        return self.client.get(reverse(name), **headers)

    def post(self, name, data, key=KEY, client=None):
        headers = {"HTTP_X_API_KEY": key} if key is not None else {}
        body = data if isinstance(data, (bytes, str)) else json.dumps(data)
        return (client or self.client).post(
            reverse(name), data=body, content_type="application/json", **headers
        )

    def login(self, **overrides):
        data = {"razred": "1.C", "ime": "Luka", "prezime": "Čolić", "racunalo": "ROBOTIKA5"}
        data.update(overrides)
        return self.post("nadzor_api_prijava", data)


class ApiKeyTests(ApiTestCase):
    def test_missing_key_is_rejected(self):
        self.assertEqual(self.get("nadzor_api_razredi", key=None).status_code, 403)

    def test_wrong_key_is_rejected(self):
        self.assertEqual(self.get("nadzor_api_razredi", key="krivi").status_code, 403)

    def test_login_and_logs_also_need_key(self):
        self.assertEqual(self.post("nadzor_api_prijava", {}, key=None).status_code, 403)
        self.assertEqual(self.post("nadzor_api_zapisi", {}, key=None).status_code, 403)

    @override_settings(NADZOR_API_KEY="")
    def test_disabled_when_no_key_configured(self):
        self.assertEqual(self.get("nadzor_api_razredi", key="").status_code, 503)

    def test_api_works_without_csrf_token(self):
        client = Client(enforce_csrf_checks=True)
        response = self.post(
            "nadzor_api_prijava",
            {"razred": "1.C", "ime": "Luka", "prezime": "Čolić", "racunalo": "PC1"},
            client=client,
        )
        self.assertEqual(response.status_code, 200)


class ClassListTests(ApiTestCase):
    def test_lists_active_year_class_names_only(self):
        response = self.get("nadzor_api_razredi")
        self.assertEqual(response.status_code, 200)
        self.assertIn("charset=utf-8", response["Content-Type"])
        self.assertEqual(response.json(), {"razredi": ["1.C", "2.F"]})
        self.assertNotIn("Čolić", response.content.decode("utf-8"))

    def test_falls_back_to_non_archived_years_when_none_active(self):
        self.year.is_active = False
        self.year.save()
        self.assertEqual(self.get("nadzor_api_razredi").json()["razredi"], ["1.C", "2.F"])


class LoginTests(ApiTestCase):
    def test_success_returns_token_and_logs_prijava(self):
        response = self.login()
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data["token"])
        self.assertEqual(data["razred"], "1.C")
        session = ComputerSession.objects.get()
        self.assertEqual(session.student, self.colic)
        self.assertEqual(session.computer_name, "ROBOTIKA5")
        log = ActivityLog.objects.get()
        self.assertEqual(log.event_type, "PRIJAVA")
        self.assertEqual((log.last_name, log.class_name, log.computer_name), ("Čolić", "1.C", "ROBOTIKA5"))

    def test_token_is_stored_only_as_hash(self):
        token = self.login().json()["token"]
        session = ComputerSession.objects.get()
        self.assertNotEqual(session.token_hash, token)
        self.assertEqual(session.token_hash, hash_token(token))

    def test_matching_ignores_case_and_extra_spaces_including_croatian_letters(self):
        response = self.login(razred=" 1.c ", ime="  LUKA ", prezime="ČOLIĆ")
        self.assertEqual(response.status_code, 200)

    def test_double_first_name_with_extra_spaces(self):
        response = self.login(ime="ana   marija", prezime="đurašin")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(ComputerSession.objects.get().student, self.anamarija)

    def test_unknown_student_is_404(self):
        response = self.login(prezime="Nepostojeći")
        self.assertEqual(response.status_code, 404)
        self.assertIn("greska", response.json())
        self.assertFalse(ComputerSession.objects.exists())

    def test_wrong_class_is_404(self):
        self.assertEqual(self.login(razred="2.F").status_code, 404)

    def test_archived_student_and_archived_year_are_not_matched(self):
        self.assertEqual(self.login(ime="Arhiviran", prezime="Učenik").status_code, 404)
        self.assertEqual(self.login(ime="Stari", prezime="Učenik").status_code, 404)

    def test_missing_fields_is_400(self):
        self.assertEqual(self.login(racunalo="").status_code, 400)
        self.assertEqual(self.login(ime="   ").status_code, 400)

    def test_invalid_json_is_400(self):
        self.assertEqual(self.post("nadzor_api_prijava", b"{nije json").status_code, 400)
        self.assertEqual(self.post("nadzor_api_prijava", "[1, 2]").status_code, 400)

    def test_two_identical_students_is_409(self):
        Student.objects.create(first_name="Luka", last_name="Čolić", school_class=self.klasa)
        self.assertEqual(self.login().status_code, 409)

    def test_too_many_failed_logins_are_throttled(self):
        for _ in range(5):
            self.assertEqual(self.login(prezime="Krivo").status_code, 404)
        self.assertEqual(self.login().status_code, 429)

    def test_control_characters_are_stripped_from_computer_name(self):
        self.login(racunalo="PC\x00\n12")
        self.assertEqual(ComputerSession.objects.get().computer_name, "PC 12")


class LogTests(ApiTestCase):
    def setUp(self):
        super().setUp()
        self.token = self.login().json()["token"]
        ActivityLog.objects.all().delete()  # drop the PRIJAVA row

    def send(self, data):
        payload = {"token": self.token, "racunalo": "ROBOTIKA5"}
        payload.update(data)
        return self.post("nadzor_api_zapisi", payload)

    def test_single_event(self):
        response = self.send({"vrsta": "INSTALIRAN PROGRAM", "detalji": "Roblox 1.0 (Roblox)"})
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json(), {"primljeno": 1})
        log = ActivityLog.objects.get()
        self.assertEqual(log.event_type, "INSTALIRAN PROGRAM")
        self.assertEqual(log.details, "Roblox 1.0 (Roblox)")
        self.assertEqual(log.student, self.colic)
        self.assertIsNotNone(log.received_at)

    def test_batch_of_events_with_client_time(self):
        response = self.send(
            {
                "zapisi": [
                    {"vrsta": "POKRENUTA APLIKACIJA", "detalji": "RobloxPlayerBeta", "vrijeme": "2026-09-29T09:15:00.000+02:00"},
                    {"vrsta": "PROMJENA POZADINE", "detalji": "C:\\Slike\\pozadina.jpg"},
                ]
            }
        )
        self.assertEqual(response.status_code, 201)
        self.assertEqual(ActivityLog.objects.count(), 2)
        started = ActivityLog.objects.get(event_type="POKRENUTA APLIKACIJA")
        self.assertEqual(started.client_time.isoformat(), "2026-09-29T07:15:00+00:00")
        self.assertIsNone(ActivityLog.objects.get(event_type="PROMJENA POZADINE").client_time)

    def test_unparseable_client_time_is_ignored(self):
        self.send({"vrsta": "X", "vrijeme": "jučer"})
        self.assertIsNone(ActivityLog.objects.get().client_time)

    def test_croatian_characters_survive(self):
        self.send({"vrsta": "NOVA IKONA/PRECAC", "detalji": "Čarobnjak šah žđ.lnk"})
        self.assertEqual(ActivityLog.objects.get().details, "Čarobnjak šah žđ.lnk")

    def test_names_are_denormalized_and_stay_after_student_changes(self):
        self.send({"vrsta": "X"})
        self.colic.last_name = "Promijenjen"
        self.colic.school_class = self.other
        self.colic.save()
        log = ActivityLog.objects.get()
        self.assertEqual((log.last_name, log.class_name), ("Čolić", "1.C"))

    def test_logs_survive_student_deletion(self):
        self.send({"vrsta": "X"})
        self.colic.delete()
        log = ActivityLog.objects.get()
        self.assertIsNone(log.student)
        self.assertEqual(log.last_name, "Čolić")

    def test_invalid_token_is_401(self):
        self.token = "krivi-token"
        self.assertEqual(self.send({"vrsta": "X"}).status_code, 401)

    def test_expired_token_is_401(self):
        ComputerSession.objects.update(created_at=timezone.now() - timedelta(days=8))
        self.assertEqual(self.send({"vrsta": "X"}).status_code, 401)

    def test_event_without_type_rejects_whole_batch(self):
        response = self.send({"zapisi": [{"vrsta": "OK"}, {"detalji": "bez vrste"}]})
        self.assertEqual(response.status_code, 400)
        self.assertFalse(ActivityLog.objects.exists())

    def test_empty_or_bad_batch_is_400(self):
        self.assertEqual(self.send({"zapisi": []}).status_code, 400)
        self.assertEqual(self.send({"zapisi": "x"}).status_code, 400)

    def test_too_many_events_is_413(self):
        self.assertEqual(self.send({"zapisi": [{"vrsta": "X"}] * 201}).status_code, 413)

    def test_long_details_are_truncated(self):
        self.send({"vrsta": "X", "detalji": "a" * 5000})
        self.assertEqual(len(ActivityLog.objects.get().details), 2000)

    def test_computer_name_falls_back_to_session(self):
        self.post("nadzor_api_zapisi", {"token": self.token, "vrsta": "X"})
        self.assertEqual(ActivityLog.objects.get().computer_name, "ROBOTIKA5")

    def test_get_not_allowed(self):
        self.assertEqual(self.get("nadzor_api_zapisi").status_code, 405)
