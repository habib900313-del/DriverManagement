"""PostgreSQL driver-type enforcement via triggers (Phase 9 corrective migration).

Why this migration exists
-------------------------
Migration `payments.0005_driver_type_constraints` implements driver-type
separation with a `CHECK (EXISTS (SELECT ... FROM drivers_driver ...))`
constraint on PostgreSQL. PostgreSQL does not support that: a CHECK
constraint expression may not contain subqueries or reference other rows.
The statement therefore aborts with

    psycopg2.errors.FeatureNotSupported: cannot use subquery in check constraint

and `payments.0005` cannot be applied to a PostgreSQL database at all.

This migration provides the equivalent enforcement using PostgreSQL
triggers, which — like the SQLite triggers installed by `payments.0005` and
re-installed by `payments.0007` — are able to look up the related driver
row. The trigger names are deliberately identical to the SQLite ones so
that both database vendors end up with the same set of enforcement objects:

    payments_pay_driver_type_ins     payments_payment        (INSERT)
    payments_pay_driver_type_upd     payments_payment        (UPDATE OF driver_id)
    payments_onlpay_driver_type_ins  payments_onlinepayment  (INSERT)
    payments_onlpay_driver_type_upd  payments_onlinepayment  (UPDATE OF driver_id)

Enforced rules:
  - payments_payment.driver_id        -> driver must be driver_type='guaranteed'
  - payments_onlinepayment.driver_id -> driver must be driver_type='online'

This migration is a no-op on SQLite, where `payments.0005` (and the
re-install in `payments.0007`) already create equivalent triggers.
"""

from django.db import migrations


# ---------------------------------------------------------------------------
# PostgreSQL trigger function definitions
# ---------------------------------------------------------------------------

POSTGRESQL_FUNCTION_DEFS = [
    {
        "name": "payments_pay_driver_type_fn",
        "sql": """
CREATE OR REPLACE FUNCTION payments_pay_driver_type_fn()
RETURNS TRIGGER AS $$
DECLARE
    driver_kind TEXT;
BEGIN
    SELECT driver_type INTO driver_kind
    FROM drivers_driver WHERE id = NEW.driver_id;

    IF driver_kind IS DISTINCT FROM 'guaranteed' THEN
        RAISE EXCEPTION 'payment requires a guaranteed driver';
    END IF;

    RETURN NEW;
END;
$$ LANGUAGE plpgsql;
""",
    },
    {
        "name": "payments_onlpay_driver_type_fn",
        "sql": """
CREATE OR REPLACE FUNCTION payments_onlpay_driver_type_fn()
RETURNS TRIGGER AS $$
DECLARE
    driver_kind TEXT;
BEGIN
    SELECT driver_type INTO driver_kind
    FROM drivers_driver WHERE id = NEW.driver_id;

    IF driver_kind IS DISTINCT FROM 'online' THEN
        RAISE EXCEPTION 'online payment requires an online driver';
    END IF;

    RETURN NEW;
END;
$$ LANGUAGE plpgsql;
""",
    },
]


POSTGRESQL_TRIGGER_DEFS = [
    {
        "name": "payments_pay_driver_type_ins",
        "table": "payments_payment",
        "sql": """
CREATE TRIGGER payments_pay_driver_type_ins
BEFORE INSERT ON payments_payment
FOR EACH ROW
EXECUTE FUNCTION payments_pay_driver_type_fn();
""",
    },
    {
        "name": "payments_pay_driver_type_upd",
        "table": "payments_payment",
        "sql": """
CREATE TRIGGER payments_pay_driver_type_upd
BEFORE UPDATE OF driver_id ON payments_payment
FOR EACH ROW
EXECUTE FUNCTION payments_pay_driver_type_fn();
""",
    },
    {
        "name": "payments_onlpay_driver_type_ins",
        "table": "payments_onlinepayment",
        "sql": """
CREATE TRIGGER payments_onlpay_driver_type_ins
BEFORE INSERT ON payments_onlinepayment
FOR EACH ROW
EXECUTE FUNCTION payments_onlpay_driver_type_fn();
""",
    },
    {
        "name": "payments_onlpay_driver_type_upd",
        "table": "payments_onlinepayment",
        "sql": """
CREATE TRIGGER payments_onlpay_driver_type_upd
BEFORE UPDATE OF driver_id ON payments_onlinepayment
FOR EACH ROW
EXECUTE FUNCTION payments_onlpay_driver_type_fn();
""",
    },
]


# ---------------------------------------------------------------------------
# Migration operations
# ---------------------------------------------------------------------------


def create_postgresql_driver_type_triggers(apps, schema_editor):
    """Install the driver-type triggers for the active database vendor."""
    vendor = schema_editor.connection.vendor

    if vendor == "sqlite":
        # Already handled by payments.0005 / payments.0007.
        return
    elif vendor == "postgresql":
        for func_def in POSTGRESQL_FUNCTION_DEFS:
            schema_editor.execute(func_def["sql"])
        for trigger_def in POSTGRESQL_TRIGGER_DEFS:
            schema_editor.execute(trigger_def["sql"])
    else:
        raise RuntimeError(
            f"Unsupported database vendor '{vendor}' for driver type triggers. "
            f"Supported vendors: sqlite, postgresql."
        )


def drop_postgresql_driver_type_triggers(apps, schema_editor):
    """Remove the driver-type triggers (and functions) for the active vendor."""
    vendor = schema_editor.connection.vendor

    if vendor == "sqlite":
        return
    elif vendor == "postgresql":
        for trigger_def in POSTGRESQL_TRIGGER_DEFS:
            schema_editor.execute(
                f"DROP TRIGGER IF EXISTS {trigger_def['name']} "
                f"ON {trigger_def['table']};"
            )
        for func_def in POSTGRESQL_FUNCTION_DEFS:
            schema_editor.execute(
                f"DROP FUNCTION IF EXISTS {func_def['name']}();"
            )
    else:
        raise RuntimeError(
            f"Unsupported database vendor '{vendor}' for driver type triggers. "
            f"Supported vendors: sqlite, postgresql."
        )


class Migration(migrations.Migration):

    dependencies = [
        ("payments", "0007_recreate_driver_type_triggers"),
    ]

    operations = [
        migrations.RunPython(
            create_postgresql_driver_type_triggers,
            drop_postgresql_driver_type_triggers,
        ),
    ]
