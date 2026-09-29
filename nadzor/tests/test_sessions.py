from datetime import timedelta

from django.contrib.auth.models import User
from django.urls import reverse
from django.utils import timezone

from nadzor.models import ActivityLog, ComputerSession

from .test_api import ApiTestCase


class DuplicateLoginTests(ApiTestCase):
    def test_second_computer_is_rejected_while_first_is_active(self):
        self.assertEqual(self.login(racunalo="PC1").status_code, 200)
        response = self.login(racunalo="PC2")
        self.assertEqual(response.status_code, 409)
        data = response.json()
        self.assertEqual(data["kod"], "vec_prijavljen")
        self.assertEqual(data["racunalo"], "PC1")
        self.assertIn("PC1", data["greska"])
        self.assertEqual(ComputerSession.objects.count(), 1)

    def test_same_computer_again_replaces_the_old_session(self):
        self.login(racunalo="PC1")
        self.assertEqual(self.login(racunalo="pc1").status_code, 200)
        old, new = ComputerSession.objects.order_by("created_at")
        self.assertIsNotNone(old.ended_at)
        self.assertIsNone(new.ended_at)
        self.assertTrue(ActivityLog.objects.filter(session=old, event_type="ODJAVA").exists())

    def test_after_logoff_another_computer_is_allowed(self):
        token = self.login(racunalo="PC1").json()["token"]
        self.assertEqual(self.post("nadzor_api_odjava", {"token": token}).status_code, 200)
        self.assertEqual(self.login(racunalo="PC2").status_code, 200)

    def test_inactive_session_does_not_block(self):
        self.login(racunalo="PC1")
        ComputerSession.objects.update(last_seen_at=timezone.now() - timedelta(minutes=6))
        self.assertEqual(self.login(racunalo="PC2").status_code, 200)

    def test_other_students_are_not_affected(self):
        self.login(racunalo="PC1")
        response = self.login(racunalo="PC2", ime="Ana Marija", prezime="Đurašin")
        self.assertEqual(response.status_code, 200)

    def test_late_login_skips_duplicate_check_and_can_be_already_ended(self):
        self.login(racunalo="PC1")
        response = self.login(racunalo="PC2", naknadno=True, zavrsena=True)
        self.assertEqual(response.status_code, 200)
        late = ComputerSession.objects.get(computer_name="PC2")
        self.assertIsNotNone(late.ended_at)
        prijava = ActivityLog.objects.get(session=late, event_type="PRIJAVA")
        self.assertIn("naknadno", prijava.details)


class HeartbeatAndLogoffTests(ApiTestCase):
    def setUp(self):
        super().setUp()
        self.token = self.login(racunalo="PC1").json()["token"]

    def test_heartbeat_keeps_session_active(self):
        ComputerSession.objects.update(last_seen_at=timezone.now() - timedelta(minutes=10))
        self.assertEqual(self.post("nadzor_api_zivost", {"token": self.token}).status_code, 200)
        self.assertEqual(self.login(racunalo="PC2").status_code, 409)

    def test_heartbeat_with_bad_token_is_401(self):
        self.assertEqual(self.post("nadzor_api_zivost", {"token": "x"}).status_code, 401)

    def test_heartbeat_after_logoff_is_401(self):
        self.post("nadzor_api_odjava", {"token": self.token})
        self.assertEqual(self.post("nadzor_api_zivost", {"token": self.token}).status_code, 401)

    def test_logoff_logs_odjava_once(self):
        self.post("nadzor_api_odjava", {"token": self.token})
        self.post("nadzor_api_odjava", {"token": self.token})
        self.assertEqual(ActivityLog.objects.filter(event_type="ODJAVA").count(), 1)

    def test_queued_logs_are_still_accepted_after_logoff(self):
        self.post("nadzor_api_odjava", {"token": self.token})
        response = self.post(
            "nadzor_api_zapisi",
            {"token": self.token, "racunalo": "PC1", "vrsta": "POKRENUTA APLIKACIJA", "detalji": "x"},
        )
        self.assertEqual(response.status_code, 201)


class UnidentifiedLogTests(ApiTestCase):
    def test_typed_name_is_kept_but_not_linked_to_a_student(self):
        response = self.post(
            "nadzor_api_zapisi",
            {
                "racunalo": "PC9",
                "neidentificiran": {"razred": "1.C", "ime": "Luka", "prezime": "Čolić"},
                "zapisi": [{"vrsta": "POKRENUTA APLIKACIJA", "detalji": "Roblox"}],
            },
        )
        self.assertEqual(response.status_code, 201)
        log = ActivityLog.objects.get()
        self.assertFalse(log.identified)
        self.assertIsNone(log.student)
        self.assertIsNone(log.session)
        self.assertEqual((log.last_name, log.class_name, log.computer_name), ("Čolić", "1.C", "PC9"))

    def test_nothing_typed_at_all(self):
        response = self.post(
            "nadzor_api_zapisi",
            {"racunalo": "PC9", "neidentificiran": {}, "vrsta": "ODJAVA - NIJE SE PRIJAVIO"},
        )
        self.assertEqual(response.status_code, 201)
        log = ActivityLog.objects.get()
        self.assertEqual((log.first_name, log.last_name, log.identified), ("", "", False))

    def test_computer_name_is_required(self):
        response = self.post("nadzor_api_zapisi", {"neidentificiran": {}, "vrsta": "X"})
        self.assertEqual(response.status_code, 400)

    def test_without_token_or_marker_is_401(self):
        self.assertEqual(self.post("nadzor_api_zapisi", {"racunalo": "PC9", "vrsta": "X"}).status_code, 401)

    def test_teacher_view_marks_unidentified(self):
        self.post("nadzor_api_zapisi", {"racunalo": "PC9", "neidentificiran": {"ime": "Nitko"}, "vrsta": "X"})
        admin = User.objects.create_user(username="admin1", password="x", is_staff=True)
        admin.profile.must_change_password = False
        admin.profile.save()
        self.client.login(username="admin1", password="x")
        response = self.client.get(reverse("nadzor_zapisi"))
        self.assertContains(response, "neidentificiran")
        self.assertContains(response, "upisano: Nitko")
