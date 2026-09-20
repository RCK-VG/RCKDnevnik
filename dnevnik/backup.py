"""Creates timestamped copies of the SQLite database file.

Used by both the `backup_db` management command (for the daily automated
backup) and the admin's "Preuzmi backup" button, so both paths behave
identically and stay in one place.
"""

import shutil
from pathlib import Path

from django.conf import settings
from django.utils import timezone


class BackupNotSupported(Exception):
    """Raised when the configured database isn't SQLite (e.g. PostgreSQL,
    which needs pg_dump instead of a plain file copy)."""


def create_backup(keep=None):
    engine = settings.DATABASES["default"]["ENGINE"]
    if "sqlite3" not in engine:
        raise BackupNotSupported(
            "Automatska sigurnosna kopija ovdje podržava samo SQLite bazu. "
            "Za PostgreSQL koristite pg_dump."
        )

    db_path = Path(settings.DATABASES["default"]["NAME"])
    if not db_path.exists():
        raise FileNotFoundError("Baza podataka još ne postoji.")

    settings.BACKUP_DIR.mkdir(exist_ok=True, parents=True)
    # Microsecond precision avoids overwriting a previous backup if this is
    # ever called twice within the same second (e.g. admin clicks the
    # "Preuzmi backup" button right after the daily service ran).
    timestamp = timezone.now().strftime("%Y%m%d_%H%M%S_%f")
    dest = settings.BACKUP_DIR / f"db_{timestamp}.sqlite3"
    shutil.copy2(db_path, dest)

    keep = settings.BACKUP_KEEP if keep is None else keep
    existing = sorted(
        settings.BACKUP_DIR.glob("db_*.sqlite3"), key=lambda p: p.stat().st_mtime, reverse=True
    )
    for old_backup in existing[keep:]:
        old_backup.unlink()

    return dest
