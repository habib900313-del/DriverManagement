"""Shared Django settings with local-development defaults."""

import os
from pathlib import Path

# backend/ directory (contains manage.py)
BASE_DIR = Path(__file__).resolve().parent.parent
# DriverManagement/ directory (project root)
PROJECT_DIR = BASE_DIR.parent

# Runtime data outside the code tree, so the backend stays portable.
STORAGE_ROOT = PROJECT_DIR / "storage"
MEDIA_ROOT = STORAGE_ROOT / "media"
BACKUP_ROOT = PROJECT_DIR / "backups"


# ---------------------------------------------------------------------------
# Environment file
#
# A machine-local .env (or .env.postgres) at the project root holds the
# database credentials. It is loaded here so the project runs with no manual
# `export` step; real environment variables always win over file values.
# ---------------------------------------------------------------------------
def _load_env_file(path):
    """Load KEY=VALUE pairs from an env file into os.environ (no extra dependency)."""
    try:
        content = path.read_text(encoding="utf-8")
    except OSError:
        return
    for raw_line in content.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        os.environ.setdefault(key, value)


if os.environ.get("DJANGO_SETTINGS_MODULE") != "config.production_settings":
    for _env_name in (".env", ".env.postgres"):
        _load_env_file(PROJECT_DIR / _env_name)
    del _env_name

# ---------------------------------------------------------------------------
# Security
#
# These defaults are for local development only. Production uses
# config.production_settings and requires explicit environment variables.
# ---------------------------------------------------------------------------
SECRET_KEY = os.environ.get(
    "DJANGO_SECRET_KEY",
    "django-insecure-local-development-only-change-me",
)

DEBUG = os.environ.get("DJANGO_DEBUG", "1") == "1"


def _comma_separated_setting(name, default):
    value = os.environ.get(name)
    if value is None:
        return default
    return [item.strip() for item in value.split(",") if item.strip()]


ALLOWED_HOSTS = _comma_separated_setting(
    "DJANGO_ALLOWED_HOSTS", ["127.0.0.1", "localhost"]
)

# The Vite dev server proxies /api to Django, but the browser still sends
# its own Origin header, so the dev origins must be trusted for CSRF.
CSRF_TRUSTED_ORIGINS = _comma_separated_setting(
    "DJANGO_CSRF_TRUSTED_ORIGINS",
    ["http://127.0.0.1:5173", "http://localhost:5173"],
)

# Session/CSRF cookie hardening for the local SPA.
# The CSRF cookie must stay readable by JavaScript so fetch() can echo it.
CSRF_COOKIE_HTTPONLY = False
CSRF_COOKIE_SAMESITE = "Lax"
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
SESSION_COOKIE_AGE = 60 * 60 * 12  # 12-hour office session
X_FRAME_OPTIONS = "DENY"
SECURE_CONTENT_TYPE_NOSNIFF = True

# ---------------------------------------------------------------------------
# Applications
# ---------------------------------------------------------------------------
INSTALLED_APPS = [
    "apps.core.admin_apps.SuperuserOnlyAdminConfig",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    # Third-party
    "rest_framework",
    # Local apps (domain models are added in a later phase)
    "apps.core.apps.CoreConfig",
    "apps.drivers.apps.DriversConfig",
    "apps.payments.apps.PaymentsConfig",
    "apps.documents.apps.DocumentsConfig",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

# ---------------------------------------------------------------------------
# Database: PostgreSQL is the primary database of the project.
#
# The connection is configured through DATABASE_URL (e.g.
# postgres://user:password@host:5432/dbname) or through the individual
# DB_NAME / DB_USER / DB_PASSWORD / DB_HOST / DB_PORT variables.
#
# SQLite is kept only as an explicit opt-in for offline tooling:
# DATABASE_URL=sqlite:////absolute/path/to/db.sqlite3
# ---------------------------------------------------------------------------
import urllib.parse

DATABASE_URL = os.environ.get("DATABASE_URL", "")

if DATABASE_URL.startswith("sqlite:"):
    # Explicit SQLite opt-in (offline tooling / emergency fallback).
    # sqlite:///abs/path.db  -> absolute,  sqlite://relative.db -> relative.
    _sqlite_raw = DATABASE_URL[len("sqlite:"):]
    _sqlite_stripped = _sqlite_raw.lstrip("/")
    _sqlite_leading = len(_sqlite_raw) - len(_sqlite_stripped)
    _sqlite_path = (
        ("/" + _sqlite_stripped) if _sqlite_leading >= 3 else _sqlite_stripped
    ) or "db.sqlite3"
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": Path(_sqlite_path),
            "OPTIONS": {
                # Give SQLite room to wait out brief locks from local tooling.
                "timeout": 20,
            },
        }
    }
else:
    _parsed = urllib.parse.urlparse(DATABASE_URL) if DATABASE_URL else None
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.postgresql",
            "NAME": (
                (_parsed.path[1:] if _parsed and _parsed.path else "")
                or os.environ.get("DB_NAME", "")
                or "drivermanagement"
            ),
            "USER": (
                (_parsed.username if _parsed and _parsed.username else "")
                or os.environ.get("DB_USER", "")
            ),
            "PASSWORD": (
                (_parsed.password if _parsed and _parsed.password else "")
                or os.environ.get("DB_PASSWORD", "")
            ),
            "HOST": (
                (_parsed.hostname if _parsed and _parsed.hostname else "")
                or os.environ.get("DB_HOST", "127.0.0.1")
            ),
            "PORT": str(
                (_parsed.port if _parsed and _parsed.port else "")
                or os.environ.get("DB_PORT", "5432")
            ),
            "OPTIONS": {
                # Keep the session time zone deterministic: the project stores
                # timezone-aware datetimes (USE_TZ=True) and pins the database
                # to UTC so a server-side default change cannot shift them.
                "options": "-c timezone=UTC",
            },
            "CONN_MAX_AGE": int(os.environ.get("DB_CONN_MAX_AGE", "60")),
        },
    }

# ---------------------------------------------------------------------------
# Authentication: Django's built-in auth. No custom User model.
# ---------------------------------------------------------------------------
AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.CommonPasswordValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.NumericPasswordValidator",
    },
]

# ---------------------------------------------------------------------------
# Internationalization
# ---------------------------------------------------------------------------
LANGUAGE_CODE = "en-us"
# Fees and due dates are local calendar dates for a Kabul-based office.
TIME_ZONE = "Asia/Kabul"
USE_I18N = True
USE_TZ = True

# ---------------------------------------------------------------------------
# Static and media files
# ---------------------------------------------------------------------------
STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"

# Uploaded photos and documents are stored on local disk, never in the DB.
# They are intentionally NOT served through MEDIA_URL: files are delivered by
# authenticated API views only.
MEDIA_URL = "/media/"
MEDIA_ROOT = MEDIA_ROOT

# Driver documents can be scans/PDFs; allow reasonably sized uploads.
DATA_UPLOAD_MAX_MEMORY_SIZE = 50 * 1024 * 1024  # 50 MB
FILE_UPLOAD_MAX_MEMORY_SIZE = 5 * 1024 * 1024  # larger files stream to disk

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# ---------------------------------------------------------------------------
# Django REST Framework
#
# Session auth only (built-in Django users) and authenticated-by-default,
# which is the safe posture for a single-administrator system.
# ---------------------------------------------------------------------------
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework.authentication.SessionAuthentication",
    ],
    "DEFAULT_PERMISSION_CLASSES": [
        "rest_framework.permissions.IsAuthenticated",
    ],
    "DEFAULT_PAGINATION_CLASS": "rest_framework.pagination.PageNumberPagination",
    "PAGE_SIZE": 25,
    "DEFAULT_RENDERER_CLASSES": [
        "rest_framework.renderers.JSONRenderer",
        "rest_framework.renderers.BrowsableAPIRenderer",
    ],
    "DATETIME_FORMAT": "iso-8601",
    "DATE_FORMAT": "%Y-%m-%d",
}

# ---------------------------------------------------------------------------
# Local overrides (generated secret key, optional machine-specific values).
# Keeping this file out of version control avoids committing secrets.
# ---------------------------------------------------------------------------
if os.environ.get("DJANGO_SETTINGS_MODULE") != "config.production_settings":
    try:  # pragma: no cover - environment-specific
        from config.local_settings import *  # noqa: F401,F403,E402
    except ImportError:
        pass
