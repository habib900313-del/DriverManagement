"""Test settings: file-based SQLite test DB so thread/lock tests (V2/V3a/V8)
share one database across connections (the default :memory: is per-connection).
Never points at the real backend/db.sqlite3.

PostgreSQL is the primary database, and the Django test runner already builds
a real ``test_<dbname>`` database there, so the file-based override only
applies when the active engine is SQLite.
"""

from .settings import *  # noqa: F401,F403

if DATABASES["default"]["ENGINE"] == "django.db.backends.sqlite3":  # noqa: F405
    DATABASES["default"]["TEST"] = {"NAME": BASE_DIR / "test_financial.sqlite3"}  # noqa: F405
    DATABASES["default"]["OPTIONS"]["timeout"] = 5