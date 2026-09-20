from django.core.management.base import BaseCommand

from dnevnik.backup import BackupNotSupported, create_backup


class Command(BaseCommand):
    help = "Creates a timestamped copy of the SQLite database in the backups folder."

    def handle(self, *args, **options):
        try:
            dest = create_backup()
        except BackupNotSupported as exc:
            self.stderr.write(self.style.WARNING(str(exc)))
            return
        except FileNotFoundError as exc:
            self.stderr.write(self.style.WARNING(str(exc)))
            return
        self.stdout.write(self.style.SUCCESS(f"Backup created: {dest}"))
