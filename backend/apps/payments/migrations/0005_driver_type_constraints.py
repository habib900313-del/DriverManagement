"""Database-level enforcement of driver type separation (Phase 8).

The application layer (views) already rejects cross-type writes, but the
database must enforce it too so raw SQL / ORM writes cannot bypass it.

SQLite does not support `ALTER TABLE ... ADD CONSTRAINT`, so enforcement is
implemented with BEFORE INSERT/UPDATE triggers using RAISE(ABORT) — the same
pattern already used by the payments invariant triggers (0002).

PostgreSQL: the same rule is enforced with triggers as well. A CHECK
constraint cannot be used because PostgreSQL forbids subqueries in CHECK
expressions, so the PostgreSQL branch here is a no-op and the triggers are
created by payments.0008_postgresql_driver_type_triggers. (Before that
migration existed, this branch tried to add a CHECK constraint containing
`EXISTS (SELECT ...)`, which aborted with "cannot use subquery in check
constraint" and made the migration chain unrunnable on PostgreSQL.)

Enforced rules:
  - payments_payment.driver_id         → driver must be driver_type='guaranteed'
  - payments_onlinepayment.driver_id  → driver must be driver_type='online'
"""

from django.db import migrations


SQLITE_TRIGGERS = [
    (
        "payments_pay_driver_type_ins",
        """
CREATE TRIGGER payments_pay_driver_type_ins
BEFORE INSERT ON payments_payment
WHEN NOT EXISTS (
  SELECT 1 FROM drivers_driver d
  WHERE d.id = NEW.driver_id AND d.driver_type = 'guaranteed'
)
BEGIN
  SELECT RAISE(ABORT, 'payment requires a guaranteed driver');
END;
""",
    ),
    (
        "payments_pay_driver_type_upd",
        """
CREATE TRIGGER payments_pay_driver_type_upd
BEFORE UPDATE OF driver_id ON payments_payment
WHEN NOT EXISTS (
  SELECT 1 FROM drivers_driver d
  WHERE d.id = NEW.driver_id AND d.driver_type = 'guaranteed'
)
BEGIN
  SELECT RAISE(ABORT, 'payment requires a guaranteed driver');
END;
""",
    ),
    (
        "payments_onlpay_driver_type_ins",
        """
CREATE TRIGGER payments_onlpay_driver_type_ins
BEFORE INSERT ON payments_onlinepayment
WHEN NOT EXISTS (
  SELECT 1 FROM drivers_driver d
  WHERE d.id = NEW.driver_id AND d.driver_type = 'online'
)
BEGIN
  SELECT RAISE(ABORT, 'online payment requires an online driver');
END;
""",
    ),
    (
        "payments_onlpay_driver_type_upd",
        """
CREATE TRIGGER payments_onlpay_driver_type_upd
BEFORE UPDATE OF driver_id ON payments_onlinepayment
WHEN NOT EXISTS (
  SELECT 1 FROM drivers_driver d
  WHERE d.id = NEW.driver_id AND d.driver_type = 'online'
)
BEGIN
  SELECT RAISE(ABORT, 'online payment requires an online driver');
END;
""",
    ),
]


def create_driver_type_constraints(apps, schema_editor):
    """Enforce driver type separation at the database level."""
    vendor = schema_editor.connection.vendor

    if vendor == "sqlite":
        for name, sql in SQLITE_TRIGGERS:
            schema_editor.execute(sql)
    elif vendor == "postgresql":
        # PostgreSQL cannot express this rule as a CHECK constraint: a CHECK
        # expression may not contain a subquery or reference other rows, so
        # `CHECK (EXISTS (SELECT ... FROM drivers_driver ...))` is rejected
        # with "cannot use subquery in check constraint". The equivalent
        # enforcement on PostgreSQL is implemented with triggers in
        # payments.0008_postgresql_driver_type_triggers, which installs the
        # same four trigger names used on SQLite.
        pass
    else:
        raise RuntimeError(
            f"Unsupported database vendor '{vendor}' for driver type constraints. "
            f"Supported vendors: sqlite, postgresql."
        )


def drop_driver_type_constraints(apps, schema_editor):
    """Remove the driver type constraints/triggers."""
    vendor = schema_editor.connection.vendor

    if vendor == "sqlite":
        for name, _sql in SQLITE_TRIGGERS:
            schema_editor.execute(f"DROP TRIGGER IF EXISTS {name};")
    elif vendor == "postgresql":
        # The PostgreSQL enforcement lives in the triggers created by
        # payments.0008_postgresql_driver_type_triggers; that migration's
        # reverse operation drops them, and it is reversed before this one.
        pass
    else:
        raise RuntimeError(
            f"Unsupported database vendor '{vendor}' for driver type constraints. "
            f"Supported vendors: sqlite, postgresql."
        )


class Migration(migrations.Migration):

    dependencies = [
        ("drivers", "0006_add_driver_type"),
        ("payments", "0004_add_online_payment"),
    ]

    operations = [
        migrations.RunPython(
            create_driver_type_constraints,
            drop_driver_type_constraints,
        ),
    ]
