"""Preuzima gotovi popis reklamnih/tracking domena i sprema ga kao
reklamne_domene.txt u mapu klijenta, odakle ga računala povuku auto-updateom.

Popis se NE sprema u git (gitignore) - živi samo na školskom poslužitelju.
Pokreće se ručno (`manage.py nadzor_reklame`) ili dnevno iz docker-compose
(usluga backup). Dopune/iznimke stavljaju se u preskoci_domene.txt (u gitu)."""

import re
import urllib.request
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

# Peter Lowe's ad/tracking server list (plain format, jedna domena po retku).
DEFAULT_URL = "https://pgl.yoyo.org/adservers/serverlist.php?hostformat=plain&showintro=0&mimetype=plaintext"

_DOMAIN = re.compile(r"^(?:0\.0\.0\.0\s+|127\.0\.0\.1\s+)?([a-z0-9][a-z0-9.-]*\.[a-z]{2,})$", re.IGNORECASE)
_SKIP = {"localhost", "localhost.localdomain", "local", "broadcasthost", "ip6-localhost"}


class Command(BaseCommand):
    help = "Preuzima popis reklamnih/tracking domena (reklamne_domene.txt) za klijente."

    def add_arguments(self, parser):
        parser.add_argument("--url", default=DEFAULT_URL, help="Izvor popisa (zadano: Peter Lowe).")
        parser.add_argument("--datoteka", help="Lokalna datoteka umjesto URL-a (za test/offline).")

    def handle(self, *args, **options):
        if options.get("datoteka"):
            text = Path(options["datoteka"]).read_text(encoding="utf-8", errors="ignore")
            source = options["datoteka"]
        else:
            source = options["url"]
            try:
                req = urllib.request.Request(source, headers={"User-Agent": "RCKNadzor"})
                with urllib.request.urlopen(req, timeout=60) as resp:
                    text = resp.read().decode("utf-8", "ignore")
            except Exception as exc:
                raise CommandError(f"Preuzimanje nije uspjelo ({exc}).")

        domains = set()
        for line in text.splitlines():
            line = line.strip()
            if not line or line[0] in "#;!":
                continue
            match = _DOMAIN.match(line)
            if not match:
                continue
            domain = match.group(1).lower().strip(".")
            if domain in _SKIP:
                continue
            domains.add(domain)

        if len(domains) < 100:
            raise CommandError(f"Preuzeto premalo domena ({len(domains)}) - popis vjerojatno nije ispravan.")

        folder = Path(settings.NADZOR_KLIJENT_DIR)
        if not folder.is_dir():
            raise CommandError(f"Mapa klijenta ne postoji: {folder}")
        out = folder / "reklamne_domene.txt"
        header = (
            "# Reklamne/tracking domene - automatski preuzeto (manage.py nadzor_reklame).\n"
            f"# Izvor: {source}\n"
            "# NE uredjuj rucno; iznimke/dopune stavi u preskoci_domene.txt.\n"
        )
        out.write_text(header + "\n".join(sorted(domains)) + "\n", encoding="utf-8")
        self.stdout.write(self.style.SUCCESS(f"Spremljeno {len(domains)} domena u {out}"))
