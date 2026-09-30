import base64
import hashlib
import tempfile
from pathlib import Path

from django.test import override_settings

from nadzor import services

from .test_api import ApiTestCase


class ClientUpdateTests(ApiTestCase):
    def test_bundle_serves_whitelisted_files_with_hash(self):
        with tempfile.TemporaryDirectory() as d:
            folder = Path(d)
            (folder / "servis.ps1").write_bytes("čć servis".encode("utf-8"))
            (folder / "preskoci_domene.txt").write_bytes(b"poki.com\n")
            (folder / "config.json").write_bytes(b'{"apiKey":"TAJNA"}')  # must never be served
            with override_settings(NADZOR_KLIJENT_DIR=str(folder)):
                response = self.get("nadzor_api_klijent")
                self.assertEqual(response.status_code, 200)
                data = response.json()
                self.assertIn("verzija", data)
                self.assertEqual(set(data["datoteke"]), {"servis.ps1", "preskoci_domene.txt"})
                entry = data["datoteke"]["servis.ps1"]
                raw = base64.b64decode(entry["sadrzaj"])
                self.assertEqual(raw.decode("utf-8"), "čć servis")
                self.assertEqual(entry["sha256"], hashlib.sha256(raw).hexdigest())

    def test_version_changes_when_a_file_changes(self):
        with tempfile.TemporaryDirectory() as d:
            folder = Path(d)
            (folder / "servis.ps1").write_bytes(b"v1")
            with override_settings(NADZOR_KLIJENT_DIR=str(folder)):
                first = self.get("nadzor_api_klijent").json()["verzija"]
                (folder / "servis.ps1").write_bytes(b"v2")
                second = self.get("nadzor_api_klijent").json()["verzija"]
        self.assertNotEqual(first, second)

    def test_needs_api_key(self):
        self.assertEqual(self.get("nadzor_api_klijent", key=None).status_code, 403)

    @override_settings(NADZOR_KLIJENT_DIR="/nema/ovakve/mape")
    def test_missing_folder_is_503(self):
        self.assertEqual(self.get("nadzor_api_klijent").status_code, 503)

    def test_config_json_is_never_in_the_whitelist(self):
        self.assertNotIn("config.json", services.CLIENT_UPDATE_FILES)
        self.assertNotIn("rck-ca.crt", services.CLIENT_UPDATE_FILES)
