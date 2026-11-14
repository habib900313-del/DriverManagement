"""Copy auth_user rows from a SQLite database into the current database.

Used for the PostgreSQL cutover: the operator's existing login (including the
already-hashed password) is carried over verbatim, so the same credentials keep
working on the new primary database.

The password hash is written as-is — Django stores it in a plain CharField and
does not re-hash on save, so `check_password` still verifies it.
"""

import sqlite3
from datetime import timezone as dt_timezone

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import connection, transaction
from django.utils import timezone
from django.utils.dateparse import parse_datetime

FIELDS = [
    "id",
    "password",
    "last_login",
    "is_superuser",
    "username",
    "first_name",
    "last_name",
    "email",
    "is_staff",
    "is_active",
    "date_joined",
]

DATETIME_FIELDS = {"last_login", "date_joined"}


def _as_aware(value):
    """SQLite stores UTC wall-clock; make the value explicitly UTC-aware.

    Without this the naive value would be read as Asia/Kabul and silently
    shift by the local UTC offset.
    """
    if value is None:
        return None
    if isinstance(value, str):
        value = parse_datetime(value)
    if value is None:
        return None
    if timezone.is_naive(value):
        value = value.replace(tzinfo=dt_timezone.utc)
    return value


class Command(BaseCommand):
    help = "Copy auth_user rows from a SQLite file into the current database."

    def add_arguments(self, parser):
        parser.add_argument("--source", required=True, help="source SQLite file")
        parser.add_argument(
            "--dry-run", action="store_true", help="report without writing"
        )

    def handle(self, *args, **options):
        source = options["source"]
        dry_run = options["dry_run"]
        User = get_user_model()

        try:
            src = sqlite3.connect(f"file:{source}?mode=ro", uri=True)
        except sqlite3.Error as exc:
            raise CommandError(f"cannot open {source}: {exc}") from exc

        cols = ",".join(FIELDS)
        rows = src.execute(f"SELECT {cols} FROM auth_user ORDER BY id").fetchall()
        src.close()

        existing = set(User.objects.values_list("username", flat=True))
        self.stdout.write(f"source rows: {len(rows)}")
        self.stdout.write(f"already present: {sorted(existing)}")

        if dry_run:
            for row in rows:
                self.stdout.write(f"  would copy id={row[0]} username={row[4]!r}")
            return

        created = 0
        updated = 0
        with transaction.atomic():
            for row in rows:
                data = dict(zip(FIELDS, row))
                username = data.pop("username")
                pk = data.pop("id")
                for field in DATETIME_FIELDS:
                    data[field] = _as_aware(data[field])

                if username in existing:
                    # Re-runnable: refresh the stored account (password hash
                    # and timestamps) without creating a duplicate.
                    User.objects.filter(username=username).update(**data)
                    updated += 1
                    self.stdout.write(f"  updated username={username!r}")
                    continue

                User.objects.create(pk=pk, username=username, **data)
                created += 1
                self.stdout.write(f"  copied id={pk} username={username!r}")

            # keep the identity sequence ahead of the explicitly-inserted ids
            if connection.vendor == "postgresql":
                with connection.cursor() as cur:
                    cur.execute("SELECT pg_get_serial_sequence('auth_user', 'id')")
                    seq = cur.fetchone()[0]
                    if seq:
                        cur.execute(
                            "SELECT setval(%s, COALESCE((SELECT MAX(id) FROM auth_user), 1))",
                            [seq],
                        )
            self.stdout.write(f"created: {created}, updated: {updated}")

        self.stdout.write(self.style.SUCCESS("auth users imported"))
