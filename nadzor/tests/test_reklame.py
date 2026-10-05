import tempfile
from pathlib import Path

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import SimpleTestCase, override_settings


class AdListCommandTests(SimpleTestCase):
    def _run(self, lines, folder):
        src = Path(folder) / "izvor.txt"
        src.write_text("\n".join(lines), encoding="utf-8")
        with override_settings(NADZOR_KLIJENT_DIR=folder):
            call_command("nadzor_reklame", "--datoteka", str(src))
        return (Path(folder) / "reklamne_domene.txt").read_text(encoding="utf-8")

    def test_parses_plain_and_hosts_format(self):
        with tempfile.TemporaryDirectory() as d:
            lines = ["# komentar", "0.0.0.0 doubleclick.net", "127.0.0.1 tracker.test",
                     "criteo.com", "ADS.Example.COM", "localhost", "nije domena"]
            lines += [f"x{i}.adnet.com" for i in range(120)]  # da prijeđe prag od 100
            out = self._run(lines, d)
            self.assertIn("doubleclick.net", out)
            self.assertIn("tracker.test", out)
            self.assertIn("criteo.com", out)
            self.assertIn("ads.example.com", out)   # lowercased
            self.assertNotIn("localhost", out)
            self.assertNotIn("nije domena", out)

    def test_refuses_too_small_list(self):
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaises(CommandError):
                self._run(["criteo.com", "doubleclick.net"], d)
