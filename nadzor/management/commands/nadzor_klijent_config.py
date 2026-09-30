import json

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = (
        "Ispisuje config.json za klijent na ucenickim racunalima (klijent/), s adresom "
        "servera i API kljucem iz postavki servera - jedan izvor istine, kljuc nikad u gitu."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--url",
            required=True,
            help="Adresa na kojoj racunala dosezu server, npr. https://192.168.1.50:8443",
        )
        parser.add_argument("--interval", type=int, default=60, help="Sekunde izmedu provjera (zadano 60).")

    def handle(self, *args, **options):
        if not settings.NADZOR_API_KEY:
            raise CommandError("NADZOR_API_KEY nije postavljen u .env - prvo ga postavi.")
        url = options["url"].rstrip("/")
        if not url.startswith(("https://", "http://")):
            raise CommandError("--url mora pocinjati s https:// (ili http://).")
        config = {
            "serverUrl": url,
            "apiKey": settings.NADZOR_API_KEY,
            "pollSeconds": max(10, options["interval"]),
            "loginTimeoutMinutes": 2,
            "restrictions": True,
            "logSites": True,
            "autoUpdate": True,
            "skipWindowsDir": True,
        }
        self.stdout.write(json.dumps(config, indent=2, ensure_ascii=False))
