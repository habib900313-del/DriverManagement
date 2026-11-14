"""Re-create driver type triggers after the OnlinePayment table rebuild.

SQLite implements `ALTER TABLE ... ALTER COLUMN` by rebuilding the table
(recreating it and copying rows). Rebuilding a table drops every trigger
attached to it. Migration 0006 altered `OnlinePayment.status`, which
rebuilt `payments_onlinepayment` and silently removed the two
`payments_onlpay_driver_type_*` triggers created by 0005.

This migration re-installs all four driver type triggers. It is written
idempotently (DROP ... IF EXISTS before CREATE) so it is safe to run on
databases where the triggers are still present.

The same pattern would be needed for any future SQLite `AlterField` on a
table that carries triggers.
"""

import importlib

from django.db import migrations

# Migration module names start with a digit, so a normal import is not possible.
_TRIGGER_MODULE = importlib.import_module(
    "apps.payments.migrations.0005_driver_type_constraints"
)
SQLITE_TRIGGERS = _TRIGGER_MODULE.SQLITE_TRIGGERS


def recreate_driver_type_triggers(apps, schema_editor):
    """Drop and re-create the driver type triggers for the active vendor."""
    vendor = schema_editor.connection.vendor

    if vendor == "sqlite":
        for name, sql in SQLITE_TRIGGERS:
            schema_editor.execute(f"DROP TRIGGER IF EXISTS {name};")
            schema_editor.execute(sql)
    elif vendor == "postgresql":
        # PostgreSQL keeps CHECK constraints across ALTER TABLE; nothing to redo.
        pass
    else:
        raise RuntimeError(
            f"Unsupported database vendor '{vendor}' for driver type constraints. "
            f"Supported vendors: sqlite, postgresql."
        )


def drop_recreated_driver_type_triggers(apps, schema_editor):
    """Drop the re-created driver type triggers (SQLite only)."""
    vendor = schema_editor.connection.vendor

    if vendor == "sqlite":
        for name, _sql in SQLITE_TRIGGERS:
            schema_editor.execute(f"DROP TRIGGER IF EXISTS {name};")
    elif vendor == "postgresql":
        pass
    else:
        raise RuntimeError(
            f"Unsupported database vendor '{vendor}' for driver type constraints. "
            f"Supported vendors: sqlite, postgresql."
        )


class Migration(migrations.Migration):

    dependencies = [
        ("payments", "0006_online_payment_correction"),
    ]

    operations = [
        migrations.RunPython(
            recreate_driver_type_triggers,
            drop_recreated_driver_type_triggers,
        ),
    ]
