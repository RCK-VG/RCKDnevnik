import tempfile
from pathlib import Path
from unittest.mock import patch

from django.contrib.auth.models import User
from django.test import SimpleTestCase, TestCase, override_settings
from django.urls import reverse

from dnevnik.backup import BackupNotSupported, create_backup


class CreateBackupTests(SimpleTestCase):
    databases = set()

    def test_creates_timestamped_copy_of_the_db_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            db_file = tmp_path / "db.sqlite3"
            db_file.write_bytes(b"fake-sqlite-content")
            backup_dir = tmp_path / "backups"

            with override_settings(
                DATABASES={"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": str(db_file)}},
                BACKUP_DIR=backup_dir,
                BACKUP_KEEP=14,
            ):
                dest = create_backup()

            self.assertTrue(dest.exists())
            self.assertEqual(dest.read_bytes(), b"fake-sqlite-content")
            self.assertTrue(dest.name.startswith("db_"))

    def test_keeps_only_the_newest_n_backups(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            db_file = tmp_path / "db.sqlite3"
            db_file.write_bytes(b"content")
            backup_dir = tmp_path / "backups"

            with override_settings(
                DATABASES={"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": str(db_file)}},
                BACKUP_DIR=backup_dir,
                BACKUP_KEEP=2,
            ):
                create_backup()
                create_backup()
                create_backup()

            remaining = sorted(backup_dir.glob("db_*.sqlite3"))
            self.assertEqual(len(remaining), 2)

    def test_raises_for_non_sqlite_engine(self):
        with override_settings(
            DATABASES={"default": {"ENGINE": "django.db.backends.postgresql", "NAME": "dnevnik"}}
        ):
            with self.assertRaises(BackupNotSupported):
                create_backup()

    def test_raises_when_db_file_is_missing(self):
        with tempfile.TemporaryDirectory() as tmp:
            missing = Path(tmp) / "does_not_exist.sqlite3"
            with override_settings(
                DATABASES={"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": str(missing)}}
            ):
                with self.assertRaises(FileNotFoundError):
                    create_backup()


class PreuzmiBackupViewTests(TestCase):
    def setUp(self):
        self.teacher = User.objects.create_user(username="nastavnik1", password="x")
        self.teacher.profile.must_change_password = False
        self.teacher.profile.save()
        self.admin = User.objects.create_user(username="admin1", password="x", is_staff=True)
        self.admin.profile.must_change_password = False
        self.admin.profile.save()

    def test_regular_teacher_forbidden(self):
        self.client.login(username="nastavnik1", password="x")
        response = self.client.get(reverse("preuzmi_backup"))
        self.assertEqual(response.status_code, 403)

    def test_admin_gets_a_file_download(self):
        # The Django test runner uses an in-memory SQLite database, so we
        # can't point create_backup() at a real file via override_settings
        # while also going through the test client (which needs the real
        # test DB connection for the session/permission lookups). Mocking
        # keeps this a clean view-level test: given a backup file exists,
        # does the view serve it correctly as an attachment?
        with tempfile.TemporaryDirectory() as tmp:
            fake_backup = Path(tmp) / "db_20260101_120000_000000.sqlite3"
            fake_backup.write_bytes(b"fake-sqlite-content")

            self.client.login(username="admin1", password="x")
            with patch("dnevnik.views_backup.create_backup", return_value=fake_backup):
                response = self.client.get(reverse("preuzmi_backup"))

            self.assertEqual(response.status_code, 200)
            self.assertTrue(response["Content-Disposition"].startswith("attachment;"))
            self.assertIn(fake_backup.name, response["Content-Disposition"])
            self.assertEqual(b"".join(response.streaming_content), b"fake-sqlite-content")
            # Release the file handle before the TemporaryDirectory tries to
            # delete it (Windows keeps an open file locked).
            response.close()
