import io

from django.contrib.auth.models import User
from django.urls import reverse

from nadzor import services
from nadzor.models import ActivityLog, BlockedSite

from .test_api import ApiTestCase

SITE = services.SITE_EVENT


class BlockedServiceTests(ApiTestCase):
    def test_normalize_pattern_strips_scheme_path_www(self):
        self.assertEqual(services.normalize_pattern("https://www.Roblox.com/games/123"), "roblox.com")
        self.assertEqual(services.normalize_pattern("  TikTok "), "tiktok")

    def test_domain_is_blocked_is_substring_match(self):
        BlockedSite.objects.create(pattern="roblox.com")
        BlockedSite.objects.create(pattern="tiktok")
        self.assertTrue(services.domain_is_blocked("www.roblox.com"))
        self.assertTrue(services.domain_is_blocked("m.tiktok.com"))
        self.assertFalse(services.domain_is_blocked("24sata.hr"))

    def test_inactive_pattern_does_not_match(self):
        BlockedSite.objects.create(pattern="roblox.com", is_active=False)
        self.assertFalse(services.domain_is_blocked("roblox.com"))

    def test_blocked_logs_q_selects_only_matching_site_events(self):
        BlockedSite.objects.create(pattern="roblox.com")
        good = ActivityLog.objects.create(computer_name="PC1", event_type=SITE, details="roblox.com")
        ActivityLog.objects.create(computer_name="PC1", event_type=SITE, details="24sata.hr")
        ActivityLog.objects.create(computer_name="PC1", event_type="POKRENUTA APLIKACIJA", details="roblox.com")
        hits = list(ActivityLog.objects.filter(services.blocked_logs_q()))
        self.assertEqual(hits, [good])

    def test_empty_list_matches_nothing(self):
        ActivityLog.objects.create(computer_name="PC1", event_type=SITE, details="roblox.com")
        self.assertEqual(ActivityLog.objects.filter(services.blocked_logs_q()).count(), 0)


class BlockedViewTests(ApiTestCase):
    def setUp(self):
        super().setUp()
        self.admin = User.objects.create_user(username="admin1", password="x", is_staff=True)
        self.admin.profile.must_change_password = False
        self.admin.profile.save()
        self.client.login(username="admin1", password="x")

    def test_add_and_delete_pattern(self):
        self.client.post(reverse("nadzor_blokirane"), {"akcija": "dodaj", "izraz": "HTTPS://www.Roblox.com/x", "kategorija": "igre"})
        site = BlockedSite.objects.get()
        self.assertEqual(site.pattern, "roblox.com")
        self.assertEqual(site.category, "igre")
        self.client.post(reverse("nadzor_blokirane"), {"akcija": "obrisi", "id": site.id})
        self.assertFalse(BlockedSite.objects.exists())

    def test_import_csv(self):
        f = io.BytesIO("domena,kategorija\nroblox.com,igre\npoki.com\ntiktok\n".encode("utf-8"))
        f.name = "popis.csv"
        self.client.post(reverse("nadzor_blokirane"), {"akcija": "uvoz", "datoteka": f})
        self.assertEqual(set(BlockedSite.objects.values_list("pattern", flat=True)), {"roblox.com", "poki.com", "tiktok"})

    def test_violations_page_summarizes_per_student(self):
        BlockedSite.objects.create(pattern="roblox.com")
        for _ in range(3):
            ActivityLog.objects.create(
                computer_name="PC1", class_name="1.C", last_name="Čolić", first_name="Luka",
                event_type=SITE, details="www.roblox.com", identified=True,
            )
        ActivityLog.objects.create(
            computer_name="PC1", class_name="1.C", last_name="Čolić", first_name="Luka",
            event_type=SITE, details="24sata.hr", identified=True,
        )
        response = self.client.get(reverse("nadzor_prekrsaji"))
        self.assertEqual(response.status_code, 200)
        rows = response.context["rows"]
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["count"], 3)
        self.assertEqual(rows[0]["domains"], ["www.roblox.com"])

    def test_violations_page_without_list_prompts_setup(self):
        response = self.client.get(reverse("nadzor_prekrsaji"))
        self.assertTrue(response.context["nema_popisa"])

    def test_zapisi_marks_blocked_rows(self):
        BlockedSite.objects.create(pattern="roblox.com")
        ActivityLog.objects.create(computer_name="PC1", event_type=SITE, details="www.roblox.com")
        response = self.client.get(reverse("nadzor_zapisi"))
        self.assertContains(response, "nedopušteno")
