"""Production-only settings; secrets and hostnames must come from the process environment."""

import os
from urllib.parse import urlsplit

from django.core.exceptions import ImproperlyConfigured

from config.settings import *  # noqa: F403


def _required(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise ImproperlyConfigured(f"{name} must be set in the production environment.")
    return value


def _required_csv(name: str) -> list[str]:
    values = [value.strip() for value in _required(name).split(",") if value.strip()]
    if not values:
        raise ImproperlyConfigured(f"{name} must contain at least one value.")
    return values


SECRET_KEY = _required("DJANGO_SECRET_KEY")
if len(SECRET_KEY) < 50 or SECRET_KEY.startswith("django-insecure-"):
    raise ImproperlyConfigured(
        "DJANGO_SECRET_KEY must be a strong, generated secret of at least 50 characters."
    )

DEBUG = False
ALLOWED_HOSTS = _required_csv("DJANGO_ALLOWED_HOSTS")
if "*" in ALLOWED_HOSTS:
    raise ImproperlyConfigured("DJANGO_ALLOWED_HOSTS must not contain '*'.")

CSRF_TRUSTED_ORIGINS = _required_csv("DJANGO_CSRF_TRUSTED_ORIGINS")
for origin in CSRF_TRUSTED_ORIGINS:
    parsed_origin = urlsplit(origin)
    if (
        parsed_origin.scheme != "https"
        or not parsed_origin.netloc
        or parsed_origin.path not in ("", "/")
        or parsed_origin.query
        or parsed_origin.fragment
    ):
        raise ImproperlyConfigured(
            "Every DJANGO_CSRF_TRUSTED_ORIGINS value must be an HTTPS origin."
        )

database = DATABASES["default"]  # noqa: F405
if database["ENGINE"] != "django.db.backends.postgresql":
    raise ImproperlyConfigured("Production must use PostgreSQL, not SQLite.")
if not database["NAME"] or not database["USER"]:
    raise ImproperlyConfigured("Production DB_NAME and DB_USER must be configured.")
if not os.environ.get("DATABASE_URL") and not os.environ.get("DB_NAME"):
    raise ImproperlyConfigured("Set DATABASE_URL or an explicit DB_NAME for production.")

STATIC_URL = "/static/"

# Trust this header only because Gunicorn is bound to loopback and Nginx
# overwrites X-Forwarded-Proto before proxying the request.
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SECURE_SSL_REDIRECT = True
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
CSRF_COOKIE_HTTPONLY = False
SESSION_COOKIE_SAMESITE = "Lax"
CSRF_COOKIE_SAMESITE = "Lax"

try:
    SECURE_HSTS_SECONDS = int(os.environ.get("DJANGO_HSTS_SECONDS", "3600"))
except ValueError as exc:
    raise ImproperlyConfigured("DJANGO_HSTS_SECONDS must be an integer.") from exc
if SECURE_HSTS_SECONDS < 1:
    raise ImproperlyConfigured("DJANGO_HSTS_SECONDS must be greater than zero.")

SECURE_HSTS_INCLUDE_SUBDOMAINS = False
SECURE_HSTS_PRELOAD = False
SECURE_REFERRER_POLICY = "strict-origin-when-cross-origin"
