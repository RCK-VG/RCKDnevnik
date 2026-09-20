"""
Django settings for the Mali e-Dnevnik project.
"""

from pathlib import Path
from urllib.parse import urlparse
import os

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent

load_dotenv(BASE_DIR / ".env")


def env_bool(name, default=False):
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in ("1", "true", "yes", "on")


def env_list(name, default=""):
    raw = os.environ.get(name, default)
    return [item.strip() for item in raw.split(",") if item.strip()]


SECRET_KEY = os.environ.get("SECRET_KEY", "django-insecure-dev-only-change-me")

DEBUG = env_bool("DEBUG", True)

ALLOWED_HOSTS = env_list("ALLOWED_HOSTS", "localhost,127.0.0.1")

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "dnevnik",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "dnevnik.middleware.ForcePasswordChangeMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"


# Database: SQLite by default; set DATABASE_URL for PostgreSQL,
# e.g. postgres://user:password@host:5432/dbname
DATABASE_URL = os.environ.get("DATABASE_URL", "").strip()

if DATABASE_URL:
    parsed = urlparse(DATABASE_URL)
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.postgresql",
            "NAME": parsed.path.lstrip("/"),
            "USER": parsed.username,
            "PASSWORD": parsed.password,
            "HOST": parsed.hostname,
            "PORT": parsed.port or 5432,
        }
    }
else:
    DATA_DIR = BASE_DIR / "data"
    DATA_DIR.mkdir(exist_ok=True)
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": DATA_DIR / "db.sqlite3",
        }
    }


AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]


# Internationalization
LANGUAGE_CODE = "hr"
TIME_ZONE = os.environ.get("TIME_ZONE", "Europe/Zagreb")
USE_I18N = True
USE_TZ = True


# Static files
STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STATICFILES_STORAGE = "whitenoise.storage.CompressedManifestStaticFilesStorage"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"


# Auth / login flow
LOGIN_URL = "prijava"
LOGIN_REDIRECT_URL = "pocetna"
LOGOUT_REDIRECT_URL = "prijava"

# Session timeout: expires after N hours of inactivity (also on browser close)
SESSION_TIMEOUT_HOURS = float(os.environ.get("SESSION_TIMEOUT_HOURS", "8"))
SESSION_COOKIE_AGE = int(SESSION_TIMEOUT_HOURS * 3600)
SESSION_SAVE_EVERY_REQUEST = True
SESSION_EXPIRE_AT_BROWSER_CLOSE = False

# Login attempt throttling (used by dnevnik.auth_throttle)
LOGIN_MAX_ATTEMPTS = int(os.environ.get("LOGIN_MAX_ATTEMPTS", "5"))
LOGIN_LOCKOUT_MINUTES = int(os.environ.get("LOGIN_LOCKOUT_MINUTES", "15"))

# CSRF / cookies
CSRF_COOKIE_HTTPONLY = False
SESSION_COOKIE_HTTPONLY = True

SECURE_SSL_REDIRECT = env_bool("SECURE_SSL_REDIRECT", False)
if SECURE_SSL_REDIRECT:
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True

# Trust the X-Forwarded-Proto header from a reverse proxy (Caddy in
# docker-compose.prod.yml) so Django knows the original request was HTTPS,
# even though Caddy forwards it to gunicorn over plain HTTP internally.
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

CSRF_TRUSTED_ORIGINS = env_list("CSRF_TRUSTED_ORIGINS", "")

# Where "Preuzmi backup" and the daily backup service write their files.
BACKUP_DIR = Path(os.environ.get("BACKUP_DIR", str(BASE_DIR / "backups")))
BACKUP_DIR.mkdir(exist_ok=True, parents=True)
BACKUP_KEEP = int(os.environ.get("BACKUP_KEEP", "14"))

# Do not leak personal data (names, notes) into logs - keep Django's default
# logging (errors to console) and avoid custom request/body logging.

from django.contrib.messages import constants as message_constants

MESSAGE_TAGS = {
    message_constants.ERROR: "danger",
}
