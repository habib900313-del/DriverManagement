"""DB-level defense-in-depth triggers (spec §9, T2).

Database-aware migration supporting both SQLite and PostgreSQL.

SQLite: native BEFORE INSERT/UPDATE triggers with RAISE(ABORT).
PostgreSQL: PL/pgSQL trigger functions with RAISE EXCEPTION.

Critical aggregate invariants (§9):
  (a) active allocation sum per payment ≤ payment.amount
  (b) consumption source must be an active credit allocation and
      active consumption sum ≤ source.allocated_amount
  (c) cumulative reversal sum ≤ original adjustment amount, with type pairing
      and terminal reversals

On existing SQLite databases where this migration was already applied with
the original RunSQL approach, the triggers already exist and this migration
is a no-op (Django's migration recorder marks it applied). On new databases,
the appropriate triggers for the active database vendor are created.
"""

from django.db import migrations

# ---------------------------------------------------------------------------
# SQLite trigger definitions (unchanged behavior)
# ---------------------------------------------------------------------------

SQLITE_TRIGGER_DEFS = [
    # (a) allocation cap — INSERT
    {
        "name": "payments_alloc_cap_ins",
        "sql": """
CREATE TRIGGER payments_alloc_cap_ins
BEFORE INSERT ON payments_paymentallocation
WHEN NEW.reversed_at IS NULL
BEGIN
  SELECT CASE WHEN (
    SELECT COALESCE(SUM(allocated_amount), 0)
    FROM payments_paymentallocation
    WHERE payment_id = NEW.payment_id AND reversed_at IS NULL
  ) + NEW.allocated_amount > (
    SELECT amount FROM payments_payment WHERE id = NEW.payment_id
  ) THEN RAISE(ABORT, 'allocations exceed payment amount') END;
END;
""",
    },
    # (a) allocation cap — UPDATE (exclude the row being updated)
    {
        "name": "payments_alloc_cap_upd",
        "sql": """
CREATE TRIGGER payments_alloc_cap_upd
BEFORE UPDATE ON payments_paymentallocation
WHEN NEW.reversed_at IS NULL
BEGIN
  SELECT CASE WHEN (
    SELECT COALESCE(SUM(allocated_amount), 0)
    FROM payments_paymentallocation
    WHERE payment_id = NEW.payment_id AND reversed_at IS NULL AND id != NEW.id
  ) + NEW.allocated_amount > (
    SELECT amount FROM payments_payment WHERE id = NEW.payment_id
  ) THEN RAISE(ABORT, 'allocations exceed payment amount') END;
END;
""",
    },
    # (b) consumption source — INSERT
    {
        "name": "payments_cons_source_ins",
        "sql": """
CREATE TRIGGER payments_cons_source_ins
BEFORE INSERT ON payments_allocationconsumption
WHEN NEW.reversed_at IS NULL
BEGIN
  SELECT CASE WHEN COALESCE((
    SELECT allocation_type FROM payments_paymentallocation
    WHERE id = NEW.source_allocation_id
  ), '') != 'credit'
  THEN RAISE(ABORT, 'consumption source must be a credit allocation') END;
  SELECT CASE WHEN (
    SELECT reversed_at FROM payments_paymentallocation
    WHERE id = NEW.source_allocation_id
  ) IS NOT NULL
  THEN RAISE(ABORT, 'consumption source allocation is reversed') END;
  SELECT CASE WHEN (
    SELECT COALESCE(SUM(consumption_amount), 0)
    FROM payments_allocationconsumption
    WHERE source_allocation_id = NEW.source_allocation_id AND reversed_at IS NULL
  ) + NEW.consumption_amount > (
    SELECT allocated_amount FROM payments_paymentallocation
    WHERE id = NEW.source_allocation_id
  ) THEN RAISE(ABORT, 'consumption exceeds source available balance') END;
END;
""",
    },
    # (b) consumption source — UPDATE
    {
        "name": "payments_cons_source_upd",
        "sql": """
CREATE TRIGGER payments_cons_source_upd
BEFORE UPDATE ON payments_allocationconsumption
WHEN NEW.reversed_at IS NULL
BEGIN
  SELECT CASE WHEN COALESCE((
    SELECT allocation_type FROM payments_paymentallocation
    WHERE id = NEW.source_allocation_id
  ), '') != 'credit'
  THEN RAISE(ABORT, 'consumption source must be a credit allocation') END;
  SELECT CASE WHEN (
    SELECT reversed_at FROM payments_paymentallocation
    WHERE id = NEW.source_allocation_id
  ) IS NOT NULL
  THEN RAISE(ABORT, 'consumption source allocation is reversed') END;
  SELECT CASE WHEN (
    SELECT COALESCE(SUM(consumption_amount), 0)
    FROM payments_allocationconsumption
    WHERE source_allocation_id = NEW.source_allocation_id
      AND reversed_at IS NULL AND id != NEW.id
  ) + NEW.consumption_amount > (
    SELECT allocated_amount FROM payments_paymentallocation
    WHERE id = NEW.source_allocation_id
  ) THEN RAISE(ABORT, 'consumption exceeds source available balance') END;
END;
""",
    },
    # (c) cumulative reversal cap + pairing + terminal — INSERT
    {
        "name": "payments_adj_reversal_cap_ins",
        "sql": """
CREATE TRIGGER payments_adj_reversal_cap_ins
BEFORE INSERT ON payments_adjustment
WHEN NEW.reverses_adjustment_id IS NOT NULL
BEGIN
  SELECT CASE WHEN (
    SELECT adjustment_type FROM payments_adjustment
    WHERE id = NEW.reverses_adjustment_id
  ) IS NULL
  THEN RAISE(ABORT, 'reversal target adjustment does not exist') END;
  SELECT CASE WHEN (
    SELECT adjustment_type FROM payments_adjustment
    WHERE id = NEW.reverses_adjustment_id
  ) NOT IN ('waiver', 'transfer')
  THEN RAISE(ABORT, 'reversals are terminal and cannot be reversed') END;
  SELECT CASE WHEN NEW.adjustment_type != (
    SELECT adjustment_type || '_reversal' FROM payments_adjustment
    WHERE id = NEW.reverses_adjustment_id
  ) THEN RAISE(ABORT, 'reversal type does not match original adjustment') END;
  SELECT CASE WHEN (
    SELECT COALESCE(SUM(amount), 0) FROM payments_adjustment
    WHERE reverses_adjustment_id = NEW.reverses_adjustment_id
  ) + NEW.amount > (
    SELECT amount FROM payments_adjustment WHERE id = NEW.reverses_adjustment_id
  ) THEN RAISE(ABORT, 'reversals exceed original adjustment amount') END;
END;
""",
    },
    # (c) cumulative reversal cap — UPDATE
    {
        "name": "payments_adj_reversal_cap_upd",
        "sql": """
CREATE TRIGGER payments_adj_reversal_cap_upd
BEFORE UPDATE ON payments_adjustment
WHEN NEW.reverses_adjustment_id IS NOT NULL
BEGIN
  SELECT CASE WHEN (
    SELECT adjustment_type FROM payments_adjustment
    WHERE id = NEW.reverses_adjustment_id
  ) NOT IN ('waiver', 'transfer')
  THEN RAISE(ABORT, 'reversals are terminal and cannot be reversed') END;
  SELECT CASE WHEN NEW.adjustment_type != (
    SELECT adjustment_type || '_reversal' FROM payments_adjustment
    WHERE id = NEW.reverses_adjustment_id
  ) THEN RAISE(ABORT, 'reversal type does not match original adjustment') END;
  SELECT CASE WHEN (
    SELECT COALESCE(SUM(amount), 0) FROM payments_adjustment
    WHERE reverses_adjustment_id = NEW.reverses_adjustment_id AND id != NEW.id
  ) + NEW.amount > (
    SELECT amount FROM payments_adjustment WHERE id = NEW.reverses_adjustment_id
  ) THEN RAISE(ABORT, 'reversals exceed original adjustment amount') END;
END;
""",
    },
]

SQLITE_TRIGGER_NAMES = [
    "payments_alloc_cap_ins",
    "payments_alloc_cap_upd",
    "payments_cons_source_ins",
    "payments_cons_source_upd",
    "payments_adj_reversal_cap_ins",
    "payments_adj_reversal_cap_upd",
]


# ---------------------------------------------------------------------------
# PostgreSQL trigger function definitions
# ---------------------------------------------------------------------------

POSTGRESQL_FUNCTION_DEFS = [
    # (a) allocation cap function — used by both INSERT and UPDATE triggers
    {
        "name": "payments_alloc_cap_fn",
        "sql": """
CREATE OR REPLACE FUNCTION payments_alloc_cap_fn()
RETURNS TRIGGER AS $$
DECLARE
    existing_sum NUMERIC;
    payment_amount NUMERIC;
BEGIN
    IF TG_OP = 'UPDATE' THEN
        SELECT COALESCE(SUM(allocated_amount), 0) INTO existing_sum
        FROM payments_paymentallocation
        WHERE payment_id = NEW.payment_id
          AND reversed_at IS NULL
          AND id != NEW.id;
    ELSE
        SELECT COALESCE(SUM(allocated_amount), 0) INTO existing_sum
        FROM payments_paymentallocation
        WHERE payment_id = NEW.payment_id AND reversed_at IS NULL;
    END IF;

    SELECT amount INTO payment_amount
    FROM payments_payment WHERE id = NEW.payment_id;

    IF existing_sum + NEW.allocated_amount > payment_amount THEN
        RAISE EXCEPTION 'allocations exceed payment amount';
    END IF;

    RETURN NEW;
END;
$$ LANGUAGE plpgsql;
""",
    },
    # (b) consumption source function — used by both INSERT and UPDATE triggers
    {
        "name": "payments_cons_source_fn",
        "sql": """
CREATE OR REPLACE FUNCTION payments_cons_source_fn()
RETURNS TRIGGER AS $$
DECLARE
    source_type TEXT;
    source_reversed TIMESTAMPTZ;
    existing_sum NUMERIC;
    source_allocated NUMERIC;
BEGIN
    SELECT allocation_type, reversed_at INTO source_type, source_reversed
    FROM payments_paymentallocation WHERE id = NEW.source_allocation_id;

    IF source_type IS NULL THEN
        RAISE EXCEPTION 'consumption source allocation does not exist';
    END IF;

    IF source_type != 'credit' THEN
        RAISE EXCEPTION 'consumption source must be a credit allocation';
    END IF;

    IF source_reversed IS NOT NULL THEN
        RAISE EXCEPTION 'consumption source allocation is reversed';
    END IF;

    IF TG_OP = 'UPDATE' THEN
        SELECT COALESCE(SUM(consumption_amount), 0) INTO existing_sum
        FROM payments_allocationconsumption
        WHERE source_allocation_id = NEW.source_allocation_id
          AND reversed_at IS NULL
          AND id != NEW.id;
    ELSE
        SELECT COALESCE(SUM(consumption_amount), 0) INTO existing_sum
        FROM payments_allocationconsumption
        WHERE source_allocation_id = NEW.source_allocation_id AND reversed_at IS NULL;
    END IF;

    SELECT allocated_amount INTO source_allocated
    FROM payments_paymentallocation WHERE id = NEW.source_allocation_id;

    IF existing_sum + NEW.consumption_amount > source_allocated THEN
        RAISE EXCEPTION 'consumption exceeds source available balance';
    END IF;

    RETURN NEW;
END;
$$ LANGUAGE plpgsql;
""",
    },
    # (c) reversal cap function — used by both INSERT and UPDATE triggers
    {
        "name": "payments_adj_reversal_cap_fn",
        "sql": """
CREATE OR REPLACE FUNCTION payments_adj_reversal_cap_fn()
RETURNS TRIGGER AS $$
DECLARE
    target_type TEXT;
    target_exists BOOLEAN;
    existing_sum NUMERIC;
    target_amount NUMERIC;
BEGIN
    SELECT adjustment_type, amount INTO target_type, target_amount
    FROM payments_adjustment WHERE id = NEW.reverses_adjustment_id;

    IF target_type IS NULL THEN
        RAISE EXCEPTION 'reversal target adjustment does not exist';
    END IF;

    IF target_type NOT IN ('waiver', 'transfer') THEN
        RAISE EXCEPTION 'reversals are terminal and cannot be reversed';
    END IF;

    IF NEW.adjustment_type != target_type || '_reversal' THEN
        RAISE EXCEPTION 'reversal type does not match original adjustment';
    END IF;

    IF TG_OP = 'UPDATE' THEN
        SELECT COALESCE(SUM(amount), 0) INTO existing_sum
        FROM payments_adjustment
        WHERE reverses_adjustment_id = NEW.reverses_adjustment_id
          AND id != NEW.id;
    ELSE
        SELECT COALESCE(SUM(amount), 0) INTO existing_sum
        FROM payments_adjustment
        WHERE reverses_adjustment_id = NEW.reverses_adjustment_id;
    END IF;

    IF existing_sum + NEW.amount > target_amount THEN
        RAISE EXCEPTION 'reversals exceed original adjustment amount';
    END IF;

    RETURN NEW;
END;
$$ LANGUAGE plpgsql;
""",
    },
]


POSTGRESQL_TRIGGER_DEFS = [
    # (a) allocation cap — INSERT
    {
        "name": "payments_alloc_cap_ins",
        "table": "payments_paymentallocation",
        "function": "payments_alloc_cap_fn",
        "sql": """
CREATE TRIGGER payments_alloc_cap_ins
BEFORE INSERT ON payments_paymentallocation
FOR EACH ROW
WHEN (NEW.reversed_at IS NULL)
EXECUTE FUNCTION payments_alloc_cap_fn();
""",
    },
    # (a) allocation cap — UPDATE
    {
        "name": "payments_alloc_cap_upd",
        "table": "payments_paymentallocation",
        "function": "payments_alloc_cap_fn",
        "sql": """
CREATE TRIGGER payments_alloc_cap_upd
BEFORE UPDATE ON payments_paymentallocation
FOR EACH ROW
WHEN (NEW.reversed_at IS NULL)
EXECUTE FUNCTION payments_alloc_cap_fn();
""",
    },
    # (b) consumption source — INSERT
    {
        "name": "payments_cons_source_ins",
        "table": "payments_allocationconsumption",
        "function": "payments_cons_source_fn",
        "sql": """
CREATE TRIGGER payments_cons_source_ins
BEFORE INSERT ON payments_allocationconsumption
FOR EACH ROW
WHEN (NEW.reversed_at IS NULL)
EXECUTE FUNCTION payments_cons_source_fn();
""",
    },
    # (b) consumption source — UPDATE
    {
        "name": "payments_cons_source_upd",
        "table": "payments_allocationconsumption",
        "function": "payments_cons_source_fn",
        "sql": """
CREATE TRIGGER payments_cons_source_upd
BEFORE UPDATE ON payments_allocationconsumption
FOR EACH ROW
WHEN (NEW.reversed_at IS NULL)
EXECUTE FUNCTION payments_cons_source_fn();
""",
    },
    # (c) reversal cap — INSERT
    {
        "name": "payments_adj_reversal_cap_ins",
        "table": "payments_adjustment",
        "function": "payments_adj_reversal_cap_fn",
        "sql": """
CREATE TRIGGER payments_adj_reversal_cap_ins
BEFORE INSERT ON payments_adjustment
FOR EACH ROW
WHEN (NEW.reverses_adjustment_id IS NOT NULL)
EXECUTE FUNCTION payments_adj_reversal_cap_fn();
""",
    },
    # (c) reversal cap — UPDATE
    {
        "name": "payments_adj_reversal_cap_upd",
        "table": "payments_adjustment",
        "function": "payments_adj_reversal_cap_fn",
        "sql": """
CREATE TRIGGER payments_adj_reversal_cap_upd
BEFORE UPDATE ON payments_adjustment
FOR EACH ROW
WHEN (NEW.reverses_adjustment_id IS NOT NULL)
EXECUTE FUNCTION payments_adj_reversal_cap_fn();
""",
    },
]


# ---------------------------------------------------------------------------
# Migration operations
# ---------------------------------------------------------------------------


def create_triggers(apps, schema_editor):
    """Create the appropriate triggers for the active database vendor."""
    vendor = schema_editor.connection.vendor

    if vendor == "sqlite":
        for trigger_def in SQLITE_TRIGGER_DEFS:
            schema_editor.execute(trigger_def["sql"])
    elif vendor == "postgresql":
        for func_def in POSTGRESQL_FUNCTION_DEFS:
            schema_editor.execute(func_def["sql"])
        for trigger_def in POSTGRESQL_TRIGGER_DEFS:
            schema_editor.execute(trigger_def["sql"])
    else:
        raise RuntimeError(
            f"Unsupported database vendor '{vendor}' for invariant triggers. "
            f"Supported vendors: sqlite, postgresql."
        )


def drop_triggers(apps, schema_editor):
    """Drop the triggers (and functions on PostgreSQL) for the active vendor."""
    vendor = schema_editor.connection.vendor

    if vendor == "sqlite":
        for name in SQLITE_TRIGGER_NAMES:
            schema_editor.execute(f"DROP TRIGGER IF EXISTS {name};")
    elif vendor == "postgresql":
        # Drop triggers first, then functions
        for trigger_def in POSTGRESQL_TRIGGER_DEFS:
            schema_editor.execute(
                f"DROP TRIGGER IF EXISTS {trigger_def['name']} "
                f"ON {trigger_def['table']};"
            )
        for func_def in POSTGRESQL_FUNCTION_DEFS:
            schema_editor.execute(f"DROP FUNCTION IF EXISTS {func_def['name']}();")
    else:
        raise RuntimeError(
            f"Unsupported database vendor '{vendor}' for invariant triggers. "
            f"Supported vendors: sqlite, postgresql."
        )


class Migration(migrations.Migration):

    dependencies = [
        ("payments", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(create_triggers, drop_triggers),
    ]
